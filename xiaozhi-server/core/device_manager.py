# core/device_manager.py
"""
设备管理器 —— 管理所有在线设备的 WebSocket 连接
替代 websocket_server.connections 字典
"""

import json
import asyncio
from typing import Dict, Optional, List, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class DeviceManager:
    """管理所有设备连接，支持注册/注销/发送/广播/查询"""

    def __init__(self):
        # device_id → websocket 连接
        self._connections: Dict[str, Any] = {}
        # device_id → ConnectionHandler 实例（用于 API 调用）
        self._handlers: Dict[str, Any] = {}
        # device_id → 设备元信息（能力、别名等）
        self._device_info: Dict[str, Dict] = {}
        self._lock = asyncio.Lock()

    async def register(self, device_id: str, websocket: Any, handler: Any = None, metadata: Optional[Dict] = None):
        """
        注册设备连接

        Args:
            device_id: 设备唯一标识（MAC 地址或自定义 ID）
            websocket: WebSocket 连接对象
            handler: ConnectionHandler 实例（用于 API 调用）
            metadata: 设备元信息（如 capabilities、alias、ip 等）
        """
        async with self._lock:
            self._connections[device_id] = websocket
            if handler:
                self._handlers[device_id] = handler
            self._device_info[device_id] = {
                "online": True,
                "last_seen": datetime.now().isoformat(),
                "registered_at": datetime.now().isoformat(),
                **(metadata or {})
            }
            logger.info(f"✅ 设备注册: {device_id}，当前在线: {len(self._connections)}")

    async def unregister(self, device_id: str):
        """注销设备连接"""
        async with self._lock:
            if device_id in self._connections:
                del self._connections[device_id]
            if device_id in self._handlers:
                del self._handlers[device_id]
            if device_id in self._device_info:
                self._device_info[device_id]["online"] = False
                self._device_info[device_id]["last_seen"] = datetime.now().isoformat()
            logger.info(f"❌ 设备离线: {device_id}，当前在线: {len(self._connections)}")

    async def send(self, device_id: str, message: dict) -> bool:
        """
        发送消息到指定设备

        Returns:
            bool: 是否发送成功
        """
        if device_id not in self._connections:
            logger.warning(f"⚠️ 设备离线，消息未发送: {device_id}")
            return False

        try:
            await self._connections[device_id].send(json.dumps(message))
            if device_id in self._device_info:
                self._device_info[device_id]["last_seen"] = datetime.now().isoformat()
            return True
        except Exception as e:
            logger.error(f"❌ 发送失败 {device_id}: {e}")
            await self.unregister(device_id)
            return False

    async def broadcast(self, message: dict, exclude: Optional[List[str]] = None):
        """广播消息到所有在线设备"""
        exclude = exclude or []
        for device_id, ws in self._connections.items():
            if device_id in exclude:
                continue
            try:
                await ws.send(json.dumps(message))
            except Exception as e:
                logger.warning(f"⚠️ 广播失败 {device_id}: {e}")

    def get_online_devices(self) -> List[str]:
        """获取所有在线设备 ID 列表"""
        return list(self._connections.keys())

    def is_online(self, device_id: str) -> bool:
        """检查设备是否在线"""
        return device_id in self._connections

    def get_device_info(self, device_id: str) -> Optional[Dict]:
        """获取设备元信息"""
        return self._device_info.get(device_id)

    def get_all_devices_info(self) -> Dict[str, Dict]:
        """获取所有设备信息（含离线）"""
        return self._device_info.copy()

    def get_connection(self, device_id: str) -> Optional[Any]:
        """获取设备的 WebSocket 连接对象"""
        return self._connections.get(device_id)

    def get_handler(self, device_id: str) -> Optional[Any]:
        """获取设备的 ConnectionHandler 实例"""
        return self._handlers.get(device_id)

    async def update_heartbeat(self, device_id: str):
        """更新设备心跳时间"""
        if device_id in self._device_info:
            self._device_info[device_id]["last_seen"] = datetime.now().isoformat()