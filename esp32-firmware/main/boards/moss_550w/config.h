// ============================================================
// MOSS 550W 硬件配置文件 (官方引脚分配)
// ============================================================

#ifndef MOSS_550W_CONFIG_H
#define MOSS_550W_CONFIG_H

#include "driver/gpio.h"

// ============================================================
// I2C (OLED)
// ============================================================
#define I2C_SDA_GPIO        GPIO_NUM_2
#define I2C_SCL_GPIO        GPIO_NUM_1
#define I2C_PORT            I2C_NUM_0
#define I2C_CLOCK_SPEED     (400 * 1000)

// ============================================================
// OLED 屏幕 (已放弃)
// ============================================================
#define DISPLAY_SDA         GPIO_NUM_2
#define DISPLAY_SCL         GPIO_NUM_1
#define DISPLAY_WIDTH       128
#define DISPLAY_HEIGHT      64
#define DISPLAY_I2C_ADDR    0x3C
#define DISPLAY_DC          GPIO_NUM_NC
#define DISPLAY_CS          GPIO_NUM_NC
#define DISPLAY_RES         GPIO_NUM_NC
#define DISPLAY_MIRROR_X    false
#define DISPLAY_MIRROR_Y    false
#define DISPLAY_SWAP_XY     false
#define DISPLAY_OFFSET_X    0
#define DISPLAY_OFFSET_Y    0

// ============================================================
// 音频 (I2S Speaker + PDM Mic) — 官方引脚分配
// ============================================================
#define AUDIO_INPUT_SAMPLE_RATE   16000
#define AUDIO_OUTPUT_SAMPLE_RATE  16000

// --- 扬声器 (NS4168/MAX98357) ---
#define AUDIO_I2S_SPK_GPIO_BCLK   GPIO_NUM_10   // BCK
#define AUDIO_I2S_SPK_GPIO_LRCK   GPIO_NUM_9    // LRCK  ← 修正
#define AUDIO_I2S_SPK_GPIO_DOUT   GPIO_NUM_11   // DOUT  ← 修正

// --- 麦克风 (INMP441 PDM) ---
#define AUDIO_I2S_MIC_GPIO_SCK    GPIO_NUM_12   // PDM CLK
#define AUDIO_I2S_MIC_GPIO_DIN    GPIO_NUM_13   // PDM DATA
// MIC_WS (GPIO14) 用于左右声道选择，PDM 模式下不需要

// --- 兼容别名 ---
#define I2S_DIN_GPIO        AUDIO_I2S_SPK_GPIO_DOUT
#define I2S_BCLK_GPIO       AUDIO_I2S_SPK_GPIO_BCLK
#define I2S_LRCK_GPIO       AUDIO_I2S_SPK_GPIO_LRCK
#define I2S_PORT            I2S_NUM_0
#define MIC_BCK_GPIO        AUDIO_I2S_MIC_GPIO_SCK
#define MIC_DIN_GPIO        AUDIO_I2S_MIC_GPIO_DIN

// ============================================================
// 74HC595 (步进电机)
// ============================================================
#define HC595_SHCP_GPIO     GPIO_NUM_3
#define HC595_STCP_GPIO     GPIO_NUM_4
#define HC595_DS_GPIO       GPIO_NUM_5

// ============================================================
// WS2812 LED 灯带
// ============================================================
#define LED_1313_GPIO       GPIO_NUM_7    // 第一组 (3颗)
#define LED_4020_GPIO       GPIO_NUM_48   // 第二组 (2颗)
#define LED_1313_NUM        3
#define LED_4020_NUM        2

// ============================================================
// 电池 / 电压检测
// ============================================================
#define VBAT_ADC_GPIO       GPIO_NUM_8
#define VBAT_ADC_CHANNEL    ADC_CHANNEL_7

// ============================================================
// BOOT 按键
// ============================================================
#define BOOT_BUTTON_GPIO    GPIO_NUM_0

#endif // MOSS_550W_CONFIG_H