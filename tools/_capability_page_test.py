# ai_robot/tools/_capability_page_test.py
"""
能力库页面自检（Streamlit AppTest，不需要起服务器；**不点「执行」，不碰真硬件**）。

覆盖：
  1. 渲染无异常；① 设备 + 硬件速查卡（MCU/串口/引脚/换设备跟着换）
  2. ② 能力清单：注入一条能力 → 出现在列表 → ✏️ 能打开 → 🗑 能删
  3. ③ 指令输入框：默认示例解析成正确信封；坏 JSON 直接报错且不显示信封

跑法：
  C:\\ProgramData\\miniconda3\\envs\\lzluck\\python.exe ai_robot\\tools\\_capability_page_test.py
"""

import os
import sys

SERVER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "xiaozhi-server")
sys.path.insert(0, SERVER)

from streamlit.testing.v1 import AppTest  # noqa: E402
from core.data import CapabilityRepo, DeviceRepo  # noqa: E402

PAGE = os.path.join(SERVER, "web_console", "pages", "能力库管理.py")
MOSS = "58:e6:c5:5a:2f:fc"
TEST_NAME = "自检-亮红灯"
TEST_CAP_ID = "cap_selftest_0001"

fails = []


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


# ---- 准备：MOSS 必须先存在（外键），测试结束恢复 ----
moss_existed = DeviceRepo.exists(MOSS)
if not moss_existed:
    DeviceRepo.create(MOSS, "MOSS 550W", "robot")
if CapabilityRepo.get_by_id(TEST_CAP_ID):
    CapabilityRepo.delete(TEST_CAP_ID)

at = AppTest.from_file(PAGE, default_timeout=60)
at.run()
check("① 渲染无异常", not at.exception, [str(e.value) for e in at.exception])
check("② 标题是能力库", any("能力库" in str(t.value) for t in at.title), [t.value for t in at.title])

sels = [s for s in at.selectbox if s.label == "选择设备"]
check("③ 有设备选择器", len(sels) == 1, [s.label for s in at.selectbox])

text = all_text(at)
check("④ 速查卡有 MCU / 串口", "MCU：" in text and "串口：" in text, text[:300])
check("⑤ 速查卡有引脚表（GPIO7）", "GPIO7" in text, text[:300])

if sels:
    cur = sels[0].value
    others = [o for o in sels[0].options if o != cur]
    if others:
        at.selectbox(key=sels[0].key).set_value(others[0]).run()
        check("⑥ 换设备后卡片跟着换", all_text(at) != text, "两次渲染完全相同")

# ---- ③ 指令输入框 ----
areas = [a for a in at.text_area if a.label == "指令 JSON"]
check("⑦ 有「指令 JSON」输入框", len(areas) == 1, [a.label for a in at.text_area])
check("⑧ 默认示例已解析出信封",
      '"type":"command"' in "".join(c.value for c in at.code), [c.value[:80] for c in at.code][:3])

if areas:
    areas[0].set_value("{这不是 json")
at.run()
check("⑨ 坏 JSON 会报错且不发", any("没解析成功" in str(e.value) for e in at.error),
      [str(e.value) for e in at.error])
check("⑩ 坏 JSON 时没有信封预览", "type&#34;:&#34;command" not in all_text(at) and
      not any('"type":"command"' in c.value for c in at.code), [c.value[:60] for c in at.code][:3])

# 恢复合法
areas = [a for a in at.text_area if a.label == "指令 JSON"]
if areas:
    areas[0].set_value('{"actions":[{"type":"ws2812","pin":7,"count":1,"rgb":[64,0,0]}]}')
at.run()
check("⑪ 合法写法（只有 payload）也能出信封",
      any('"type":"command"' in c.value and '"pin":7' in c.value for c in at.code),
      [c.value[:100] for c in at.code][:3])

# ---- ② 清单：注入 → 出现 → 编辑 → 删除 ----
CapabilityRepo.create(TEST_CAP_ID, MOSS, TEST_NAME,
                      {"actions": [{"type": "ws2812", "pin": 7, "count": 1, "rgb": [64, 0, 0]}]},
                      description="自检用", llm_visible=True)
at.run()
check("⑫ 注入的能力出现在列表", TEST_NAME in all_text(at), all_text(at)[-400:])

edit = [b for b in at.button if b.key == f"cap_edit_{TEST_CAP_ID}"]
check("⑬ 有 ✏️ 编辑按钮", len(edit) == 1, [b.key for b in at.button if b.key and "edit" in b.key])
if edit:
    edit[0].click().run()
check("⑭ 编辑表单能打开", any("✏️ 编辑" in str(m.value) for m in at.markdown),
      [str(m.value)[:40] for m in at.markdown][:6])

dele = [b for b in at.button if b.key == f"cap_del_{TEST_CAP_ID}"]
check("⑮ 有 🗑 删除按钮", len(dele) == 1, [b.key for b in at.button if b.key and "del" in b.key])
if dele:
    dele[0].click().run()
check("⑯ 删掉后库里没有", CapabilityRepo.get_by_id(TEST_CAP_ID) is None)

# ---- 收尾 ----
if CapabilityRepo.get_by_id(TEST_CAP_ID):
    CapabilityRepo.delete(TEST_CAP_ID)
if not moss_existed and DeviceRepo.exists(MOSS):
    DeviceRepo.delete(MOSS)

print(f"\n通过 {16 - len(fails)} 项，失败 {len(fails)} 项")
sys.exit(1 if fails else 0)
