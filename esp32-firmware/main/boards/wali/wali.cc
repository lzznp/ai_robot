// ============================================================
// wali.cc — 瓦力（Wali）板级实现
//
// 硬件（2026-10-22 实测，见 工作文档\瓦力-硬件台账.md）：
//   ESP32-S3-WROOM-1-N16R8（16MB Flash / 8MB PSRAM）
//   电机 A = GPIO13/14    电机 B = GPIO17/18   （TC1508 双路 H 桥）
//   左手舵机 = GPIO11     右手舵机 = GPIO12    （50Hz PWM）
//   屏 = SSD1306 I2C 128x32（SDA 41 / SCL 42）
//   音频 = Simplex I2S：麦克风 4/5/6，喇叭 7/15/16
//   按键 = BOOT 0 / 触摸 47 / 音量+ 40 / 音量- 39
//   ⚠ 板上有电源开关：打开才给电机/舵机供电
//
// MCP 工具（能被语音/后台直接调）：
//   self.motor.forward / backward / turn_left / turn_right / stop
//   self.servo.left_wave / right_wave
// ============================================================

#include "wifi_board.h"
#include "codecs/no_audio_codec.h"
#include "display/oled_display.h"
#include "system_reset.h"
#include "application.h"
#include "button.h"
#include "config.h"
#include "mcp_server.h"
#include "led/single_led.h"
#include "assets/lang_config.h"

#include <wifi_station.h>
#include <esp_log.h>
#include <driver/i2c_master.h>
#include <driver/gpio.h>
#include <driver/ledc.h>
#include <esp_lcd_panel_ops.h>
#include <esp_lcd_panel_vendor.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

#ifdef SH1106
#include <esp_lcd_panel_sh1106.h>
#endif

#define TAG "WaliBoard"

// ------------------------------------------------------------
// 直流电机（TC1508）：GPIO 直驱，够用（速度控制以后再说）
// ------------------------------------------------------------
class WaliMotor {
public:
    void Init(gpio_num_t in1, gpio_num_t in2) {
        in1_ = in1;
        in2_ = in2;
        gpio_config_t io = {};
        io.pin_bit_mask = (1ULL << in1) | (1ULL << in2);
        io.mode = GPIO_MODE_OUTPUT;
        io.pull_up_en = GPIO_PULLUP_DISABLE;
        io.pull_down_en = GPIO_PULLDOWN_DISABLE;
        io.intr_type = GPIO_INTR_DISABLE;
        gpio_config(&io);
        Stop();
    }
    void Forward() { Set(1, 0); }
    void Backward() { Set(0, 1); }
    void Brake() { Set(1, 1); }
    void Stop() { Set(0, 0); }

private:
    gpio_num_t in1_ = GPIO_NUM_NC;
    gpio_num_t in2_ = GPIO_NUM_NC;
    void Set(int a, int b) {
        if (in1_ != GPIO_NUM_NC) gpio_set_level(in1_, a);
        if (in2_ != GPIO_NUM_NC) gpio_set_level(in2_, b);
    }
};

// ------------------------------------------------------------
// 舵机：50Hz / 13bit
// ------------------------------------------------------------
class WaliServo {
public:
    void Init(gpio_num_t pin, ledc_channel_t ch) {
        pin_ = pin;
        ch_ = ch;

        ledc_timer_config_t timer = {};
        timer.speed_mode = LEDC_LOW_SPEED_MODE;
        timer.duty_resolution = LEDC_TIMER_13_BIT;
        timer.timer_num = LEDC_TIMER_1;
        timer.freq_hz = 50;
        timer.clk_cfg = LEDC_AUTO_CLK;
        ledc_timer_config(&timer);

        ledc_channel_config_t c = {};
        c.gpio_num = pin;
        c.speed_mode = LEDC_LOW_SPEED_MODE;
        c.channel = ch;
        c.intr_type = LEDC_INTR_DISABLE;
        c.timer_sel = LEDC_TIMER_1;
        c.duty = 0;
        c.hpoint = 0;
        ledc_channel_config(&c);

        SetAngle(90);
    }

    void SetAngle(int angle) {
        if (angle < 0) angle = 0;
        if (angle > 180) angle = 180;
        // 20ms 周期；0.5ms=205, 2.5ms=1024（13bit / 8192）
        uint32_t duty = 205 + (uint32_t)((1024 - 205) * angle / 180);
        ledc_set_duty(LEDC_LOW_SPEED_MODE, ch_, duty);
        ledc_update_duty(LEDC_LOW_SPEED_MODE, ch_);
    }

    void Wave() {
        SetAngle(0);
        vTaskDelay(pdMS_TO_TICKS(400));
        SetAngle(180);
        vTaskDelay(pdMS_TO_TICKS(400));
        SetAngle(90);
    }

private:
    gpio_num_t pin_ = GPIO_NUM_NC;
    ledc_channel_t ch_ = LEDC_CHANNEL_0;
};

