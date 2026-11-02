# -*- coding: utf-8 -*-
"""月球车 5 路灯/灯板逐一点亮测试。

要点（踩过的坑）：
  * 打开 COM8 会让板子复位（USB-Serial-JTAG 的 DTR/RTS）。所以流程必须是：
    先开串口 -> 等它重新连上后台 -> 再发指令。不能"先发指令再开串口"。
  * 一次只点一个脚，间隔 2.5 秒，这样能分辨是哪颗灯。
  * 每个脚用独立的 command 消息（固件里 gpio 带 duration 时，"回低"任务会被
    追加到队列尾部；单独发一条最干净：亮 -> 到点自动回低）。

引脚来自 boards/lingkong-s3-moc-cam-1.54tft/config.h：
  GPIO4 = 车顶左灯  GPIO5 = 车顶右灯  GPIO6 = 车底左灯
  GPIO7 = 车底右灯  GPIO8 = 车厢灯板
判据：
  * 串口出现 "GPIO n -> 1 (hold 800 ms)" => 指令真的执行了
  * 对应灯亮 => 这颗灯是"高电平直驱"的普通灯
  * 指令执行但灯不亮 => 可能是 WS2812/需数据流，或该脚没接、或灯要供电开关
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
OUT = "_lingkong_led_test.txt"

PINS = [
    (4, "LED_1 top-left"),
    (5, "LED_2 top-right"),
    (6, "LED_3 bottom-left"),
    (7, "LED_4 bottom-right"),
    (8, "LED_STRIP cabin"),
]

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


def online_ips():
    try:
        with urllib.request.urlopen(DEVICES_API, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
        return [d.get("device_id") for d in data.get("devices", [])]
    except Exception:
        return []


def do_cmd(actions):
    return post({"type": "command", "payload": {"actions": actions}})


th = threading.Thread(target=capture, daemon=True)
th.start()
print("serial opened:", PORT)

# 等板子重新连上后台（开串口会复位它）
t0 = time.time()
while time.time() - t0 < 40:
    ids = online_ips()
    if DEVICE in ids:
        break
    time.sleep(2)
print("wait %.1fs, online=%s" % (time.time() - t0, DEVICE in online_ips()))
time.sleep(1.0)

log = []
for pin, name in PINS:
    r = do_cmd([{"type": "gpio", "pin": pin, "level": 1, "duration": 800}])
    line = "TEST pin=%d %-22s success=%s msg=%s" % (
        pin, name, r.get("success"), r.get("message"))
    print(line)
    log.append(line)
    time.sleep(2.5)

# 收尾：全部拉低，别留高电平
for pin, name in PINS:
    do_cmd([{"type": "gpio", "pin": pin, "level": 0}])
print("all pins -> 0")

time.sleep(1.5)
stop.set()
th.join(timeout=3)

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(log) + "\n\n===== SERIAL =====\n")
    f.write(buf.decode("utf-8", errors="replace"))
print("wrote", OUT, "serial_bytes=%d" % len(buf))
