# web_console/services/command_service.py
"""
指令服务：封装指令下发和响应处理
"""

import asyncio
from typing import Dict, Any
from core.command_sender import CommandSender


class CommandService:
    """指令服务 - 供 Streamlit 控制台使用"""

    def __init__(self, command_sender: CommandSender):
        self.command_sender = command_sender

    def send_command_sync(self, device_id: str, command_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        同步下发指令（Streamlit 中调用）
        因为 Streamlit 是同步环境，需要包装异步调用
        """
        try:
            # 获取当前事件循环或创建新循环
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果已有循环在运行，使用 run_coroutine_threadsafe
                import concurrent.futures
                future = asyncio.run_coroutine_threadsafe(
                    self.command_sender.send_command(device_id, command_type, params),
                    loop
                )
                return future.result(timeout=10)
            else:
                return loop.run_until_complete(
                    self.command_sender.send_command(device_id, command_type, params)
                )
        except RuntimeError:
            # 没有事件循环，创建一个新循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(
                    self.command_sender.send_command(device_id, command_type, params)
                )
            finally:
                loop.close()
        except Exception as e:
            return {"success": False, "message": f"执行失败: {str(e)}"}