// ------------------------------------------------------------
// 板子
// ------------------------------------------------------------
class WaliBoard : public WifiBoard {
private:
    i2c_master_bus_handle_t display_i2c_bus_ = nullptr;
    esp_lcd_panel_io_handle_t panel_io_ = nullptr;
    esp_lcd_panel_handle_t panel_ = nullptr;
    Display* display_ = nullptr;

    Button boot_button_;
    Button touch_button_;
    Button volume_up_button_;
    Button volume_down_button_;

    WaliMotor motor_a_;
    WaliMotor motor_b_;
    WaliServo servo_l_;
    WaliServo servo_r_;

    void InitializeDisplayI2c() {
        i2c_master_bus_config_t bus_config = {
            .i2c_port = (i2c_port_t)0,
            .sda_io_num = DISPLAY_SDA_PIN,
            .scl_io_num = DISPLAY_SCL_PIN,
            .clk_source = I2C_CLK_SRC_DEFAULT,
            .glitch_ignore_cnt = 7,
            .intr_priority = 0,
            .trans_queue_depth = 0,
            .flags = { .enable_internal_pullup = 1 },
        };
        ESP_ERROR_CHECK(i2c_new_master_bus(&bus_config, &display_i2c_bus_));
    }

    void InitializeSsd1306Display() {
        esp_lcd_panel_io_i2c_config_t io_config = {
            .dev_addr = 0x3C,
            .on_color_trans_done = nullptr,
            .user_ctx = nullptr,
            .control_phase_bytes = 1,
            .dc_bit_offset = 6,
            .lcd_cmd_bits = 8,
            .lcd_param_bits = 8,
            .flags = {
                .dc_low_on_data = 0,
                .disable_control_phase = 0,
            },
            .scl_speed_hz = 400 * 1000,
        };
        ESP_ERROR_CHECK(esp_lcd_new_panel_io_i2c_v2(display_i2c_bus_, &io_config, &panel_io_));

        ESP_LOGI(TAG, "Install SSD1306 driver (%dx%d)", DISPLAY_WIDTH, DISPLAY_HEIGHT);
        esp_lcd_panel_dev_config_t panel_config = {};
        panel_config.reset_gpio_num = -1;
        panel_config.bits_per_pixel = 1;

        esp_lcd_panel_ssd1306_config_t ssd1306_config = {
            .height = static_cast<uint8_t>(DISPLAY_HEIGHT),
        };
        panel_config.vendor_config = &ssd1306_config;

#ifdef SH1106
        ESP_ERROR_CHECK(esp_lcd_new_panel_sh1106(panel_io_, &panel_config, &panel_));
#else
        ESP_ERROR_CHECK(esp_lcd_new_panel_ssd1306(panel_io_, &panel_config, &panel_));
#endif

        ESP_ERROR_CHECK(esp_lcd_panel_reset(panel_));
        if (esp_lcd_panel_init(panel_) != ESP_OK) {
            ESP_LOGE(TAG, "Failed to initialize display");
            display_ = new NoDisplay();
            return;
        }
        ESP_ERROR_CHECK(esp_lcd_panel_invert_color(panel_, false));
        ESP_ERROR_CHECK(esp_lcd_panel_disp_on_off(panel_, true));

        display_ = new OledDisplay(panel_io_, panel_, DISPLAY_WIDTH, DISPLAY_HEIGHT,
                                   DISPLAY_MIRROR_X, DISPLAY_MIRROR_Y);
        ESP_LOGI(TAG, "Display ready");
    }

    void InitializeButtons() {
        boot_button_.OnClick([this]() {
            auto& app = Application::GetInstance();
            if (app.GetDeviceState() == kDeviceStateStarting &&
                !WifiStation::GetInstance().IsConnected()) {
                ResetWifiConfiguration();
            }
            app.ToggleChatState();
        });
        // 长按 BOOT = 重新配网（进 AP 模式）
        boot_button_.OnLongPress([this]() {
            ESP_LOGW(TAG, "长按 BOOT -> 重新配网");
            this->ResetWifiConfiguration();
        });
        touch_button_.OnPressDown([]() {
            Application::GetInstance().StartListening();
        });
        touch_button_.OnPressUp([]() {
            Application::GetInstance().StopListening();
        });
        volume_up_button_.OnClick([this]() {
            auto codec = GetAudioCodec();
            auto volume = codec->output_volume() + 10;
            if (volume > 100) volume = 100;
            codec->SetOutputVolume(volume);
            GetDisplay()->ShowNotification(Lang::Strings::VOLUME + std::to_string(volume));
        });
        volume_down_button_.OnClick([this]() {
            auto codec = GetAudioCodec();
            auto volume = codec->output_volume() - 10;
            if (volume < 0) volume = 0;
            codec->SetOutputVolume(volume);
            GetDisplay()->ShowNotification(Lang::Strings::VOLUME + std::to_string(volume));
        });
    }

