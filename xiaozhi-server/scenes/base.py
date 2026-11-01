# scenes/base.py
"""
场景插件基类 —— 所有场景必须实现这个接口
"""

from typing import Dict, Any, List, Optional


class ScenePlugin:
    """场景插件基类"""

    # === 元数据（子类必须覆盖） ===
    id: str = "base_scene"
    name: str = "基础场景"
    description: str = "场景描述"
    priority: int = 2  # 0-10，越大优先级越高
    can_be_interrupted: bool = True

    # === 生命周期方法（子类可选覆盖） ===
    async def on_enter(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        进入场景时调用
        Returns: 场景状态（存入 Redis）
        """
        return {"scene_state": {}}

    async def on_exit(self, context: Dict[str, Any]):
        """退出场景时调用"""
        pass

    async def on_pause(self, context: Dict[str, Any]):
        """被高优先级场景打断时调用"""
        pass

    async def on_resume(self, context: Dict[str, Any]):
        """被恢复时调用"""
        pass

    # === 核心方法（子类必须实现） ===
    async def build_prompt(
        self,
        context: Dict[str, Any],
        history: List[Dict[str, str]]
    ) -> str:
        """
        构建 Prompt

        Args:
            context: 上下文（user_input, device_id, scene_state 等）
            history: 对话历史 [{"role": "user"/"assistant", "content": "..."}]

        Returns:
            完整的 Prompt 字符串
        """
        raise NotImplementedError

    async def parse_response(self, llm_output: Dict[str, Any]) -> Dict[str, Any]:
        """
        解析 LLM 返回

        Args:
            llm_output: LLM 返回的 JSON

        Returns:
            {
                "actions": [{"type": "tts"/"llm"/"action", ...}],
                "scene_state": {"key": "value"},  # 场景状态更新
                "response": "文本回复"  # 可选，用于日志
            }
        """
        raise NotImplementedError