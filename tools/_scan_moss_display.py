# -*- coding: utf-8 -*-
"""扫 MOSS 原厂固件：它到底怎么驱动那块屏的？

用户回忆"好像是因为用了 0 引脚"，但 doc 里查不到这条记录。
直接从原厂固件镜像里找证据：驱动 IC 名、I2C 地址、初始化日志、引脚相关字符串。
"""
import io
import os
import re

DUMP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "firmware_dumps", "moss_flash_16MB_20261031.bin")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_moss_vendor_display.txt")

with open(DUMP, "rb") as f:
    f.seek(0x20000)
    app = f.read(0x3F0000)

PROBES = [
    ("SSD1306", "SSD1306"), ("SSD1315", "SSD1315"), ("SH1106", "SH1106"),
    ("ST7789", "ST7789"), ("GC9A01", "GC9A01"),
    ("OledDisplay", "OledDisplay"), ("LcdDisplay", "LcdDisplay"),
    ("Install SSD1306 driver", "Install SSD1306 driver"),
    ("Failed to initialize display", "Failed to initialize display"),
    ("esp_lcd_new_panel_ssd1306", "esp_lcd_new_panel_ssd1306"),
    ("lvgl", "lvgl"), ("LVGL", "LVGL"),
    ("No display", "No display"), ("display_", "display"),
    ("H4/I2C 相关日志", "I2C bus"),
]

log = io.StringIO()
log.write("=== MOSS 原厂固件里的显示相关证据 ===\n")
for name, s in PROBES:
    n = app.count(s.encode("utf-8"))
    log.write("%-28s %-30s %s\n" % (name, s, ("命中 %d" % n) if n else "— 没有"))

printable = re.compile(rb"[\x20-\x7e]{6,}")
hits = set()
for m in printable.finditer(app):
    s = m.group().decode("ascii", "replace")
    low = s.lower()
    if any(k in low for k in ("ssd13", "sh110", "display", "oled", "panel_io", "spi_lcd")):
        hits.add(s)
log.write("\n=== 含 display/oled/panel 的字符串（%d 条，取前 70）===\n" % len(hits))
for h in sorted(hits)[:70]:
    log.write("    %s\n" % h[:150])

with open(OUT, "w", encoding="utf-8") as f:
    f.write(log.getvalue())
print("written:", OUT)
