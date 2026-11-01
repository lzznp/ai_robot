// ============================================================
// board_moss_550w.cc — MOSS 550W 板卡完整实现
//
// 硬件配置:
//   - 主控: ESP32-S3-WROOM-1-N16R8
//   - 扬声器: NS4168 I2S 功放 (标准 I2S 模式, 无 MCLK)
//   - 麦克风: INMP441 PDM 数字麦克风
//   - 连接: 74HC595 步进电机控制, WS2812 双路灯带
//
// 音频架构: NoAudioCodecSimplexPdm
//   - I2S_NUM_1 → 扬声器 (标准 I2S TX, 32bit mono)
//   - I2S_NUM_0 → 麦克风 (PDM RX, 16bit mono)
//
// 参考实现: df-s3-ai-cam/df_s3_ai_cam.cc (DFRobot 摄像头板)
//           doit-s3-aibox/doit_s3_aibox.cc (Doit S3 AI Box)
// ============================================================

#include "wifi_board.h"
#include "codecs/no_audio_codec.h"
#include "application.h"
#include "button.h"
#include "config.h"
#include "led/gpio_led.h"

#include <wifi_station.h>
#include <esp_log.h>
#include <driver/gpio.h>

// ============================================================
// 宏定义映射: 将 MOSS 550W config.h 原始宏名映射为框架标准命名
//
// 如果在 config.h 中直接定义了以下宏，请删除此映射段:
//   AUDIO_I2S_SPK_GPIO_BCLK, AUDIO_I2S_SPK_GPIO_LRCK,
//   AUDIO_I2S_SPK_GPIO_DOUT, AUDIO_I2S_MIC_GPIO_SCK,
//   AUDIO_I2S_MIC_GPIO_DIN
// ============================================================
#ifndef AUDIO_I2S_SPK_GPIO_BCLK
#define AUDIO_I2S_SPK_GPIO_BCLK  I2S_BCLK_GPIO    // GPIO_NUM_10
#endif
#ifndef AUDIO_I2S_SPK_GPIO_LRCK
#define AUDIO_I2S_SPK_GPIO_LRCK  I2S_LRCK_GPIO    // GPIO_NUM_11
#endif
#ifndef AUDIO_I2S_SPK_GPIO_DOUT
#define AUDIO_I2S_SPK_GPIO_DOUT  I2S_DIN_GPIO     // GPIO_NUM_9  (NS4168 DOUT)
#endif
#ifndef AUDIO_I2S_MIC_GPIO_SCK
#define AUDIO_I2S_MIC_GPIO_SCK   MIC_BCK_GPIO     // GPIO_NUM_13 (INMP441 PDM CLK)
#endif
#ifndef AUDIO_I2S_MIC_GPIO_DIN
#define AUDIO_I2S_MIC_GPIO_DIN   MIC_DIN_GPIO     // GPIO_NUM_12 (INMP441 PDM DATA)
#endif

#define TAG "Moss550W"

class Moss550WBoard : public WifiBoard {
private:
    Button boot_button_;

    // ============================================================
    // BOOT 按键初始化
    //
    // 单击: 切换聊天状态 (ToggleChatState)
    // 长按 + 未连接: 重置 WiFi 配置
    // ============================================================
    void InitializeButtons() {
        boot_button_.OnClick([this]() {
            auto& app = Application::GetInstance();
            if (app.GetDeviceState() == kDeviceStateStarting &&
                !WifiStation::GetInstance().IsConnected()) {
                ResetWifiConfiguration();
            }
            app.ToggleChatState();
        });
    }

    // ============================================================
    // GPIO 上拉初始化 (用于特定引脚电平设置)
    //
    // MOSS 550W 某些外设需要在启动时拉高/拉低电平。
    // 可根据实际硬件原理图调整。
    // ============================================================
    void InitializeGpio(gpio_num_t gpio_num, int level) {
        gpio_config_t config = {
            .pin_bit_mask = (1ULL << gpio_num),
            .mode = GPIO_MODE_OUTPUT,
            .pull_up_en = GPIO_PULLUP_ENABLE,
            .pull_down_en = GPIO_PULLDOWN_DISABLE,
            .intr_type = GPIO_INTR_DISABLE,
        };
        ESP_ERROR_CHECK(gpio_config(&config));
        gpio_set_level(gpio_num, level);
    }

public:
    Moss550WBoard() : boot_button_(BOOT_BUTTON_GPIO) {
        ESP_LOGI(TAG, "Initializing MOSS 550W Board...");

        InitializeButtons();

        // 如需要特定 GPIO 上拉，取消注释并按需调整
        // InitializeGpio(GPIO_NUM_48, 1);  // 示例: 拉高 WS2812 电源

        ESP_LOGI(TAG, "MOSS 550W Board initialized successfully!");
    }

