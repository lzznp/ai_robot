// ============================================================
// config.h — 瓦力（wali）实测引脚
//
// ★ 全部来自 2026-10-22 实测，**不是**作者 qebabe 的 config.h。
//   作者资料：电机 12/13/14/21、灯 18、无舵机
//   实测实物：电机 A = 13/14，电机 B = 17/18，舵机 = 11(左) 12(右)
//   详见 工作文档\瓦力-硬件台账.md
//
// 注意：板上有电源开关，打开才给电机/舵机供电；
//       不打开也能连 COM（逻辑由 USB 供电）。
// ============================================================

#ifndef WALI_CONFIG_H
#define WALI_CONFIG_H

#include "driver/gpio.h"

// ---- 电机（TC1508 双路 H 桥，IN 一高一低 = 转，两低 = 停，两高 = 刹车）----
#define WALI_MOTOR_A_IN1 13
#define WALI_MOTOR_A_IN2 14
#define WALI_MOTOR_B_IN1 17
#define WALI_MOTOR_B_IN2 18

// ---- 舵机（50Hz PWM）----
#define WALI_SERVO_L_PIN 11
#define WALI_SERVO_R_PIN 12

// ---- 屏：SSD1306 I2C（原厂固件下正常，引脚沿用作者定义）----
#define WALI_I2C_SDA           GPIO_NUM_41
#define WALI_I2C_SCL           GPIO_NUM_42
#define WALI_DISPLAY_ADDR      0x3C
#define WALI_DISPLAY_WIDTH     128
#define WALI_DISPLAY_HEIGHT    32     // 作者 config.json 默认就是 128x32

// ---- 按键（原厂固件下可用，沿用作者定义）----
#define WALI_BOOT_GPIO     0
#define WALI_TOUCH_GPIO    47
#define WALI_VOL_UP_GPIO   40
#define WALI_VOL_DOWN_GPIO 39

// ---- 板载 LED ----
#define WALI_LED_GPIO      48

// ---- 音频（原厂固件下语音正常，沿用作者定义）----
#define WALI_MIC_WS        4
#define WALI_MIC_SCK       5
#define WALI_MIC_DIN       6
#define WALI_SPK_DOUT      7
#define WALI_SPK_BCLK      15
#define WALI_SPK_LRCK      16

#endif  // WALI_CONFIG_H
