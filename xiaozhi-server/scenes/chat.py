# scenes/chat.py
"""
闲聊场景 —— 最简单的基础场景
"""

import json
from typing import Dict, Any, List

from .base import ScenePlugin


class ChatScene(ScenePlugin):
    id = "chat"
    name = "闲聊场景"
    description = "日常对话，机器人自由发挥"
    priority = 2

    # 角色性格（借鉴自 character.py 的设计，但改为 dict 配置）
    # TODO: 后续从 config/roles.yaml 读取
    PERSONALITIES = {
        "doly": "你叫Doly，是活泼可爱的前台机器人，喜欢开玩笑，说话语气轻快，经常用'呢~'、'呀~'结尾",
        "walle": "你叫瓦力，是憨厚老实的机器人，说话慢吞吞，喜欢用'嘿嘿'开头，有点呆萌",
        "moss": "你叫MOSS，是高冷理性的总裁机器人，说话简洁精准，不废话，偶尔毒舌",
    }

    # 默认语音配置
    VOICE_MAP = {
        "doly": "zh-CN-XiaoxiaoNeural",
        "walle": "zh-CN-YunyangNeural",
        "moss": "zh-CN-YunxiNeural",
    }

    # 默认表情
    DEFAULT_EMOTION = {
        "doly": "happy",
        "walle": "neutral",
        "moss": "neutral",
    }

    async def build_prompt(
        self,
        context: Dict[str, Any],
        history: List[Dict[str, str]]
    ) -> str:
        """构建闲聊场景的 Prompt"""
        device_id = context.get("device_id", "doly")
        user_input = context.get("user_input", "")
        personality = self.PERSONALITIES.get(
            device_id,
            "你是AI机器人，请友好地回应"
        )

        # 历史记录（只保留最近 5 条）
        history_text = "\n".join([
            f"{h['role']}: {h['content']}"
            for h in history[-5:]
        ]) if history else "（没有历史记录）"

        return f"""### 角色设定
{personality}

### 对话历史
{history_text}

### 用户输入
{user_input}

### 输出要求
请用一句话回应，并决定你的表情。
输出格式（严格 JSON，不要加其他文字）：
{{"text": "你的回复内容", "emotion": "happy/sad/angry/thinking/neutral/laughing"}}
"""

    async def parse_response(self, llm_output: Dict[str, Any]) -> Dict[str, Any]:
        """解析 LLM 返回"""
        text = llm_output.get("text", "你好呀！")
        emotion = llm_output.get("emotion", "neutral")

        return {
            "actions": [
                {"type": "tts", "text": text},
                {"type": "emotion", "emotion": emotion}
            ],
            "scene_state": {},
            "response": text
        }