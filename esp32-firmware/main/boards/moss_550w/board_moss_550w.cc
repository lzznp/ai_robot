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
// ============================================================

#include "wifi_board.h"
#include "codecs/no_audio_codec.h"
#include "application.h"
#include "button.h"
#include "config.h"
#include "led/gpio_led.h"
#include "motor_control.h"          // ← 新增：电机控制头文件

#include <wifi_station.h>
#include <esp_log.h>
#include <driver/gpio.h>

#define TAG "Moss550W"

// ============================================================
// 宏定义映射: 将 MOSS 550W config.h 原始宏名映射为框架标准命名
// ============================================================
#ifndef AUDIO_I2S_SPK_GPIO_BCLK
#define AUDIO_I2S_SPK_GPIO_BCLK  I2S_BCLK_GPIO    // GPIO_NUM_10
#endif
#ifndef AUDIO_I2S_SPK_GPIO_LRCK
#define AUDIO_I2S_SPK_GPIO_LRCK  I2S_LRCK_GPIO    // GPIO_NUM_9
#endif
#ifndef AUDIO_I2S_SPK_GPIO_DOUT
#define AUDIO_I2S_SPK_GPIO_DOUT  I2S_DIN_GPIO     // GPIO_NUM_11
#endif
#ifndef AUDIO_I2S_MIC_GPIO_SCK
#define AUDIO_I2S_MIC_GPIO_SCK   MIC_BCK_GPIO     // GPIO_NUM_13
#endif
#ifndef AUDIO_I2S_MIC_GPIO_DIN
#define AUDIO_I2S_MIC_GPIO_DIN   MIC_DIN_GPIO     // GPIO_NUM_12
#endif

class Moss550WBoard : public WifiBoard {
private:
    Button boot_button_;

    // ============================================================
    // BOOT 按键初始化
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
    // ★ 电机测试函数
    // ============================================================
    void TestMotor() {
        ESP_LOGI(TAG, "===== Motor Test Start =====");

        // 初始化电机驱动
        motor_control_init();

        // 设置速度：每秒 100 步（24BYJ48 转一圈约 512 步）
        motor_set_speed(MOTOR_1, 100);
        motor_set_speed(MOTOR_2, 100);

        // ---- 电机1 正转一圈 ----
        ESP_LOGI(TAG, "Motor 1: CW 512 steps...");
        motor_step(MOTOR_1, MOTOR_CW, 512);
        vTaskDelay(pdMS_TO_TICKS(1000));

        // ---- 电机1 反转一圈 ----
        ESP_LOGI(TAG, "Motor 1: CCW 512 steps...");
        motor_step(MOTOR_1, MOTOR_CCW, 512);
        vTaskDelay(pdMS_TO_TICKS(1000));

        // ---- 电机2 正转一圈 ----
        ESP_LOGI(TAG, "Motor 2: CW 512 steps...");
        motor_step(MOTOR_2, MOTOR_CW, 512);
        vTaskDelay(pdMS_TO_TICKS(1000));

        // ---- 电机2 反转一圈 ----
        ESP_LOGI(TAG, "Motor 2: CCW 512 steps...");
        motor_step(MOTOR_2, MOTOR_CCW, 512);
        vTaskDelay(pdMS_TO_TICKS(1000));

        // ---- 持续旋转测试 (2秒) ----
        ESP_LOGI(TAG, "Motor 1: CW continuous for 2 seconds...");
        motor_rotate(MOTOR_1, MOTOR_CW);
        vTaskDelay(pdMS_TO_TICKS(2000));
        motor_stop(MOTOR_1);
        vTaskDelay(pdMS_TO_TICKS(500));

        ESP_LOGI(TAG, "Motor 2: CCW continuous for 2 seconds...");
        motor_rotate(MOTOR_2, MOTOR_CCW);
        vTaskDelay(pdMS_TO_TICKS(2000));
        motor_stop(MOTOR_2);

        ESP_LOGI(TAG, "===== Motor Test End =====");
    }

public:
    Moss550WBoard() : boot_button_(BOOT_BUTTON_GPIO) {
        ESP_LOGI(TAG, "Initializing MOSS 550W Board...");

        InitializeButtons();

        ESP_LOGI(TAG, "MOSS 550W Board initialized successfully!");

        // ★ 启动电机测试任务（延迟 3 秒，等系统稳定）
        xTaskCreate([](void* arg) {
            auto* board = (Moss550WBoard*)arg;
            vTaskDelay(pdMS_TO_TICKS(3000));
            board->TestMotor();
            vTaskDelete(NULL);
        }, "motor_test", 4096, this, 1, NULL);
    }

    virtual ~Moss550WBoard() {}

    // ============================================================
    // 音频编解码器
    // ============================================================
    virtual AudioCodec* GetAudioCodec() override {
        static NoAudioCodecSimplexPdm audio_codec(
            AUDIO_INPUT_SAMPLE_RATE,          // 16000
            AUDIO_OUTPUT_SAMPLE_RATE,         // 16000
            AUDIO_I2S_SPK_GPIO_BCLK,          // GPIO_NUM_10
            AUDIO_I2S_SPK_GPIO_LRCK,          // GPIO_NUM_9
            AUDIO_I2S_SPK_GPIO_DOUT,          // GPIO_NUM_11
            AUDIO_I2S_MIC_GPIO_SCK,           // GPIO_NUM_13
            AUDIO_I2S_MIC_GPIO_DIN            // GPIO_NUM_12
        );
        return &audio_codec;
    }

    // ============================================================
    // LED
    // ============================================================
    virtual Led* GetLed() override {
        static GpioLed led(LED_1313_GPIO, 0);
        return &led;
    }
};

DECLARE_BOARD(Moss550WBoard);