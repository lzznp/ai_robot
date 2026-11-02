# -*- coding: utf-8 -*-
"""第二轮扫描：这版固件认不认 command 指令流？认哪几种 action？

依据：application.cc 里 OnIncomingJson 的所有分支都会先打日志，
这些日志字符串（英文 + 中文 UTF-8）会原样留在 app 镜像里。
有字符串 = 有那段代码；没有 = 那版还没有。

重点查：
  * "command" 通道本身        -> "🎬 [Command] 收到新指令" / "📦 Payload"
  * actions 数组的处理        -> "🎬 [Command] 收到 %d 个动作" / "未知动作类型"
  * 各动作类型                -> gpio / pwm / pulse_us / servo / move / delay / emotion / code_stream
"""
import io
import os
import re

DUMP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "firmware_dumps", "lingkong_flash_16MB_20261027.bin")
APP_OFF = 0x20000
APP_LEN = 0x3F0000
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_lingkong_cmd_scan.txt")

with open(DUMP, "rb") as f:
    f.seek(APP_OFF)
    app = f.read(APP_LEN)

log = io.StringIO()

# 关键判据：这些是源码里独一无二的日志/字段字符串
PROBES = [
    ("command 通道",        "[Command] 收到新指令".encode("utf-8")),
    ("command payload日志", "Payload".encode("ascii")),
    ("actions 计数日志",    "个动作".encode("utf-8")),
    ("未知动作类型",        "未知动作类型".encode("utf-8")),
    ("系统命令 channel",    "Unknown system command".encode("ascii")),
    ("code_stream",         "code_stream".encode("ascii")),
    ("TaskQueue 锁日志",    "ProcessNextTask".encode("ascii")),
    ("action: gpio",        b'"gpio"'),
    ("action: pwm",         b'"pwm"'),
    ("action: pulse_us",    b'pulse_us'),
    ("action: duty",        b'"duty"'),
    ("action: servo",       b'"servo"'),
    ("action: move",        b'"move"'),
    ("action: delay",       b'"delay"'),
    ("action: emotion",     b'"emotion"'),
    ("action: forward",     b'"forward"'),
    ("Action 逐条日志",     "  [%d] Action: %s".encode("ascii")),
    ("PWM 执行日志",        "pulse_us".encode("ascii")),
    ("GPIO 执行日志",       "(hold %d ms)".encode("ascii")),
    ("运动控制就绪日志",    "运动控制系统已就绪".encode("utf-8")),
]

log.write("app 镜像: 0x%x..0x%x\n\n=== 判据 ===\n" % (APP_OFF, APP_OFF + APP_LEN))
for name, needle in PROBES:
    n = app.count(needle)
    log.write("%-22s %-42s %s\n" % (name, needle.decode("utf-8", "replace"),
                                    ("命中 %d" % n) if n else "— 没有"))

# 顺带把含 "Command" 的可打印字符串列出来，便于人工判断
printable = re.compile(rb"[\x20-\x7e]{6,}")
hits = sorted({m.group().decode("ascii", "replace")
               for m in printable.finditer(app) if b"Command" in m.group()})
log.write("\n=== 含 'Command' 的字符串（%d 条）===\n" % len(hits))
for h in hits[:40]:
    log.write("    %s\n" % h[:150])

with open(OUT, "w", encoding="utf-8") as f:
    f.write(log.getvalue())
print("written:", OUT)
