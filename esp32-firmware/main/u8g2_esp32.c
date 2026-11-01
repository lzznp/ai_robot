// main/u8g2_esp32.c
// U8g2 I2C 硬件适配层（使用新版 I2C driver_ng API）
// 修改：将旧版 driver/i2c.h 替换为 driver/i2c_master.h，解决 I2C 驱动冲突
#include "u8g2.h"
#include "driver/i2c_master.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_rom_sys.h"

static const char *TAG = "U8G2_ESP32";

#define I2C_MASTER_TIMEOUT_MS 100

// I2C 总线句柄（由 board 层通过 u8g2_esp32_set_i2c_bus() 设置）
static i2c_master_bus_handle_t g_u8g2_i2c_bus = NULL;
// 缓存的设备句柄（避免每次传输都 add/remove device）
static i2c_master_dev_handle_t g_u8g2_i2c_dev = NULL;
static uint8_t g_u8g2_i2c_dev_addr = 0;


// I2C 发送回调函数
uint8_t u8g2_esp32_i2c_tx(u8x8_t *u8x8, uint8_t msg, uint8_t arg_int, void *arg_ptr) {
    switch(msg) {
        case U8X8_MSG_BYTE_INIT: {
            ESP_LOGI(TAG, "U8X8_MSG_BYTE_INIT");
            break;
        }
        case U8X8_MSG_BYTE_SEND: {
            uint8_t *data = (uint8_t *)arg_ptr;
            uint8_t addr_raw = u8x8_GetI2CAddress(u8x8);
            uint8_t addr = addr_raw >> 1;

            // ============================================================
            // 📋 详细日志：打印地址和数据
            // ============================================================
            ESP_LOGI(TAG, "📤 SEND: raw_addr=0x%02X, 7bit_addr=0x%02X, len=%d",
                     addr_raw, addr, arg_int);

            // 打印前 16 个字节的数据（十六进制）
            if (arg_int > 0) {
                char hex_str[64] = {0};
                int len = arg_int > 16 ? 16 : arg_int;
                for (int i = 0; i < len; i++) {
                    sprintf(hex_str + i * 3, "%02X ", data[i]);
                }
                ESP_LOGI(TAG, "📦 Data: %s%s", hex_str, arg_int > 16 ? "..." : "");
            }

            // 检查总线句柄是否有效
            if (g_u8g2_i2c_bus == NULL) {
                ESP_LOGE(TAG, "❌ g_u8g2_i2c_bus is NULL!");
                return 0;
            }

            // 检查设备句柄是否有效
            if (g_u8g2_i2c_dev == NULL) {
                ESP_LOGW(TAG, "⚠️ g_u8g2_i2c_dev is NULL, will create");
            }
            // ============================================================

            // 如果设备句柄尚未创建或地址变化，重新创建设备
            if (g_u8g2_i2c_dev == NULL || g_u8g2_i2c_dev_addr != addr) {
                // 先移除旧设备（如果有）
                if (g_u8g2_i2c_dev != NULL) {
                    i2c_master_bus_rm_device(g_u8g2_i2c_dev);
                    g_u8g2_i2c_dev = NULL;
                }
                // 在总线上添加新设备
                i2c_device_config_t dev_cfg = {
                    .dev_addr_length = I2C_ADDR_BIT_LEN_7,
                    .device_address = addr,
                    .scl_speed_hz = 400000,
                };
                esp_err_t err = i2c_master_bus_add_device(
                    g_u8g2_i2c_bus, &dev_cfg, &g_u8g2_i2c_dev);
                if (err != ESP_OK) {
                    ESP_LOGE(TAG, "❌ Failed to add I2C device: %s",
                             esp_err_to_name(err));
                    return 0;
                }
                g_u8g2_i2c_dev_addr = addr;
                ESP_LOGI(TAG, "✅ I2C device added at 0x%02X", addr);
            }

            // 使用新版驱动 API 发送数据
            esp_err_t ret = i2c_master_transmit(
                g_u8g2_i2c_dev, data, arg_int, I2C_MASTER_TIMEOUT_MS);
            if (ret != ESP_OK) {
                ESP_LOGW(TAG, "❌ I2C send failed: %s", esp_err_to_name(ret));
                return 0;
            }
            ESP_LOGI(TAG, "✅ I2C send success");
            break;
        }
        case U8X8_MSG_BYTE_SET_DC: {
            break;
        }
        case U8X8_MSG_BYTE_START_TRANSFER: {
            ESP_LOGI(TAG, "U8X8_MSG_BYTE_START_TRANSFER");
            break;
        }
        case U8X8_MSG_BYTE_END_TRANSFER: {
            ESP_LOGI(TAG, "U8X8_MSG_BYTE_END_TRANSFER");
            break;
        }
        default:
            return 0;
    }
    return 1;
}

// GPIO 和延迟回调函数
uint8_t u8g2_esp32_gpio_and_delay(u8x8_t *u8x8, uint8_t msg, uint8_t arg_int, void *arg_ptr) {
    switch(msg) {
        // GPIO_INIT 已经被移除，不需要处理
        case U8X8_MSG_DELAY_MILLI: {
            vTaskDelay(arg_int / portTICK_PERIOD_MS);
            break;
        }
        case U8X8_MSG_DELAY_10MICRO: {
            esp_rom_delay_us(arg_int * 10);
            break;
        }
        case U8X8_MSG_DELAY_100NANO: {
            // 100纳秒太短，忽略
            break;
        }
        default:
            return 0;
    }
    return 1;
}

// ============================================================
// Board 层接口：设置/获取 I2C 总线句柄
// ============================================================
void u8g2_esp32_set_i2c_bus(i2c_master_bus_handle_t bus) {
    g_u8g2_i2c_bus = bus;
    ESP_LOGI(TAG, "I2C bus handle set successfully");
}

i2c_master_bus_handle_t u8g2_esp32_get_i2c_bus(void) {
    return g_u8g2_i2c_bus;
}
