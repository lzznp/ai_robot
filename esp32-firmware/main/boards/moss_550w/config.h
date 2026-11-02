// ============================================================
// MOSS 550W 硬件配置文件 (官方引脚分配)
// ============================================================

#ifndef MOSS_550W_CONFIG_H
#define MOSS_550W_CONFIG_H

#include "driver/gpio.h"

// ============================================================
// ★ 自检模式开关（2026-10-19 新增）
//   1 = 上电后不启动 WiFi/Application，直接进自检
//       交互：BOOT 键单击换项、长按执行；结果走串口
//       用于判定"元件/接线"问题，不依赖网络
//   0 = 正常固件
// ============================================================
#define MOSS_SELFTEST 0

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
// 摄像头（DVP 8 位并行，插在 U13 那个 20 针座；别插 FPC1）
//
// 2026-10-31 由网表的"模块脚号"换算成 GPIO，换算规则用 I2S 三个已知脚校验过：
//   网表 U8_17/U8_18/U8_19 = GPIO9/10/11，与 config.h 里 I2S LRCK/BCLK/DOUT 一致
//
// ⚠️ CAM_RST 在网表里是 U8_3 —— 那是模块的 EN 脚（同一网络挂着 R17 + C23 复位 RC），
//    也就是摄像头复位被焊死在整机复位上，**软件不可控**，所以写 NC。
// ⚠️ SCCB 与 OLED 共用同一条 I2C（GPIO1/GPIO2）。若摄像头 SCCB 地址是 0x3C，
//    会与 SSD1306 OLED 撞地址；OV2640 是 0x30，不撞。
// ============================================================
#define CAMERA_PIN_PWDN     GPIO_NUM_47   // U8_24
#define CAMERA_PIN_RESET    GPIO_NUM_NC   // U8_3 = EN，软件不可控
#define CAMERA_PIN_XCLK     GPIO_NUM_21   // U8_23
#define CAMERA_PIN_SIOD     GPIO_NUM_2    // SCCB SDA（= OLED 那条 I2C 的 SDA）
#define CAMERA_PIN_SIOC     GPIO_NUM_1    // SCCB SCL
#define CAMERA_PIN_D7       GPIO_NUM_40   // U8_33
#define CAMERA_PIN_D6       GPIO_NUM_17   // U8_10
#define CAMERA_PIN_D5       GPIO_NUM_18   // U8_11
#define CAMERA_PIN_D4       GPIO_NUM_16   // U8_9
#define CAMERA_PIN_D3       GPIO_NUM_41   // U8_34
#define CAMERA_PIN_D2       GPIO_NUM_46   // U8_16
#define CAMERA_PIN_D1       GPIO_NUM_45   // U8_26
#define CAMERA_PIN_D0       GPIO_NUM_42   // U8_35
#define CAMERA_PIN_VSYNC    GPIO_NUM_38   // U8_31
#define CAMERA_PIN_HREF     GPIO_NUM_39   // U8_32
#define CAMERA_PIN_PCLK     GPIO_NUM_15   // U8_8
#define XCLK_FREQ_HZ        20000000

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