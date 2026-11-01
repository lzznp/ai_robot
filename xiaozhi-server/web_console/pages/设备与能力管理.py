"""
设备与能力管理页面
使用 st.tabs 合并设备管理和能力库两个功能
"""

import streamlit as st
import requests
import json
import sys
import os

import pandas as pd

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.data import DeviceRepo, CapabilityRepo


# ==================== 工具函数 ====================

def get_api_base():
    """获取 API 基础 URL"""
    return st.session_state.get("api_base", "http://localhost:8004")


def call_api(method, endpoint, data=None):
    """调用后端 API"""
    url = f"{get_api_base()}{endpoint}"
    try:
        if method == "GET":
            resp = requests.get(url, timeout=5)
        elif method == "POST":
            resp = requests.post(url, json=data, timeout=5)
        else:
            return {"success": False, "message": f"不支持的请求方法: {method}"}
        return resp.json()
    except requests.exceptions.ConnectionError:
        return {"success": False, "message": f"❌ 无法连接到后端服务: {url}"}
    except Exception as e:
        return {"success": False, "message": f"❌ 请求失败: {str(e)}"}


# ==================== 设备管理 Tab ====================

def render_device_tab():
    """渲染设备管理 Tab"""
    st.markdown("### 📡 设备列表")

    # ----- 添加设备按钮 -----
    col1, col2 = st.columns([6, 1])
    with col2:
        if st.button("➕ 添加设备", use_container_width=True):
            st.session_state.show_add_device = True

    # ----- 添加设备弹窗 -----
    if st.session_state.get("show_add_device", False):
        with st.expander("✏️ 添加新设备", expanded=True):
            with st.form("add_device_form"):
                device_id = st.text_input("设备 ID *", placeholder="例如: esp32_001")
                alias = st.text_input("别名 *", placeholder="例如: 月球车")
                device_type = st.text_input("设备类型", placeholder="例如: mobile / desktop", value="unknown")
                ip = st.text_input("IP 地址", placeholder="例如: 192.168.1.100")

                col1, col2 = st.columns(2)
                with col1:
                    submitted = st.form_submit_button("✅ 保存", use_container_width=True)
                with col2:
                    cancelled = st.form_submit_button("❌ 取消", use_container_width=True)

                if submitted:
                    if not device_id or not alias:
                        st.error("设备 ID 和别名不能为空")
                    else:
                        if DeviceRepo.create(device_id, alias, device_type, ip):
                            st.success(f"✅ 设备 {alias} 创建成功")
                            st.session_state.show_add_device = False
                            st.rerun()
                        else:
                            st.error("❌ 创建失败，请检查设备 ID 是否已存在")

                if cancelled:
                    st.session_state.show_add_device = False
                    st.rerun()

    # ----- 设备列表 -----
    devices = DeviceRepo.get_all()
    if not devices:
        st.info("📭 暂无设备，请添加")
        return

    # 表格
    table_data = []
    for d in devices:
        status = "🟢 在线" if d["online"] else "🔴 离线"
        table_data.append([
            d["id"],
            d["alias"],
            d["device_type"],
            status,
            d.get("ip", "-"),
        ])

    st.table(
        pd.DataFrame(
            table_data,
            columns=["设备 ID", "别名", "类型", "状态", "IP"]
        )
    )

    # ----- 操作区 -----
    st.markdown("---")
    st.markdown("#### 🔧 操作")

    # 选择设备
    device_options = [f"{d['alias']} ({d['id']})" for d in devices]
    selected = st.selectbox("选择要操作的设备", device_options)

    if selected:
        device_id = selected.split("(")[-1].rstrip(")")
        device = DeviceRepo.get_by_id(device_id)

        if device:
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("✏️ 编辑", use_container_width=True):
                    st.session_state.edit_device = device
            with col2:
                if st.button("🔄 刷新状态", use_container_width=True):
                    # 调用后端刷新在线状态
                    result = call_api("GET", "/api/devices")
                    if result.get("success"):
                        DeviceRepo.set_online(device_id, device_id in result.get("online_ids", []))
                        st.success("✅ 状态已刷新")
                        st.rerun()
                    else:
                        st.error(f"❌ 刷新失败: {result.get('message')}")
            with col3:
                if st.button("🗑️ 删除", use_container_width=True):
                    if DeviceRepo.delete(device_id):
                        st.success(f"✅ 设备 {device['alias']} 已删除")
                        st.rerun()
                    else:
                        st.error("❌ 删除失败")

    # ----- 编辑弹窗 -----
    if st.session_state.get("edit_device"):
        device = st.session_state.edit_device
        with st.expander(f"✏️ 编辑 {device['alias']}", expanded=True):
            with st.form("edit_device_form"):
                new_alias = st.text_input("别名", value=device["alias"])
                new_type = st.text_input("设备类型", value=device["device_type"])
                new_ip = st.text_input("IP 地址", value=device.get("ip", ""))

                col1, col2 = st.columns(2)
                with col1:
                    submitted = st.form_submit_button("✅ 保存", use_container_width=True)
                with col2:
                    cancelled = st.form_submit_button("❌ 取消", use_container_width=True)

                if submitted:
                    if DeviceRepo.update(device["id"], new_alias, new_type, new_ip):
                        st.success("✅ 更新成功")
                        st.session_state.edit_device = None
                        st.rerun()
                    else:
                        st.error("❌ 更新失败")

                if cancelled:
                    st.session_state.edit_device = None
                    st.rerun()


