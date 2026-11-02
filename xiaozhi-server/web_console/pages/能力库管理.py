"""
能力库 —— 后台唯一的主力页面。

    ① 设备 + 硬件速查卡（台账 + 本机备注）
    ② 这台设备已有的能力（▶ 重放 / ✏️ 编辑 / 🗑 删除）
    ③ 发送指令：**一个输入框**，粘 JSON → 执行 → 看固件表现（不造表单、不入库）

设计依据：`工作文档\\后台框架·一页纸_20261101.md`
  · §1 铁律：Streamlit 是**另一个进程** → 只直读 SQLite + HTTP 打 8004，禁止 import 后台对象。
  · §4 动作词汇表：字段/判据来自 `core/actions.py`（唯一真相源）。
  · D1：能力库存 **payload**（`{"actions":[...]}`），信封由 `build_command()` / `normalize_command_input()` 统一包。
  · 硬件资料来自 `KNOWN_BOARDS` + `devices.hw_json`，页面不另存一份。

③ 为什么是"输入框"而不是"动作表单"（2026-11-01 用户定）：
    这些指令是**人和 AI 一条条试出来的**，不是让用户在下拉框里拼字段。
    所以这里只做：粘贴 → 看清最终信封 → 执行 → 看串口/实物。
    "命名成能力 / 存库 / 交给 LLM" 等测通之后再单独设计。
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import json
import time

import requests
import streamlit as st

from core.actions import (
    board_hint,
    build_command,
    canonical_json,
    judge_hint,
    normalize_command_input,
    queue_warnings,
)
from core.data import CapabilityRepo, DeviceRepo
from web_console.ui_components import fetch_online, render_board_card

API_BASE = "http://192.168.199.106:8004"
P = "cap_"

st.set_page_config(page_title="能力库", page_icon="🧩", layout="wide")
st.title("🧩 能力库")
st.caption(
    "① 设备 ② 已有能力 ③ 发指令测固件。"
    "**HTTP 200 只代表 ws 写成功，不代表设备执行了**；判据是串口日志 + 实物。"
)

for _k, _v in {"logs": []}.items():
    if f"{P}{_k}" not in st.session_state:
        st.session_state[f"{P}{_k}"] = _v


# ============================================================================
# 与后台通信（只有 HTTP 这一条路）
# ============================================================================
def post_command(api_base: str, device_id: str, command: dict):
    try:
        resp = requests.post(
            f"{api_base}/api/command",
            json={"device_id": device_id, "command": command},
            timeout=5,
        )
        try:
            return resp.status_code, resp.json()
        except ValueError:
            return resp.status_code, {"success": False, "message": resp.text[:200]}
    except Exception as e:
        return None, {"success": False, "message": f"{type(e).__name__}: {e}"}


def add_log(device_id: str, payload: dict, ok: bool, message: str):
    st.session_state[f"{P}logs"].insert(0, {
        "t": time.strftime("%H:%M:%S"),
        "device": device_id,
        "payload": canonical_json(payload),
        "ok": ok,
        "msg": message,
    })
    st.session_state[f"{P}logs"] = st.session_state[f"{P}logs"][:40]


def parse_payload(raw):
    """把库里存的 command 取成 payload(dict)。

    `device_capabilities.command` 是 TEXT（写入时 json.dumps），读出来是字符串；
    直接当 dict 发会被 /api/command 的类型校验拒掉（400）。
    """
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return None
    if not isinstance(raw, dict):
        return None
    if raw.get("type") == "command" and isinstance(raw.get("payload"), dict):
        return raw["payload"]
    if "actions" in raw or "tts" in raw or "emotion" in raw:
        return raw
    return None


# ============================================================================
# ① 设备
# ============================================================================
online, online_err = fetch_online(API_BASE)
registered = DeviceRepo.get_all()
registered_ids = {d["id"].lower() for d in registered}

options = []
for d in registered:
    did = d["id"].lower()
    options.append((did, f"{'🟢' if did in online else '🔴'} {d['alias']} ({did})"))
for did in online:
    if did not in registered_ids:
        options.append((did, f"🟢 未登记 ({did})"))

st.subheader("① 设备")

c_sel, c_btn = st.columns([5, 1])
device_id, hint = "", None

if not options:
    with c_sel:
        st.warning("没有任何设备：先去「设备管理」登记一台。")
else:
    labels = [lbl for _, lbl in options]
    label_to_id = {lbl: did for did, lbl in options}

    cur = st.session_state.get(f"{P}device_label")
    if cur not in labels:
        st.session_state.pop(f"{P}device_label", None)

    default_label = (
        next((lbl for lbl in labels if lbl.startswith("🟢")), None)
        or next((lbl for lbl in labels if "moss" in lbl.lower()), None)
        or labels[0]
    )
    with c_sel:
        device_label = st.selectbox(
            "选择设备", labels,
            index=labels.index(default_label),
            key=f"{P}device_label",
            help="🟢 = 后台现在连得到它（/api/devices）；🔴 = 离线，发指令会 404",
        )
    device_id = label_to_id[device_label]
    hint = board_hint(device_id)

    with c_btn:
        st.write("")
        st.write("")
        if st.button("🔄 刷新在线", use_container_width=True):
            fetch_online.clear()
            st.rerun()

    if device_id in online:
        st.success(f"在线：`{device_id}`")
    else:
        st.warning(f"离线：`{device_id}` —— 发指令会直接 404（不会假成功）。"
                   + (f"  接口错误：{online_err}" if online_err else ""))

    render_board_card(device_id, hint=hint, online=(device_id in online))

st.divider()

# ============================================================================
# ② 这台设备的能力
# ============================================================================
st.subheader("② 这台设备的能力")


def _send_from_capability(cap: dict, payload: dict) -> None:
    if not device_id:
        st.error("先选设备")
        return
    if device_id not in online:
        st.error(f"设备 `{device_id}` 不在线，指令发不出去（404）")
        return
    status, result = post_command(API_BASE, device_id, build_command(
        actions=payload.get("actions"), tts=payload.get("tts"), emotion=payload.get("emotion")))
    ok = bool(result.get("success"))
    add_log(device_id, payload, ok, f"{status} {result.get('message', '')}")
    if ok:
        st.success(f"✅ 已写进 ws：{cap.get('name')} —— 现在看串口 + 实物")
    else:
        st.error(f"❌ 下发失败：{result.get('message')}")


if not device_id:
    st.info("先在上面选一台设备。")
else:
    caps = CapabilityRepo.get_by_device(device_id)

    if not caps:
        st.info("📭 这台设备还没有能力。（能力 = 测通之后命名的指令，等我们下一步再定怎么存）")
    else:
        edited = st.session_state.get(f"{P}editing_cap")
        for cap in caps:
            payload = parse_payload(cap.get("command"))
            cols = st.columns([2.2, 0.8, 0.9, 1.6])
            cols[0].markdown(f"**{cap['name']}**  \n<small>{cap.get('description') or '—'}</small>",
                             unsafe_allow_html=True)
            cols[1].caption("LLM 可见" if cap.get("llm_visible") else "仅后台")
            cols[2].caption(cap.get("capability_type") or "atomic")

            with cols[3]:
                b1, b2, b3 = st.columns(3)
                if b1.button("▶", key=f"{P}play_{cap['id']}", help="重放这条 payload"):
                    if payload:
                        _send_from_capability(cap, payload)
                    else:
                        st.error("这条能力的 command 不是合法 JSON，先点 ✏️ 修")
                if b2.button("✏️", key=f"{P}edit_{cap['id']}"):
                    st.session_state[f"{P}editing_cap"] = cap["id"]
                    st.rerun()
                if b3.button("🗑", key=f"{P}del_{cap['id']}"):
                    if CapabilityRepo.delete(cap["id"]):
                        st.success(f"已删除 {cap['name']}")
                        st.rerun()

            with st.expander("看 payload"):
                st.code(canonical_json(payload) if payload else str(cap.get("command")), language="json")
            st.divider()

        # ---- 编辑 ----
        if edited:
            cap = next((c for c in caps if c["id"] == edited), None)
            if not cap:
                st.session_state[f"{P}editing_cap"] = None
            else:
                payload = parse_payload(cap.get("command"))
                with st.container(border=True):
                    st.markdown(f"**✏️ 编辑：{cap['name']}**")
                    with st.form(f"{P}editform_{cap['id']}"):
                        e_name = st.text_input("名称", value=cap["name"])
                        e_desc = st.text_area("描述", value=cap.get("description") or "", height=60)
                        e_type = st.selectbox("能力类型", ["atomic", "composite"],
                                              index=0 if (cap.get("capability_type") or "atomic") == "atomic" else 1)
                        e_visible = st.checkbox("上报给 LLM", value=bool(cap.get("llm_visible")))
                        e_payload = st.text_area(
                            "payload JSON（只存 payload，不要包 type/payload 信封）",
                            value=json.dumps(payload, ensure_ascii=False, indent=2) if payload else "",
                            height=180,
                        )
                        c1, c2 = st.columns(2)
                        save = c1.form_submit_button("💾 保存", use_container_width=True)
                        cancel = c2.form_submit_button("取消", use_container_width=True)
                    if save:
                        try:
                            new_payload = json.loads(e_payload)
                            if not isinstance(new_payload, dict):
                                raise ValueError("payload 必须是 JSON 对象")
                            CapabilityRepo.update(cap["id"], name=e_name, description=e_desc,
                                                  command=new_payload, capability_type=e_type,
                                                  llm_visible=e_visible)
                            st.session_state[f"{P}editing_cap"] = None
                            st.rerun()
                        except (json.JSONDecodeError, ValueError) as e:
                            st.error(f"payload 不是合法 JSON：{e}")
                    if cancel:
                        st.session_state[f"{P}editing_cap"] = None
                        st.rerun()

st.divider()

# ============================================================================
# ③ 发送指令（一个输入框）
# ============================================================================
st.subheader("③ 发送指令（测固件）")
st.caption(
    "把 JSON 粘进来就行 —— **整封信封 / 只有 payload / 单条动作** 三种写法都认。"
    "发出去之前会显示最终信封；发完看串口和实物。"
)

lamp_pins = (hint or {}).get("lamp_pins") or []
sample_pin = lamp_pins[0] if lamp_pins else 5

if f"{P}cmd_text" not in st.session_state:
    st.session_state[f"{P}cmd_text"] = canonical_json({
        "actions": [{"type": "ws2812", "pin": sample_pin, "count": 1, "rgb": [64, 0, 0]}]
    })

cmd_text = st.text_area(
    "指令 JSON", key=f"{P}cmd_text", height=170,
    help="可以让 AI 给你一段，直接粘进来；不合法会在下面直接报错，不会发出去",
)

envelope, parse_err = None, ""
if cmd_text and cmd_text.strip():
    try:
        envelope = normalize_command_input(cmd_text)
    except ValueError as e:
        parse_err = str(e)

if parse_err:
    st.error(f"❌ 这段没解析成功：{parse_err}")
elif envelope:
    st.caption("最终发出去的 command（后台原样转发给设备）：")
    st.code(canonical_json(envelope), language="json")

    acts = (envelope.get("payload") or {}).get("actions") or []
    if acts:
        for w in queue_warnings(acts):
            st.warning(w)
        if hint and hint.get("lamp_pins"):
            for act in acts:
                if act.get("type") == "ws2812" and act.get("pin") not in hint["lamp_pins"]:
                    st.warning(f"台账里 {hint['alias']} 的灯脚是 {hint['lamp_pins']}，"
                               f"这条发的是 pin={act.get('pin')} —— 先确认接线，灯不亮不是固件的错。")
        with st.container(border=True):
            st.markdown("**判据（串口 + 实物，两样都要）**")
            for i, act in enumerate(acts, 1):
                st.text(f"{i}. {judge_hint(act)}")
            st.caption("`tts` 动作只打日志不出声；`delay` 的 duration 不生效（固件固定 100ms）。")

    send = st.button(
        "🚀 执行（发到设备）", type="primary", use_container_width=True,
        disabled=(not device_id or device_id not in online),
    )
    if send:
        status, result = post_command(API_BASE, device_id, envelope)
        ok = bool(result.get("success"))
        add_log(device_id, (envelope.get("payload") or {}), ok, f"{status} {result.get('message', '')}")
        if status == 404:
            st.error(f"❌ 设备不在线：{result.get('message', '')}")
        elif ok:
            st.success(f"✅ 已写进 ws：{result.get('message', '')} —— 现在去看串口 + 实物")
        else:
            st.error(f"❌ 下发失败：{result.get('message', '')}")
else:
    st.info("把指令 JSON 粘进上面那个框。")

with st.expander("📋 常用示例（点右上角图标可复制）"):
    st.caption("ws2812：亮红 / 关灯")
    st.code(canonical_json({"actions": [{"type": "ws2812", "pin": sample_pin, "count": 1, "rgb": [64, 0, 0]}]}),
            language="json")
    st.code(canonical_json({"actions": [{"type": "ws2812", "pin": sample_pin, "count": 1, "rgb": [0, 0, 0]}]}),
            language="json")
    st.caption("gpio：拉高 1 秒（17 号脚在 MOSS 上是摄像头 D6，别乱发）")
    st.code(canonical_json({"actions": [{"type": "gpio", "pin": 17, "level": 1, "duration": 1000}]}),
            language="json")
    st.caption("单条动作写法（等价于上面第一段）")
    st.code(canonical_json({"type": "ws2812", "pin": sample_pin, "count": 1, "rgb": [64, 0, 0]}),
            language="json")

# ============================================================================
# 发送日志
# ============================================================================
logs = st.session_state[f"{P}logs"]
with st.expander(f"📋 发送日志（{len(logs)} 条，只在本会话）", expanded=False):
    if not logs:
        st.caption("还没有发送记录。")
    else:
        if st.button("🗑 清空日志", key=f"{P}clearlogs"):
            st.session_state[f"{P}logs"] = []
            st.rerun()
        for e in logs:
            st.text(f"[{e['t']}] {'✅' if e['ok'] else '❌'} {e['device']}")
            st.caption(f"    {e['msg']}")
            st.code(e["payload"], language="json")
