"""
聊天测试页面
模拟用户输入文字，触发 LLM 对话和 TTS 播报
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import streamlit as st
import requests
import json

st.set_page_config(page_title="聊天测试", page_icon="💬", layout="wide")
st.title("💬 聊天测试")


def get_api_base():
    return "http://192.168.199.106:8004"


def send_text_to_llm(text: str, device_id: str = "58:e6:c5:58:0c:58"):
    """发送文本给后台 LLM 处理"""
    try:
        # 小智后台的文本消息格式
        message = {
            "type": "stt",
            "text": text
        }
        # 通过 WebSocket 模拟文本消息
        # 直接调用后台的文本处理接口
        resp = requests.post(
            f"{get_api_base()}/api/text",
            json={
                "device_id": device_id,
                "text": text,
                "session_id": "test_session"
            },
            timeout=30
        )
        return resp.json()
    except Exception as e:
        return {"success": False, "message": str(e)}


# 输入区域
st.subheader("📝 输入文字")

user_input = st.text_input("请输入你要说的话", placeholder="例如: 月球车，介绍一下自己")

col1, col2 = st.columns(2)
with col1:
    if st.button("🚀 发送", type="primary", use_container_width=True):
        if user_input:
            with st.spinner("处理中..."):
                result = send_text_to_llm(user_input)
                if result.get("success"):
                    st.success(f"✅ 已处理: {result.get('response', '')}")
                else:
                    st.error(f"❌ 处理失败: {result.get('message', '未知错误')}")
        else:
            st.warning("请输入文字")
with col2:
    if st.button("🗑️ 清空", use_container_width=True):
        st.session_state["chat_history"] = []

st.divider()

# 显示历史记录
if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = []

st.subheader("📋 对话历史")
for msg in st.session_state["chat_history"]:
    if msg["role"] == "user":
        st.info(f"🧑: {msg['content']}")
    else:
        st.success(f"🤖: {msg['content']}")