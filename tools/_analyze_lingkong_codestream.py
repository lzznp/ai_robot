# -*- coding: utf-8 -*-
"""第四轮：确认板上这版 code_stream 解释器认哪些 op、日志串长什么样。

code_interpreter.cc 的日志是独一无二的字面量：
  "GPIO %d -> %d for %d ms" / "PWM %d -> %d for %d ms" / "Unknown op: %s" / "Steps..."
op 名是 strcmp 用的裸字面量：gpio_write / pwm_write / delay / loop
"""
import io
import os

DUMP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "firmware_dumps", "lingkong_flash_16MB_20261027.bin")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_lingkong_codestream.txt")

with open(DUMP, "rb") as f:
    f.seek(0x20000)
    app = f.read(0x3F0000)

PROBES = [
    ("CodeInterpreter TAG",  "CodeInterpreter"),
    ("gpio_write 日志",      "GPIO %d -> %d for %d ms"),
    ("pwm_write 日志",       "PWM %d -> %d for %d ms"),
    ("Unknown op 日志",      "Unknown op: %s"),
    ("steps 非数组日志",     "steps is not an array"),
    ("Executing N steps",    "Executing %d steps"),
    ("别名字段 op",          "op"),
    ("op: gpio_write",       "gpio_write"),
    ("op: pwm_write",        "pwm_write"),
    ("gpio_config 被调用",   "gpio_config"),
    ("gpio_set_level 存在",  "gpio_set_level"),
    ("gpio_set_direction",   "gpio_set_direction"),
]

log = io.StringIO()
log.write("=== code_stream 解释器对号（app 0x20000 +0x3f0000）===\n")
for name, s in PROBES:
    n = app.count(s.encode("utf-8"))
    log.write("%-22s %-32s %s\n" % (name, s, ("命中 %d" % n) if n else "— 没有"))

with open(OUT, "w", encoding="utf-8") as f:
    f.write(log.getvalue())
print("written:", OUT)
