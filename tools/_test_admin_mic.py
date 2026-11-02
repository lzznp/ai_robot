#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证脚本：冒充「管理员麦克风」指挥台，往后台上发一句**文字**，
看后台会不会走 ASR/LLM/TTS 回话。

协议取自 ai_robot\tools\esp32_simulator.py（:209-215 hello，:266-275 listen+text）。
用法：python _test_admin_mic.py [ws地址] ["要说的话"]
"""
import asyncio
import json
import sys

import websockets

DEFAULT_URL = "ws://192.168.199.107:8000/xiaozhi/v1/"
DEFAULT_TEXT = "你好，用一句话回答我就行：你能听到我说话吗"


async def main(url: str, text: str):
    full = url + ("&" if "?" in url else "?") + "device-id=admin_mic"
    print("连接:", full)
    async with websockets.connect(full, open_timeout=10) as ws:
        await ws.send(json.dumps({
            "type": "hello",
            "device_id": "admin_mic",
            "version": "0.9.3",
            "features": {"mcp": True},
        }))
        print("已发 hello")
        await asyncio.sleep(0.6)

        await ws.send(json.dumps({
            "type": "listen",
            "state": "detect",
            "mode": "auto",
            "text": text,
        }))
        print("已发言:", text)

        loop = asyncio.get_event_loop()
        deadline = loop.time() + 30
        audio_bytes = 0
        while loop.time() < deadline:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
            except asyncio.TimeoutError:
                continue
            if isinstance(msg, (bytes, bytearray)):
                audio_bytes += len(msg)
                continue
            try:
                data = json.loads(msg)
            except Exception:
                print("[RAW]", str(msg)[:200])
                continue
            t = data.get("type", "?")
            if t == "tts":
                st = data.get("state")
                txt = data.get("text", "")
                print(f"[TTS] state={st} " + (f"text={txt}" if txt else ""))
                if st == "stop":
                    break
            elif t == "stt":
                print("[STT]", data.get("text", ""))
            elif t in ("llm", "intent", "mcp"):
                print(f"[{t.upper()}]", json.dumps(data, ensure_ascii=False)[:240])
            else:
                print(f"[{t}]", json.dumps(data, ensure_ascii=False)[:200])
        print(f"--- 收到音频 {audio_bytes} 字节 ---")


if __name__ == "__main__":
    u = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    t = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_TEXT
    asyncio.run(main(u, t))
