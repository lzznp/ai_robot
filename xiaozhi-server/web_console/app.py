"""
AI 剧场 · 控制台入口（Streamlit）。

起法（工作目录无所谓，路径都按本文件位置算）：
    python -m streamlit run app.py
或者 PyCharm：Module name=streamlit，Parameters=run app.py。

为什么不用 st_pages：
    本项目装的是 Streamlit 1.55，而 `st_pages`（1.0.1）的 `add_page_title()` 会读
    `StreamlitPage.title` → `self._title`；但 Streamlit 1.55 的 StreamlitPage 在
    **没有脚本运行时上下文**时会提前 return，`_title` / `_page` 都没被赋值，
    于是报 `AttributeError: 'StreamlitPage' object has no attribute '_title'`。
    删掉 add_page_title 也只是把错误挪到 `pg.run()`（同一个空壳对象）。
    ⇒ 改用 Streamlit 原生 `st.Page` + `st.navigation`，`config/pages.toml` 仍是唯一配置。
    页面标题由各页自己的 `st.title()` 负责（1.55 支持多次追加式 `set_page_config`，
    所以页面里那句 `st.set_page_config` 不会和下面这句打架）。
"""

from pathlib import Path
import tomllib

import streamlit as st

CONFIG_DIR = Path(__file__).parent
PAGES_TOML = CONFIG_DIR / "config" / "pages.toml"

st.set_page_config(
    page_title="AI剧场管理系统",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)


def build_navigation(toml_path: Path):
    """把 config/pages.toml 读成 st.navigation 要的结构。

    toml 结构（见 config/pages.toml）：
        [[pages]] name=... icon=... is_section=true     ← 分组标题
        [[pages]] path=... name=... icon=...            ← 具体页面
    返回 {分组标题: [st.Page, ...]}；分组之前的页面放进 "" 组。
    """
    with open(toml_path, "rb") as f:
        data = tomllib.load(f)

    nav: dict[str, list] = {}
    current_section = ""
    is_first_page = True

    for entry in data.get("pages", []):
        icon = (entry.get("icon") or "").strip()
        name = (entry.get("name") or "").strip()

        if entry.get("is_section"):
            current_section = f"{icon} {name}".strip()
            nav.setdefault(current_section, [])
            continue

        page_path = entry.get("path")
        if not page_path:
            continue

        page = st.Page(
            page_path,
            title=name or Path(page_path).stem,
            icon=icon or None,
            default=is_first_page,       # 第一篇当默认页，避免 Streamlit 自己挑
        )
        is_first_page = False
        nav.setdefault(current_section, []).append(page)

    return nav


nav = build_navigation(PAGES_TOML)
# st.sidebar 顶部系统名（原来是注释掉的，保留注释位置）
# with st.sidebar:
#     st.markdown("### 🎯 AI 剧场")
#     st.divider()

pg = st.navigation(nav)
pg.run()
