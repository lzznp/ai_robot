#ifndef WALI_CONFIG_H
#define WALI_CONFIG_H

#include <driver/gpio.h>

// ============================================================
// 瓦力（wali）板级配置
//
// ★ 引脚来源：2026-10-22 逐脚实测（见 工作文档\瓦力-硬件台账.md）
//   卖家刷的原厂固件用的是 bread-compact-wifi 的默认引脚（10/13/14/21 电机
//   + 18 当灯），**和实物接线对不上**；下面是实测出来的真值：
//
//   电机 A = 13/14    电机 B = 17/18
//   左手舵机 = 11     右手舵机 = 12
//
//   其它（音频/屏/按键/LED）沿用 bread-compact-wifi 定义 —— 原厂固件下
//   语音、屏、按键都正常工作，说明这几组是对的。
// ============================================================

// ---- 音频（Simplex I2S）----
#define AUDIO_INPUT_SAMPLE_RATE  16000
#define AUDIO_OUTPUT_SAMPLE_RATE 24000
#define AUDIO_I2S_METHOD_SIMPLEX

#define AUDIO_I2S_MIC_GPIO_WS   GPIO_NUM_4
#define AUDIO_I2S_MIC_GPIO_SCK  GPIO_NUM_5
#define AUDIO_I2S_MIC_GPIO_DIN  GPIO_NUM_6
#define AUDIO_I2S_SPK_GPIO_DOUT GPIO_NUM_7
#define AUDIO_I2S_SPK_GPIO_BCLK GPIO_NUM_15
#define AUDIO_I2S_SPK_GPIO_LRCK GPIO_NUM_16

// ---- LED / 按键 ----
#define BUILTIN_LED_GPIO        GPIO_NUM_48
#define BOOT_BUTTON_GPIO        GPIO_NUM_0
#define TOUCH_BUTTON_GPIO       GPIO_NUM_47
#define VOLUME_UP_BUTTON_GPIO   GPIO_NUM_40
#define VOLUME_DOWN_BUTTON_GPIO GPIO_NUM_39

// ---- 屏：SSD1306 I2C ----
#define DISPLAY_SDA_PIN GPIO_NUM_41
#define DISPLAY_SCL_PIN GPIO_NUM_42
#define DISPLAY_WIDTH   128

#if CONFIG_OLED_SSD1306_128X32
#define DISPLAY_HEIGHT  32
#elif CONFIG_OLED_SSD1306_128X64
#define DISPLAY_HEIGHT  64
#elif CONFIG_OLED_SH1106_128X64
#define DISPLAY_HEIGHT  64
#define SH1106
#else
#define DISPLAY_HEIGHT  32      // 兜底：作者 config.json 默认就是 128x32
#endif

#define DISPLAY_MIRROR_X true
#define DISPLAY_MIRROR_Y true

// ---- 电机（TC1508 双路 H 桥：IN 一高一低 = 转，两低 = 停）----
#define WALI_MOTOR_A_IN1 GPIO_NUM_13
#define WALI_MOTOR_A_IN2 GPIO_NUM_14
#define WALI_MOTOR_B_IN1 GPIO_NUM_17
#define WALI_MOTOR_B_IN2 GPIO_NUM_18

// ---- 舵机（50Hz PWM）----
#define WALI_SERVO_L_PIN GPIO_NUM_11
#define WALI_SERVO_R_PIN GPIO_NUM_12

// 一次"动一下"的默认时长（毫秒）
#define WALI_MOVE_MS 1200

#endif // WALI_CONFIG_H
