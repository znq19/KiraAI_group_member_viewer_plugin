"""禁言判定回归：shut_up_timestamp 是"截止时间戳"，不是布尔值。

实机（2026-11-25 13:35）成员 10 秒前刚发过言，却显示"当前处于禁言状态"。
原因：旧代码 `shut_up_timestamp > 0` —— 禁言到期后 QQ 仍保留过去的到期时间戳。
LLOneBot 的接口测试也明确：禁言时 > now，解除后为 0 或 < now。
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from mute_status import mute_expiry, normalize_ts  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print(f"  OK   {name}")
    else:
        FAIL.append((name, detail))
        print(f"  FAIL {name}  {detail}")


def main():
    now = 1_764_000_000

    check("0 = 未禁言", mute_expiry(0, now) == 0)
    check("缺失 = 未禁言", mute_expiry(None, now) == 0)
    check("空串 = 未禁言", mute_expiry("", now) == 0)
    check("过去的到期时间 = 已解除", mute_expiry(now - 3600, now) == 0, mute_expiry(now - 3600, now))
    check("刚好现在 = 已解除", mute_expiry(now, now) == 0)
    check("未来 = 禁言中", mute_expiry(now + 600, now) == now + 600)
    check("字符串时间戳", mute_expiry(str(now + 600), now) == now + 600)
    check("毫秒时间戳归一化", mute_expiry((now + 600) * 1000, now) == now + 600)
    check("负数 = 未禁言", mute_expiry(-1, now) == 0)
    check("脏数据 = 未禁言", mute_expiry("abc", now) == 0)

    check("normalize_ts 秒级不变", normalize_ts(now) == now)
    check("normalize_ts 毫秒转秒", normalize_ts(now * 1000) == now)
    check("normalize_ts 浮点", normalize_ts(float(now) + 0.7) == now)

    # 真实时钟下的等价性
    check("真实时间：1 小时前已解除", mute_expiry(int(time.time()) - 3600) == 0)
    check("真实时间：10 分钟后仍在禁言", mute_expiry(int(time.time()) + 600) > 0)

    print("\n" + "=" * 50)
    print(f"禁言判定: {len(PASS)} 通过, {len(FAIL)} 失败")
    if FAIL:
        for n, d in FAIL:
            print(f"  FAIL {n}: {d}")
        sys.exit(1)
    print("=== 全部通过 ===")


if __name__ == "__main__":
    main()
