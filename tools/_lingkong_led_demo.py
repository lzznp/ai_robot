# -*- coding: utf-8 -*-
"""月球车灯带"表现"演示（装进模型后看观感）。

四个阶段：
  A 纯色 @ 亮度64   ：红 / 绿 / 蓝 / 白，各 6 秒   —— 看颜色是否正、亮度够不够
  B 纯色 @ 亮度128  ：同上                      —— 看最大亮度下的观感与发热
  C 呼吸（暖白）    ：亮度 0→120→0，每步 8、200ms —— 看动态效果
  D 关灯

实现要点：
  * A/B 用 duration（固件到点自动关），每次之间留一点空隙便于分辨；
  * C 不用 duration（要连续变化），由主机侧按 200ms 节拍推亮度，
    所以最后必须单独发一条关灯。
  * 打开 COM8 会复位板子，所以先开串口、等它重连上后台，再开始。
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
OUT = "_lingkong_led_demo.txt"

PIN = 5
COUNT = 8
SOLID_SECS = 6
SOLID = [((64, 0, 0), "RED  "), ((0, 64, 0), "GREEN"), ((0, 0, 64), "BLUE "),
         ((64, 64, 64), "WHITE")]

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


def set_rgb(rgb, duration_ms=None):
    action = {"type": "ws2812", "pin": PIN, "count": COUNT, "rgb": list(rgb)}
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
print("online=%s (waited %.1fs)" % (online(), time.time() - t0))
time.sleep(1.0)

log = []
start = time.time()


def note(msg):
    line = "t=%6.1fs  %s" % (time.time() - start, msg)
    print(line)
    log.append(line)


# ---- A/B：纯色两档亮度 ----
for scale, tag in ((1, "A @64 "), (2, "B @128")):
    for rgb, name in SOLID:
        color = tuple(min(255, c * scale) for c in rgb)
        res = set_rgb(color, SOLID_SECS * 1000)
        note("%s %s rgb=%s ok=%s" % (tag, name, color, res.get("success")))
        time.sleep(SOLID_SECS + 1)

# ---- C：呼吸（暖白），主机侧推亮度 ----
WARM = (255, 170, 70)
note("C breath start (warm white)")
steps = list(range(0, 121, 8)) + list(range(120, -1, -8))
for b in steps:
    color = tuple(int(c * b / 255) for c in WARM)
    set_rgb(color)
    time.sleep(0.2)
note("C breath done")

# ---- D：关灯 ----
set_rgb((0, 0, 0))
note("D OFF")

time.sleep(1.5)
stop.set()
th.join(timeout=3)

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(log) + "\n\n===== SERIAL =====\n")
    f.write(buf.decode("utf-8", errors="replace"))
print("wrote %s serial_bytes=%d" % (OUT, len(buf)))
