#ifndef _BOARD_CONFIG_H_
#define _BOARD_CONFIG_H_

#include <driver/gpio.h>

// ============================================================
// ★ 自检模式开关（2026-10-22 新增，和 MOSS 用同一套引擎）
//   1 = 上电后不启动 WiFi/Application/屏/摄像头，直接进元件自检
//       交互：BOOT 键单击换项、长按执行；结果只看串口
//   0 = 正常固件
//   项表在 boards/lingkong-s3-moc-cam-1.54tft/selftest_items.cc
// ============================================================
#define LINGKONG_SELFTEST 0

// ========== 电源管理 ==========
#define POWER_CHARGE_DETECT_PIN GPIO_NUM_11
#define POWER_ADC_UNIT ADC_UNIT_1
#define POWER_ADC_CHANNEL ADC_CHANNEL_9

// ========== 音频 ==========
#define AUDIO_INPUT_SAMPLE_RATE  24000
#define AUDIO_OUTPUT_SAMPLE_RATE 24000

#define AUDIO_I2S_GPIO_MCLK GPIO_NUM_42
#define AUDIO_I2S_GPIO_WS GPIO_NUM_38
#define AUDIO_I2S_GPIO_BCLK GPIO_NUM_41
#define AUDIO_I2S_GPIO_DIN GPIO_NUM_40
#define AUDIO_I2S_GPIO_DOUT GPIO_NUM_39

#define AUDIO_CODEC_PA_PIN      GPIO_NUM_NC
#define AUDIO_CODEC_I2C_SDA_PIN GPIO_NUM_21
#define AUDIO_CODEC_I2C_SCL_PIN GPIO_NUM_14
#define AUDIO_CODEC_ES8311_ADDR ES8311_CODEC_DEFAULT_ADDR

// ========== 按钮 ==========
#define BUILTIN_LED_GPIO        GPIO_NUM_NC
#define BOOT_BUTTON_GPIO        GPIO_NUM_0
#define VOLUME_UP_BUTTON_GPIO   GPIO_NUM_NC
#define VOLUME_DOWN_BUTTON_GPIO GPIO_NUM_NC

// ========== 屏幕 ==========
#define DISPLAY_SDA GPIO_NUM_48
#define DISPLAY_SCL GPIO_NUM_45
#define DISPLAY_DC GPIO_NUM_47
#define DISPLAY_CS GPIO_NUM_NC
#define DISPLAY_RES GPIO_NUM_NC
#define DISPLAY_WIDTH   240
#define DISPLAY_HEIGHT  320
#define DISPLAY_MIRROR_X false
#define DISPLAY_MIRROR_Y false
#define DISPLAY_SWAP_XY false
#define DISPLAY_OFFSET_X  0
#define DISPLAY_OFFSET_Y  0

// ========== 摄像头 ==========

#define CAMERA_PIN_PWDN GPIO_NUM_NC
#define CAMERA_PIN_RESET GPIO_NUM_NC
#define CAMERA_PIN_XCLK GPIO_NUM_8
#define CAMERA_PIN_SIOD GPIO_NUM_21
#define CAMERA_PIN_SIOC GPIO_NUM_14
#define CAMERA_PIN_D7 GPIO_NUM_3
#define CAMERA_PIN_D6 GPIO_NUM_18
#define CAMERA_PIN_D5 GPIO_NUM_17
#define CAMERA_PIN_D4 GPIO_NUM_15
#define CAMERA_PIN_D3 GPIO_NUM_6
#define CAMERA_PIN_D2 GPIO_NUM_4
#define CAMERA_PIN_D1 GPIO_NUM_5
#define CAMERA_PIN_D0 GPIO_NUM_7
#define CAMERA_PIN_VSYNC GPIO_NUM_9
#define CAMERA_PIN_HREF GPIO_NUM_46
#define CAMERA_PIN_PCLK GPIO_NUM_16
#define XCLK_FREQ_HZ 20000000


// ========== 4G 模块 ==========
#define ML307_RX_PIN GPIO_NUM_44
#define ML307_TX_PIN GPIO_NUM_43

// ========== 电机控制（TC118S） ==========
#define MOTOR1_IN1 GPIO_NUM_1
#define MOTOR1_IN2 GPIO_NUM_2
#define MOTOR2_IN1 GPIO_NUM_12
#define MOTOR2_IN2 GPIO_NUM_13

// ========== 舵机控制（PWM） ==========
#define SERVO1_PIN GPIO_NUM_3

// ========== 各种灯 ==========
// ⚠️ 2026-10-27 实测：下面 5 个宏是从"带摄像头"的板子抄来的占位符，
//    和 CAMERA_PIN_D0..D3 / XCLK 完全重叠，**不是这块板量出来的**。
//    实测结论见 工作文档\月球车-硬件台账.md：
//      · 板上灯座丝印 G / V / S；3 针 5V WS2812 灯带 DIN 接 GPIO5 已点亮（GRB）
//      · 其余 4 个"灯"脚未见到实物
//    ⇒ GPIO5 现阶段当 WS2812 数据脚用，别再当"车顶右灯"打电平。
#define LED_1_PIN GPIO_NUM_4    // 车顶左灯（占位符，未证实）
#define LED_2_PIN GPIO_NUM_5    // 车顶右灯（占位符）；2026-10-27 实测用作 WS2812 数据脚
#define LED_3_PIN GPIO_NUM_6    // 车底左灯（占位符，未证实）
#define LED_4_PIN GPIO_NUM_7    // 车底右灯（占位符，未证实）
#define LED_STRIP_PIN GPIO_NUM_8 // 车厢灯板（占位符，未证实）

#endif // _BOARD_CONFIG_H_