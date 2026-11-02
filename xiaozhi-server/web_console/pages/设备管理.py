"""
设备管理 —— 只做「登记 / 改 / 删」和「确认本机引脚与备注」。

设计约定（2026-11-01 与用户确认）：
  · 这一页只管设备本身；造动作/测固件/存能力都在「🧩 能力库」。
  · 硬件资料分两层：
      - 固件/设计事实 → core/actions.py 的 KNOWN_BOARDS（页面只读）
      - 这台机器的实物现状 → devices.hw_json（这页可以改：灯脚覆盖 + 本机备注）
    所以“我现在只有 1 颗灯珠”这种话写“本机备注”，不要去改 KNOWN_BOARDS。

⚠️ 删除设备会 ON DELETE CASCADE 连带删掉它的能力（device_capabilities）
   和场景角色（template_role_configs）——所以删除要勾确认。
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import json
import sqlite3

import streamlit as st

from core.actions import board_hint, is_mac, normalize_device_id
from core.data import CapabilityRepo, DeviceRepo
from web_console.ui_components import fetch_online, render_board_card

API_BASE = "http://192.168.199.106:8004"
P = "dev_"

st.set_page_config(page_title="设备管理", page_icon="📥", layout="wide")
st.title("📥 设备管理")
st.caption("只负责登记 / 改 / 删。造动作用「🧩 能力库」；引脚的本机实物差异写这里的「本机备注」。")


def parse_pins(text: str):
    """把 "7,48" / "7 48" / "GPIO7、GPIO48" 解析成 [7, 48]；空 → None。"""
    if not text or not text.strip():
        return None
    nums = []
    for token in text.replace("，", ",").replace("、", ",").replace(" ", ",").split(","):
        token = token.strip().upper().replace("GPIO", "")
        if not token:
            continue
        if not token.isdigit():
            raise ValueError(f"灯脚只能是数字：{token!r}")
        nums.append(int(token))
    return sorted(set(nums)) or None


# ============================================================================
# 在线设备（唯一可靠的在线来源：/api/devices）
# ============================================================================
c1, c2 = st.columns([5, 1])
with c2:
    st.write("")
    if st.button("🔄 刷新在线", use_container_width=True):
        fetch_online.clear()
        st.rerun()

online, online_err = fetch_online(API_BASE)
registered = DeviceRepo.get_all()
registered_ids = {d["id"].lower() for d in registered}

with c1:
    if online:
        st.success(f"后台在线设备 {len(online)} 台")
    else:
        st.warning("后台现在没有任何在线设备" + (f"（接口错误：{online_err}）" if online_err else ""))

st.subheader("① 在线设备")
if not online:
    st.caption("没有设备连到后台。设备上电 → 看它连上 8000 → 再点「🔄 刷新在线」。")
else:
    for did, info in online.items():
        registered_flag = "已登记" if did in registered_ids else "**未登记**"
        last_seen = str(info.get("last_seen", ""))[:19]
        cols = st.columns([3, 2, 2, 1])
        cols[0].markdown(f"🟢 `{did}`")
        cols[1].caption(f"最后活跃：{last_seen}")
        cols[2].caption(registered_flag)
        with cols[3]:
            if did not in registered_ids:
                if st.button("登记它", key=f"{P}reg_{did}", use_container_width=True):
                    st.session_state[f"{P}pending_mac"] = did
                    st.rerun()

st.divider()

# ============================================================================
# ② 添加设备
# ============================================================================
st.subheader("② 添加设备")

pending = st.session_state.pop(f"{P}pending_mac", None)
if pending:
    st.session_state[f"{P}new_mac"] = pending          # 必须在控件创建前塞
    st.session_state[f"{P}new_alias"] = board_hint(pending)["alias"] if board_hint(pending) else ""
    st.session_state[f"{P}new_type"] = "robot"
    st.info(f"已把 `{pending}` 填进下面的表单，补个名称再提交。")

with st.form(f"{P}addform"):
    a1, a2, a3 = st.columns([2, 2, 1])
    new_mac = a1.text_input("MAC / device_id *", key=f"{P}new_mac",
                            placeholder="58:E6:C5:5A:2F:FC")
    new_alias = a2.text_input("名称 *", key=f"{P}new_alias", placeholder="MOSS")
    new_type = a3.text_input("类型", key=f"{P}new_type", value="robot")
    submitted = st.form_submit_button("➕ 登记", type="primary")

if submitted:
    mac = normalize_device_id(new_mac)
    if not mac:
        st.error("请先填 MAC（例如 `58:E6:C5:5A:2F:FC`）")
    elif not is_mac(mac):
        st.error(f"MAC 格式不对：`{new_mac}` —— 要 6 段十六进制")
    elif not new_alias.strip():
        st.error("名称不能为空")
    elif DeviceRepo.exists(mac):
        st.error(f"`{mac}` 已经登记过了")
    else:
        try:
            DeviceRepo.create(mac, new_alias.strip(), new_type.strip() or "robot")
            st.success(f"已登记 `{mac}`（{new_alias.strip()}）")
            st.rerun()
        except sqlite3.IntegrityError as e:
            st.error(f"登记失败（主键冲突）：{e}")

st.divider()

# ============================================================================
# ③ 已登记设备
# ============================================================================
st.subheader("③ 已登记设备")

if not registered:
    st.info("还没有登记任何设备。上面②加一台，或从「① 在线设备」里点「登记它」。")
    st.stop()

for d in registered:
    did = d["id"].lower()
    alias = d["alias"] or "(未命名)"
    is_online = did in online
    hint = board_hint(did)
    hw = DeviceRepo.get_hw(did)
    caps = CapabilityRepo.get_by_device(did)
    pins = (hw.get("lamp_pins") or (hint or {}).get("lamp_pins"))
    pins_text = "、".join(f"GPIO{p}" for p in pins) if pins else "—"

    head = st.columns([2, 2.4, 1.2, 1.6, 2])
    head[0].markdown(f"**{alias}**  \n<small>`{did}`</small>", unsafe_allow_html=True)
    head[1].caption(f"串口：{(hint or {}).get('serial_port', '未记录')} ｜ 灯脚：{pins_text}"
                    + ("（本机覆盖）" if hw.get("lamp_pins") else ""))
    head[2].caption("🟢 在线" if is_online else "🔴 离线")
    head[3].caption(f"能力 {len(caps)} 条")

    with head[4]:
        b1, b2, b3 = st.columns(3)
        if b1.button("🔧", key=f"{P}hw_{did}", help="看硬件速查卡"):
            st.session_state[f"{P}show_hw"] = did if st.session_state.get(f"{P}show_hw") != did else None
            st.rerun()
        if b2.button("✏️", key=f"{P}edit_{did}", help="改名称 / 灯脚 / 本机备注"):
            st.session_state[f"{P}editing"] = did if st.session_state.get(f"{P}editing") != did else None
            st.rerun()
        if b3.button("🗑", key=f"{P}del_{did}", help="删除设备（会级联删能力与场景角色）"):
            st.session_state[f"{P}deleting"] = did if st.session_state.get(f"{P}deleting") != did else None
            st.rerun()

    # ---- 硬件速查卡 ----
    if st.session_state.get(f"{P}show_hw") == did:
        render_board_card(did, hint=hint, online=is_online)

    # ---- 编辑 ----
    if st.session_state.get(f"{P}editing") == did:
        with st.container(border=True):
            st.markdown(f"**✏️ 编辑：{alias}**")
            with st.form(f"{P}editform_{did}"):
                e_alias = st.text_input("名称", value=alias)
                e_type = st.text_input("类型", value=d.get("device_type") or "unknown")
                e_pins = st.text_input(
                    "灯脚（本机，逗号分隔；留空 = 用台账值）",
                    value=",".join(str(p) for p in hw.get("lamp_pins", [])),
                    help="只写这台机器实际的灯脚。台账原值不会被改。",
                )
                e_notes = st.text_area(
                    "本机备注（一行一条）",
                    value="\n".join(str(n) for n in hw.get("notes", [])),
                    height=110,
                    help="例如：灯组1 目前只接了 1 颗；GPIO48 那组没接线",
                )
                s1, s2 = st.columns(2)
                save = s1.form_submit_button("💾 保存", use_container_width=True, type="primary")
                cancel = s2.form_submit_button("取消", use_container_width=True)
            if save:
                try:
                    pins_val = parse_pins(e_pins)
                    notes = [ln.strip() for ln in e_notes.splitlines() if ln.strip()]
                    new_hw = {}
                    if pins_val:
                        new_hw["lamp_pins"] = pins_val
                    if notes:
                        new_hw["notes"] = notes
                    DeviceRepo.update(did, alias=e_alias.strip() or alias,
                                      device_type=e_type.strip() or "unknown")
                    DeviceRepo.set_hw(did, new_hw)
                    st.session_state[f"{P}editing"] = None
                    st.success("已保存")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
            if cancel:
                st.session_state[f"{P}editing"] = None
                st.rerun()

    # ---- 删除（要勾确认）----
    if st.session_state.get(f"{P}deleting") == did:
        with st.container(border=True):
            st.warning(
                f"删除 `{did}` 会**级联删掉**它的 {len(caps)} 条能力和场景角色配置"
                "（数据库里 ON DELETE CASCADE）。这一步不可撤销。"
            )
            confirm = st.checkbox("我确认删除这台设备及其全部能力", key=f"{P}confirm_{did}")
            d1, d2 = st.columns(2)
            if d1.button("🗑 确认删除", key=f"{P}do_{did}", disabled=not confirm,
                         use_container_width=True):
                if DeviceRepo.delete(did):
                    st.session_state[f"{P}deleting"] = None
                    st.success("已删除")
                    st.rerun()
                else:
                    st.error("删除失败")
            if d2.button("取消", key=f"{P}cancel_{did}", use_container_width=True):
                st.session_state[f"{P}deleting"] = None
                st.rerun()

    st.divider()
