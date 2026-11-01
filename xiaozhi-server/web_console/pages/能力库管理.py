"""
能力库页面
管理设备的能力（增删改 + 测试发送）
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import streamlit as st
import json
import requests
from datetime import datetime

from core.data import DeviceRepo, CapabilityRepo

st.set_page_config(page_title="能力库", page_icon="🧩", layout="wide")
st.title("🧩 能力库")

# ========== session_state ==========
PREFIX = "capability_mgmt_"

if f"{PREFIX}show_add_form" not in st.session_state:
    st.session_state[f"{PREFIX}show_add_form"] = False
if f"{PREFIX}editing_capability" not in st.session_state:
    st.session_state[f"{PREFIX}editing_capability"] = None
if f"{PREFIX}selected_device" not in st.session_state:
    st.session_state[f"{PREFIX}selected_device"] = None
if f"{PREFIX}test_result" not in st.session_state:
    st.session_state[f"{PREFIX}test_result"] = None


# ========== 工具函数 ==========
def get_api_base():
    return "http://192.168.199.106:8004"


def send_command(device_id: str, command: dict) -> dict:
    """发送指令给固件"""
    try:
        resp = requests.post(
            f"{get_api_base()}/api/command",
            json={"device_id": device_id, "command": command},
            timeout=5
        )
        return resp.json()
    except Exception as e:
        return {"success": False, "message": str(e)}


# ========== 添加能力 ==========
def render_add_form(device_id: str):
    with st.expander("✏️ 添加新能力", expanded=True):
        with st.form("add_capability_form"):
            cap_id = st.text_input("能力 ID *", placeholder="例如: cap_mooncar_turn_around")
            name = st.text_input("能力名称 *", placeholder="例如: 转一圈")
            description = st.text_area("描述", placeholder="能力说明", height=60)
            capability_type = st.selectbox("能力类型", ["atomic", "composite"])
            command_json = st.text_area(
                "指令 JSON *",
                placeholder='{"type":"code_stream","steps":[{"op":"gpio_write","pin":1,"value":1,"duration":2000}]}',
                height=150
            )
            llm_visible = st.checkbox("上报给 LLM", value=True)

            col1, col2 = st.columns(2)
            with col1:
                if st.form_submit_button("✅ 保存", use_container_width=True):
                    if not cap_id or not name or not command_json:
                        st.error("能力 ID、名称和指令 JSON 不能为空")
                    else:
                        try:
                            command = json.loads(command_json)
                            if CapabilityRepo.create(
                                cap_id, device_id, name, command,
                                description, capability_type, llm_visible=llm_visible
                            ):
                                st.success(f"✅ 能力 {name} 创建成功")
                                st.session_state[f"{PREFIX}show_add_form"] = False
                                st.rerun()
                            else:
                                st.error("❌ 创建失败，能力 ID 可能已存在")
                        except json.JSONDecodeError as e:
                            st.error(f"❌ JSON 格式错误: {e}")
            with col2:
                if st.form_submit_button("❌ 取消", use_container_width=True):
                    st.session_state[f"{PREFIX}show_add_form"] = False
                    st.rerun()


# ========== 编辑能力 ==========
def render_edit_form(cap):
    with st.expander(f"✏️ 编辑 {cap['name']}", expanded=True):
        with st.form("edit_capability_form"):
            st.text_input("能力 ID", value=cap["id"], disabled=True)
            new_name = st.text_input("能力名称 *", value=cap["name"])
            new_desc = st.text_area("描述", value=cap.get("description", ""), height=60)
            new_type = st.selectbox(
                "能力类型",
                ["atomic", "composite"],
                index=0 if cap.get("capability_type") == "atomic" else 1
            )
            new_command = st.text_area(
                "指令 JSON *",
                value=json.dumps(cap["command"], ensure_ascii=False, indent=2),
                height=150
            )
            new_visible = st.checkbox("上报给 LLM", value=cap.get("llm_visible", True))

            col1, col2 = st.columns(2)
            with col1:
                if st.form_submit_button("✅ 保存", use_container_width=True):
                    if not new_name or not new_command:
                        st.error("名称和指令 JSON 不能为空")
                    else:
                        try:
                            command = json.loads(new_command)
                            if CapabilityRepo.update(
                                cap["id"],
                                name=new_name,
                                description=new_desc,
                                command=command,
                                capability_type=new_type,
                                llm_visible=new_visible
                            ):
                                st.success("✅ 更新成功")
                                st.session_state[f"{PREFIX}editing_capability"] = None
                                st.rerun()
                            else:
                                st.error("❌ 更新失败")
                        except json.JSONDecodeError as e:
                            st.error(f"❌ JSON 格式错误: {e}")
            with col2:
                if st.form_submit_button("❌ 取消", use_container_width=True):
                    st.session_state[f"{PREFIX}editing_capability"] = None
                    st.rerun()


# ========== 主界面 ==========
# 获取所有设备
devices = DeviceRepo.get_all()
if not devices:
    st.info("📭 请先在「设备管理」页面添加设备")
    st.stop()

# 设备选择器
device_options = [f"{d['alias']} ({d['id']})" for d in devices]
selected_device = st.selectbox(
    "选择设备",
    device_options,
    key="cap_device_selector"
)

if selected_device:
    device_id = selected_device.split("(")[-1].rstrip(")")
    device = DeviceRepo.get_by_id(device_id)
    st.caption(f"设备: {device['alias']} | 类型: {device.get('device_type', 'unknown')}")

    # 顶部按钮
    col1, col2 = st.columns([5, 1])
    with col2:
        if st.button("➕ 添加能力", use_container_width=True):
            st.session_state[f"{PREFIX}show_add_form"] = True

    if st.session_state[f"{PREFIX}show_add_form"]:
        render_add_form(device_id)

    if st.session_state[f"{PREFIX}editing_capability"]:
        render_edit_form(st.session_state[f"{PREFIX}editing_capability"])

    # ========== 能力列表 ==========
    capabilities = CapabilityRepo.get_by_device(device_id)

    if not capabilities:
        st.info("📭 该设备暂无能力，点击「添加能力」创建")
    else:
        # 表格显示
        for cap in capabilities:
            col1, col2, col3, col4, col5 = st.columns([1.5, 2, 1, 1, 1.5])

            with col1:
                st.write(cap["name"])
            with col2:
                st.write(cap.get("description", "-")[:30])
            with col3:
                st.write("✅" if cap.get("llm_visible") else "❌")
            with col4:
                st.write(cap.get("capability_type", "-"))
            with col5:
                # 操作按钮
                col_edit, col_delete, col_send = st.columns(3)
                with col_edit:
                    if st.button("✏️", key=f"edit_{cap['id']}"):
                        st.session_state[f"{PREFIX}editing_capability"] = cap
                        st.rerun()
                with col_delete:
                    if st.button("🗑️", key=f"del_{cap['id']}"):
                        if CapabilityRepo.delete(cap["id"]):
                            st.success(f"✅ 已删除 {cap['name']}")
                            st.rerun()
                        else:
                            st.error("❌ 删除失败")
                with col_send:
                    if st.button("▶", key=f"send_{cap['id']}"):
                        # 发送能力给固件测试
                        with st.spinner(f"发送 {cap['name']}..."):
                            result = send_command(device_id, cap["command"])
                            if result.get("success"):
                                st.success(f"✅ {cap['name']} 已发送")
                            else:
                                st.error(f"❌ 发送失败: {result.get('message', '未知错误')}")

            st.divider()