    virtual ~Moss550WBoard() {}

    // ============================================================
    // 音频编解码器 (AudioCodec)
    //
    // 使用 NoAudioCodecSimplexPdm 实现:
    //   扬声器输出: I2S_NUM_1 — 标准 I2S TX, 32bit mono
    //   麦克风输入: I2S_NUM_0 — PDM RX, 16bit mono
    //
    // 构造函数参数顺序:
    //   (input_sample_rate, output_sample_rate,
    //    spk_bclk, spk_lrck, spk_dout,
    //    mic_sck, mic_din)
    //
    // I2S 引脚分配 (I2S_NUM_1 — 扬声器):
    //   BCLK = GPIO_NUM_10  (NS4168 BCK)
    //   LRCK = GPIO_NUM_11  (NS4168 WS/LRCK)
    //   DOUT = GPIO_NUM_9   (NS4168 DIN)
    //
    // PDM 引脚分配 (I2S_NUM_0 — 麦克风):
    //   SCK  = GPIO_NUM_13  (INMP441 PDM CLK)
    //   DIN  = GPIO_NUM_12  (INMP441 PDM DATA)
    // ============================================================
    virtual AudioCodec* GetAudioCodec() override {
        static NoAudioCodecSimplexPdm audio_codec(
            AUDIO_INPUT_SAMPLE_RATE,          // 24000
            AUDIO_OUTPUT_SAMPLE_RATE,         // 24000
            AUDIO_I2S_SPK_GPIO_BCLK,          // GPIO_NUM_10
            AUDIO_I2S_SPK_GPIO_LRCK,          // GPIO_NUM_11
            AUDIO_I2S_SPK_GPIO_DOUT,          // GPIO_NUM_9
            AUDIO_I2S_MIC_GPIO_SCK,           // GPIO_NUM_13 (PDM CLK)
            AUDIO_I2S_MIC_GPIO_DIN            // GPIO_NUM_12 (PDM DATA)
        );
        return &audio_codec;
    }

    // ============================================================
    // LED (可选)
    //
    // MOSS 550W 有双路 WS2812 灯带:
    //   第一组 3 颗 2020 灯珠 (GPIO_NUM_7)
    //   第二组 2 颗 4020 灯珠 (GPIO_NUM_48)
    //
    // 框架的 GpioLed 只支持单 GPIO LED。
    // WS2812 需要通过 RMT 驱动 LedStrip 实现，
    // 这里返回默认 LED 先确保基础功能正常。
    // ============================================================
    virtual Led* GetLed() override {
        static GpioLed led(GPIO_NUM_NC, 0);
        return &led;
    }

    // ============================================================
    // 电池电量检测 (可选)
    //
    // MOSS 550W 有 ADC 电池检测引脚:
    //   VBAT_ADC_GPIO   = GPIO_NUM_8   (ADC1_CH7)
    //   VBAT_ADC_CHANNEL = ADC_CHANNEL_7
    //
    // 框架提供默认实现返回 false，
    // 如需电池显示，按此重写。
    // ============================================================
    // virtual bool GetBatteryLevel(int& level, bool& charging, bool& discharging) override {
    //     // TODO: 实现电池检测逻辑
    //     return false;
    // }

    // ============================================================
    // 屏幕 (MOSS 550W 已放弃显示)
    // ============================================================
    // virtual Display* GetDisplay() override { return nullptr; }

    // ============================================================
    // 摄像头 (MOSS 550W 摄像头引脚与音频冲突，暂禁用)
    //
    //   CAM_D5 = GPIO_10 → BCLK    冲突
    //   CAM_D4 = GPIO_11 → LRCK    冲突
    //   CAM_D2 = GPIO_13 → PDM CLK 冲突
    //   CAM_D3 = GPIO_12 → PDM DATA 冲突
    // ============================================================
    // virtual Camera* GetCamera() override { return nullptr; }
};

DECLARE_BOARD(Moss550WBoard);
