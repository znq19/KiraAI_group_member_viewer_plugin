"""群成员查询插件 - Group Member Viewer Plugin

轻量级 QQ 群成员查询插件，纯查询、无任何管理操作，Bot 无需管理员权限。

功能：
- group_member_overview: 群概览（总人数、群主、管理员列表）
- group_find_member: 按关键词查找成员（同时匹配 QQ号 / QQ昵称 / 群名片）
- group_member_detail: 指定成员详情（入群时间、最后发言、等级、头衔等）

与 group_manager（群管理插件）的关系：
- 两个插件可同时安装，互不冲突。本插件加载时，若检测到 group_manager，
  会调用其 disable_member_query_tools() 卸载 group_manager 自带的
  group_get_member_list / group_get_member_info，避免 LLM 面前出现重复工具。
- 单独安装本插件即可拥有完整成员查询能力。
"""

import time
from typing import Optional

from core.plugin import BasePlugin, logger, on, Priority, register
from core.chat.message_utils import KiraMessageBatchEvent
from core.provider import LLMRequest
from core.prompt_manager import Prompt


ROLE_MAP = {"owner": "群主", "admin": "管理员", "member": "成员"}

USAGE_PROMPT = """\
## 群成员查询工具说明

你可以使用以下工具查询 QQ 群成员信息（纯查询，无需管理员权限）：

- group_member_overview: 查看群总人数、群主和管理员列表
- group_find_member: 按关键词查找群成员，会同时匹配 QQ号、QQ昵称、群名片
- group_member_detail: 查看指定成员的详情（入群时间、最后发言等）

### 重要概念
- 「群名片」是成员在本群专用的名字，「QQ昵称」是其全局昵称，两者经常不同
- 工具返回格式为「群名片 | QQ昵称 | QQ号」，引用成员时注意不要混淆
- 用户说的人名可能是名片也可能是昵称，找不到时可以换个关键词再试
- 结果中 🏷️ 标记的是成员的专属头衔，也可以直接用头衔文字作为关键词查找
"""


