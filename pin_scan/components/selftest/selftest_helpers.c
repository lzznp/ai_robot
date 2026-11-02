// ============================================================
// selftest_helpers.c — 自检项共用的打印/扫描助手
// ============================================================

#include "selftest_helpers.h"

#include <stdio.h>

#include "esp_err.h"
#include "esp_system.h"
#include "esp_chip_info.h"
#include "esp_mac.h"
#include "esp_heap_caps.h"
#include "driver/i2c_master.h"

void st_print_sep(void)
{
    printf("-------------------------------------------------\n");
}

// ------------------------------------------------------------
// 系统信息
// ------------------------------------------------------------
void st_print_sysinfo(void)
{
    esp_chip_info_t info;
    esp_chip_info(&info);

    const char *model = "unknown";
    switch (info.model) {
        case CHIP_ESP32S2: model = "ESP32-S2"; break;
        case CHIP_ESP32S3: model = "ESP32-S3"; break;
        case CHIP_ESP32C3: model = "ESP32-C3"; break;
        case CHIP_ESP32C6: model = "ESP32-C6"; break;
        default: break;
    }

    uint8_t mac[6] = {0};
    esp_read_mac(mac, ESP_MAC_WIFI_STA);

    printf("芯片型号   : %s  rev%d.%d   %d 核\n", model, info.revision / 100,
           info.revision % 100, info.cores);
    printf("主频       : %d MHz\n", (int)CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ);
    printf("WiFi MAC   : %02X:%02X:%02X:%02X:%02X:%02X\n",
           mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
    printf("复位原因   : %d\n", (int)esp_reset_reason());
    printf("内部空闲堆 : %u 字节\n", (unsigned)esp_get_free_heap_size());
    printf("PSRAM 总量 : %u 字节\n",
           (unsigned)heap_caps_get_total_size(MALLOC_CAP_SPIRAM));

    st_print_sep();
    printf("说明：这一项只要能看到输出，就证明\n");
    printf("      芯片在跑 / 串口通 / 固件是这一份。\n");
}

// ------------------------------------------------------------
// I2C 扫描
//
// 扫到地址不等于知道是谁：先确认"板上有没有那个器件"。
// MOSS 550W 的 0x3C 是摄像头（OV5640 SCCB），不是 OLED 屏
// （网表里一颗显示驱动 IC 都没有，见 MOSS-硬件台账.md 三③）。
// ------------------------------------------------------------
static const char *i2c_name(uint16_t addr)
{
    switch (addr) {
        // ---- 屏 / 摄像头 ----
        case 0x3C: return "  <-- OLED 屏(SSD1306) 或 摄像头 SCCB(OV5640)，先看板上装的是哪个";
        case 0x3D: return "  <-- OLED 备用地址 (0x3C 被占时试这个)";
        case 0x30: return "  <-- 摄像头 SCCB (OV2640)";
        case 0x31: return "  <-- 摄像头 SCCB 备用";
        // ---- 音频 codec ----
        case 0x18: return "  <-- 音频 codec (ES8311)";
        case 0x10: return "  <-- 音频 codec (ES7243E 同类)";
        case 0x1A: return "  <-- 音频 codec (ES8388 之类)";
        // ---- IO 扩展 / 触摸 ----
        case 0x20: return "  <-- IO 扩展 (TCA6408 / PCF8574)";
        case 0x21: return "  <-- IO 扩展 备用地址";
        case 0x38: return "  <-- 触摸 (FT5x06) 或 AXP192 电源";
        case 0x15: return "  <-- 触摸备用地址 (FT5x06 变体)";
        // ---- 其它 ----
        case 0x51: return "  <-- RTC / EEPROM";
        case 0x68: return "  <-- RTC (DS3231 之类)";
        default:   return "";
    }
}

void st_i2c_scan(int port, int sda, int scl, const char *why)
{
    printf("扫描目标: I2C%d  SDA=GPIO%d  SCL=GPIO%d   %s\n", port, sda, scl,
           why ? why : "");

    i2c_master_bus_config_t cfg = {0};
    cfg.i2c_port = (i2c_port_num_t)port;
    cfg.sda_io_num = (gpio_num_t)sda;
    cfg.scl_io_num = (gpio_num_t)scl;
    cfg.clk_source = I2C_CLK_SRC_DEFAULT;
    cfg.glitch_ignore_cnt = 7;
    cfg.flags.enable_internal_pullup = true;

    i2c_master_bus_handle_t bus = NULL;
    esp_err_t err = i2c_new_master_bus(&cfg, &bus);
    if (err != ESP_OK) {
        printf("  [X] 创建 I2C 总线失败: %s\n", esp_err_to_name(err));
        printf("      （引脚可能被别的外设占住）\n");
        return;
    }

    int found = 0;
    for (uint16_t addr = 0x08; addr < 0x78; addr++) {
        if (i2c_master_probe(bus, addr, 30) == ESP_OK) {
            printf("  [OK] 发现设备 0x%02X%s\n", addr, i2c_name(addr));
            found++;
        }
    }

    if (found == 0) {
        printf("  [X] 一个设备都没扫到\n");
        printf("      可能原因：1 SDA/SCL 接反  2 目标器件没接/没供电  3 总线被拉死\n");
    } else {
        printf("  共 %d 个设备\n", found);
    }

    i2c_del_master_bus(bus);
}
