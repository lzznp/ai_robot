# -*- coding: utf-8 -*-
"""任意板子的 WS2812 验灯脚本（按 设备ID + 引脚 发四色）。

用法: python _ws2812_test.py <device_id> <port> <pin1> [pin2] ...
  例: python _ws2812_test.py 58:e6:c5:5a:2f:fc COM4 7 48

每个引脚依次发 红/绿/蓝/白，各 5 秒，然后关灯。
判据：哪个引脚的哪一轮让实物变色 = 该脚是该灯的数据线。
"""
import json
import sys
import threading
import time
import urllib.request

import serial

DEVICES_API = "http://192.168.199.106:8004/api/devices"
CMD_API = "http://192.168.199.106:8004/api/command"
OUT = "_ws2812_test.txt"

DEVICE = sys.argv[1]
PORT = sys.argv[2]
PINS = [int(x) for x in sys.argv[3:]] or [7]
COUNT = 3
HOLD = 5.0
ROUNDS = [((64, 0, 0), "RED  "), ((0, 64, 0), "GREEN"),
          ((0, 0, 64), "BLUE "), ((64, 64, 64), "WHITE")]

buf = bytearray()
stop = threading.Event()


def capture():
    ser = serial.Serial()
    ser.port = PORT
    ser.baudrate = 115200
    ser.timeout = 0.2
    ser.dsrdtr = False
    ser.rtscts = False
    ser.open()
    while not stop.is_set():
        chunk = ser.read(4096)
        if chunk:
            buf.extend(chunk)
    ser.close()


def post(command):
    req = urllib.request.Request(
        CMD_API,
        data=json.dumps({"device_id": DEVICE, "command": command}).encode(),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except Exception as e:
        return {"success": False, "message": str(e)}


def online():
    try:
        with urllib.request.urlopen(DEVICES_API, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
        return DEVICE in [d.get("device_id") for d in data.get("devices", [])]
    except Exception:
        return False


def ws(pin, rgb, duration_ms=None):
    action = {"type": "ws2812", "pin": pin, "count": COUNT, "rgb": list(rgb)}
    if duration_ms is not None:
        action["duration"] = duration_ms
    return post({"type": "command", "payload": {"actions": [action]}})


th = threading.Thread(target=capture, daemon=True)
th.start()

t0 = time.time()
while time.time() - t0 < 60:
    if online():
        break
    time.sleep(2)
print("device=%s online=%s (waited %.1fs)" % (DEVICE, online(), time.time() - t0))
time.sleep(1.0)

log = []
start = time.time()
for pin in PINS:
    for rgb, name in ROUNDS:
        res = ws(pin, rgb, int(HOLD * 1000))
        line = "t=%5.1fs  pin=%-2d %s rgb=%s ok=%s" % (
            time.time() - start, pin, name, rgb, res.get("success"))
        print(line)
        log.append(line)
        time.sleep(HOLD + 0.8)
    ws(pin, (0, 0, 0))
    time.sleep(0.5)

print("ALL OFF")
time.sleep(1.5)
stop.set()
th.join(timeout=3)

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(log) + "\n\n===== SERIAL =====\n")
    f.write(buf.decode("utf-8", errors="replace"))
print("wrote %s serial_bytes=%d" % (OUT, len(buf)))
