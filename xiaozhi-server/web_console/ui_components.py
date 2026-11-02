# web_console/ui_components.py
"""
控制台共用的 UI 组件。

规矩：只依赖 `core.actions`（纯数据）和 `core.data`（直读 SQLite），
**不 import 后台进程里的任何对象**（Streamlit 是另一个进程，
见 工作文档\\后台框架·一页纸_20261101.md §1 铁律 2）。

硬件资料分两层，别混：
  1. `core.actions.KNOWN_BOARDS` —— **固件/设计事实**（来自硬件台账 + 各板 config.h，
     跟固件一起 review）。页面不另存一份。
  2. `devices.hw_json` —— **这台机器的实物现状/备注**（会变，页面上可改）：
        {"lamp_pins": [7], "notes": ["灯组1 目前只接了 1 颗"]}
     只做“覆盖 / 补充”，渲染时明确标出「本机」，避免变成第二个真相源。
"""

from typing import Any, Dict, Optional, Tuple

import requests
import streamlit as st

from core.actions import ACTION_SPECS, board_hint, normalize_device_id, supports_text
from core.data import DeviceRepo


@st.cache_data(ttl=5, show_spinner=False)
def fetch_online(api_base: str) -> Tuple[Dict[str, Any], str]:
    """GET /api/devices → ({小写 device_id: 信息}, 错误文本)。

    ⚠️ 这是唯一可靠的“在不在线”来源：`devices.online` 是死字段（永远 0）。
    """
    try:
        resp = requests.get(f"{api_base}/api/devices", timeout=3)
        data = resp.json()
        if data.get("success"):
            return {str(d.get("device_id", "")).lower(): d for d in data.get("devices", [])}, ""
        return {}, data.get("message") or "接口返回 success=false"
    except Exception as e:
        return {}, f"{type(e).__name__}: {e}"


def device_online_text(device_id: str, online: Dict[str, Any], err: str = "") -> str:
    if device_id.lower() in online:
        return "🟢 在线"
    return "🔴 离线" + (f"（接口错误：{err}）" if err else "")


def render_board_card(device_id: str, hint: Optional[Dict[str, Any]] = None,
                      online: Optional[bool] = None) -> None:
    """渲染“这台板是什么、引脚在哪、固件认哪些动作”的速查卡（台账 + 本机备注合并）。"""
    hint = hint if hint is not None else board_hint(device_id)
    hw = DeviceRepo.get_hw(device_id) if DeviceRepo.exists(device_id) else {}

    if not hint and not hw:
        st.info(
            "这台设备不在已知硬件资料里（`core/actions.py` 的 `KNOWN_BOARDS`），也没有本机备注。\n\n"
            "要加：按台账补一条 alias / mcu / serial_port / lamp_pins / supports / hardware，"
            "**未实测的项写 None 或“未验”**，别写推测；单台的特殊情况写在「设备管理」的本机备注里。"
        )
        return

    hint = hint or {}

    with st.container(border=True):
        title = f"🔧 {hint.get('alias') or normalize_device_id(device_id)} ｜ `{normalize_device_id(device_id)}`"
        if online is True:
            title += " ｜ 🟢 在线"
        elif online is False:
            title += " ｜ 🔴 离线"
        st.markdown(f"**{title}**")

        if hint:
            st.caption(f"MCU：{hint.get('mcu', '未记录')} ｜ 串口：{hint.get('serial_port', '未记录')}")
        else:
            st.caption("（没有固件/台账资料，只有本机备注）")

        # ---- 灯脚：本机覆盖优先，但把台账值一起显示，别让人以为台账被改没了 ----
        stock_pins = hint.get("lamp_pins")
        local_pins = hw.get("lamp_pins")
        if local_pins or stock_pins:
            def pins_text(pins):
                return "、".join(f"GPIO{p}" for p in pins) if pins else "无"
            line = f"灯脚（本机）：**{pins_text(local_pins or stock_pins)}**"
            if local_pins and stock_pins and list(local_pins) != list(stock_pins):
                line += f"　＜台账原值：{pins_text(stock_pins)}＞"
            st.markdown(line)

        rows = hint.get("hardware") or []
        if rows:
            st.table({
                "部位": [r[0] for r in rows],
                "引脚 / 硬件事实（台账）": [r[1] for r in rows],
            })
        elif hint:
            st.caption("（这块板没有记录引脚表）")

        if hint:
            caps = []
            for kind in ACTION_SPECS:
                flag = (hint.get("supports") or {}).get(kind)
                caps.append(f"{kind} {supports_text(flag)}")
            st.caption("固件动作：" + "　".join(caps))
            if hint.get("verified_at"):
                st.caption(f"台账验证情况：{hint['verified_at']}")
            for note in hint.get("notes", []):
                st.caption("· " + note)

        # ---- 本机备注：这台机器此刻的实际情况（用户可改）----
        local_notes = hw.get("notes") or []
        if local_notes:
            st.markdown("**📝 本机备注**")
            for note in local_notes:
                st.caption("· " + str(note))
        else:
            st.caption("📝 本机备注：（空 —— 可在「设备管理」里加，例如“灯组1 目前只接了 1 颗”）")
