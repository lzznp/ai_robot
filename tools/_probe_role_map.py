# -*- coding: utf-8 -*-
"""只验一件事：用 Doly 的 MAC 冒充一次连接，看后台
_init_scene_dispatcher() 读出来的角色-设备映射里有没有 Doly。

不驱动物理外设、不发指令；连上 -> 发 hello -> 收几秒 -> 断开。
判据：后台日志出现  [SceneDispatcher] 角色-设备映射: {... 'Doly': '58:e6:c5:11:e8:60' ...}
"""
import asyncio, json, sys
import websockets

URL = "ws://192.168.199.106:8000/xiaozhi/v1/?device-id=58:e6:c5:11:e8:60"
DEVICE_ID = "58:e6:c5:11:e8:60"


async def main():
    print("连接:", URL)
    async with websockets.connect(URL, open_timeout=10) as ws:
        await ws.send(json.dumps({
            "type": "hello",
            "device_id": DEVICE_ID,
            "version": "0.9.3",
            "features": {"mcp": True},
        }))
        print("已发 hello")
        loop = asyncio.get_event_loop()
        deadline = loop.time() + 6
        while loop.time() < deadline:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=2)
            except asyncio.TimeoutError:
                continue
            if isinstance(msg, (bytes, bytearray)):
                print("[BIN]", len(msg), "bytes")
                continue
            try:
                d = json.loads(msg)
            except Exception:
                print("[RAW]", str(msg)[:120]); continue
            print("[%s]" % d.get("type", "?"), json.dumps(d, ensure_ascii=False)[:200])
    print("已断开")

asyncio.run(main())
