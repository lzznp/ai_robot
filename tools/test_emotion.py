# test_emotion.py
import asyncio
import websockets
import json


async def test():
    uri = "ws://192.168.199.102:8000/xiaozhi/v1/"

    async with websockets.connect(uri) as ws:
        # 握手
        await ws.send(json.dumps({
            "type": "hello",
            "device_id": "test",
            "version": "0.9.3"
        }))
        resp = await ws.recv()
        print("握手成功:", resp)

        # 发送表情
        await ws.send(json.dumps({
            "type": "llm",
            "emotion": "happy"
        }))
        print("✅ 已发送 happy")


asyncio.run(test())