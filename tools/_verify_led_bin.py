# -*- coding: utf-8 -*-
"""编译产物自检（对任意板子通用）：确认 xiaozhi.bin 里
  ① 没有自检固件的横幅（*_SELFTEST=0 生效）
  ② 有我们新加的 ws2812 动作（日志串）
  ③ 有 command / gpio / pwm / code_stream（原有能力没被破坏）

用法: python _verify_led_bin.py [bin路径]
"""
import io
import os
import sys

BIN = (sys.argv[1] if len(sys.argv) > 1
       else r"D:\study\jiqiren\ai_robot\esp32-firmware\build_lingkong\xiaozhi.bin")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_verify_led_bin.txt")

with open(BIN, "rb") as f:
    data = f.read()

CHECKS = [
    ("自检横幅 SELF-TEST MODE（应为 0）", "SELF-TEST MODE", False),
    ("自检横幅 不启动 WiFi（应为 0）",    "不启动 WiFi / Application", False),
    ("ws2812 新动作日志（应 >0）",        "[WS2812] pin=%d count=%d rgb=", True),
    ("ws2812 建带日志（应 >0）",          "[WS2812] 新建灯带", True),
    ("ws2812 关灯日志（死代码已删，应 0）", "[WS2812] pin=%d 关灯", False),
    ("ws2812 创建失败日志（应 >0）",      "[WS2812] 创建失败", True),
    ("command 通道（应 >0）",             "[Command] 收到新指令", True),
    ("gpio 动作日志（应 >0）",            "(hold %d ms)", True),
    ("pwm 动作日志（应 >0）",             "pulse_us", True),
    ("code_stream（应 >0）",              "CodeInterpreter", True),
]

log = io.StringIO()
log.write("bin=%s\nsize=%d bytes\n\n" % (os.path.basename(BIN), len(data)))
ok = True
for name, needle, want in CHECKS:
    n = data.count(needle.encode("utf-8"))
    good = (n > 0) == want
    ok = ok and good
    log.write("%-30s %-34s 命中 %-3d %s\n"
              % (name, needle, n, "OK" if good else "!! 不符合预期"))
log.write("\n总结: %s\n" % ("全部符合预期" if ok else "有不符合项，先别烧"))

with open(OUT, "w", encoding="utf-8") as f:
    f.write(log.getvalue())
print("written:", OUT, "| all_ok=%s" % ok)