    // ---- 动作：跑 WALI_MOVE_MS 毫秒后自动停（避免"说一句就一直跑"）----
    void MoveForwardFor(int ms) {
        motor_a_.Forward();
        motor_b_.Forward();
        vTaskDelay(pdMS_TO_TICKS(ms));
        motor_a_.Stop();
        motor_b_.Stop();
    }
    void MoveBackwardFor(int ms) {
        motor_a_.Backward();
        motor_b_.Backward();
        vTaskDelay(pdMS_TO_TICKS(ms));
        motor_a_.Stop();
        motor_b_.Stop();
    }
    void TurnLeftFor(int ms) {          // 原地左转：A 退 + B 进
        motor_a_.Backward();
        motor_b_.Forward();
        vTaskDelay(pdMS_TO_TICKS(ms));
        motor_a_.Stop();
        motor_b_.Stop();
    }
    void TurnRightFor(int ms) {         // 原地右转：A 进 + B 退
        motor_a_.Forward();
        motor_b_.Backward();
        vTaskDelay(pdMS_TO_TICKS(ms));
        motor_a_.Stop();
        motor_b_.Stop();
    }

    void InitializeTools() {
        motor_a_.Init(WALI_MOTOR_A_IN1, WALI_MOTOR_A_IN2);
        motor_b_.Init(WALI_MOTOR_B_IN1, WALI_MOTOR_B_IN2);
        servo_l_.Init(WALI_SERVO_L_PIN, LEDC_CHANNEL_0);
        servo_r_.Init(WALI_SERVO_R_PIN, LEDC_CHANNEL_1);

        auto& mcp_server = McpServer::GetInstance();

        mcp_server.AddTool("self.motor.forward", "让机器人向前走一小段", PropertyList(),
            [this](const PropertyList&) -> ReturnValue {
                MoveForwardFor(WALI_MOVE_MS);
                return true;
            });
        mcp_server.AddTool("self.motor.backward", "让机器人向后退一小段", PropertyList(),
            [this](const PropertyList&) -> ReturnValue {
                MoveBackwardFor(WALI_MOVE_MS);
                return true;
            });
        mcp_server.AddTool("self.motor.turn_left", "让机器人原地左转", PropertyList(),
            [this](const PropertyList&) -> ReturnValue {
                TurnLeftFor(WALI_MOVE_MS);
                return true;
            });
        mcp_server.AddTool("self.motor.turn_right", "让机器人原地右转", PropertyList(),
            [this](const PropertyList&) -> ReturnValue {
                TurnRightFor(WALI_MOVE_MS);
                return true;
            });
        mcp_server.AddTool("self.motor.stop", "立刻停止移动", PropertyList(),
            [this](const PropertyList&) -> ReturnValue {
                motor_a_.Stop();
                motor_b_.Stop();
                return true;
            });
        mcp_server.AddTool("self.servo.left_wave", "挥动左手（左手舵机）", PropertyList(),
            [this](const PropertyList&) -> ReturnValue {
                servo_l_.Wave();
                return true;
            });
        mcp_server.AddTool("self.servo.right_wave", "挥动右手（右手舵机）", PropertyList(),
            [this](const PropertyList&) -> ReturnValue {
                servo_r_.Wave();
                return true;
            });

        ESP_LOGI(TAG, "电机/舵机/MCP 工具就绪");
    }

public:
    WaliBoard() :
        boot_button_(BOOT_BUTTON_GPIO),
        touch_button_(TOUCH_BUTTON_GPIO),
        volume_up_button_(VOLUME_UP_BUTTON_GPIO),
        volume_down_button_(VOLUME_DOWN_BUTTON_GPIO) {

        ESP_LOGI(TAG, "初始化瓦力板：电机 A 13/14，电机 B 17/18，舵机 11/12");
        InitializeDisplayI2c();
        InitializeSsd1306Display();
        InitializeButtons();
        InitializeTools();
    }

    virtual Led* GetLed() override {
        static SingleLed led(BUILTIN_LED_GPIO);
        return &led;
    }

    virtual AudioCodec* GetAudioCodec() override {
        static NoAudioCodecSimplex audio_codec(AUDIO_INPUT_SAMPLE_RATE, AUDIO_OUTPUT_SAMPLE_RATE,
            AUDIO_I2S_SPK_GPIO_BCLK, AUDIO_I2S_SPK_GPIO_LRCK, AUDIO_I2S_SPK_GPIO_DOUT,
            AUDIO_I2S_MIC_GPIO_SCK, AUDIO_I2S_MIC_GPIO_WS, AUDIO_I2S_MIC_GPIO_DIN);
        return &audio_codec;
    }

    virtual Display* GetDisplay() override {
        return display_;
    }
};

DECLARE_BOARD(WaliBoard);
