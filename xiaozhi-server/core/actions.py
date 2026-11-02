# core/actions.py
"""
固件动作词汇表 —— 后台的**唯一真相源**。

对照文档：`工作文档\\后台框架·一页纸_20261101.md` §4（字段与日志全部核对过
`esp32-firmware/main/application.cc` 的 `ExecuteCommand()` / `ExecuteTask()`）。

这个模块只做纯事，**不 import streamlit、不 import 后台进程里的任何对象**：
  1. ACTION_SPECS  —— 每个动作的字段规格 + 串口判据文案（页面靠它生成表单）
  2. build_action() / build_payload() / build_command() —— 统一构造信封
  3. judge_hint() / queue_warnings() —— 判据提示 + “多条一起发”的坑
  4. KNOWN_BOARDS / board_hint() —— 已知板子的灯脚与固件能力（来源：硬件台账）

**不要往这里加语义**（亮红灯 / 呼吸 / 前进）。语义属于能力库（device_capabilities），
固件和这份词汇表都只认芯片级 / 引脚级动作 —— 这是 2026-10-31 已拍板的路线。

信封（不可变）：
    {"type": "command", "payload": {"tts"?, "emotion"?, "actions": [...]}}
后台的 /api/command 是**原样转发**，不包装 —— 所以谁发谁用 build_command() 包。
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Sequence

COMMAND_TYPE = "command"

# ============================================================================
# 一、动作规格
#   kind: int     必填整数
#         int?    可选整数（留空 = 不下发这个字段）
#         rgb     三元颜色，输出 [r, g, b]
#         text    自由文本
#         choice  枚举（choices 里选）
# ============================================================================

ACTION_SPECS: Dict[str, Dict[str, Any]] = {
    "ws2812": {
        "label": "ws2812 · 灯带（芯片级，gpio/pwm 点不亮它）",
        "fields": [
            {"key": "pin", "label": "数据脚 pin", "kind": "int", "default": 5},
            {"key": "count", "label": "灯珠数 count（固件缺省 1）", "kind": "int", "default": 1},
            {"key": "rgb", "label": "颜色 R,G,B（0-255；全 0 = 关灯）", "kind": "rgb",
             "default": (64, 0, 0)},
            {"key": "duration", "label": "保持 duration(ms)，留空 = 一直亮", "kind": "int?",
             "default": None},
        ],
        "judge": "[WS2812] pin={pin} count={count} rgb=({r},{g},{b})",
        "notes": [
            "实物必须变色才算成；带 duration 时到点会自动 rgb=(0,0,0)。",
            "count 只是“发几颗的数据”，物理上少几颗不会报错。",
        ],
    },
    "gpio": {
        "label": "gpio · 引脚电平（到点自动回低）",
        "fields": [
            {"key": "pin", "label": "引脚 pin", "kind": "int", "default": 17},
            {"key": "level", "label": "电平 level（1 = 高，0 = 低）", "kind": "int", "default": 1},
            {"key": "duration", "label": "保持 duration(ms)，留空 = 一直保持", "kind": "int?",
             "default": None},
        ],
        "judge": "GPIO {pin} -> {level} (hold {duration} ms)",
        "notes": ["固件会先把引脚配成输出（老 code_stream 的坑在这条动作里没有）。"],
    },
    "pwm": {
        "label": "pwm · 引脚级 PWM（舵机用 pulse_us，调速用 duty）",
        "fields": [
            {"key": "pin", "label": "引脚 pin", "kind": "int", "default": 32},
            {"key": "freq", "label": "频率 freq(Hz)（舵机用 50）", "kind": "int", "default": 50},
            {"key": "pulse_us", "label": "脉宽 pulse_us（500~2500，舵机用）", "kind": "int?",
             "default": None},
            {"key": "duty", "label": "占空比 duty(%)（调速用，与 pulse_us 二选一）", "kind": "int?",
             "default": None},
            {"key": "duration", "label": "保持 duration(ms)，留空 = 不收手", "kind": "int?",
             "default": None},
        ],
        "judge": "[PWM] pin={pin} freq={freq} pulse_us=…（或 duty=…）bits=… duty=…",
        "notes": [
            "pulse_us 与 duty 只能给一个；两个都给固件会优先 pulse_us，本模块直接报错拦下。",
            "带 duration 时到点会发一条 duty=0 的收手指令（舵机松劲 / 电机停）。",
        ],
    },
    "camera": {
        "label": "camera · 摄像头（支持相机、抓帧）",
        "fields": [
            {"key": "op", "label": "操作 op", "kind": "choice", "choices": ["capture", "explain"],
             "default": "capture"},
        ],
        "judge": "[CAMERA] 抓帧开始 (op={op}) → [CAMERA] 抓帧成功",
        "notes": [
            "没有摄像头的板会打「[CAMERA] 这块板没有摄像头」（例如月球车，需重编才有）。",
            "op=explain 需要后台填好 VLLM 的 api_key，现在还是占位符，会失败。",
        ],
    },
    "stepper": {
        "label": "stepper · 步进电机（芯片级，走 N 步）",
        "fields": [
            {"key": "motor", "label": "电机编号 motor（0 = 第 1 路，1 = 第 2 路）", "kind": "int",
             "default": 0},
            {"key": "steps", "label": "步数（带符号：正 = CW，负 = CCW）", "kind": "int_sign",
             "default": 64},
            {"key": "speed", "label": "速度（步/秒）", "kind": "int?", "default": 60},
            {"key": "release", "label": "走完断电松劲（关掉 = 保持力矩）", "kind": "bool",
             "default": True},
        ],
        "judge": "[STEPPER] motor={motor} steps={steps} speed={speed}",
        "notes": [
            "**开环**：没有编码器/限位，只有上电以来的步数计数，复位就归零 ⇒ 别把“走 N 步”当“转到某个角度”。",
            "标定（MOSS，2026-11-01）：512 步 ≈ **30°** ⇒ 一圈 ≈ 6144 步（1° ≈ 17 步）。固件上限 ±1024 步 ≈ ±60°。",
            "剧场够用的幅度是 64~256 步（≈4°~15°），不必大角度；速度别超 200 步/秒（更快可能丢步，未验）。",
            "走完缺省断电松劲；MOSS 的垂直轴断电**不会**回落（机构自锁，实测），所以默认不用保持力矩。",
        ],
    },
    "delay": {
        "label": "delay · 延时 ⚠️（duration 不生效，见备注）",
        "fields": [
            {"key": "duration", "label": "duration(ms)", "kind": "int", "default": 300},
        ],
        "judge": "Delay: {duration} ms",
        "notes": [
            "⚠️ 固件的 delay 用 StartTaskTimer()，固定只等 100ms，传 300 也不会等 300。",
            "要真间隔：用上一条动作的 duration，或后台按时间连发。",
        ],
    },
    "emotion": {
        "label": "emotion · 表情（屏上）",
        "fields": [
            {"key": "emotion", "label": "表情 emotion", "kind": "text", "default": "happy"},
        ],
        "judge": "  Emotion: {emotion}",
        "notes": ["需要这块板有屏（MOSS 外挂 SSD1306 / 月球车 ST7789 / 瓦力 128×32）。"],
    },
    "tts": {
        "label": "tts · 直接播报 ⚠️（只会打日志，不出声）",
        "fields": [
            {"key": "text", "label": "文本 text", "kind": "text", "default": "你好"},
        ],
        "judge": "🔊 [PlayTtsDirectly] 播放: {text}",
        "notes": [
            "⚠️ PlayTtsDirectly() 是占位实现：只打日志、不合成音频、不出声。",
            "所以这条动作**不能**用来判“设备会说话”。要出声走后台 TTS 音频流。",
            "带这条动作会等音频空闲（实际很快），不会把队列卡死。",
        ],
    },
}

ACTION_ORDER: List[str] = list(ACTION_SPECS)


# ============================================================================
# 二、构造
# ============================================================================

def _is_blank(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, str) and not v.strip():
        return True
    return False


def _coerce_int(label: str, raw: Any) -> int:
    if isinstance(raw, bool):
        return int(raw)
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        if raw != int(raw):
            raise ValueError(f"「{label}」要整数，给的是 {raw}")
        return int(raw)
    s = str(raw).strip()
    try:
        return int(float(s)) if "." in s else int(s)
    except ValueError:
        raise ValueError(f"「{label}」要整数，给的是 {raw!r}")


def _coerce_rgb(raw: Any) -> tuple:
    """接受 (r,g,b) / [r,g,b] / "64,0,0"；越界直接报错，不静默截断。"""
    if isinstance(raw, str):
        parts = [p for p in re.split(r"[,\s]+", raw.strip()) if p]
        if len(parts) != 3:
            raise ValueError(f'颜色要写成 "R,G,B"，给的是 {raw!r}')
        vals = [_coerce_int("颜色", p) for p in parts]
    elif isinstance(raw, (list, tuple)):
        if len(raw) < 3:
            raise ValueError(f"颜色要三个数，给的是 {raw!r}")
        vals = [_coerce_int("颜色", p) for p in raw[:3]]
    else:
        raise ValueError(f"颜色格式不认识: {raw!r}")
    for v in vals:
        if not 0 <= v <= 255:
            raise ValueError(f"颜色分量必须在 0~255，给的是 {v}")
    return tuple(vals)


def build_action(kind: str, values: Dict[str, Any]) -> Dict[str, Any]:
    """按词汇表构造一条动作。返回可以原样放进 payload['actions'] 的 dict。

    校验是**严格**的：字段不对就抛 ValueError，不静默丢弃（静默丢弃会变成假成功）。
    """
    if kind not in ACTION_SPECS:
        raise ValueError(f"未知动作类型: {kind}（固件会打「未知动作类型: {kind}」）")

    spec = ACTION_SPECS[kind]
    action: Dict[str, Any] = {"type": kind}

    for f in spec["fields"]:
        key = f["key"]
        kind_ = f["kind"]

        if kind_ == "int?":
            # 可选字段：没给 / 留空 → 不下发这个字段
            raw = values.get(key, f.get("default"))
            if _is_blank(raw):
                continue
            action[key] = _coerce_int(f["label"], raw)
            continue

        if kind_ == "bool":
            # 布尔字段：没给就用规格里的默认值（True/False 没有“留空”这回事）
            raw = values.get(key, f.get("default", False))
            if isinstance(raw, bool):
                action[key] = raw
            else:
                s = str(raw).strip().lower()
                if s in ("1", "true", "yes", "on"):
                    action[key] = True
                elif s in ("0", "false", "no", "off"):
                    action[key] = False
                else:
                    raise ValueError(f"「{f['label']}」要 true/false，给的是 {raw!r}")
            continue

        # 必填字段：必须**显式**给。不给默认值兜底 —— 悄悄用默认 pin 会驱动错的引脚，
        # 这类"看起来发成功了"的假成功比报错昂贵得多。
        raw = values.get(key)
        if _is_blank(raw):
            raise ValueError(f"缺少必填字段：{f['label']}")

        if kind_ == "rgb":
            action["rgb"] = list(_coerce_rgb(raw))
        elif kind_ == "int":
            action[key] = _coerce_int(f["label"], raw)
        elif kind_ == "int_sign":
            # 允许负数（步进电机的 steps：正 = CW，负 = CCW）
            action[key] = _coerce_int(f["label"], raw)
        elif kind_ == "choice":
            val = str(raw).strip()
            if val not in f.get("choices", []):
                raise ValueError(f"「{f['label']}」只能是 {f.get('choices')}，给的是 {val!r}")
            action[key] = val
        else:  # text
            action[key] = str(raw).strip()

    if kind == "pwm" and "pulse_us" in action and "duty" in action:
        raise ValueError("pwm 的 pulse_us 与 duty 只能给一个（两个都给固件会优先 pulse_us）")

    if kind == "stepper":
        if action.get("motor") not in (0, 1):
            raise ValueError("stepper 的 motor 只能是 0 或 1")
        if action.get("steps", 0) == 0:
            raise ValueError("stepper 的 steps 不能是 0")
        if abs(action["steps"]) > 1024:
            raise ValueError("stepper 的 steps 上限 ±1024（防撞机械限位）")
        if action.get("speed") is not None and not 1 <= action["speed"] <= 400:
            raise ValueError("stepper 的 speed 上限 400 步/秒（太快会丢步）")

    return action


def build_payload(
    actions: Optional[Sequence[Dict[str, Any]]] = None,
    tts: Optional[str] = None,
    emotion: Optional[str] = None,
) -> Dict[str, Any]:
    """payload = tts? + emotion? + actions? ；三者全空视为错误。"""
    payload: Dict[str, Any] = {}
    if not _is_blank(tts):
        payload["tts"] = str(tts).strip()
    if not _is_blank(emotion):
        payload["emotion"] = str(emotion).strip()
    if actions:
        payload["actions"] = [dict(a) for a in actions]
    if not payload:
        raise ValueError("payload 是空的：至少要有 tts / emotion / 一条 action")
    return payload


def build_command(
    actions: Optional[Sequence[Dict[str, Any]]] = None,
    tts: Optional[str] = None,
    emotion: Optional[str] = None,
) -> Dict[str, Any]:
    """构造可以直接塞给 POST /api/command 的 command 字段（含 type 信封）。"""
    return {"type": COMMAND_TYPE, "payload": build_payload(actions=actions, tts=tts, emotion=emotion)}


def canonical_json(obj: Any) -> str:
    """紧凑、稳定、中文不转义。页面展示和“逐字节对比”都用它。"""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def normalize_command_input(raw: Any) -> Dict[str, Any]:
    """把用户粘进来的 JSON 统一成 `/api/command` 的 command 信封。

    认三种写法（都允许是 JSON 字符串或 dict）：
      1. 整封信封   {"type":"command","payload":{...}}
      2. 只要 payload {"actions":[...]} / {"tts":"..."} / {"emotion":"happy"}
      3. 单条动作   {"type":"ws2812","pin":7,"count":1,"rgb":[64,0,0]}

    返回 {"type":"command","payload":{...}}；写法不对就抛 ValueError（带清楚原因）。
    这样页面上“复制粘贴 → 执行”不会因为少包一层而白跑一次。
    """
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            raise ValueError("指令是空的")
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON 解析失败：{e}")
    if not isinstance(raw, dict):
        raise ValueError("指令必须是一个 JSON 对象")

    # 1. 已经是信封
    if raw.get("type") == COMMAND_TYPE and isinstance(raw.get("payload"), dict):
        return {"type": COMMAND_TYPE, "payload": raw["payload"]}

    # 2. 是 payload
    if "actions" in raw or "tts" in raw or "emotion" in raw:
        payload = dict(raw)
        if "actions" in payload and not isinstance(payload["actions"], list):
            raise ValueError("payload.actions 必须是数组")
        return {"type": COMMAND_TYPE, "payload": payload}

    # 3. 是单条动作（必须有 type）
    if "type" in raw:
        return {"type": COMMAND_TYPE, "payload": {"actions": [dict(raw)]}}

    raise ValueError('看不懂这段指令：既没有 "type":"command" 信封，也没有 actions/tts/emotion，也不是单条动作')


# ============================================================================
# 三、判据与坑
# ============================================================================

def judge_hint(action: Dict[str, Any]) -> str:
    """这条动作在串口上该出现什么。页面直接显示给人看。"""
    kind = action.get("type")
    spec = ACTION_SPECS.get(kind)
    if not spec:
        return f"⚠️ 未知动作类型 {kind!r}：串口会出现「未知动作类型: {kind}」"

    fmt: Dict[str, Any] = {}
    for f in spec["fields"]:
        fmt[f["key"]] = action.get(f["key"], "")
    rgb = action.get("rgb") or [0, 0, 0]
    fmt.update({"r": rgb[0], "g": rgb[1], "b": rgb[2]})
    try:
        return spec["judge"].format(**fmt)
    except (KeyError, IndexError, ValueError):
        return spec["judge"]


def queue_warnings(actions: Sequence[Dict[str, Any]]) -> List[str]:
    """把“已发生的坑”变成发送前的提示。返回空列表 = 没发现已知问题。"""
    warns: List[str] = []
    kinds = [a.get("type") for a in actions]

    unknown = [k for k in kinds if k not in ACTION_SPECS]
    for k in unknown:
        warns.append(f"动作类型 {k!r} 不在词汇表里：串口会出现「未知动作类型: {k}」")

    timed = [a for a in actions if a.get("duration")]
    if len(timed) > 1:
        warns.append(
            f"有 {len(timed)} 条带 duration 的动作：固件把“收尾”任务追加到**队尾**，"
            "实际顺序会乱。一次只发一条带 duration 的，其余分开发。"
        )

    if "delay" in kinds:
        warns.append("delay 的 duration 不生效（固件固定等 100ms）——要间隔请用上一条动作的 duration。")

    if "tts" in kinds:
        warns.append("tts 动作只打日志、不出声（PlayTtsDirectly 是占位实现），不能当“会说话”的判据。")

    if not warns and not actions:
        warns.append("队列是空的。")
    return warns


# ============================================================================
# 四、已知板子（来源：三份硬件台账 + 各板 config.h；未测的一律 None，不许猜）
# ============================================================================
#   supports 取值：True = 实测支持 / False = 确定不支持 / None = 未验
#
#   这里是**硬件速查的共同底座**：页面只负责把它渲染出来，不另存一份到数据库。
#   理由：硬件事实必须和固件 config.h 保持一致，放代码里才能一起 review；
#   放 DB 会变成第二个真相源（历史教训：0x3C 到底是屏还是摄像头，误判过两次）。
#   改硬件后请同时更新 "verified_at" 和 "source"。

KNOWN_BOARDS: Dict[str, Dict[str, Any]] = {
    "58:e6:c5:5a:2f:fc": {
        "alias": "MOSS 550W",
        "mcu": "ESP32-S3-WROOM-1-N16R8（16MB Flash / 8MB PSRAM）",
        "serial_port": "COM4（USB-Serial-JTAG）",
        "lamp_pins": [7, 48],
        "supports": {"ws2812": True, "gpio": True, "pwm": True, "camera": True,
                     "delay": True, "emotion": True, "tts": True, "stepper": True},
        "hardware": [
            ["灯组 1", "GPIO7（排针 H5，+5V/GPIO7/GND）｜原 3 颗 2020；需 FMH1.2 ↔ H5.2 三线对接"],
            ["灯组 2", "GPIO48（排针 H6，+5V/GPIO48/GND）｜原 2 颗 4020；需 FMH2.2 ↔ H6.2"],
            ["屏", "外挂 SSD1306 128×64，I2C port0，SDA=GPIO2 / SCL=GPIO1，地址 0x3C"],
            ["摄像头", "OV2640 @ SCCB 0x30（DVP 8 位，XCLK=21 PCLK=15 VSYNC=38 HREF=39 PWDN=47，D0-D7=42/45/46/41/16/18/17/40），RST 焊在模块 EN 上不可控"],
            ["麦克风", "PDM：CLK=GPIO12（H2）/ DATA=GPIO13（H3）"],
            ["音频输出", "NS4168 I2S：BCLK=10 / LRCK=9 / DOUT=11"],
            ["步进电机 ×2", "74HC595（SHCP=3 / STCP=4 / DS=5）+ ULN2003；24BYJ48 四相八拍。"
                          "2026-11-01 起有 `stepper` 动作（走 N 步）；**开环无编码器/限位**，"
                          "走完缺省断电松劲。595 低半字节=电机1，高半字节=电机2"],
            ["电机映射（2026-11-01 实测）", "motor=0 → **垂直轴**（+步数 = 向后仰，-步数 = 向前俯）；"
                                       "motor=1 → **水平轴**（+步数 = 向左，-步数 = 向右）"],
            ["ADC", "电池 GPIO8 / USB 插入检测 GPIO6（都用分压电阻）"],
            ["BOOT 键", "GPIO0（下载/配网；自检固件下单击换项、长按执行）"],
        ],
        "verified_at": "2026-10-31（灯两组四色、屏、摄像头抓帧 640×480 都有实测记录）",
        "notes": [
            "灯：GPIO7 今天（11-01）实测会亮/会灭；**GPIO48 这次发绿没亮，接线待查**，别当它坏了。",
            "摄像头要插 U13 那个 20 针座，别插 FPC1（FPC1 不接 MCU）。",
            "固件里 GetLed() 已改 NoLed，所以 GPIO7/48 不会再被 PWM 抢走。",
            "步进（2026-11-01 实测）：motor=0 = **垂直轴**（+ 向后仰 / − 向前俯）；"
            "motor=1 = **水平轴**（+ 向左 / − 向右）。开环无回零，位置不可靠。",
        ],
    },
    "58:e6:c5:58:0c:58": {
        "alias": "月球车",
        "mcu": "ESP32-S3（16MB Flash / 8MB PSRAM，USB-Serial-JTAG）",
        "serial_port": "COM8",
        "lamp_pins": [5],
        "supports": {"ws2812": True, "gpio": True, "pwm": True, "camera": False,
                     "delay": True, "emotion": True, "tts": True, "stepper": False},
        "hardware": [
            ["灯带", "GPIO5（板上灯座丝印 G/V/S，DIN 接 S）｜GRB 颜色顺序正确"],
            ["电机", "GPIO1/2（电机1）、GPIO12/13（电机2）"],
            ["舵机", "GPIO3（与摄像头 D7 撞脚，开摄像头会抢）"],
            ["屏", "ST7789 SPI3：SCL=45 / DC=47 / SDA=48"],
            ["音频", "ES8311，I2C port1 SCL=14 / SDA=21；I2S WS=38 DOUT=39 DIN=40 BCLK=41 MCLK=42"],
            ["电池", "ADC GPIO10 / 充电检测 GPIO11"],
        ],
        "verified_at": "2026-10-27（灯带四色 + 亮度两档 + 呼吸，装车后复测通过）",
        "notes": [
            "**没有 camera 动作**（固件未初始化摄像头，要重编才有）。",
            "⚠️ 打开 COM8 串口会复位板子：先开串口 → 等它重连后台 → 再发指令。",
            "目前实物只接了 1 颗灯珠，`count` 给大了也不报错（多的被忽略）。",
            "config.h 里的 LED_1..4 / LED_STRIP 是占位符（与摄像头脚重叠），**不是实物依据**。",
        ],
    },
    "58:e6:c5:11:e8:60": {
        "alias": "Doly",
        "mcu": "ESP32-P4（32MB Flash）",
        "serial_port": "COM6",
        "lamp_pins": None,
        "supports": {"ws2812": None, "gpio": None, "pwm": None, "camera": None,
                     "delay": True, "emotion": None, "tts": None, "stepper": False},
        "hardware": [
            ["电机", "GPIO17/18（A）、GPIO26/27（B）"],
            ["舵机", "GPIO32 / GPIO11"],
            ["灯", "未知（没有台账，别照抄别的板子）"],
        ],
        "verified_at": "未逐项实测（只有固件动作清单）",
        "notes": [
            "MAC 已在角色映射里，但 devices 表原来没有它（11-01 起可登记）。",
            "电机真转**未验**。",
        ],
    },
    "1c:db:d4:4c:51:74": {
        "alias": "瓦力",
        "mcu": "ESP32-S3-WROOM-1-N16R8",
        "serial_port": "COM5",
        "lamp_pins": None,
        "supports": {"ws2812": False, "gpio": None, "pwm": None, "camera": False,
                     "delay": None, "emotion": True, "tts": None, "stepper": False},
        "hardware": [
            ["板型", "qebabe-xiaoche（派生自 bread-compact-wifi），卖家板与作者 config.h 引脚不一致"],
            ["电机", "GPIO13/14（A）、GPIO17/18（B）—— 实测"],
            ["舵机", "左手 GPIO11 / 右手 GPIO12；第三个挂起"],
            ["屏", "SSD1306 128×32，SDA=GPIO41 / SCL=GPIO42（扫到 0x3C）"],
            ["按键", "BOOT=0 / 触摸=47 / VOL+=40 / VOL−=39"],
            ["灯", "无（30 个脚静态高电平全扫过，没有灯反应）"],
        ],
        "verified_at": "2026-10-22（自写 wali 自检固件 8 项通过）",
        "notes": [
            "板上是 7-12 的原厂固件：`command` 通道是我们后来加的，大概率没有。",
            "判固件版本：串口打 `Unknown message type: command` = 连通道都没有；"
            "打 `未知动作类型: …` = 有通道但没这个动作。",
        ],
    },
    "a0:f2:62:e3:e0:d0": {
        "alias": "双目屏",
        "mcu": "未记录",
        "serial_port": "未记录",
        "lamp_pins": None,
        "supports": {k: None for k in ACTION_SPECS},
        "hardware": [],
        "verified_at": "无台账",
        "notes": ["老固件，没有项目台账；目前不作为测试对象。"],
    },
}

_MAC_RE = re.compile(r"^[0-9a-f]{2}(:[0-9a-f]{2}){5}$")


def normalize_device_id(raw: Any) -> str:
    """MAC 归一：去空格、转小写、- 和 . 统一成 :。后台的 device_id 就是小写冒号形式。"""
    s = str(raw or "").strip().lower().replace("-", ":").replace(".", ":")
    return s


def is_mac(raw: Any) -> bool:
    return bool(_MAC_RE.match(normalize_device_id(raw)))


def board_hint(device_id: Any) -> Optional[Dict[str, Any]]:
    return KNOWN_BOARDS.get(normalize_device_id(device_id))


def supports_text(flag: Optional[bool]) -> str:
    if flag is True:
        return "✅ 实测支持"
    if flag is False:
        return "❌ 不支持"
    return "⚠️ 未验"
