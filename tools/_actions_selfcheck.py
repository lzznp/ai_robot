# ai_robot/tools/_actions_selfcheck.py
"""
core/actions.py 自检 —— 不需要后台、不需要设备。

判据（对应 工作文档\\后台框架·一页纸_20261101.md §7 第 1 步）：
  build_command() 拼出来的信封，和台账里手写的那条字符串**逐字节一致**。

跑法：
  C:\\ProgramData\\miniconda3\\envs\\lzluck\\python.exe ai_robot\\tools\\_actions_selfcheck.py
"""

import os
import sys

SERVER_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "xiaozhi-server")
sys.path.insert(0, SERVER_DIR)

from core.actions import (  # noqa: E402
    ACTION_SPECS, build_action, build_command, build_payload, canonical_json,
    judge_hint, queue_warnings, board_hint, normalize_device_id, is_mac, supports_text,
    normalize_command_input,
)

ok = 0
fail = 0


def check(name, got, want):
    global ok, fail
    if got == want:
        ok += 1
        print(f"[OK ] {name}")
    else:
        fail += 1
        print(f"[FAIL] {name}\n   得到: {got!r}\n   期望: {want!r}")


# ---- 1. 逐字节对比（这是本步的硬判据）----
hand = '{"type":"command","payload":{"actions":[{"type":"ws2812","pin":5,"count":1,"rgb":[64,0,0]}]}}'
built = canonical_json(build_command(actions=[
    build_action("ws2812", {"pin": 5, "count": 1, "rgb": (64, 0, 0), "duration": ""})
]))
check("月球车亮红灯：信封逐字节一致", built, hand)

# ---- 2. 带 duration / 关灯 ----
check(
    "ws2812 带 duration",
    canonical_json(build_action("ws2812", {"pin": 5, "count": 1, "rgb": "64,0,0", "duration": "3000"})),
    '{"type":"ws2812","pin":5,"count":1,"rgb":[64,0,0],"duration":3000}',
)
check(
    "ws2812 关灯（全 0）",
    canonical_json(build_action("ws2812", {"pin": 7, "count": 2, "rgb": [0, 0, 0]})),
    '{"type":"ws2812","pin":7,"count":2,"rgb":[0,0,0]}',
)

# ---- 3. 每种动作都能按缺省值构造出来 ----
for kind, spec in ACTION_SPECS.items():
    defaults = {f["key"]: f.get("default") for f in spec["fields"]}
    try:
        act = build_action(kind, defaults)
        assert act["type"] == kind
        check(f"{kind} 缺省构造", True, True)
    except Exception as e:
        check(f"{kind} 缺省构造", f"异常: {e}", True)

# ---- 4. 该拦的必须拦（不静默丢字段）----
for bad_name, kind, vals in [
    ("pwm 同时给 pulse_us 和 duty", "pwm", {"pin": 32, "freq": 50, "pulse_us": 1500, "duty": 30}),
    ("颜色越界", "ws2812", {"pin": 5, "count": 1, "rgb": (300, 0, 0)}),
    ("未知动作", "rgb_led", {"pin": 5}),
    ("camera 非法 op", "camera", {"op": "snapshot"}),
    ("缺必填 pin", "ws2812", {"count": 1, "rgb": (1, 2, 3)}),
]:
    try:
        build_action(kind, vals)
        check(f"应拦截：{bad_name}", "没报错", "抛 ValueError")
    except ValueError:
        check(f"应拦截：{bad_name}", "ValueError", "ValueError")

# ---- 5. 空 payload 必须报错 ----
try:
    build_payload()
    check("空 payload 拦截", "没报错", "抛 ValueError")
except ValueError:
    check("空 payload 拦截", "ValueError", "ValueError")

# ---- 6. 判据文案 & 坑提示 ----
check(
    "ws2812 判据文案",
    judge_hint(build_action("ws2812", {"pin": 5, "count": 1, "rgb": (64, 0, 0)})),
    "[WS2812] pin=5 count=1 rgb=(64,0,0)",
)
warn = queue_warnings([
    build_action("ws2812", {"pin": 5, "count": 1, "rgb": (64, 0, 0), "duration": 1000}),
    build_action("gpio", {"pin": 17, "level": 1, "duration": 500}),
])
check("多条带 duration 会提示", any("队尾" in w for w in warn), True)
check(
    "delay 会提示不生效",
    any("100ms" in w for w in queue_warnings([build_action("delay", {"duration": 300})])),
    True,
)
check("单条无 duration 时不误报", queue_warnings([build_action("ws2812", {"pin": 5, "count": 1, "rgb": (1, 2, 3)})]), [])

