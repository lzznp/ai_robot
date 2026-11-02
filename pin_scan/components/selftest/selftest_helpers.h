// ============================================================
// selftest_helpers.h — 各板自检项共用的打印/扫描助手
// ============================================================

#ifndef ST_SELFTEST_HELPERS_H
#define ST_SELFTEST_HELPERS_H

#ifdef __cplusplus
extern "C" {
#endif

// 分隔线
void st_print_sep(void);

// 系统信息：芯片 / 主频 / MAC / 复位原因 / 堆 / PSRAM
// 判据：能看到输出 = 芯片在跑 + 串口通 + 固件是这一份
void st_print_sysinfo(void);

// I2C 总线扫描（0x08..0x77），打印每个应答地址
// port = I2C 端口号（MOSS 用 0，lingkong 用 1 —— 各板不同，别写死）
// sda/scl 传 GPIO 号；why = 这次扫描的用途说明（会打印出来）
void st_i2c_scan(int port, int sda, int scl, const char *why);

#ifdef __cplusplus
}
#endif

#endif  // ST_SELFTEST_HELPERS_H
