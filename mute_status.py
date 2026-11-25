"""禁言状态判定（纯函数，便于单测）。

OneBot 的 `shut_up_timestamp` 是**禁言截止时间戳**（秒），不是"是否禁言"的布尔值：
  · 0 / 缺失        → 没有禁言
  · 过去的时间戳     → 禁言已到期（QQ 常在字段里留上一次的到期时间）
  · 未来的时间戳     → 当前处于禁言中
  · 毫秒时间戳       → 归一化为秒再比较

LLOneBot 的接口测试也明确断言：禁言时 `shut_up_timestamp > now`，
解除后 `shut_up_timestamp` 为 0 或小于当前时间。
"""

from __future__ import annotations

import time


def normalize_ts(value) -> int:
    """把时间戳归一化为秒（兼容毫秒、字符串、None）。

    Args:
        value: 原始时间戳。

    Returns:
        秒级时间戳；解析不了返回 0。
    """
    try:
        ts = int(float(value or 0))
    except (TypeError, ValueError):
        return 0
    if ts > 10 ** 12:  # 毫秒级
        ts //= 1000
    return ts


def mute_expiry(shut_up_timestamp, now: float | None = None) -> int:
    """返回**仍然有效**的禁言截止时间戳（秒）；未禁言返回 0。

    Args:
        shut_up_timestamp: OneBot 群成员字段 `shut_up_timestamp`。
        now: 当前时间（默认 time.time()）。

    Returns:
        仍在禁言中 → 截止时间戳；否则 0。
    """
    ts = normalize_ts(shut_up_timestamp)
    if ts <= 0:
        return 0
    if ts <= (time.time() if now is None else now):
        return 0
    return ts
