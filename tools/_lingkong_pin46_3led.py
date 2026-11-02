# -*- coding: utf-8 -*-
"""GPIO46 上的 MOSS 三灯组：判定"数据到底有没有到它手上"。

判据只有一条：
  发出的颜色变 -> 那颗亮着的灯跟着变   = 数据到了，链在第 1 颗之后断了（2/3 颗坏）
  怎么发都不变（一直保持原来那个颜色）= 数据没到（脚不对 / 没接到 DI / 线断）

所以三种颜色给足时间（各 6 秒），最后来一发白色（最容易看出"变了没"）。
"""
import json
import threading
import time
import urllib.request

import serial

PORT = "COM8"
DEVICES_API = "http://192.168.199.106:8004/api/devices"
CMD_API = "http://192.168.199.106:8004/api/command"
DEVICE = "58:e6:c5:58:0c:58"
OUT = "_lingkong_pin46_3led.txt"

PIN = 46
COUNT = 3
HOLD = 6.0

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
    line = "t=%5.1fs  %s rgb=%s ok=%s" % (
        time.time() - start, name, rgb, res.get("success"))
    print(line)
    log.append(line)
    time.sleep(HOLD + 1.0)

post({"type": "command", "payload": {"actions": [
    {"type": "ws2812", "pin": PIN, "count": COUNT, "rgb": [0, 0, 0]}]}})
print("OFF")
time.sleep(1.5)
stop.set()
th.join(timeout=3)

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(log) + "\n\n===== SERIAL =====\n")
    f.write(buf.decode("utf-8", errors="replace"))
print("wrote %s serial_bytes=%d" % (OUT, len(buf)))
