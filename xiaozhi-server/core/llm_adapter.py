# core/llm_adapter.py - 适配小智 LLM 到 Character 接口

import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


class LLMAdapter:
    """
    适配小智的 LLM 到 Character 的接口
    Character 期望：llm_client(messages: List[Dict]) -> str
    小智的 LLM 期望：response(session_id, messages) -> 流式迭代器
    """

    def __init__(self, llm_instance, session_id: str = None):
        self.llm = llm_instance
        self.session_id = session_id

    def set_session_id(self, session_id: str):
        self.session_id = session_id

    def __call__(self, messages: List[Dict]) -> str:
        """
        调用 LLM 并返回完整响应文本
        """
        if not self.llm:
            logger.error("[LLMAdapter] LLM 实例为空")
            return "（系统错误：LLM 未配置）"

        try:
            # 调用小智的 LLM（非流式，收集所有内容）
            full_response = ""

            # 使用 response 方法（非流式）
            # 注意：小智的 LLM 可能没有直接的非流式接口，我们使用流式并收集
            if hasattr(self.llm, 'response'):
                # 尝试流式收集
                responses = self.llm.response(self.session_id, messages)
                for chunk in responses:
                    if isinstance(chunk, str):
                        full_response += chunk
                    elif isinstance(chunk, dict) and "content" in chunk:
                        full_response += chunk["content"]
                    elif isinstance(chunk, tuple) and len(chunk) > 0:
                        # 处理 (content, tools) 格式
                        if chunk[0]:
                            full_response += chunk[0]
            else:
                # fallback：如果有 chat 方法
                if hasattr(self.llm, 'chat'):
                    full_response = self.llm.chat(messages)
                else:
                    logger.error("[LLMAdapter] LLM 没有 response 或 chat 方法")
                    return "（系统错误：LLM 接口不兼容）"

            return full_response.strip() or "（收到空响应）"

        except Exception as e:
            logger.error(f"[LLMAdapter] LLM 调用失败: {e}")
            return f"（调用失败: {e}）"