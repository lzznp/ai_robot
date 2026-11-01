"""
场景编排页面
配置场景角色、性格、语音风格，启动场景调度
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import streamlit as st
import json
from datetime import datetime

from core.data import DeviceRepo, SceneRepo, RoleConfigRepo

st.set_page_config(page_title="场景编排", page_icon="🎬", layout="wide")
st.title("🎬 场景编排")

# ========== session_state ==========
PREFIX = "scene_mgmt_"

if f"{PREFIX}roles" not in st.session_state:
    st.session_state[f"{PREFIX}roles"] = []
if f"{PREFIX}scene_id" not in st.session_state:
    st.session_state[f"{PREFIX}scene_id"] = None
if f"{PREFIX}is_active" not in st.session_state:
    st.session_state[f"{PREFIX}is_active"] = False
if f"{PREFIX}loading_scene" not in st.session_state:
    st.session_state[f"{PREFIX}loading_scene"] = False
if f"{PREFIX}edit_mode" not in st.session_state:
    st.session_state[f"{PREFIX}edit_mode"] = False


# ========== 辅助函数 ==========
def load_scene_to_form(scene_id: str):
    """加载场景配置到表单"""
    scene = SceneRepo.get_by_id(scene_id)
    if not scene:
        return

    role_configs = RoleConfigRepo.get_by_template(scene_id)

    # 填充到 session_state
    st.session_state["scene_name_input"] = scene["name"]
    st.session_state["scene_desc_input"] = scene.get("description", "")
    st.session_state[f"{PREFIX}scene_id"] = scene_id
    st.session_state[f"{PREFIX}roles"] = []

    for r in role_configs:
        device = DeviceRepo.get_by_id(r["device_id"])
        st.session_state[f"{PREFIX}roles"].append({
            "role_name": r["role_name"],
            "device_id": r["device_id"],
            "device_alias": device["alias"] if device else r["device_id"],
            "personality": r.get("personality", "默认性格"),
            "config_id": r["id"]
        })

    st.session_state[f"{PREFIX}is_active"] = scene.get("is_active", 0) == 1


def reset_form():
    """重置表单"""
    st.session_state["scene_name_input"] = ""
    st.session_state["scene_desc_input"] = ""
    st.session_state[f"{PREFIX}roles"] = []
    st.session_state[f"{PREFIX}scene_id"] = None
    st.session_state[f"{PREFIX}is_active"] = False


# ========== 主界面 ==========
# 获取设备列表
devices = DeviceRepo.get_all()
device_options = [f"{d['alias']} ({d['id']})" for d in devices]
device_id_map = {d["id"]: d["alias"] for d in devices}

if not devices:
    st.warning("⚠️ 请先在「设备管理」页面添加设备")
    st.stop()

# ========== 侧边栏：场景列表 ==========
with st.sidebar:
    st.subheader("📋 已保存的场景")

    scenes = SceneRepo.get_all()

    if not scenes:
        st.info("暂无场景")
    else:
        for s in scenes:
            col1, col2 = st.columns([3, 1])
            with col1:
                active_tag = "🟢 " if s.get("is_active") else ""
                st.write(f"{active_tag}{s['name']}")
            with col2:
                if st.button("加载", key=f"load_{s['id']}"):
                    load_scene_to_form(s["id"])
                    st.rerun()

        st.divider()
        if st.button("➕ 新建场景", use_container_width=True):
            reset_form()
            st.rerun()

# ========== 主表单 ==========
# 场景基本信息
scene_name = st.text_input(
    "场景名称 *",
    value=st.session_state.get("scene_name_input", ""),
    key="scene_name_input",
    placeholder="例如: 闲聊场景"
)
scene_desc = st.text_input(
    "场景描述",
    value=st.session_state.get("scene_desc_input", ""),
    key="scene_desc_input",
    placeholder="例如: 默认闲聊场景"
)

# 显示当前状态
if st.session_state[f"{PREFIX}scene_id"]:
    scene = SceneRepo.get_by_id(st.session_state[f"{PREFIX}scene_id"])
    if scene:
        st.caption(f"📌 当前编辑: {scene['name']} | ID: {scene['id']}")
        if scene.get("is_active"):
            st.success("🟢 此场景当前已激活")

st.divider()

# ========== 角色配置 ==========
st.subheader("👥 角色配置")

# 添加角色
col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
with col1:
    new_role_name = st.text_input("角色名", placeholder="如: MOSS", key="new_role_name")
with col2:
    new_device = st.selectbox("设备", [""] + device_options, key="new_device")
with col3:
    new_personality = st.text_input("性格", placeholder="如: 高冷理性", key="new_personality")
with col4:
    st.write("")
    st.write("")
    if st.button("➕ 添加", key="add_role", use_container_width=True):
        if new_role_name and new_device:
            device_id = new_device.split("(")[-1].rstrip(")")
            # 检查是否已存在同名角色
            existing = [r for r in st.session_state[f"{PREFIX}roles"] if r["role_name"] == new_role_name]
            if existing:
                st.warning(f"角色「{new_role_name}」已存在")
            else:
                role = {
                    "role_name": new_role_name,
                    "device_id": device_id,
                    "device_alias": new_device.split("(")[0].strip(),
                    "personality": new_personality or "默认性格"
                }
                st.session_state[f"{PREFIX}roles"].append(role)
                st.rerun()
        else:
            st.warning("请填写角色名并选择设备")

# 显示已添加的角色
roles = st.session_state[f"{PREFIX}roles"]

if not roles:
    st.info("📭 请添加角色（至少需要 1 个机器人角色）")
else:
    # 用表格显示
    import pandas as pd

    df_data = []
    for idx, r in enumerate(roles):
        df_data.append({
            "序号": idx + 1,
            "角色名": r["role_name"],
            "设备": r["device_alias"],
            "性格": r["personality"],
            "操作": f"🗑️ 删除"
        })
    df = pd.DataFrame(df_data)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # 删除按钮（放在下方）
    col_del1, col_del2 = st.columns([3, 1])
    with col_del2:
        delete_target = st.selectbox(
            "选择要删除的角色",
            [""] + [r["role_name"] for r in roles],
            key="delete_role_select"
        )
        if delete_target and st.button("🗑️ 删除选中角色"):
            st.session_state[f"{PREFIX}roles"] = [r for r in roles if r["role_name"] != delete_target]
            st.rerun()

st.divider()

# ========== 操作按钮 ==========
col1, col2, col3 = st.columns(3)

with col1:
    if st.button("💾 保存场景", type="primary", use_container_width=True):
        if not scene_name:
            st.error("请填写场景名称")
        elif len(roles) == 0:
            st.error("请至少添加一个角色")
        else:
            # 检查名称是否重复
            all_scenes = SceneRepo.get_all()
            existing = [s for s in all_scenes if s["name"] == scene_name]
            # 如果是在编辑模式且是同一个场景，允许
            current_id = st.session_state[f"{PREFIX}scene_id"]
            if existing and (not current_id or existing[0]["id"] != current_id):
                st.error(f"❌ 场景名称「{scene_name}」已存在，请换一个")
            else:
                if current_id:
                    # 更新已有场景
                    SceneRepo.update(current_id, scene_name, scene_desc)
                    # 删除旧角色配置
                    RoleConfigRepo.delete_by_template(current_id)
                else:
                    # 新建场景
                    current_id = f"scene_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    SceneRepo.create(current_id, scene_name, scene_desc, "chat")

                # 保存角色配置
                for idx, r in enumerate(roles):
                    config_id = f"role_{current_id}_{idx}"
                    RoleConfigRepo.create(
                        config_id,
                        current_id,
                        r["device_id"],
                        r["role_name"],
                        r["personality"],
                        "zh-CN-XiaoxiaoNeural",
                        [],
                        None,
                        idx
                    )

                st.session_state[f"{PREFIX}scene_id"] = current_id
                st.success(f"✅ 场景「{scene_name}」保存成功")
                st.rerun()

with col2:
    if st.button("▶ 启动场景", use_container_width=True):
        scene_id = st.session_state[f"{PREFIX}scene_id"]
        if not scene_id:
            st.error("请先保存场景")
        else:
            if SceneRepo.set_active(scene_id):
                st.success(f"✅ 场景「{scene_name}」已激活")
                st.session_state[f"{PREFIX}is_active"] = True
                st.rerun()
            else:
                st.error("❌ 激活失败")

with col3:
    if st.button("🔄 重置表单", use_container_width=True):
        reset_form()
        st.rerun()

# ========== 状态提示 ==========
st.divider()
col_status1, col_status2 = st.columns(2)

with col_status1:
    if st.session_state[f"{PREFIX}scene_id"]:
        st.info(f"📌 当前场景 ID: {st.session_state[f'{PREFIX}scene_id']}")
    else:
        st.info("📌 未保存任何场景")

with col_status2:
    if st.session_state[f"{PREFIX}is_active"]:
        st.success("🟢 场景已激活")
    else:
        st.info("⚪ 场景未激活")