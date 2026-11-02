# -*- coding: utf-8 -*-
"""Doly 电机真转验证：从后台下发 command 指令流（引脚级 gpio），听串口 + 看轮子。

不发语义（"前进"），只发引脚电平 —— 固件里只有 gpio/pwm/delay。

设计依据（main/application.cc）：
  * gpio 带 duration 时，到点自动追加一条"回低"任务到队列尾部，
    因此"A 脚高 1200ms"之后队列会继续跑下一条，A 的回落排在更后面。
  * 所以两条高电平任务会顺序执行：左轮 0~1.2s，右轮 1.2~2.4s，然后两脚都回低。
    判据清晰：先左轮转、再右轮转、然后都停。
  * `delay` 动作在本固件里实际只等 ~100ms（StartTaskTimer），不要依赖它。

用法：
  python _doly_motor_test.py            # 先检测在线，再发正转+反转两条流
  python _doly_motor_test.py check      # 只看设备在不在线
"""
import json
import sys
import time

import requests

API = "http://192.168.199.106:8004"
DEVICE = "58:e6:c5:11:e8:60"

# Doly 引脚：左 A=17 B=18；右 A=26 B=27（见 boards/doly/config.h）
LEFT_A, LEFT_B = 17, 18
RIGHT_A, RIGHT_B = 26, 27

STREAM_FORWARD = {"type": "command", "payload": {"actions": [
    {"type": "gpio", "pin": LEFT_B, "level": 0},
    {"type": "gpio", "pin": RIGHT_B, "level": 0},
    {"type": "gpio", "pin": LEFT_A, "level": 1, "duration": 1200},
    {"type": "gpio", "pin": RIGHT_A, "level": 1, "duration": 1200},
    {"type": "gpio", "pin": LEFT_A, "level": 0},
    {"type": "gpio", "pin": RIGHT_A, "level": 0},
]}}

STREAM_BACKWARD = {"type": "command", "payload": {"actions": [
    {"type": "gpio", "pin": LEFT_A, "level": 0},
    {"type": "gpio", "pin": RIGHT_A, "level": 0},
    {"type": "gpio", "pin": LEFT_B, "level": 1, "duration": 1200},
    {"type": "gpio", "pin": RIGHT_B, "level": 1, "duration": 1200},
    {"type": "gpio", "pin": LEFT_B, "level": 0},
    {"type": "gpio", "pin": RIGHT_B, "level": 0},
]}}


def devices():
    r = requests.get(API + "/api/devices", timeout=10)
    r.raise_for_status()
    return r.json().get("devices", [])


def send(cmd):
    r = requests.post(API + "/api/command",
                      json={"device_id": DEVICE, "command": cmd}, timeout=10)
    return r.status_code, r.text


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "run"
    online = devices()
    print("在线设备:", [d.get("device_id") for d in online])
    if not any(d.get("device_id") == DEVICE for d in online):
        print("DOLY_OFFLINE", DEVICE)
        return 2
    if mode == "check":
        print("DOLY_ONLINE", DEVICE)
        return 0

    print("\n[1] 正转流（17/26 高，18/27 低）")
    print(send(STREAM_FORWARD))
    time.sleep(3.5)

    print("\n[2] 反转流（18/27 高，17/26 低）")
    print(send(STREAM_BACKWARD))
    time.sleep(3.5)
    print("\n完成。串口判据：GPIO 17 -> 1 (hold 1200 ms) / GPIO 26 -> 1 (hold 1200 ms)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
