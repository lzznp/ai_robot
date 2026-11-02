# -*- coding: utf-8 -*-
"""灯测试探针：一边抓串口，一边从后台发只打一个引脚的电平指令。

为什么先探：板上这版固件编译于 Jul 21 2026，而 gpio/pwm 引脚级执行器是
10-26 才加进源码的。所以先确认"这版认不认 gpio 动作"，再谈灯。

判据（串口）：
  · "GPIO 4 -> 1 (hold 600 ms)"   => 这版有 gpio 执行器，可以直接测灯
  · "未知动作类型: gpio"           => 有 command 通道但没有 gpio
  · 什么都没打印                   => 连 command 通道都没有（要重新编译烧写）
实物判据：对应那颗灯亮/不亮。

用法: python _led_probe.py [pin] [level] [ms]
"""
import json
import sys
import threading
import time
import urllib.request

import serial

PORT = "COM8"
API = "http://192.168.199.106:8004/api/command"
DEVICE = "58:e6:c5:58:0c:58"

PIN = int(sys.argv[1]) if len(sys.argv) > 1 else 4
LEVEL = int(sys.argv[2]) if len(sys.argv) > 2 else 1
MS = int(sys.argv[3]) if len(sys.argv) > 3 else 600
OUT = sys.argv[4] if len(sys.argv) > 4 else "_led_probe_serial.txt"
CAPTURE_SECS = float(sys.argv[5]) if len(sys.argv) > 5 else 9.0

buf = bytearray()


def capture():
    ser = serial.Serial()
    ser.port = PORT
    ser.baudrate = 115200
    ser.timeout = 0.2
    ser.dsrdtr = False
    ser.rtscts = False
    ser.open()
    ser.dtr = False
    ser.rts = False
    t0 = time.time()
    try:
        while time.time() - t0 < CAPTURE_SECS:
            chunk = ser.read(4096)
            if chunk:
                buf.extend(chunk)
    finally:
        ser.close()


th = threading.Thread(target=capture)
th.start()
time.sleep(1.5)   # 让串口先抓上

payload = {"device_id": DEVICE, "command": {"type": "command", "payload": {"actions": [
    {"type": "gpio", "pin": PIN, "level": LEVEL, "duration": MS},
]}}}
req = urllib.request.Request(API, data=json.dumps(payload).encode(),
                             headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        print("HTTP %s %s" % (resp.status, resp.read().decode("utf-8", "replace")))
except Exception as e:
    print("HTTP ERROR:", e)

th.join()
text = buf.decode("utf-8", errors="replace")
with open(OUT, "w", encoding="utf-8") as f:
    f.write("PIN=%d LEVEL=%d MS=%d\n" % (PIN, LEVEL, MS))
    f.write(text)
print("bytes=%d file=%s" % (len(buf), OUT))
