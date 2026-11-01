"""
设备管理页面
管理所有机器人设备（增删改）
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import streamlit as st
import pandas as pd
from datetime import datetime

from core.data import DeviceRepo

st.set_page_config(page_title="设备管理", page_icon="📡", layout="wide")
st.title("📡 设备管理")

# ========== session_state ==========
PREFIX = "device_mgmt_"

if f"{PREFIX}show_add_form" not in st.session_state:
    st.session_state[f"{PREFIX}show_add_form"] = False
if f"{PREFIX}editing_device" not in st.session_state:
    st.session_state[f"{PREFIX}editing_device"] = None


def format_datetime(dt_str):
    if not dt_str:
        return "-"
    try:
        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        return dt.strftime("%Y-%m-%d %H:%M")
    except:
        return dt_str[:16]


# ========== 添加设备 ==========
def render_add_form():
    with st.expander("✏️ 添加新设备", expanded=True):
        with st.form("add_device_form"):
            device_id = st.text_input("设备 ID *", placeholder="例如: esp32_001")
            alias = st.text_input("别名 *", placeholder="例如: 月球车")
            device_type = st.text_input("设备类型", placeholder="例如: 桌面机器人", value="unknown")

            col1, col2 = st.columns(2)
            with col1:
                if st.form_submit_button("✅ 保存", use_container_width=True):
                    if not device_id or not alias:
                        st.error("设备 ID 和别名不能为空")
                    else:
                        if DeviceRepo.create(device_id, alias, device_type):
                            st.success(f"✅ 设备 {alias} 创建成功")
                            st.session_state[f"{PREFIX}show_add_form"] = False
                            st.rerun()
                        else:
                            st.error("❌ 创建失败，设备 ID 可能已存在")
            with col2:
                if st.form_submit_button("❌ 取消", use_container_width=True):
                    st.session_state[f"{PREFIX}show_add_form"] = False
                    st.rerun()


# ========== 编辑设备 ==========
def render_edit_form(device):
    with st.expander(f"✏️ 编辑 {device['alias']}", expanded=True):
        with st.form("edit_device_form"):
            st.text_input("设备 ID", value=device["id"], disabled=True)
            new_alias = st.text_input("别名 *", value=device["alias"])
            new_type = st.text_input("设备类型", value=device.get("device_type", "unknown"))

            col1, col2 = st.columns(2)
            with col1:
                if st.form_submit_button("✅ 保存", use_container_width=True):
                    if not new_alias:
                        st.error("别名不能为空")
                    else:
                        if DeviceRepo.update(device["id"], new_alias, new_type):
                            st.success("✅ 更新成功")
                            st.session_state[f"{PREFIX}editing_device"] = None
                            st.rerun()
                        else:
                            st.error("❌ 更新失败")
            with col2:
                if st.form_submit_button("❌ 取消", use_container_width=True):
                    st.session_state[f"{PREFIX}editing_device"] = None
                    st.rerun()


# ========== 主体 ==========
# 顶部：标题 + 按钮
col1, col2 = st.columns([5, 1])
with col2:
    if st.button("➕ 添加设备", use_container_width=True):
        st.session_state[f"{PREFIX}show_add_form"] = True

if st.session_state[f"{PREFIX}show_add_form"]:
    render_add_form()

if st.session_state[f"{PREFIX}editing_device"]:
    render_edit_form(st.session_state[f"{PREFIX}editing_device"])

# ========== 设备列表 ==========
devices = DeviceRepo.get_all()

if not devices:
    st.info("📭 暂无设备，请点击右上角「添加设备」")
    st.stop()

# 构建表格数据（每行带操作按钮）
for d in devices:
    status = "🟢 在线" if d.get("online") else "🔴 离线"
    last_seen = format_datetime(d.get("last_seen"))

    col_id, col_alias, col_type, col_status, col_last, col_action = st.columns([1.5, 1, 1, 1, 1.5, 1.5])

    with col_id:
        st.code(d["id"], language="text")
    with col_alias:
        st.write(d["alias"])
    with col_type:
        st.write(d.get("device_type", "-"))
    with col_status:
        st.write(status)
    with col_last:
        st.write(last_seen)
    with col_action:
        col_edit, col_delete = st.columns(2)
        with col_edit:
            if st.button("✏️", key=f"edit_{d['id']}"):
                st.session_state[f"{PREFIX}editing_device"] = DeviceRepo.get_by_id(d["id"])
                st.rerun()
        with col_delete:
            if st.button("🗑️", key=f"del_{d['id']}"):
                if DeviceRepo.delete(d["id"]):
                    st.success(f"✅ 已删除 {d['alias']}")
                    st.rerun()
                else:
                    st.error("❌ 删除失败")

    st.divider()