# -*- coding: utf-8 -*-
"""扫 MOSS 原厂固件（整片 dump 的 app 分区），回答：
  1. 这是哪个版本、什么时候编的（确认 dump 抓的是真固件）
  2. 里面有没有灯带驱动（led_strip / ws2812 / lamp / LEDC 之外的线索）
  3. 有没有把 GPIO7 / GPIO48 写死在字符串里（有的板子会打日志带脚号）

分区表：MOSS 用 sdkconfig（BOARD_TYPE_MOSS_550W），app 在 ota_0 = 0x20000。
"""
import io
import os
import re

DUMP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "firmware_dumps", "moss_flash_16MB_20261027.bin")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_moss_vendor_scan.txt")

APP_OFF = 0x20000
APP_LEN = 0x3F0000

with open(DUMP, "rb") as f:
    f.seek(APP_OFF)
    app = f.read(APP_LEN)

log = io.StringIO()

magic = app.find(b"\x32\x54\xcd\xab")
if magic >= 0:
    proj = app[magic + 48: magic + 80].split(b"\x00")[0].decode("utf-8", "replace")
    ver = app[magic + 16: magic + 48].split(b"\x00")[0].decode("utf-8", "replace")
    tstr = app[magic + 80: magic + 96].split(b"\x00")[0].decode("utf-8", "replace")
    dstr = app[magic + 96: magic + 112].split(b"\x00")[0].decode("utf-8", "replace")
    log.write("=== app description ===\n")
    log.write("project: %s\nversion: %s\ncompile: %s %s\n\n" % (proj, ver, tstr, dstr))
else:
    log.write("!! 没找到 app 描述符，dump 可能不对\n\n")

PROBES = [
    ("led_strip", "led_strip"), ("ws2812/WS2812", "ws2812"),
    ("lamp/Lamp", "lamp"), ("LEDC", "LEDC"),
    ("SingleLed", "SingleLed"), ("CircularStrip", "CircularStrip"),
    ("MCP 灯工具 lamp.on", "self.lamp"), ("跑马灯? motor", "motor"),
    ("MOSS 电机日志", "Motor"), ("74HC595", "hc595"),
]
log.write("=== 关键词 ===\n")
for name, s in PROBES:
    n = app.count(s.encode("utf-8"))
    log.write("%-22s %-16s %s\n" % (name, s, ("命中 %d" % n) if n else "— 没有"))

# 把含 led/lamp/strip/ws28 的可打印串都列出来
printable = re.compile(rb"[\x20-\x7e]{5,}")
hits = set()
for m in printable.finditer(app):
    s = m.group().decode("ascii", "replace")
    low = s.lower()
    if ("led" in low or "lamp" in low or "ws28" in low or "strip" in low):
        hits.add(s)
log.write("\n=== 含 led / lamp / strip / ws28 的字符串（%d 条）===\n" % len(hits))
for h in sorted(hits)[:60]:
    log.write("    %s\n" % h[:140])

with open(OUT, "w", encoding="utf-8") as f:
    f.write(log.getvalue())
print("written:", OUT)
