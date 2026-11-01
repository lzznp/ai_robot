# core/scene_dispatcher.py
"""
场景调度器 —— 核心大脑
支持场景切换、角色识别、LLM 调用和 TTS 下发
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional

from core.llm_adapter import LLMAdapter
from core.providers.tts.dto.dto import ContentType

import re



class SceneDispatcher:
    """场景调度器"""

    def __init__(self, llm_instance, device_manager=None, redis_manager=None, connection_handler=None):
        self.connection_handler = connection_handler
        self.device_manager = device_manager
        self.redis_manager = redis_manager

        self.logger = logging.getLogger(__name__)

        # 创建 LLM 适配器
        self.llm_adapter = LLMAdapter(llm_instance)

        # 场景注册表
        self._scenes: Dict[str, Any] = {}
        self._current_scene_id: Optional[str] = None
        self._role_device_map: Dict[str, str] = {}
        self._current_device_id: Optional[str] = None

        self.logger.info("[SceneDispatcher] 初始化完成")

    def register_scene(self, scene):
        """注册场景"""
        self._scenes[scene.id] = scene
        self.logger.info(f"📦 注册场景: {scene.id} ({scene.name})")

    def get_current_scene(self):
        """获取当前场景"""
        scene_id = self._current_scene_id or "chat"
        return self._scenes.get(scene_id)

    def switch_scene(self, scene_id: str) -> bool:
        """切换场景"""
        if scene_id not in self._scenes:
            self.logger.warning(f"⚠️ 场景不存在: {scene_id}")
            return False

        self._current_scene_id = scene_id
        self.logger.info(f"🔄 切换场景: {scene_id}")
        return True

    def set_role_device_map(self, mapping: Dict[str, str]):
        """设置角色 → 设备 ID 映射"""
        self._role_device_map = mapping
        self.logger.info(f"[SceneDispatcher] 角色-设备映射: {mapping}")

    def set_current_device(self, device_id: str):
        """设置当前会话的设备 ID"""
        self._current_device_id = device_id

    def get_device_id_for_role(self, role_name: str) -> Optional[str]:
        """根据角色名获取对应的设备 ID"""
        return self._role_device_map.get(role_name)

    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        if not self._role_device_map:
            return "你是一个智能助手，回复简洁友好。"

        roles_desc = []
        for role_name in self._role_device_map.keys():
            roles_desc.append(f"- {role_name}: 一个智能助手")

        prompt = "当前场景有以下角色参与对话：\n"
        prompt += "\n".join(roles_desc)
        prompt += "\n\n请根据用户输入，以最合适的角色身份回复。回复格式：直接输出回复内容，不需要前缀角色名。"
        return prompt

    async def process(self, user_input: str, device_id: str) -> Dict[str, Any]:
        """处理用户输入"""
        self.set_current_device(device_id)

        self.logger.info(f"[SceneDispatcher] 处理用户输入: {user_input}")

        try:
            # 1. 识别目标角色
            target_role = None
            for role_name in self._role_device_map.keys():
                if role_name in user_input:
                    target_role = role_name
                    break

            if not target_role and self._role_device_map:
                target_role = list(self._role_device_map.keys())[0]

            if not target_role:
                target_role = "助手"

            # 2. 获取目标设备
            target_device = self._role_device_map.get(target_role, device_id)

            self.logger.info(f"[SceneDispatcher] 目标角色: {target_role}, 目标设备: {target_device}")

            # 3. 构建 system prompt
            system_prompt = self._build_system_prompt()

            # 4. 调用 LLM
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input}
            ]

            response = self.llm_adapter(messages)
            self.logger.info(f"[SceneDispatcher] LLM 返回: {response}")

            # 5. 生成 actions
            actions = [{
                "type": "tts",
                "text": response,
                "target": target_device,
                "role": target_role
            }]

            self.logger.info(f"[SceneDispatcher] 生成 {len(actions)} 个动作")

            return {
                "actions": actions,
                "response": response,
                "raw_results": []
            }

        except Exception as e:
            self.logger.error(f"[SceneDispatcher] 处理失败: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return {"actions": [], "response": f"处理失败: {e}", "raw_results": []}

    import re
    import asyncio

    async def dispatch_actions(self, actions: List[Dict]):
        """下发动作到设备 —— 统一走原生 TTS 路径"""
        if not self.device_manager:
            self.logger.warning("[SceneDispatcher] DeviceManager 未设置，无法下发")
            return

        for action in actions:
            target = action.get("target")
            if not target:
                continue

            if action.get("type") == "tts":
                text = action.get("text", "")
                if not text:
                    continue

                if self.connection_handler:
                    # ✅ 直接交给 TTS 模块，让它自己处理一切
                    # TTS 模块会自己发送 start、sentence_start、stop
                    # 也会自己切分文本并正确标记 FIRST/MIDDLE/LAST
                    self.connection_handler.tts.tts_one_sentence(
                        self.connection_handler,
                        ContentType.TEXT,
                        content_detail=text
                    )
                    self.logger.info(f"[SceneDispatcher] TTS 已触发: {text[:30]}...")
                else:
                    # 没有 connection_handler 时，只发一个简单的显示消息
                    await self.device_manager.send(target, {
                        "type": "tts",
                        "state": "sentence_start",
                        "text": text
                    })

            elif action.get("type") == "emotion":
                await self.device_manager.send(target, {
                    "type": "llm",
                    "emotion": action.get("emotion", "neutral")
                })

            elif action.get("type") == "action":
                await self.device_manager.send(target, {
                    "type": "action",
                    "action": action.get("action", "")
                })

            else:
                self.logger.warning(f"[SceneDispatcher] 未知动作类型: {action.get('type')}")