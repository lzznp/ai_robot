# MOSS 550W 编译问题诊断与修复报告

> **生成日期**: 2026-07-06
> **分析基准**: ESP-IDF v5.5.4 + 小智 AI 固件
> **参考板型**: `lingkong-s3-moc-cam-1.54tft`（已确认编译通过）
> **目标板型**: `moss_550w`

---

## 目录

1. [问题诊断摘要](#1-问题诊断摘要)
2. [代码对比分析表](#2-代码对比分析表)
3. [修复后完整代码](#3-修复后完整代码)
4. [配置步骤清单](#4-配置步骤清单)
5. [附录：编译错误速查表](#5-附录编译错误速查表)

---

## 1. 问题诊断摘要

### 1.1 发现的关键问题

| 编号 | 严重度 | 文件 | 问题描述 |
|------|--------|------|----------|
| P1 | 🔴 阻断 | `board_moss_550w.cc:84` | **宏 `I2S_STD_MSB_SLOT_DEFAULT_CONFIG` 不存在** — 该宏是旧版 I2S 驱动的遗留别名，在 ESP-IDF v5.x 新 I2S 驱动中已移除。应使用 `I2S_STD_SLOT_DEFAULT_CONFIG` 或直接初始化结构体。 |
| P2 | 🔴 阻断 | `board_moss_550w.cc:115-118` | **ADC 通道配置结构体未初始化** — `adc_oneshot_chan_cfg_t chan_config;` 后直接逐字段赋值，剩余字段为未定义值。在 ESP-IDF v5.5.4 中此结构体有额外字段，必须用 `= {}` 或 designated initializer 初始化。 |
| P3 | 🔴 阻断 | `motor_control.c:59,291` | **`hc595_write()` 函数重定义** — 第 59 行和第 291 行分别定义了两次同名 `static` 函数，编译报 `redefinition` 错误。第 291 行的定义本意是更新第 59 行的实现以记录当前状态。 |
| P4 | 🟡 警告 | `board_moss_550w.cc:158-159` | **`GetAudioCodec()` 返回 `nullptr`** — 框架的音频管道依赖 AudioCodec 实例，返回 nullptr 会在音频播放时导致段错误。 |
| P5 | 🟡 警告 | `board_moss_550w.cc:131-132` | **InitI2s() + InitAdc() 与框架重复** — 框架的 AudioCodec 内部已经初始化 I2S 通道，板上再初始化一遍会导致 I2S 端口冲突。 |
| P6 | 🟡 警告 | `config.h:6-7` | **包含已废弃的旧版头文件** — `#include "driver/i2c.h"` 应替换为 `#include "driver/i2c_master.h"`；`#include "driver/i2s.h"` 是旧版 API 头文件（ESP-IDF v5.x 中已分离为多个子头文件）。 |

### 1.2 根因分析

**I2S 问题根因**:
ESP-IDF v5.x 对 I2S 驱动进行了彻底重构。旧版 API（`driver/i2s.h`）被拆分为：
- `driver/i2s_std.h` — 标准 I2S 模式
- `driver/i2s_pdm.h` — PDM 模式  
- `driver/i2s_tdm.h` — TDM 模式
- `driver/i2s_common.h` — 共用定义

新版 API 中 `I2S_STD_MSB_SLOT_DEFAULT_CONFIG` 宏已不复存在，需使用 `I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG` 或 `I2S_STD_SLOT_DEFAULT_CONFIG`。

**ADC 问题根因**:
`adc_oneshot_chan_cfg_t` 在 ESP-IDF v5.5.4 中的完整定义包含 `bitwidth`、`atten` 和可能的其他字段。未初始化的栈上变量直接赋值会导致未定义行为。

**电机控制重定义问题根因**:
代码编写过程中意图重构 `hc595_write()` 函数以增加状态跟踪，但旧版函数未删除就添加了新定义，导致同名重定义。

---

## 2. 代码对比分析表

### 2.1 I2S 初始化对比

| 方面 | lingkong-s3-moc-cam-1.54tft | moss_550w (当前) | moss_550w (修复后) |
|------|----------------------------|-----------------|-------------------|
| 方式 | 委托给 `Es8311AudioCodec` | 直接在 board 中 `InitI2s()` | 委托给 `NoAudioCodecSimplexPdm` |
| 头文件 | `<driver/i2s_std.h>` (codec 内部) | `<driver/i2s_std.h>` | `<driver/i2s_pdm.h>` + `<driver/i2s_std.h>` |
| I2S 宏 | `I2S_CHANNEL_DEFAULT_CONFIG` + 手动初始化 | `I2S_CHANNEL_DEFAULT_CONFIG` + `I2S_STD_MSB_SLOT_DEFAULT_CONFIG` ❌ | `I2S_CHANNEL_DEFAULT_CONFIG` + `I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG` ✅ |
| 通道数 | 双工 (Duplex) | TX only | 单工: TX(I2S Std) + RX(PDM) |
| MCLK | GPIO42 (ESP_PDM_BIT_CLK) | `I2S_GPIO_UNUSED` | `I2S_GPIO_UNUSED` (NS4168 不需要 MCLK) |
| 采样率 | 24000 Hz | 16000 Hz | 24000 Hz (对齐框架) |
| 数据位宽 | 16bit | 16bit | 32bit (对齐框架 NoAudioCodec 约定) |
| slot_mode | STEREO | STEREO | MONO (NS4168 典型用法) |

### 2.2 ADC 初始化对比

| 方面 | lingkong-s3-moc-cam-1.54tft | moss_550w (当前) | moss_550w (修复后) |
|------|----------------------------|-----------------|-------------------|
| 方式 | `PowerManager` 类封装 | 直接在 board 中 `InitAdc()` | 直接在 board 中 `InitAdc()` |
| 头文件 | (通过 PowerManager) | `<esp_adc/adc_oneshot.h>` | `<esp_adc/adc_oneshot.h>` |
| 结构体初始化 | (由 PowerManager 处理) | ❌ 未初始化 `chan_config` | ✅ designated initializer |
| ADC 通道 | ADC1_CH9 (GPIO11) | ADC1_CH7 (GPIO8) | ADC1_CH7 (GPIO8) |
| 衰减 | 未使用（PMU 方案） | ADC_ATTEN_DB_12 | ADC_ATTEN_DB_12 |
| 分辨率 | — | ADC_BITWIDTH_DEFAULT | ADC_BITWIDTH_12 |

### 2.3 运动控制接口对比

| 接口 | lingkong-s3-moc-cam-1.54tft | moss_550w (当前) | moss_550w (修复后) |
|------|----------------------------|-----------------|-------------------|
| 驱动方案 | 直流电机 + H桥 (TC118S) | 步进电机 + 74HC595 + ULN2003 | 步进电机 + 74HC595 + ULN2003 |
| MotorForward | `motor1_.Forward()` | `motor_rotate(MOTOR_1, MOTOR_CW)` | `motor_rotate(MOTOR_1, MOTOR_CW)` |
| MoveForward | 内部方法 | `override` 虚函数 | `override` 虚函数 ✅ |
| GetAudioCodec | 返回 Es8311AudioCodec | 返回 nullptr ❌ | 返回 NoAudioCodecSimplexPdm ✅ |
| GetDisplay | 返回 display_ | 返回 nullptr | 返回 nullptr (无显示) |
| GetBatteryLevel | 通过 PowerManager | 自定义 ADC 读取 | 自定义 ADC 读取 ✅ |

---

## 3. 修复后完整代码

### 3.1 修正后的 `board_moss_550w.cc`

```cpp
// ============================================================
// MOSS 550W 板级支持包
// 基于 ESP32-S3-WROOM-1-N16R8
// 最后更新：2026-07-06
// ============================================================

#include "config.h"
#include "motor_control.h"
#include "wifi_board.h"
#include "audio_codec.h"
#include "codecs/no_audio_codec.h"
#include "display.h"

#include "esp_log.h"
#include "esp_err.h"
#include "driver/gpio.h"
#include "driver/i2c_master.h"
#include "driver/i2s_std.h"
#include "driver/i2s_pdm.h"
#include "esp_adc/adc_oneshot.h"

static const char *TAG = "MOSS_550W_BOARD";

// ============================================================
// MOSS 550W 板子类
// ============================================================
class Moss550WBoard : public WifiBoard {
private:
    i2c_master_bus_handle_t i2c_bus_ = nullptr;
    adc_oneshot_unit_handle_t adc_handle_ = nullptr;

    // ============================================================
    // GPIO 初始化
    // ============================================================
    esp_err_t InitGpio() {
        // 74HC595 控制引脚（输出）
        gpio_config_t io_conf = {
            .pin_bit_mask = (1ULL << HC595_SHCP_GPIO) |
                            (1ULL << HC595_STCP_GPIO) |
                            (1ULL << HC595_DS_GPIO),
            .mode = GPIO_MODE_OUTPUT,
            .pull_up_en = GPIO_PULLUP_DISABLE,
            .pull_down_en = GPIO_PULLDOWN_DISABLE,
            .intr_type = GPIO_INTR_DISABLE,
        };
        ESP_ERROR_CHECK(gpio_config(&io_conf));

        // WS2812 LED 控制引脚（输出）
        io_conf.pin_bit_mask = (1ULL << LED_1313_GPIO) |
                               (1ULL << LED_4020_GPIO);
        ESP_ERROR_CHECK(gpio_config(&io_conf));

        // BOOT 按键（输入，上拉）
        io_conf.pin_bit_mask = (1ULL << BOOT_BUTTON_GPIO);
        io_conf.mode = GPIO_MODE_INPUT;
        io_conf.pull_up_en = GPIO_PULLUP_ENABLE;
        io_conf.pull_down_en = GPIO_PULLDOWN_DISABLE;
        ESP_ERROR_CHECK(gpio_config(&io_conf));

        ESP_LOGI(TAG, "GPIO initialized successfully");
        return ESP_OK;
    }

    // ============================================================
    // I2C 初始化 (用于 OLED / 摄像头)
    // ============================================================
    esp_err_t InitI2c() {
        i2c_master_bus_config_t i2c_bus_config = {
            .i2c_port = 0,
            .sda_io_num = I2C_SDA_GPIO,
            .scl_io_num = I2C_SCL_GPIO,
            .clk_source = I2C_CLK_SRC_DEFAULT,
            .glitch_ignore_cnt = 7,
            .intr_priority = 0,
            .trans_queue_depth = 0,
            .flags = {
                .enable_internal_pullup = 1,
            },
        };

        ESP_ERROR_CHECK(i2c_new_master_bus(&i2c_bus_config, &i2c_bus_));
        ESP_LOGI(TAG, "I2C initialized successfully");
        return ESP_OK;
    }

    // ============================================================
    // ADC 初始化 (电池电压检测)
    // 注：使用新版 esp_adc/adc_oneshot.h API
    // ============================================================
    esp_err_t InitAdc() {
        adc_oneshot_unit_init_cfg_t init_config = {
            .unit_id = ADC_UNIT_1,
            .ulp_mode = ADC_ULP_MODE_DISABLE,
        };
        ESP_ERROR_CHECK(adc_oneshot_new_unit(&init_config, &adc_handle_));

        // 必须使用 designated initializer 完全初始化
        adc_oneshot_chan_cfg_t chan_config = {
            .bitwidth = ADC_BITWIDTH_12,
            .atten = ADC_ATTEN_DB_12,
        };
        ESP_ERROR_CHECK(adc_oneshot_config_channel(adc_handle_, VBAT_ADC_CHANNEL, &chan_config));
        ESP_LOGI(TAG, "ADC initialized successfully");
        return ESP_OK;
    }

public:
    Moss550WBoard() {
        ESP_LOGI(TAG, "Initializing MOSS 550W board...");

        InitGpio();
        InitI2c();
        InitAdc();

        // 初始化步进电机控制（74HC595 + ULN2003）
        motor_control_init();

        // 初始状态：LED 关闭，74HC595 输出清零
        gpio_set_level(LED_1313_GPIO, 0);
        gpio_set_level(LED_4020_GPIO, 0);

        ESP_LOGI(TAG, "MOSS 550W board initialized successfully");
    }

    // ============================================================
    // 电池电压读取
    // ============================================================
    float GetBatteryVoltage() {
        int raw = 0;
        esp_err_t ret = adc_oneshot_read(adc_handle_, VBAT_ADC_CHANNEL, &raw);
        if (ret != ESP_OK) {
            ESP_LOGE(TAG, "ADC read failed");
            return 0.0f;
        }
        // VBATT → 100k+100k 分压 → ADC，ADC 量程 0~3.3V
        // 实际电压 = raw / 4095 * 3.3 * 2
        return (raw / 4095.0f) * 3.3f * 2.0f;
    }

    // ============================================================
    // 虚函数实现 — Board 标识
    // ============================================================
    virtual std::string GetBoardType() override {
        return "MOSS_550W";
    }

    // ============================================================
    // 虚函数实现 — 音频编解码器
    // 使用架构: NS4168 (I2S 标准模式 TX) + INMP441 (PDM 模式 RX)
    // ============================================================
    virtual AudioCodec* GetAudioCodec() override {
        static NoAudioCodecSimplexPdm audio_codec(
            AUDIO_INPUT_SAMPLE_RATE,    // 输入采样率 (INMP441 PDM)
            AUDIO_OUTPUT_SAMPLE_RATE,   // 输出采样率 (NS4168 I2S)
            I2S_BCLK_GPIO,              // I2S 位时钟
            I2S_LRCK_GPIO,              // I2S 帧时钟
            I2S_DIN_GPIO,               // I2S 数据输出
            I2S_STD_SLOT_LEFT,          // 扬声器 slot mask
            MIC_BCK_GPIO,               // PDM 时钟
            MIC_DIN_GPIO                // PDM 数据输入
        );
        return &audio_codec;
    }

    // ============================================================
    // 虚函数实现 — 显示 (MOSS 550W 无板载 LCD)
    // ============================================================
    virtual Display* GetDisplay() override {
        return nullptr;
    }

    // ============================================================
    // 虚函数实现 — 电池电量
    // ============================================================
    virtual bool GetBatteryLevel(int& level, bool& charging, bool& discharging) override {
        float voltage = GetBatteryVoltage();
        if (voltage > 4.0f) {
            level = 100;
        } else if (voltage > 3.8f) {
            level = 80;
        } else if (voltage > 3.6f) {
            level = 50;
        } else if (voltage > 3.4f) {
            level = 20;
        } else {
            level = 5;
        }
        // [待确认] 充电检测：TP4057 CHRG 引脚连接 LED2，需确认是否连接到 GPIO
        charging = false;
        discharging = true;
        return true;
    }

    // ============================================================
    // 运动控制接口 (通过 74HC595 + ULN2003 驱动步进电机)
    // ============================================================
    void MoveForward() override {
        motor_rotate(MOTOR_1, MOTOR_CW);
        motor_rotate(MOTOR_2, MOTOR_CW);
        ESP_LOGI(TAG, "Move Forward");
    }

    void MoveBackward() override {
        motor_rotate(MOTOR_1, MOTOR_CCW);
        motor_rotate(MOTOR_2, MOTOR_CCW);
        ESP_LOGI(TAG, "Move Backward");
    }

    void TurnLeft() override {
        motor_rotate(MOTOR_1, MOTOR_CCW);
        motor_rotate(MOTOR_2, MOTOR_CW);
        ESP_LOGI(TAG, "Turn Left");
    }

    void TurnRight() override {
        motor_rotate(MOTOR_1, MOTOR_CW);
        motor_rotate(MOTOR_2, MOTOR_CCW);
        ESP_LOGI(TAG, "Turn Right");
    }

    void Stop() override {
        motor_stop(MOTOR_1);
        motor_stop(MOTOR_2);
        ESP_LOGI(TAG, "Stop");
    }

    void Wave() override {
        // MOSS 550W 无舵机，Wave 操作可作为 LED 闪烁
        ESP_LOGI(TAG, "Wave! 👋");
    }

    void SetServoAngle(int angle) override {
        // MOSS 550W 无舵机，预留（可切换 LED 亮度或颜色）
        ESP_LOGI(TAG, "Set servo angle: %d (not supported)", angle);
    }
};

DECLARE_BOARD(Moss550WBoard);
```

### 3.2 修正后的 `config.h`

```cpp
// ============================================================
// MOSS 550W 硬件配置文件
// 基于 ESP32-S3-WROOM-1-N16R8
// 数据来源：FlyingProbeTesting.json + BOM + 原理图标注
// 最后更新：2026-07-06
// ============================================================

#ifndef MOSS_550W_CONFIG_H
#define MOSS_550W_CONFIG_H

#include "driver/gpio.h"

// ============================================================
// I2C (OLED / 摄像头配置)
// ============================================================
#define I2C_SDA_GPIO        GPIO_NUM_1
#define I2C_SCL_GPIO        GPIO_NUM_2
#define I2C_PORT            I2C_NUM_0
#define I2C_CLOCK_SPEED     (400 * 1000)  // 400kHz

// ============================================================
// 音频 (I2S → NS4168)
// 采样率对齐框架默认值 24000
// ============================================================
#define AUDIO_INPUT_SAMPLE_RATE   24000
#define AUDIO_OUTPUT_SAMPLE_RATE  24000

#define I2S_DIN_GPIO        GPIO_NUM_9    // NS4168 数据输入 (DOUT)
#define I2S_BCLK_GPIO       GPIO_NUM_10   // NS4168 位时钟 (BCK)
#define I2S_LRCK_GPIO       GPIO_NUM_11   // NS4168 帧时钟 (WS/LRCK)
#define I2S_PORT            I2S_NUM_0

// ============================================================
// 麦克风 (INMP441 - PDM 模式)
// INMP441 仅需要 PDM_CLK 和 PDM_DATA 两个引脚
// ============================================================
#define MIC_BCK_GPIO        GPIO_NUM_13   // PDM 时钟
#define MIC_DIN_GPIO        GPIO_NUM_12   // PDM 数据
// #define MIC_WS_GPIO      GPIO_NUM_14   // PDM 模式下不需要 WS（5V_INMP441 也不需要 LR 选择）

// ============================================================
// 74HC595 (步进电机控制)
// ============================================================
#define HC595_SHCP_GPIO     GPIO_NUM_3    // 移位时钟
#define HC595_STCP_GPIO     GPIO_NUM_4    // 锁存时钟
#define HC595_DS_GPIO       GPIO_NUM_5    // 串行数据

// ============================================================
// WS2812 LED 灯带 (双路独立控制)
// ============================================================
#define LED_1313_GPIO       GPIO_NUM_7    // 第一组 (3颗 2020 灯珠)
#define LED_4020_GPIO       GPIO_NUM_48   // 第二组 (2颗 4020 灯珠)
#define LED_1313_NUM        3             // 灯珠数量
#define LED_4020_NUM        2             // 灯珠数量

// ============================================================
// 电池 / 电压检测 (ADC)
// ============================================================
#define VBAT_ADC_GPIO       GPIO_NUM_8    // 电池电压检测 (ADC1_CH7)
#define VBAT_ADC_CHANNEL    ADC_CHANNEL_7

// ============================================================
// 摄像头 (OV2640) — 引脚待确认
// ============================================================
// 根据硬件分析，摄像头连接在 U13 接口上，信号通过 FPC 转接
#define CAM_XCLK_GPIO       GPIO_NUM_16
#define CAM_VSYNC_GPIO      GPIO_NUM_18
#define CAM_HREF_GPIO       GPIO_NUM_20
#define CAM_PCLK_GPIO       GPIO_NUM_19
#define CAM_RST_GPIO        GPIO_NUM_17
#define CAM_PWDN_GPIO       GPIO_NUM_21
// [待确认] 以下摄像头数据引脚需根据原理图核对
#define CAM_D0_GPIO         GPIO_NUM_21
#define CAM_D1_GPIO         GPIO_NUM_14
#define CAM_D2_GPIO         GPIO_NUM_13
#define CAM_D3_GPIO         GPIO_NUM_12
#define CAM_D4_GPIO         GPIO_NUM_11
#define CAM_D5_GPIO         GPIO_NUM_10
#define CAM_D6_GPIO         GPIO_NUM_17
#define CAM_D7_GPIO         GPIO_NUM_15

// ============================================================
// BOOT 按键
// ============================================================
#define BOOT_BUTTON_GPIO    GPIO_NUM_0

// ============================================================
// 扩展排针
// ============================================================
// H2: GPIO13, 3V3, GND
// H3: GPIO12, GPIO14, GND
// H5: +5V, GPIO07, GND
// H6: +5V, GPIO48, GND

#endif // MOSS_550W_CONFIG_H
```

### 3.3 修正后的 `motor_control.c`

**关键修复**: 删除第 291 行的重复 `hc595_write()` 定义，将第 59 行的原始函数更新为同时跟踪 `hc595_current`。

```c
// 仅展示修复的部分 — hc595_write 函数 (第 59~70 行替换为此版本)

static uint8_t hc595_current = 0;

static void hc595_write(uint8_t data)
{
    hc595_current = data;  // ★ 新增：记录当前输出状态

    // 逐位发送 (MSB first)
    for (int i = 7; i >= 0; i--) {
        gpio_set_level(HC595_DS_GPIO, (data >> i) & 0x01);
        gpio_set_level(HC595_SHCP_GPIO, 1);
        gpio_set_level(HC595_SHCP_GPIO, 0);
    }
    // 锁存输出
    gpio_set_level(HC595_STCP_GPIO, 1);
    gpio_set_level(HC595_STCP_GPIO, 0);
}

// 删除原始第 284~295 行的重复定义（hc595_current 声明 + 重复的 hc595_write）
// 删除后 hc595_read_current() 可直接使用已修复的 hc595_write
```

**完整修正版 motor_control.c 下载**（仅替换含重复定义的段落）：

按照以下步骤操作：

1. 删除 `motor_control.c` 中第 280~295 行的以下代码块：
```c
// ============================================================
// 读取当前 74HC595 输出值
// 注意: 74HC595 不支持读取, 需软件维护状态
// ============================================================
static uint8_t hc595_current = 0;

static uint8_t hc595_read_current(void)
{
    return hc595_current;
}

static void hc595_write(uint8_t data)
{
    hc595_current = data;
    // ... 原有写入代码 ...
}
```

2. 将第 59 行的 `hc595_write` 函数修改为：
```c
static void hc595_write(uint8_t data)
{
    hc595_current = data;  // ★ 新增：记录当前输出
    // 逐位发送 (MSB first)
    for (int i = 7; i >= 0; i--) {
        gpio_set_level(HC595_DS_GPIO, (data >> i) & 0x01);
        gpio_set_level(HC595_SHCP_GPIO, 1);
        gpio_set_level(HC595_SHCP_GPIO, 0);
    }
    // 锁存输出
    gpio_set_level(HC595_STCP_GPIO, 1);
    gpio_set_level(HC595_STCP_GPIO, 0);
}
```

3. 在文件开头附近（`#include` 之后、`motor_control_init` 之前）添加：
```c
static uint8_t hc595_current = 0;
```

---

## 4. 配置步骤清单

### 4.1 Kconfig 中 Board Type 选择

```bash
# 方式一：通过 menuconfig 交互式配置
idf.py menuconfig
```

在 menuconfig 中：
```
Xiaozhi Assistant ＞ Board Type ＞ MOSS 550W
```

### 4.2 需要开启的配置选项

以下是在 `menuconfig` 中需要确保开启/检查的选项：

| 配置项 | 路径 | 说明 | 必须 |
|--------|------|------|------|
| `CONFIG_BOARD_TYPE_MOSS_550W=y` | Xiaozhi Assistant → Board Type | 选择 MOSS 550W 板型 | ✅ |
| `CONFIG_SOC_I2S_SUPPORTS_PDM_RX=y` | (芯片默认) | PDM 接收支持（INMP441） | ✅ 默认开启 |
| `CONFIG_SOC_I2S_HW_VERSION_2=y` | (芯片自动) | I2S 硬件版本 v2 | ✅ 默认开启 |
| ESP-IDF 默认启用 ADC 驱动 | Component config → ADC and ADC Calibration | ADC oneshot 驱动 | ✅ 默认开启 |
| 取消 `CONFIG_USE_DEVICE_AEC` | 应用层配置 | 设备端回声消除（如果未实现 AEC 可关闭） | ⬜ 按需 |
| 取消 `CONFIG_USE_SERVER_AEC` | 应用层配置 | 服务端回声消除 | ⬜ 按需 |
| `CONFIG_USE_EMOTE_MESSAGE_STYLE=n` | 应用层配置 | MOSS 550W 无显示，无需表情表情 ✅ | 建议关闭 |

### 4.3 使用 idf.py 命令行直接设置

```bash
# 设置目标芯片
idf.py set-target esp32s3

# 设置板型为 MOSS 550W
idf.py menuconfig  # 手动选择 "Xiaozhi Assistant → Board Type → MOSS 550W"

# 或者直接修改 sdkconfig
echo 'CONFIG_BOARD_TYPE_MOSS_550W=y' >> sdkconfig
echo 'CONFIG_FLASH_DEFAULT_ASSETS=y' >> sdkconfig
echo 'CONFIG_LANGUAGE_ZH_CN=y' >> sdkconfig
```

### 4.4 修改 CMakeLists.txt

当前 CMakeLists.txt 已包含 MOSS 550W 的 Board Type 分支（第 242~251 行），无需修改。

确认当前内容：
```cmake
elseif(CONFIG_BOARD_TYPE_MOSS_550W)
    set(BOARD_TYPE "moss_550w")
    set(BUILTIN_TEXT_FONT font_puhui_basic_20_4)
    set(BUILTIN_ICON_FONT font_awesome_20_4)
    set(DEFAULT_EMOJI_COLLECTION twemoji_64)
    # 如果有额外的源文件（电机控制等），在这里添加
    set(BOARD_EXTRA_SOURCES
        "${CMAKE_CURRENT_SOURCE_DIR}/boards/moss_550w/motor_control.c"
    )
    list(APPEND SOURCES ${BOARD_EXTRA_SOURCES})
```

> **注意**: 当前 CMakeLists.txt 已添加 `motor_control.c`，不需要额外改动。如果后续增加 `motor_control.h` 等头文件路径，需要添加 `list(APPEND INCLUDE_DIRS ...)`。

### 4.5 编译测试命令

```bash
# 清理之前的编译缓存
idf.py fullclean

# 编译
idf.py build

# 如果只改动了 board 文件，可用快速增量编译
idf.py build 2>&1 | grep -E "error:|warning:.*moss"
```

---

## 5. 附录：编译错误速查表

以下为修复前可能遇到的编译错误及原因：

| 错误信息 | 原因 | 修复位置 |
|----------|------|----------|
| `'I2S_STD_MSB_SLOT_DEFAULT_CONFIG' was not declared in this scope` | ESP-IDF v5.x 移除了该宏 | `board_moss_550w.cc:84` — 改用 `I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG` |
| `redefinition of 'hc595_write'` | `motor_control.c` 中两次定义同名函数 | `motor_control.c:59,291` — 删除重复定义 |
| `'adc_oneshot_chan_cfg_t' has no non-static data member 'bitwidth'` 或段错误 | C++ 中未初始化结构体导致未定义行为 | `board_moss_550w.cc:115-118` — 使用 designated initializer |
| `cannot convert 'i2s_std_slot_mask_t' to 'i2s_slot_mask_t'` | I2S 新版 API 类型不匹配 | `board_moss_550w.cc:84` — 使用正确的 slot config |
| `undefined reference to 'vtable for Moss550WBoard'` | 虚函数未完全实现 | `board_moss_550w.cc` — 检查所有 `override` 是否实现 |
| `class Moss550WBoard has no 'GetAudioCodec'` 但声明了 | 忘记 `override` 关键字或父类接口变更 | `board_moss_550w.cc:158` — 加 `override` 关键字 |
| `'i2c_master_bus_config_t' has no member named 'i2c_port'` | ESP-IDF v5.x 中将 `i2c_port` 改名为 `i2c_port_t` | `board_moss_550w.cc:57` — 确认 API 一致性 |

---

## 总结

本次修复涉及 3 个源文件和 1 个配置文件：

| 文件 | 修改类型 | 关键变更 |
|------|----------|----------|
| `board_moss_550w.cc` | 🔴 重写 | 移除自定义 I2S 初始化，改用 `NoAudioCodecSimplexPdm`；修复 ADC 初始化；实现所有虚函数 |
| `config.h` | 🟡 修正 | 移除废弃的 `driver/i2c.h` 和 `driver/i2s.h`；添加音频采样率常量；调整麦克风引脚定义 |
| `motor_control.c` | 🔴 修正 | 删除重复的 `hc595_write()` 定义；修复状态跟踪逻辑 |
| `CMakeLists.txt` | ✅ 无需修改 | 已有完整的 moss_550w 分支 |

**修复后编译预估**: 应当零错误通过编译。如果仍有问题，请按第 5 章的速查表定位具体错误。
