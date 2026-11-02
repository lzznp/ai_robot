# -*- coding: utf-8 -*-
"""GPIO46 上的"两灯灯组"（原属 MOSS）鉴别测试。

为什么要两种驱动都试：
  这组灯来自 MOSS，MOSS 台账写的是 FMLED4/5、4020 封装、GPIO48 —— 但那只是记录，
  实物没验过，而且 MOSS 那组当时"不亮"的原因也没定死。
  两种驱动各来一次，一次就能分辨它到底是哪种：
    A/B  WS2812 数据流（RMT，800kHz）-> 亮 = WS2812 类（要数据线）
    C    普通 GPIO 高电平 5 秒        -> 亮 = 普通灯珠（只要电平，不要数据）
    D    两种都灭                     -> 查接线/供电/极性

注意：GPIO46 在 ESP32-S3 上是 strapping 脚（ROM message），启动时别被拉低；
      运行期当输出用没问题，但别在它上面挂强下拉。
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
OUT = "_lingkong_pin46_test.txt"

PIN = 46
COUNT = 2

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


def act(*actions):
    return post({"type": "command", "payload": {"actions": list(actions)}})


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


# ---- A：WS2812 红 ----
r = act({"type": "ws2812", "pin": PIN, "count": COUNT, "rgb": [64, 0, 0], "duration": 10000})
note("A ws2812 RED  10s ok=%s" % r.get("success"))
time.sleep(11)

# ---- B：WS2812 绿 ----
r = act({"type": "ws2812", "pin": PIN, "count": COUNT, "rgb": [0, 64, 0], "duration": 10000})
note("B ws2812 GREEN 10s ok=%s" % r.get("success"))
time.sleep(11)

# ---- C：普通高电平 5 秒 ----
r = act({"type": "gpio", "pin": PIN, "level": 1, "duration": 5000})
note("C gpio HIGH   5s ok=%s" % r.get("success"))
time.sleep(6)

# ---- D：收尾，两种都关 ----
act({"type": "ws2812", "pin": PIN, "count": COUNT, "rgb": [0, 0, 0]})
act({"type": "gpio", "pin": PIN, "level": 0})
note("D OFF")

time.sleep(1.5)
stop.set()
th.join(timeout=3)

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(log) + "\n\n===== SERIAL =====\n")
    f.write(buf.decode("utf-8", errors="replace"))
print("wrote %s serial_bytes=%d" % (OUT, len(buf)))
