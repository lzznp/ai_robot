# web_console/pages/固件测试.py
import sys
from pathlib import Path

# 将项目根目录添加到 sys.path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import streamlit as st
import json
from datetime import datetime
import requests

st.set_page_config(page_title="固件调试", page_icon="🧪", layout="wide")
st.title("🧪 固件指令调试")

# ========== 初始化 session_state（加前缀） ==========
PREFIX = "firmware_test_"

if f"{PREFIX}logs" not in st.session_state:
    st.session_state[f"{PREFIX}logs"] = []


# ========== 辅助函数 ==========
def add_log(device_id: str, command: str, success: bool, message: str):
    """添加日志"""
    log_entry = {
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "device_id": device_id,
        "command": command,
        "success": success,
        "message": message
    }
    st.session_state[f"{PREFIX}logs"].insert(0, log_entry)
    if len(st.session_state[f"{PREFIX}logs"]) > 100:
        st.session_state[f"{PREFIX}logs"] = st.session_state[f"{PREFIX}logs"][:100]


# ========== 清空日志按钮 ==========
col_top_left, col_top_right = st.columns([3, 1])
with col_top_right:
    if st.button("🗑️ 清空日志", use_container_width=True):
        st.session_state[f"{PREFIX}logs"] = []
        st.rerun()

st.divider()

# ========== 布局 ==========
col_left, col_right = st.columns([1, 2])

with col_left:
    st.subheader("🎯 目标固件")

    # 手动输入 device_id
    device_id = st.text_input(
        "设备 ID",
        value="58:e6:c5:58:0c:58",
        help="从后台日志中查看设备注册时的 ID"
    )

    st.divider()

    st.subheader("📤 指令")
    default_command = '{"type":"llm","emotion":"happy"}'
    command = st.text_area(
        "JSON 指令",
        value=default_command,
        height=120,
        help="输入单条 JSON 指令"
    )

    send_button = st.button("🚀 发送", type="primary", use_container_width=True)

with col_right:
    st.subheader("📋 执行日志")
    log_container = st.container(height=400)

    with log_container:
        logs = st.session_state[f"{PREFIX}logs"]
        if not logs:
            st.info("暂无日志，发送指令后会显示在这里")
        else:
            for log in logs:
                status_icon = "✅" if log["success"] else "❌"
                st.text(
                    f"[{log['timestamp']}] {status_icon} {log['device_id']} → {log['command'][:50]}{'...' if len(log['command']) > 50 else ''}"
                )
                st.caption(f"   {log['message']}")

# ========== 处理发送 ==========
if send_button:
    if not device_id.strip():
        st.error("❌ 请输入设备 ID")
        st.stop()

    if not command.strip():
        st.error("❌ 请输入指令")
        st.stop()

    # 验证 JSON 格式
    try:
        json.loads(command)
    except json.JSONDecodeError as e:
        st.error(f"❌ JSON 格式错误: {e}")
        st.stop()

    # ================================================================
    # ★★★ 调用后台 HTTP API 下发指令 ★★★
    # ================================================================
    try:
        api_url = "http://192.168.199.106:8004/api/command"
        response = requests.post(
            api_url,
            json={
                "device_id": device_id.strip(),
                "command": json.loads(command)
            },
            timeout=5
        )

        result = response.json()

        if result.get("success"):
            add_log(device_id, command, True, result.get("message", "指令已下发"))
            st.success(f"✅ {result.get('message')}")
        else:
            add_log(device_id, command, False, result.get("message", "下发失败"))
            st.error(f"❌ {result.get('message')}")

    except requests.exceptions.ConnectionError:
        add_log(device_id, command, False, "无法连接后台 API，请确认后台已启动")
        st.error("❌ 无法连接后台 API，请确认后台已启动")
    except requests.exceptions.Timeout:
        add_log(device_id, command, False, "后台 API 超时")
        st.error("❌ 后台 API 超时")
    except Exception as e:
        add_log(device_id, command, False, f"异常: {str(e)}")
        st.error(f"❌ 发送失败: {e}")

    st.rerun()