import streamlit as st
from st_pages import add_page_title, get_nav_from_toml,hide_pages

import  os

# 页面配置
st.set_page_config(
    page_title="AI剧场管理系统",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)



# 在侧边栏顶部添加系统名称
# with st.sidebar:
#     st.markdown("### 🎯 智能猎头系统")
#     st.divider()  # 分割线，让标题和导航项更美观


# 直接读取带分组的导航配置文件
nav = get_nav_from_toml("config/pages.toml")

#hide_pages(["岗位编辑"])




# 创建导航对象
pg = st.navigation(nav)



# 自动添加页面标题
add_page_title(pg)

# 运行选中的页面
pg.run()