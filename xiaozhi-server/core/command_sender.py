# core/command_sender.py
"""
统一下发指令模块
供后台核心和 Streamlit 控制台共同使用
"""

import json
from typing import Dict, Any, Optional
from core.device_manager import DeviceManager


class CommandSender:
    """统一下发指令"""

    def __init__(self, device_manager: DeviceManager):
        self.device_manager = device_manager

    async def send_command(self, device_id: str, command_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        统一下发指令接口

        Args:
            device_id: 目标设备 ID
            command_type: 指令类型 (emotion / tts / action / servo / led / custom)
            params: 指令参数

        Returns:
            {"success": True/False, "message": "...", "data": {...}}
        """
        if not self.device_manager.is_online(device_id):
            return {"success": False, "message": f"设备 {device_id} 不在线"}

        payload = self._build_payload(command_type, params)
        if not payload:
            return {"success": False, "message": f"未知指令类型: {command_type}"}

        try:
            success = await self.device_manager.send(device_id, payload)
            return {
                "success": success,
                "message": "指令已下发" if success else "指令下发失败",
                "data": {"command": payload}
            }
        except Exception as e:
            return {"success": False, "message": f"下发异常: {str(e)}"}

    def _build_payload(self, command_type: str, params: Dict[str, Any]) -> Optional[Dict]:
        """根据指令类型构建 payload"""
        if command_type == "emotion":
            return {"type": "llm", "emotion": params.get("emotion", "neutral")}
        elif command_type == "tts":
            return {"type": "tts", "state": "sentence_start", "text": params.get("text", "")}
        elif command_type == "action":
            return {"type": "action", "action": params.get("action", "stop")}
        elif command_type == "servo":
            return {
                "type": "mcp",
                "tool": "servo_control",
                "params": {
                    "servo_id": params.get("servo_id"),
                    "angle": params.get("angle", 0)
                }
            }
        elif command_type == "led":
            return {
                "type": "mcp",
                "tool": "led_control",
                "params": {
                    "on": params.get("on", True),
                    "brightness": params.get("brightness", 100),
                    "color": params.get("color", "#FFFFFF")
                }
            }
        elif command_type == "custom":
            return params.get("payload", {})
        else:
            return None