class GroupMemberViewerPlugin(BasePlugin):
    """群成员查询插件主类"""

    def __init__(self, ctx, cfg: dict):
        super().__init__(ctx, cfg)
        sec = cfg.get("section_main", {})
        self.cache_ttl = int(sec.get("cache_ttl", 600) or 0)
        self.max_results = max(1, int(sec.get("max_results", 20) or 20))
        self.inject_prompt_enabled = sec.get("inject_prompt", True)
        # 是否在查询结果中展示并匹配专属头衔
        self.show_title = sec.get("show_title", True)
        # {group_id: (fetched_at, members_list)}
        self._member_cache: dict[str, tuple[float, list]] = {}

    async def initialize(self):
        logger.info("[GroupMemberViewer] 群成员查询插件已加载")
        # 共存逻辑：通知 group_manager 卸载其重复的成员查询工具
        gm = self.ctx.get_plugin_inst("group_manager")
        if gm is not None:
            disable = getattr(gm, "disable_member_query_tools", None)
            if callable(disable):
                try:
                    disable(reason="group_member_viewer")
                except Exception as e:
                    logger.warning(f"[GroupMemberViewer] 通知 group_manager 卸载查询工具失败: {e}")

    async def terminate(self):
        self._member_cache.clear()
        logger.info("[GroupMemberViewer] 群成员查询插件已卸载")

    # ============ 内部辅助 ============

    def _get_qq_client(self, event: KiraMessageBatchEvent):
        """仅 QQ 平台返回 client，否则返回 None"""
        if not event.adapter or getattr(event.adapter, "platform", "") != "QQ":
            return None
        try:
            adapter = self.ctx.adapter_mgr.get_adapter(event.adapter.name)
            return adapter.get_client() if adapter else None
        except Exception as e:
            logger.error(f"[GroupMemberViewer] 获取适配器失败: {e}")
            return None

    @staticmethod
    def _not_qq_reply() -> str:
        return "❌ 当前会话不是 QQ 群聊，无法使用群成员查询"

    async def _fetch_members(self, event: KiraMessageBatchEvent, group_id: str):
        """获取群成员列表（带缓存）。返回 (members, err_msg)"""
        now = time.time()
        if self.cache_ttl > 0:
            cached = self._member_cache.get(group_id)
            if cached and now - cached[0] < self.cache_ttl:
                return cached[1], None
        client = self._get_qq_client(event)
        if not client:
            return None, self._not_qq_reply()
        try:
            result = await client.send_action("get_group_member_list", {"group_id": group_id})
        except Exception as e:
            logger.error(f"[GroupMemberViewer] 获取成员列表异常: {e}")
            return None, f"❌ 获取成员列表异常: {e}"
        if result.get("status") != "ok":
            return None, f"❌ 获取成员列表失败: {result.get('message', '未知错误')}"
        members = result.get("data") or []
        if self.cache_ttl > 0:
            self._member_cache[group_id] = (now, members)
        return members, None

    @staticmethod
    def _display(m: dict, show_title: bool = False) -> str:
        """统一成员展示格式：群名片 | QQ昵称 | QQ号（可选追加专属头衔）"""
        card = (m.get("card") or "").strip() or "(无群名片)"
        nickname = (m.get("nickname") or "").strip() or "(未知昵称)"
        user_id = m.get("user_id", "?")
        base = f"{card} | {nickname} | {user_id}"
        if show_title:
            title = (m.get("title") or "").strip()
            if title:
                base += f" | 🏷️{title}"
        return base

    # ============ Prompt 注入 ============

    @on.llm_request(priority=Priority.MEDIUM)
    async def inject_usage_prompt(self, event: KiraMessageBatchEvent, req: LLMRequest, *_):
        if not self.inject_prompt_enabled:
            return
        if not event.is_group_message():
            return
        if not event.adapter or getattr(event.adapter, "platform", "") != "QQ":
            return
        req.system_prompt.append(Prompt(
            name="group_member_viewer_usage",
            content=USAGE_PROMPT,
        ))

    # ============ 工具：群概览 ============

    @register.tool(
        name="group_member_overview",
        description="【仅QQ群】查看群成员概览：总人数、群主、管理员列表。想快速了解群构成时调用。",
        params={"type": "object", "properties": {}},
    )
    async def member_overview(self, event: KiraMessageBatchEvent) -> str:
        if not event.is_group_message():
            return "❌ 请在群聊中使用该工具"
        group_id = event.session.session_id
        members, err = await self._fetch_members(event, group_id)
        if err:
            return err

        owners = [m for m in members if m.get("role") == "owner"]
        admins = [m for m in members if m.get("role") == "admin"]
        lines = [f"📋 群成员概览：共 {len(members)} 人"]
        for m in owners:
            lines.append(f"👑 群主：{self._display(m, self.show_title)}")
        lines.append(f"🛡 管理员（{len(admins)} 人）：")
        for m in admins:
            lines.append(f"- {self._display(m, self.show_title)}")
        if not admins:
            lines.append("- （无）")
        lines.append("（格式：群名片 | QQ昵称 | QQ号；普通成员请用 group_find_member 按关键词查找）")
        return "\n".join(lines)

    # ============ 工具：查找成员 ============

    @register.tool(
        name="group_find_member",
        description="【仅QQ群】按关键词查找群成员，同时匹配 QQ号、QQ昵称、群名片。要找某个群友、确认其QQ号或身份时调用。",
        params={
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "搜索关键词：QQ号的一部分、QQ昵称或群名片的一部分"},
            },
            "required": ["keyword"],
        },
    )
    async def find_member(self, event: KiraMessageBatchEvent, keyword: str) -> str:
        if not event.is_group_message():
            return "❌ 请在群聊中使用该工具"
        keyword = (keyword or "").strip()
        if not keyword:
            return "❌ 请提供搜索关键词"
        group_id = event.session.session_id
        members, err = await self._fetch_members(event, group_id)
        if err:
            return err

        kw = keyword.lower()
        matched = []
        for m in members:
            user_id = str(m.get("user_id", ""))
            nickname = (m.get("nickname") or "").lower()
            card = (m.get("card") or "").lower()
            title = (m.get("title") or "").lower() if self.show_title else ""
            if kw in user_id or kw in nickname or kw in card or (title and kw in title):
                matched.append(m)

        if not matched:
            return (
                f"🔍 没有找到匹配「{keyword}」的成员。\n"
                "提示：对方在群里的名字可能是群名片而非QQ昵称，可以换个关键词（如名字的一部分）再试。"
            )

        total = len(matched)
        shown = matched[: self.max_results]
        lines = [f"🔍 匹配「{keyword}」的成员（共 {total} 人，格式：群名片 | QQ昵称 | QQ号 | 身份）："]
        for m in shown:
            role = ROLE_MAP.get(m.get("role", "member"), "成员")
            lines.append(f"- {self._display(m, self.show_title)} | {role}")
        if total > self.max_results:
            lines.append(f"... 仅显示前 {self.max_results} 条，请缩小关键词范围")
        return "\n".join(lines)

    # ============ 工具：成员详情 ============

    @register.tool(
        name="group_member_detail",
        description="【仅QQ群】查看指定群成员的详细信息：名片、昵称、身份、等级、头衔、入群时间、最后发言时间、是否被禁言。",
        params={
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "要查询的QQ号（可先用 group_find_member 查找）"},
            },
            "required": ["user_id"],
        },
    )
    async def member_detail(self, event: KiraMessageBatchEvent, user_id: str) -> str:
        if not event.is_group_message():
            return "❌ 请在群聊中使用该工具"
        group_id = event.session.session_id
        client = self._get_qq_client(event)
        if not client:
            return self._not_qq_reply()
        try:
            result = await client.send_action("get_group_member_info", {
                "group_id": group_id,
                "user_id": user_id,
            })
        except Exception as e:
            logger.error(f"[GroupMemberViewer] 获取成员详情异常: {e}")
            return f"❌ 获取成员详情异常: {e}"
        if result.get("status") != "ok":
            return f"❌ 获取成员详情失败: {result.get('message', '未知错误')}（该用户可能不在本群）"

        data = result.get("data") or {}
        role = ROLE_MAP.get(data.get("role", "member"), "成员")
        lines = [
            "📋 成员详情：",
            f"QQ号: {data.get('user_id', 'N/A')}",
            f"QQ昵称: {data.get('nickname', 'N/A')}",
            f"群名片: {(data.get('card') or '').strip() or '未设置'}",
            f"身份: {role}",
            f"群等级: {data.get('level', 'N/A')}",
            f"头衔: {data.get('title') or '无'}",
            f"入群时间: {self._format_time(data.get('join_time', 0))}",
            f"最后发言: {self._format_time(data.get('last_sent_time', 0))}",
        ]
        if data.get("shut_up_timestamp", 0) > 0:
            lines.append("⛔ 当前处于禁言状态")
        return "\n".join(lines)

    # ============ 辅助 ============

    @staticmethod
    def _format_time(timestamp: int) -> str:
        if not timestamp:
            return "N/A"
        try:
            from datetime import datetime
            return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError, OSError):
            return str(timestamp)
