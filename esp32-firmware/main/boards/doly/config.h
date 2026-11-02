#ifndef _BOARD_CONFIG_H_
#define _BOARD_CONFIG_H_

#include <driver/gpio.h>

/* ============================================================================
 * doly —— DooiRobot（ESP32-P4）板级配置
 *
 * 引脚来源：Doly 开源工程 `main/boards/dooirobot/` 的实测/源码定义
 *   - config.h（音频 / 按键 / 摄像头 / 背光）
 *   - app_peripheral/{app_motor,app_servo,app_led,ir,app_imu}.h
 *   - app_peripheral/touch_button.h
 *   - app_ui/display_hal/display_hal.h（双 240x240 GC9A01，SPI2/SPI3）
 *
 * 与 Doly 原工程的差别（有意为之）：
 *   1) 本工程不复用 Doly 的 app_* 框架（MCP 工具 / 网页 / 行为编排 / 表情库），
 *      只取硬件事实，挂到我们自己的 Board 接口上。
 *   2) 第一阶段只驱动 LCD1；LCD2 的引脚先留着，以后要再接。
 * ========================================================================== */

/* ---------------------------- 音频 ---------------------------- */
#define AUDIO_INPUT_SAMPLE_RATE     16000
#define AUDIO_OUTPUT_SAMPLE_RATE    16000
#define AUDIO_INPUT_REFERENCE       true    /* ES7243E 双通道：mic + 参考，用于 AEC */

#define AUDIO_I2S_GPIO_MCLK         GPIO_NUM_33
#define AUDIO_I2S_GPIO_WS           GPIO_NUM_37
#define AUDIO_I2S_GPIO_BCLK         GPIO_NUM_34
#define AUDIO_I2S_GPIO_DIN          GPIO_NUM_36
#define AUDIO_I2S_GPIO_DOUT         GPIO_NUM_38

#define AUDIO_CODEC_PA_PIN          GPIO_NUM_40
#define AUDIO_CODEC_I2C_SDA_PIN     GPIO_NUM_21
#define AUDIO_CODEC_I2C_SCL_PIN     GPIO_NUM_20
/* ES8311 = 输出 DAC，7 位地址 0x30（Doly 用 ES8311_CODEC_DEFAULT_ADDR） */
#define AUDIO_CODEC_ES8311_ADDR     (0x30)
/* ES7243E = 输入 ADC，Doly 传 0x10，codec 内部再 <<1 成 0x20 */
#define AUDIO_CODEC_ES7243E_ADDR    (0x10)

/* ---------------------------- 按键 ---------------------------- */
#define BOOT_BUTTON_GPIO            GPIO_NUM_35

/* 触摸键（Doly 用触摸通道实现，不是普通 GPIO 按键）
 * 暂时不用；要接时按 Doly 的做法走 TOUCH_MIN_CHAN_ID+5/+6 即 GPIO7/GPIO8 */
#define TOUCH_BUTTON_LEFT_GPIO      GPIO_NUM_7
#define TOUCH_BUTTON_RIGHT_GPIO     GPIO_NUM_8

/* ---------------------------- 摄像头 -------------------------- */
/* MIPI CSI 数据线由 P4 硬件固定，这里只有 PWDN 可配；SCCB 走上面那条 I2C */
#define CAMERA_PIN_PWDN             GPIO_NUM_23

/* ------------------------- 屏 1（SPI2） ----------------------- */
#define DISPLAY_WIDTH               240
#define DISPLAY_HEIGHT              240
#define DISPLAY_OFFSET_X            0
#define DISPLAY_OFFSET_Y            0
#define DISPLAY_MIRROR_X            true    /* Doly: esp_lcd_panel_mirror(panel, true, false) */
#define DISPLAY_MIRROR_Y            false
#define DISPLAY_SWAP_XY             false

#define LCD1_PIN_SCLK               GPIO_NUM_13
#define LCD1_PIN_MOSI               GPIO_NUM_14
#define LCD1_PIN_DC                 GPIO_NUM_12
#define LCD1_PIN_RST                GPIO_NUM_15
/* Doly 的 CS 不接（NC），靠单设备挂总线 */
#define LCD1_PIN_CS                 GPIO_NUM_NC

/* ------------------------- 屏 2（SPI3，暂不驱动） ------------- */
#define LCD2_PIN_SCLK               GPIO_NUM_29
#define LCD2_PIN_MOSI               GPIO_NUM_30
#define LCD2_PIN_DC                 GPIO_NUM_28
#define LCD2_PIN_RST                GPIO_NUM_31
#define LCD2_PIN_CS                 GPIO_NUM_NC

/* 两块屏共用一根背光 */
#define LCD_PIN_BL                  GPIO_NUM_16

/* ---------------------------- 运动 ---------------------------- */
/* 第一阶段不驱动，引脚先记下来，第二阶段做自检和 MCP 工具时用 */
#define APP_MOTOR_PIN_L_A           GPIO_NUM_17
#define APP_MOTOR_PIN_L_B           GPIO_NUM_18
#define APP_MOTOR_PIN_R_A           GPIO_NUM_26
#define APP_MOTOR_PIN_R_B           GPIO_NUM_27

#define SERVO_PIN_PWR_CTRL          GPIO_NUM_10    /* 舵机电源闸门，必须先拉 */
#define SERVO_PIN_LEFT              GPIO_NUM_32
#define SERVO_PIN_RIGHT             GPIO_NUM_11

#define LED_GPIO_LEFT               GPIO_NUM_39
#define LED_GPIO_RIGHT              GPIO_NUM_9

/* ---------------------------- 传感 ---------------------------- */
#define IR_GPIO_SENSOR_1            GPIO_NUM_2
#define IR_GPIO_SENSOR_2            GPIO_NUM_3
#define IR_GPIO_SENSOR_3            GPIO_NUM_4
#define IR_GPIO_SENSOR_4            GPIO_NUM_5

#define IMU_INT_PIN                 GPIO_NUM_19    /* BMI260 */

/* ---------------------------- 电源 ---------------------------- */
#define POWER_BUTTON_PIN            GPIO_NUM_49
#define POWER_CTRL_PIN              GPIO_NUM_50
#define POWER_CHARGE_PIN            GPIO_NUM_53

#endif  /* _BOARD_CONFIG_H_ */
