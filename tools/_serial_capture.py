# -*- coding: utf-8 -*-
"""被动抓串口：打开端口 -> 读 N 秒 -> 落 UTF-8 文件（不动 DTR/RTS，避免假复位）。

用法: python _serial_capture.py COM8 6 out.txt
判据：文件里出现什么，就是板上正在打印什么。
"""
import codecs
import sys
import time

import serial

port = sys.argv[1] if len(sys.argv) > 1 else "COM8"
secs = float(sys.argv[2]) if len(sys.argv) > 2 else 6.0
out = sys.argv[3] if len(sys.argv) > 3 else "_serial_capture.txt"

ser = serial.Serial()
ser.port = port
ser.baudrate = 115200
ser.timeout = 0.2
ser.dsrdtr = False
ser.rtscts = False
ser.open()
# 明确不动作复位线（ESP32 板常见 DTR->EN / RTS->IO0 自动复位电路）
ser.dtr = False
ser.rts = False

buf = bytearray()
t0 = time.time()
try:
    while time.time() - t0 < secs:
        chunk = ser.read(4096)
        if chunk:
            buf += chunk
finally:
    ser.close()

text = buf.decode("utf-8", errors="replace")
with open(out, "w", encoding="utf-8") as f:
    f.write(text)
print("port=%s bytes=%d file=%s" % (port, len(buf), out))