# ---- 7. 板子提示 ----
check("MAC 归一（大写+短横线）", normalize_device_id("58-E6-C5-58-0C-58"), "58:e6:c5:58:0c:58")
check("MAC 校验", is_mac("58:E6:C5:5A:2F:FC"), True)
check("非 MAC 校验", is_mac("moss"), False)
check("月球车灯脚", board_hint("58:E6:C5:58:0C:58")["lamp_pins"], [5])
check("MOSS 两个灯脚", board_hint("58:e6:c5:5a:2f:fc")["lamp_pins"], [7, 48])
check("瓦力 ws2812 不支持", board_hint("1c:db:d4:4c:51:74")["supports"]["ws2812"], False)
check("Doly ws2812 未验", board_hint("58:e6:c5:11:e8:60")["supports"]["ws2812"], None)
check("未验文案", supports_text(None), "⚠️ 未验")

# ---- 7.5 步进电机 stepper（2026-11-01 新动作）----
check(
    "stepper 缺省构造",
    canonical_json(build_action("stepper", {"motor": 0, "steps": 64})),
    '{"type":"stepper","motor":0,"steps":64,"speed":60,"release":true}',
)
check(
    "stepper 负步数 + 保持力矩",
    canonical_json(build_action("stepper", {"motor": 1, "steps": -128, "speed": 120, "release": False})),
    '{"type":"stepper","motor":1,"steps":-128,"speed":120,"release":false}',
)
check("stepper 判据文案",
      judge_hint(build_action("stepper", {"motor": 0, "steps": 64})),
      "[STEPPER] motor=0 steps=64 speed=60")
for bad_name, vals in [
    ("stepper motor 超范围", {"motor": 2, "steps": 64}),
    ("stepper steps=0", {"motor": 0, "steps": 0}),
    ("stepper 步数超上限", {"motor": 0, "steps": 2000}),
    ("stepper 速度超上限", {"motor": 0, "steps": 64, "speed": 500}),
]:
    try:
        build_action("stepper", vals)
        check(f"应拦截：{bad_name}", "没报错", "抛 ValueError")
    except ValueError:
        check(f"应拦截：{bad_name}", "ValueError", "ValueError")

# ---- 8. 粘贴进页面的三种写法都要认（normalize_command_input）----
ENVELOPE = '{"type":"command","payload":{"actions":[{"type":"ws2812","pin":7,"count":1,"rgb":[64,0,0]}]}}'
for name, text in [
    ("整封信封", ENVELOPE),
    ("只有 payload", '{"actions":[{"type":"ws2812","pin":7,"count":1,"rgb":[64,0,0]}]}'),
    ("单条动作", '{"type":"ws2812","pin":7,"count":1,"rgb":[64,0,0]}'),
]:
    try:
        got = canonical_json(normalize_command_input(text))
        check(f"粘贴识别：{name}", got, ENVELOPE)
    except ValueError as e:
        check(f"粘贴识别：{name}", f"异常 {e}", ENVELOPE)

# tts / emotion 顶层字段也要认
check("粘贴识别：payload 里带 tts",
      canonical_json(normalize_command_input('{"tts":"你好"}')),
      '{"type":"command","payload":{"tts":"你好"}}')

for bad_name, bad in [
    ("坏 JSON", "{不是 json"),
    ("空字符串", "   "),
    ("看不懂的对象", '{"foo":1}'),
    ("不是对象", "[1,2,3]"),
]:
    try:
        normalize_command_input(bad)
        check(f"应拦截：{bad_name}", "没报错", "抛 ValueError")
    except ValueError:
        check(f"应拦截：{bad_name}", "ValueError", "ValueError")

print(f"\n通过 {ok} 项，失败 {fail} 项")
sys.exit(1 if fail else 0)
