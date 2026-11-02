# 元件自检框架（三台共用）：引擎 + 通用助手
# 具体测什么在各板 main/boards/<板>/selftest_items.c 里，本组件不含板相关代码。
idf_component_register(
    SRCS "selftest.c" "selftest_helpers.c"
    INCLUDE_DIRS "."
    REQUIRES driver esp_hw_support heap esp_common
    PRIV_REQUIRES freertos
)
