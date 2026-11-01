// ============================================================
// MOSS 550W 硬件配置文件 (更新版)
// 基于 ESP32-S3-WROOM-1-N16R8
// 数据来源：FlyingProbeTesting.json + BOM + 原理图标注
// 最后更新：2026-07-11
//
// 更新说明：
//   - 新增 AUDIO_I2S_SPK_* / AUDIO_I2S_MIC_* 框架标准宏
//   - 保留原有 I2S_* / MIC_* 宏名作为兼容别名
//   - 音频架构：NS4168 I2S 扬声器 + INMP441 PDM 麦克风
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
// 0.96寸 OLED 屏幕 (SSD1315/SSD1306, I2C 接口)
// ============================================================
#define DISPLAY_SDA         GPIO_NUM_1    // I2C 数据线 (与 I2C_SDA_GPIO 共用)
#define DISPLAY_SCL         GPIO_NUM_2    // I2C 时钟线 (与 I2C_SCL_GPIO 共用)
#define DISPLAY_WIDTH       128
#define DISPLAY_HEIGHT      64
#define DISPLAY_I2C_ADDR    0x3C          // 0.96寸 OLED 最常见的 I2C 地址，如果屏幕不亮，请尝试改为 0x3D

// 以下 SPI 相关参数用不到，但为了兼容框架，保留为 NC (No Connection)
#define DISPLAY_DC          GPIO_NUM_NC
#define DISPLAY_CS          GPIO_NUM_NC
#define DISPLAY_RES         GPIO_NUM_NC
#define DISPLAY_MIRROR_X    false
#define DISPLAY_MIRROR_Y    false
#define DISPLAY_SWAP_XY     false
#define DISPLAY_OFFSET_X    0
#define DISPLAY_OFFSET_Y    0


// ============================================================
// 音频 (I2S Speaker + PDM Mic)
//
// 硬件组成:
//   - 扬声器: NS4168 (I2S 功放, 无需 Codec 芯片)
//   - 麦克风: INMP441 (PDM 数字麦克风)
//   - 无外置音频 Codec 芯片, 无 MCLK 信号
//
// 采样率: 输入输出均对齐 24000Hz
//
// I2S 端口分配:
//   - I2S_NUM_1 (TX): NS4168 扬声器 — 标准 I2S, 32bit mono
//   - I2S_NUM_0 (RX): INMP441 麦克风 — PDM 模式, 16bit mono
// ============================================================
#define AUDIO_INPUT_SAMPLE_RATE   24000
#define AUDIO_OUTPUT_SAMPLE_RATE  24000

// --- 扬声器引脚 (NS4168, 标准 I2S) ---
#define AUDIO_I2S_SPK_GPIO_BCLK   GPIO_NUM_10   // NS4168 BCK   (I2S 位时钟)
#define AUDIO_I2S_SPK_GPIO_LRCK   GPIO_NUM_11   // NS4168 WS    (I2S 帧时钟/左右声道选择)
#define AUDIO_I2S_SPK_GPIO_DOUT   GPIO_NUM_9    // NS4168 DIN   (I2S 数据输出)
// #define AUDIO_SPK_PA_PIN        GPIO_NUM_NC   // NS4168 功放使能 (如有, 取消注释)

// --- 麦克风引脚 (INMP441, PDM 模式) ---
#define AUDIO_I2S_MIC_GPIO_SCK    GPIO_NUM_13   // INMP441 PDM 时钟 (PDM CLK)
#define AUDIO_I2S_MIC_GPIO_DIN    GPIO_NUM_12   // INMP441 PDM 数据 (PDM DATA)
// INMP441 在 PDM 模式下不需要 WS/LR 选择引脚

// --- 兼容别名 (保留原有宏名, 供旧代码引用) ---
#define I2S_DIN_GPIO        AUDIO_I2S_SPK_GPIO_DOUT  // GPIO_NUM_9    NS4168 数据输入
#define I2S_BCLK_GPIO       AUDIO_I2S_SPK_GPIO_BCLK  // GPIO_NUM_10   NS4168 位时钟
#define I2S_LRCK_GPIO       AUDIO_I2S_SPK_GPIO_LRCK  // GPIO_NUM_11   NS4168 帧时钟
#define I2S_PORT            I2S_NUM_0
#define MIC_BCK_GPIO        AUDIO_I2S_MIC_GPIO_SCK   // GPIO_NUM_13   INMP441 PDM 时钟
#define MIC_DIN_GPIO        AUDIO_I2S_MIC_GPIO_DIN   // GPIO_NUM_12   INMP441 PDM 数据

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
// [重要] 以下摄像头引脚与音频、电机等引脚存在严重冲突，在调试摄像头前必须修正。
// 为避免影响其他功能，建议暂时注释掉所有 CAM_ 相关的定义。
/*
#define CAM_XCLK_GPIO       GPIO_NUM_16
#define CAM_VSYNC_GPIO      GPIO_NUM_18
#define CAM_HREF_GPIO       GPIO_NUM_20
#define CAM_PCLK_GPIO       GPIO_NUM_19
#define CAM_RST_GPIO        GPIO_NUM_17
#define CAM_PWDN_GPIO       GPIO_NUM_21
#define CAM_D0_GPIO         GPIO_NUM_21
#define CAM_D1_GPIO         GPIO_NUM_14
#define CAM_D2_GPIO         GPIO_NUM_13
#define CAM_D3_GPIO         GPIO_NUM_12
#define CAM_D4_GPIO         GPIO_NUM_11
#define CAM_D5_GPIO         GPIO_NUM_10
#define CAM_D6_GPIO         GPIO_NUM_17
#define CAM_D7_GPIO         GPIO_NUM_15
*/

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
