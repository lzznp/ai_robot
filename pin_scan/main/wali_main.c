// ============================================================
// wali_main.c — 瓦力自检固件的入口
// 直接进自检循环（不连 WiFi、不跑 Application），项表在 wali_items.cc
// ============================================================

#include "selftest.h"

// 项表定义在 wali_items.cc 里
extern const st_config_t wali_selftest_config;

void app_main(void)
{
    st_run(&wali_selftest_config);   // 不返回
}
