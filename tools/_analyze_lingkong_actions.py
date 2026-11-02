# -*- coding: utf-8 -*-
"""第三轮：把这版固件 ExecuteTask 里的动作日志逐个对号。

上一轮踩的坑：C 源码里 strcmp(action_type, "servo") 的字符串字面量在二进制里
没有引号，所以搜 '"servo"' 是错的。这里只搜"独有日志格式串"。
"""
import io
import os

DUMP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "firmware_dumps", "lingkong_flash_16MB_20261027.bin")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_lingkong_actions.txt")

with open(DUMP, "rb") as f:
    f.seek(0x20000)
    app = f.read(0x3F0000)

PROBES = [
    ("动作分发日志(逐条)",   "  [%d] Action: %s"),
    ("未知动作",             "未知动作类型: %s"),
    ("gpio 执行",            "(hold %d ms)"),
    ("pwm 执行",             "pulse_us"),
    ("servo 执行",           "  Servo -> %d"),
    ("move 执行",            "  Move: %s, duration: %d ms"),
    ("delay 执行",           "  Delay: %d ms"),
    ("emotion 执行",         "  Emotion: %s"),
    ("未知任务类型",         " 未知任务类型: %s"),
    ("TaskItem 队列日志",    "[TaskQueue] 取出任务"),
    ("TTS 直达播放",         "PlayTtsDirectly"),
    ("code_stream 解释器",   "CodeInterpreter"),
    ("mcp 通道",             '"type":"mcp"'),
    ("camera 拍照工具",      "self.camera.take_photo"),
    ("屏幕亮度工具",         "self.screen.set_brightness"),
]

log = io.StringIO()
log.write("=== 这版固件 ExecuteTask 动作对号 ===\n")
for name, s in PROBES:
    n = app.count(s.encode("utf-8"))
    log.write("%-22s %-40s %s\n" % (name, s, ("命中 %d" % n) if n else "— 没有"))

with open(OUT, "w", encoding="utf-8") as f:
    f.write(log.getvalue())
print("written:", OUT)
