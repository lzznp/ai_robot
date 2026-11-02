# -*- coding: utf-8 -*-
"""MOSS 摄像头抓帧测试：不依赖 LLM，直接发 camera 动作触发 Capture()。

判据（串口）：
  [CAMERA] 抓帧开始 (op=capture)         -> 指令到了
  [CAMERA] 抓帧成功                       -> Capture() 返回 true
  mmap_buffers_[..].length = N, frame.width/height = W,H   -> 真拿到一帧（N 字节）
  [CAMERA] 抓帧失败 / VIDIOC_DQBUF failed  -> 失败

用法: python _camera_capture_test.py <device_id> <port> [repeat]
"""
import json
import sys
import threading
import time
import urllib.request

import serial

DEVICES_API = "http://192.168.199.106:8004/api/devices"
CMD_API = "http://192.168.199.106:8004/api/command"
OUT = "_camera_capture_test.txt"

DEVICE = sys.argv[1] if len(sys.argv) > 1 else "58:e6:c5:5a:2f:fc"
PORT = sys.argv[2] if len(sys.argv) > 2 else "COM4"
REPEAT = int(sys.argv[3]) if len(sys.argv) > 3 else 2

buf = bytearray()
stop = threading.Event()


def capture_serial():
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


th = threading.Thread(target=capture_serial, daemon=True)
th.start()

t0 = time.time()
while time.time() - t0 < 75:
    if online():
        break
    time.sleep(2)
print("online=%s (waited %.1fs)" % (online(), time.time() - t0))
time.sleep(1.5)

log = []
for i in range(REPEAT):
    res = post({"type": "command", "payload": {"actions": [
        {"type": "camera", "op": "capture"},
    ]}})
    line = "shot %d: ok=%s msg=%s" % (i + 1, res.get("success"), res.get("message"))
    print(line)
    log.append(line)
    time.sleep(3.0)

time.sleep(1.5)
stop.set()
th.join(timeout=3)

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(log) + "\n\n===== SERIAL =====\n")
    f.write(buf.decode("utf-8", errors="replace"))
print("wrote %s serial_bytes=%d" % (OUT, len(buf)))
