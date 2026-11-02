# -*- coding: utf-8 -*-
"""月球车 3 针 WS2812 灯带点亮测试（GPIO5）。

为什么按"红/绿/蓝"三轮而不是随便一个颜色：
  WS2812 的颜色顺序有多种（GRB / RGB / BRG）。如果固件按 GRB 发、灯带其实是 RGB，
  那么"发红"会显示成绿。三色轮一遍就能一眼看出颜色顺序对不对 —— 这是"能分辨"的判据。

注意：打开 COM8 会复位板子（USB-Serial-JTAG 的 DTR/RTS），所以必须先开串口、
等它重新连上后台，再发指令。
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
OUT = "_lingkong_led_ws2812.txt"

PIN = 5
COUNT = 8          # 多给几颗没坏处：物理上只有 N 颗时，后面的数据被忽略
HOLD_MS = 3000

ROUNDS = [(32, 0, 0), (0, 32, 0), (0, 0, 32)]

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
print("serial opened:", PORT)

t0 = time.time()
while time.time() - t0 < 60:
    if online():
        break
    time.sleep(2)
print("wait %.1fs online=%s" % (time.time() - t0, online()))
time.sleep(1.5)

log = []
for (r, g, b) in ROUNDS:
    cmd = {"type": "command", "payload": {"actions": [
        {"type": "ws2812", "pin": PIN, "count": COUNT,
         "rgb": [r, g, b], "duration": HOLD_MS},
    ]}}
    res = post(cmd)
    line = "RGB(%3d,%3d,%3d) success=%s msg=%s" % (r, g, b, res.get("success"), res.get("message"))
    print(line)
    log.append(line)
    time.sleep(HOLD_MS / 1000.0 + 1.0)

# 收尾关灯
post({"type": "command", "payload": {"actions": [
    {"type": "ws2812", "pin": PIN, "count": COUNT, "rgb": [0, 0, 0]}]}})
print("all off")

time.sleep(2.0)
stop.set()
th.join(timeout=3)

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(log) + "\n\n===== SERIAL =====\n")
    f.write(buf.decode("utf-8", errors="replace"))
print("wrote %s serial_bytes=%d" % (OUT, len(buf)))
