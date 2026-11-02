# ai_robot/tools/_device_page_test.py
"""
设备管理页面自检（Streamlit AppTest，起不了服务器也能跑；不碰真硬件）。

覆盖：
  1. 渲染无异常
  2. 在线设备里能认出“未登记”的 MOSS，并一键登记
  3. 本机灯脚 / 本机备注能保存进 devices.hw_json
  4. 硬件速查卡会把「本机备注」渲染出来（这是“不用翻固件”的关键）
  5. 删除要勾确认；删完库里真的没有

跑法：
  C:\\ProgramData\\miniconda3\\envs\\lzluck\\python.exe ai_robot\\tools\\_device_page_test.py
"""

import os
import sys

SERVER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "xiaozhi-server")
sys.path.insert(0, SERVER)

from streamlit.testing.v1 import AppTest  # noqa: E402
from core.data import DeviceRepo  # noqa: E402

PAGE = os.path.join(SERVER, "web_console", "pages", "设备管理.py")
MOSS = "58:e6:c5:5a:2f:fc"
NOTE = "灯组1 目前只接了 1 颗（count 用 1）"

fails = []
existed_before = DeviceRepo.exists(MOSS)
hw_before = DeviceRepo.get_hw(MOSS) if existed_before else {}


def check(name, cond, extra=""):
    print(("[OK ] " if cond else "[FAIL] ") + name + (f"\n     {extra}" if not cond and extra else ""))
    if not cond:
        fails.append(name)


def all_text(at):
    parts = []
    for attr in ("markdown", "title", "subheader", "caption", "text", "info", "warning",
                 "success", "error", "table"):
        for el in getattr(at, attr, []) or []:
            val = getattr(el, "value", None)
            if val is not None:
                parts.append(str(val))
    return "\n".join(parts)


def find_input(at, label, exact=False):
    for w in at.text_input:
        if (w.label == label) if exact else str(w.label).startswith(label):
            return w
    return None


def restore():
    """把数据库恢复到测试前状态。"""
    if not existed_before and DeviceRepo.exists(MOSS):
        DeviceRepo.delete(MOSS)
    elif existed_before:
        DeviceRepo.set_hw(MOSS, hw_before)


at = AppTest.from_file(PAGE, default_timeout=60)
at.run()
check("① 渲染无异常", not at.exception, [str(e.value) for e in at.exception])
check("② 标题是设备管理", any("设备管理" in str(t.value) for t in at.title), [t.value for t in at.title])
check("③ 有「刷新在线」按钮", any("刷新在线" in b.label for b in at.button), [b.label for b in at.button])

# ---- 在线设备里登记 MOSS ----
reg_btn = [b for b in at.button if b.key == f"dev_reg_{MOSS}"]
if not existed_before:
    check("④ 在线设备里认出了未登记的 MOSS", len(reg_btn) == 1, [b.key for b in at.button])
    if reg_btn:
        reg_btn[0].click().run()
    check("⑤ 点「登记它」后表单已预填", MOSS.upper() in all_text(at).upper(), all_text(at)[:300])

    add = [b for b in at.button if b.label == "➕ 登记"]
    check("⑥ 找到「➕ 登记」按钮", len(add) == 1, [b.label for b in at.button])
    if add:
        add[0].click().run()
    check("⑦ 设备真的入库", DeviceRepo.exists(MOSS), MOSS)
else:
    check("④（MOSS 已登记，跳过在线登记）", True)

# ---- 编辑：本机灯脚 + 本机备注 ----
edit_btn = [b for b in at.button if b.key == f"dev_edit_{MOSS}"]
check("⑧ 找到编辑按钮", len(edit_btn) == 1, [b.key for b in at.button if b.key and "edit" in b.key])
if edit_btn:
    edit_btn[0].click().run()

pins_in = find_input(at, "灯脚（本机")
notes_in = [t for t in at.text_area if str(t.label).startswith("本机备注")]
if pins_in:
    pins_in.set_value("7")
if notes_in:
    notes_in[0].set_value(NOTE)
at.run()

save = [b for b in at.button if b.label == "💾 保存"]
if save:
    save[0].click().run()

hw = DeviceRepo.get_hw(MOSS)
check("⑨ 本机灯脚存进 devices.hw_json", hw.get("lamp_pins") == [7], hw)
check("⑩ 本机备注存进 devices.hw_json", NOTE in (hw.get("notes") or []), hw)

# ---- 硬件卡要显示本机备注 ----
hw_btn = [b for b in at.button if b.key == f"dev_hw_{MOSS}"]
if hw_btn:
    hw_btn[0].click().run()
check("⑪ 硬件卡渲染出「本机备注」", "本机备注" in all_text(at), all_text(at)[-600:])
check("⑫ 硬件卡显示本机灯脚 GPIO7", "GPIO7" in all_text(at), "")

# ---- 删除要确认 ----
del_btn = [b for b in at.button if b.key == f"dev_del_{MOSS}"]
if del_btn:
    del_btn[0].click().run()
confirm_btn = [b for b in at.button if b.key == f"dev_do_{MOSS}"]
check("⑬ 删除按钮未勾确认时是禁用的",
      bool(confirm_btn) and confirm_btn[0].disabled is True,
      [(b.key, b.disabled) for b in at.button if b.key and "do_" in b.key])
cb = [c for c in at.checkbox if c.key == f"dev_confirm_{MOSS}"]
if cb:
    cb[0].check()
at.run()
confirm_btn = [b for b in at.button if b.key == f"dev_do_{MOSS}"]
if confirm_btn:
    confirm_btn[0].click().run()
check("⑭ 勾确认后能删掉", not DeviceRepo.exists(MOSS), "还存在于库里")

restore()
print(f"\n通过 {14 - len(fails)} 项，失败 {len(fails)} 项")
sys.exit(1 if fails else 0)
