# 群成员查询插件 (Group Member Viewer Plugin)

为 KiraAI 提供轻量级 QQ 群成员查询能力。**纯查询、无管理操作，Bot 无需管理员权限**，适合所有 Bot。

## 为什么需要这个插件？

大部分的框架发送给LLm信息和记忆机制，都只能让bot从短期上下文中确认群成员。如果用户希望bot比如@一个暂时没在短期上下文出现的群友，那么bot很可能做不到。

但有了本插件，聪明的bot就会使用带有的工具先查询一下有没有这个人，获取信息后，就能准确互动。

此外，甚至没有本插件，你问群里有多少人了，bot都答不上来。

## 功能特性

- 📋 **群概览** (`group_member_overview`) - 总人数、群主、管理员列表，一次调清
- 🔍 **查找成员** (`group_find_member`) - 按关键词同时匹配 QQ号 / QQ昵称 / 群名片 / 专属头衔，返回格式「群名片 | QQ昵称 | QQ号 | 身份」，清晰区分名片与昵称
- 📄 **成员详情** (`group_member_detail`) - 入群时间、最后发言、等级、头衔、禁言状态等
- 🚀 **结果缓存** - 成员列表内存缓存（默认 10 分钟），减少协议端请求

## 安装

1. 将插件文件夹复制到 `data/plugins/`（文件夹名须为 `group_member_viewer`）
2. 重启 KiraAI 或重新加载插件

## 配置说明

配置文件位置：`data/config/plugins/group_member_viewer.json`

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `cache_ttl` | 整数 | 600 | 成员列表缓存秒数，0=不缓存 |
| `max_results` | 整数 | 20 | 查找结果上限，防止消耗过多 token |
| `inject_prompt` | 布尔 | true | 是否向 LLM 注入工具使用说明 |
| `show_title` | 布尔 | true | 在查询结果中展示专属头衔（🏷️），并允许按头衔关键词查找 |

## 与 group_manager（群管理插件）共存

两个插件可同时安装，**不会冲突**：

- 本插件加载时若检测到 group_manager，会自动卸载 group_manager 自带的
  `group_get_member_list` / `group_get_member_info`，由本插件接管成员查询；
- 反向顺序（group_manager 后加载）也会由 group_manager 自行检测并卸载；
- group_manager 单独安装时一切照旧。

## 使用示例

- "群里现在多少人？管理员都有谁？" → `group_member_overview`
- "帮我找一下群里的'小明'" → `group_find_member(keyword="小明")`
- "123456 这个人什么时候进群的？" → `group_member_detail(user_id="123456")`