# ==================== 能力库 Tab ====================

def render_capability_tab():
    """渲染能力库 Tab"""
    st.markdown("### 🧩 能力库")

    # ----- 设备筛选 -----
    devices = DeviceRepo.get_all()
    device_options = ["全部"] + [f"{d['alias']} ({d['id']})" for d in devices]
    selected_device = st.selectbox("按设备筛选", device_options, key="cap_filter")

    if selected_device == "全部":
        device_id = None
    else:
        device_id = selected_device.split("(")[-1].rstrip(")")

    # ----- 添加能力按钮 -----
    col1, col2 = st.columns([6, 1])
    with col2:
        if st.button("➕ 添加能力", use_container_width=True):
            st.session_state.show_add_capability = True

    # ----- 添加能力弹窗 -----
    if st.session_state.get("show_add_capability", False):
        with st.expander("✏️ 添加新能力", expanded=True):
            with st.form("add_capability_form"):
                # 选择设备
                device_opts = [f"{d['alias']} ({d['id']})" for d in devices]
                selected_dev = st.selectbox("所属设备 *", device_opts)
                dev_id = selected_dev.split("(")[-1].rstrip(")")

                cap_id = st.text_input("能力 ID *", placeholder="例如: cap_moss_custom")
                name = st.text_input("能力名称 *", placeholder="例如: 转一圈")
                description = st.text_area("描述", placeholder="能力说明")
                cap_type = st.selectbox("能力类型", ["atomic", "composite"])
                command_json = st.text_area(
                    "指令 JSON *",
                    placeholder='{"type":"action","action":"move_forward"}',
                    height=100
                )
                llm_visible = st.checkbox("上报给 LLM", value=True)

                col1, col2 = st.columns(2)
                with col1:
                    submitted = st.form_submit_button("✅ 保存", use_container_width=True)
                with col2:
                    cancelled = st.form_submit_button("❌ 取消", use_container_width=True)

                if submitted:
                    if not cap_id or not name or not command_json:
                        st.error("能力 ID、名称和指令 JSON 不能为空")
                    else:
                        try:
                            command = json.loads(command_json)
                            if CapabilityRepo.create(
                                cap_id, dev_id, name, command,
                                description, cap_type, llm_visible=llm_visible
                            ):
                                st.success(f"✅ 能力 {name} 创建成功")
                                st.session_state.show_add_capability = False
                                st.rerun()
                            else:
                                st.error("❌ 创建失败，请检查能力 ID 是否已存在")
                        except json.JSONDecodeError:
                            st.error("❌ 指令 JSON 格式错误")

                if cancelled:
                    st.session_state.show_add_capability = False
                    st.rerun()

    # ----- 能力列表 -----
    if device_id:
        capabilities = CapabilityRepo.get_by_device(device_id)
    else:
        # 全部设备：分别获取再合并
        capabilities = []
        for d in devices:
            capabilities.extend(CapabilityRepo.get_by_device(d["id"]))

    if not capabilities:
        st.info("📭 暂无能力，请添加")
        return

    # 表格
    table_data = []
    for c in capabilities:
        # 获取设备别名
        dev = DeviceRepo.get_by_id(c["device_id"])
        dev_name = dev["alias"] if dev else c["device_id"]
        visible = "✅" if c["llm_visible"] else "❌"

        table_data.append([
            c["name"],
            dev_name,
            c["capability_type"],
            visible,
            c["id"],
        ])

    st.table(
        pd.DataFrame(
            table_data,
            columns=["能力名称", "所属设备", "类型", "LLM可见", "ID"]
        )
    )

    # ----- 操作区 -----
    st.markdown("---")
    st.markdown("#### 🔧 操作")

    cap_options = [f"{c['name']} ({c['id']})" for c in capabilities]
    if cap_options:
        selected = st.selectbox("选择要操作的能力", cap_options, key="cap_operation")
        cap_id = selected.split("(")[-1].rstrip(")")
        cap = CapabilityRepo.get_by_id(cap_id)

        if cap:
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✏️ 编辑能力", use_container_width=True):
                    st.session_state.edit_capability = cap
            with col2:
                if st.button("🗑️ 删除能力", use_container_width=True):
                    if CapabilityRepo.delete(cap_id):
                        st.success(f"✅ 能力 {cap['name']} 已删除")
                        st.rerun()
                    else:
                        st.error("❌ 删除失败")

    # ----- 编辑能力弹窗 -----
    if st.session_state.get("edit_capability"):
        cap = st.session_state.edit_capability
        with st.expander(f"✏️ 编辑 {cap['name']}", expanded=True):
            with st.form("edit_capability_form"):
                new_name = st.text_input("能力名称", value=cap["name"])
                new_desc = st.text_area("描述", value=cap.get("description", ""))
                new_type = st.selectbox("能力类型", ["atomic", "composite"], index=0 if cap["capability_type"] == "atomic" else 1)
                new_command = st.text_area(
                    "指令 JSON",
                    value=json.dumps(cap["command"], ensure_ascii=False, indent=2),
                    height=100
                )
                new_visible = st.checkbox("上报给 LLM", value=cap["llm_visible"])

                col1, col2 = st.columns(2)
                with col1:
                    submitted = st.form_submit_button("✅ 保存", use_container_width=True)
                with col2:
                    cancelled = st.form_submit_button("❌ 取消", use_container_width=True)

                if submitted:
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
                            st.session_state.edit_capability = None
                            st.rerun()
                        else:
                            st.error("❌ 更新失败")
                    except json.JSONDecodeError:
                        st.error("❌ 指令 JSON 格式错误")

                if cancelled:
                    st.session_state.edit_capability = None
                    st.rerun()


# ==================== 页面入口 ====================

# 初始化 session_state
if "show_add_device" not in st.session_state:
    st.session_state.show_add_device = False
if "show_add_capability" not in st.session_state:
    st.session_state.show_add_capability = False
if "edit_device" not in st.session_state:
    st.session_state.edit_device = None
if "edit_capability" not in st.session_state:
    st.session_state.edit_capability = None

st.set_page_config(page_title="设备与能力管理", page_icon="📡")

st.title("📡 设备与能力管理")

# 使用 st.tabs 切换
tab1, tab2 = st.tabs(["📡 设备管理", "🧩 能力库"])

with tab1:
    render_device_tab()

with tab2:
    render_capability_tab()