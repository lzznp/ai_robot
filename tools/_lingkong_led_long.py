# -*- coding: utf-8 -*-
"""长时间版灯测试：红 / 绿 / 蓝 各保持 20 秒，够人盯着看。

用法: python _lingkong_led_long.py [pin] [count] [hold_secs]
"""
import json
import sys
import threading
import time
import urllib.request

import serial

PORT = "COM8"
DEVICES_API = "http://192.168.199.106:8004/api/devices"
CMD_API = "http://192.168.199.106:8004/api/command"
DEVICE = "58:e6:c5:58:0c:58"
OUT = "_lingkong_led_long.txt"

PIN = int(sys.argv[1]) if len(sys.argv) > 1 else 5
COUNT = int(sys.argv[2]) if len(sys.argv) > 2 else 8
HOLD = float(sys.argv[3]) if len(sys.argv) > 3 else 20.0

ROUNDS = [((64, 0, 0), "RED  "), ((0, 64, 0), "GREEN"), ((0, 0, 64), "BLUE ")]

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


th = threading.Thread(target=capture, daemon=True)
th.start()

t0 = time.time()
while time.time() - t0 < 60:
    if online():
        break
    time.sleep(2)
print("online=%s (waited %.1fs)" % (online(), time.time() - t0))
time.sleep(1.0)

log = []
start = time.time()
for rgb, name in ROUNDS:
    res = post({"type": "command", "payload": {"actions": [
        {"type": "ws2812", "pin": PIN, "count": COUNT,
         "rgb": list(rgb), "duration": int(HOLD * 1000)},
    ]}})
    line = "t=%5.1fs  %s rgb=%s success=%s" % (
        time.time() - start, name, rgb, res.get("success"))
    print(line)
    log.append(line)
    time.sleep(HOLD + 1.0)

post({"type": "command", "payload": {"actions": [
    {"type": "ws2812", "pin": PIN, "count": COUNT, "rgb": [0, 0, 0]}]}})
print("OFF (all pixels cleared)")
time.sleep(2.0)
stop.set()
th.join(timeout=3)

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(log) + "\n\n===== SERIAL =====\n")
    f.write(buf.decode("utf-8", errors="replace"))
print("wrote %s serial_bytes=%d" % (OUT, len(buf)))
