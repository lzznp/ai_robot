# web_console/services/device_service.py
"""
设备服务：提供设备列表和状态信息
"""

from typing import List, Dict, Any
from core.device_manager import DeviceManager


class DeviceService:
    """设备服务 - 供 Streamlit 控制台使用"""

    def __init__(self, device_manager: DeviceManager):
        self.device_manager = device_manager

    def get_online_devices(self) -> List[Dict[str, Any]]:
        """获取所有在线设备信息"""
        devices = []
        for device_id in self.device_manager.get_online_devices():
            info = self.device_manager.get_device_info(device_id)
            devices.append({
                "device_id": device_id,
                "online": True,
                **info
            })
        return devices

    def get_all_devices(self) -> List[Dict[str, Any]]:
        """获取所有设备信息（含离线）"""
        result = []
        all_info = self.device_manager.get_all_devices_info()
        for device_id, info in all_info.items():
            result.append({
                "device_id": device_id,
                "online": info.get("online", False),
                **info
            })
        return result

    def get_device_status_text(self, device_id: str) -> str:
        """获取设备状态的文本描述"""
        info = self.device_manager.get_device_info(device_id)
        if not info:
            return "设备不存在"

        online = info.get("online", False)
        status_parts = [
            f"设备: {device_id}",
            f"状态: {'🟢 在线' if online else '🔴 离线'}",
            f"最后心跳: {info.get('last_seen', '未知')}"
        ]
        return " | ".join(status_parts)