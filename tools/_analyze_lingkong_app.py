# -*- coding: utf-8 -*-
"""从月球车的整片 dump 里扒"板载固件到底动没动灯"。

不看源码、只看出厂/当时烧进去的那份二进制，回答三件事：
  1. 这份 app 的版本号 + 编译时间（确认 dump 抓的就是板上跑的那版）
  2. app 里有没有灯驱动相关的符号/字符串（led_strip / ws2812 / lamp / LEDC ...）
  3. app 里注册了哪些 MCP 工具名（self.xxx）

分区表 partitions/v2/16m.csv：ota_0 在 0x20000，大小 0x3f0000。
"""
import io
import os
import re

DUMP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "firmware_dumps", "lingkong_flash_16MB_20261027.bin")
APP_OFF = 0x20000
APP_LEN = 0x3F0000
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_lingkong_app_scan.txt")

KEYS = [
    "led_strip", "ws2812", "WS2812", "lamp", "Lamp", "LAMP",
    "LEDC", "ledc", "rgb", "RGB", "SingleLed", "CircularStrip",
    "LedStrip", "SetOutputState", "TCA6408",
]

log = io.StringIO()

with open(DUMP, "rb") as f:
    f.seek(APP_OFF)
    app = f.read(APP_LEN)

log.write("dump=%s\napp range=0x%x..0x%x  read=%d bytes\n\n"
          % (os.path.basename(DUMP), APP_OFF, APP_OFF + APP_LEN, len(app)))

# ---- 1) app description ----
magic = app.find(b"\x32\x54\xcd\xab")
if magic >= 0:
    ver = app[magic + 16: magic + 48].split(b"\x00")[0].decode("utf-8", "replace")
    proj = app[magic + 48: magic + 80].split(b"\x00")[0].decode("utf-8", "replace")
    tstr = app[magic + 80: magic + 96].split(b"\x00")[0].decode("utf-8", "replace")
    dstr = app[magic + 96: magic + 112].split(b"\x00")[0].decode("utf-8", "replace")
    log.write("=== app description ===\n")
    log.write("project   : %s\n" % proj)
    log.write("version   : %s\n" % ver)
    log.write("compile   : %s  %s\n" % (tstr, dstr))
    log.write("(对照串口日志: 2.0.5 / Jul 21 2026 09:43:47)\n\n")

# ---- 2) 关键词命中 ----
printable = re.compile(rb"[\x20-\x7e]{4,}")
strings = [m.group().decode("ascii", "replace") for m in printable.finditer(app)]

log.write("=== 灯相关关键词（在 app 里出现的字符串）===\n")
for k in KEYS:
    hits = sorted({s for s in strings if k in s})
    log.write("\n[%s] 命中 %d 条\n" % (k, len(hits)))
    for h in hits[:12]:
        log.write("    %s\n" % h[:160])

# ---- 3) MCP 工具名 ----
tools = sorted({s for s in strings if s.startswith("self.") and len(s) < 60})
log.write("\n=== self.* 字符串（%d 条）===\n" % len(tools))
for t in tools:
    log.write("    %s\n" % t)

with open(OUT, "w", encoding="utf-8") as f:
    f.write(log.getvalue())
print("written:", OUT)
