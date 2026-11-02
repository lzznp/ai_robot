#include "wifi_board.h"
#include "codecs/es8311_audio_codec.h"
#include "display/lcd_display.h"
#include "display/emote_display.h"
#include "application.h"
#include "button.h"
#include "config.h"
#include "i2c_device.h"
#include "esp32_camera.h"
#include "power_save_timer.h"
#include "power_manager.h"

// ★ 新增：运动控制头文件
#include "motor_control.h"
#include "servo_control.h"

// ★ 新增：元件自检引擎（components/selftest/，和 MOSS 共用）
#include "selftest.h"

// 月球车自己的项表（boards/lingkong-s3-moc-cam-1.54tft/selftest_items.cc 里定义）
extern "C" const st_config_t lingkong_selftest_config;

#include <esp_log.h>
#include <esp_sleep.h>
#include <esp_lcd_panel_vendor.h>
#include <driver/i2c_master.h>
#include <driver/rtc_io.h>
#include <driver/spi_common.h>
#include <wifi_station.h>

#include <esp_lcd_touch_ft5x06.h>
#include <esp_lvgl_port.h>
#include <lvgl.h>

#define TAG "LichuangDevBoard"

class TCA6408 : public I2cDevice {
public:
    TCA6408(i2c_master_bus_handle_t i2c_bus, uint8_t addr) : I2cDevice(i2c_bus, addr) {
        WriteReg(0x03, 0x00);
        WriteReg(0x01, 0xFF);
        WriteReg(0x02, 0x00);
    }

    void SetOutputState(uint8_t bit, uint8_t level) {
        uint8_t data = ReadReg(0x01);
        data = (data & ~(1 << bit)) | (level << bit);
        WriteReg(0x01, data);
    }
};

class CustomAudioCodec : public Es8311AudioCodec {
private:
    TCA6408* tca6408_;

public:
    CustomAudioCodec(i2c_master_bus_handle_t i2c_bus, TCA6408* tca6408)
        : Es8311AudioCodec(i2c_bus, I2C_NUM_0, AUDIO_INPUT_SAMPLE_RATE, AUDIO_OUTPUT_SAMPLE_RATE,
            AUDIO_I2S_GPIO_MCLK, AUDIO_I2S_GPIO_BCLK, AUDIO_I2S_GPIO_WS, AUDIO_I2S_GPIO_DOUT, AUDIO_I2S_GPIO_DIN,
            AUDIO_CODEC_PA_PIN, AUDIO_CODEC_ES8311_ADDR),
          tca6408_(tca6408) {
    }

    virtual void EnableOutput(bool enable) override {
        Es8311AudioCodec::EnableOutput(enable);
        tca6408_->SetOutputState(6, enable ? 1 : 0);
    }
};

class LichuangDevBoard : public WifiBoard {
private:
    i2c_master_bus_handle_t i2c_bus_;
    PowerManager* power_manager_;
    PowerSaveTimer* power_save_timer_;
    Button boot_button_;
    Display* display_;
    TCA6408* tca6408_;
    Esp32Camera* camera_ = nullptr;

    // ★ 运动控制对象
    MotorControl motor1_;
    MotorControl motor2_;
    ServoControl servo1_;

    void InitializePowerManager() {
        power_manager_ = new PowerManager(POWER_CHARGE_DETECT_PIN);
        power_manager_->OnChargingStatusChanged([this](bool is_charging) {
            // 可以添加充电状态处理
        });
    }

    void InitializeI2c() {
        i2c_master_bus_config_t i2c_bus_cfg = {
            .i2c_port = (i2c_port_t)1,
            .sda_io_num = AUDIO_CODEC_I2C_SDA_PIN,
            .scl_io_num = AUDIO_CODEC_I2C_SCL_PIN,
            .clk_source = I2C_CLK_SRC_DEFAULT,
            .glitch_ignore_cnt = 7,
            .intr_priority = 0,
            .trans_queue_depth = 0,
            .flags = { .enable_internal_pullup = 0 },
        };
        ESP_ERROR_CHECK(i2c_new_master_bus(&i2c_bus_cfg, &i2c_bus_));
        tca6408_ = new TCA6408(i2c_bus_, 0x20);
    }

    void InitializeSpi() {
        spi_bus_config_t buscfg = {};
        buscfg.mosi_io_num = DISPLAY_SDA;
        buscfg.miso_io_num = GPIO_NUM_NC;
        buscfg.sclk_io_num = DISPLAY_SCL;
        buscfg.quadwp_io_num = GPIO_NUM_NC;
        buscfg.quadhd_io_num = GPIO_NUM_NC;
        buscfg.max_transfer_sz = DISPLAY_WIDTH * DISPLAY_HEIGHT * sizeof(uint16_t);
        ESP_ERROR_CHECK(spi_bus_initialize(SPI3_HOST, &buscfg, SPI_DMA_CH_AUTO));
    }

    void InitializeButtons() {
        boot_button_.OnClick([this]() {
            ESP_LOGI(TAG, "Boot button pressed");
        });
    }

    void InitializeSt7789Display() {
        esp_lcd_panel_io_handle_t panel_io = nullptr;
        esp_lcd_panel_handle_t panel = nullptr;

        esp_lcd_panel_io_spi_config_t io_config = {};
        io_config.cs_gpio_num = DISPLAY_CS;
        io_config.dc_gpio_num = DISPLAY_DC;
        io_config.spi_mode = 3;
        io_config.pclk_hz = 80 * 1000 * 1000;
        io_config.trans_queue_depth = 10;
        io_config.lcd_cmd_bits = 8;
        io_config.lcd_param_bits = 8;
        ESP_ERROR_CHECK(esp_lcd_new_panel_io_spi(SPI3_HOST, &io_config, &panel_io));

        esp_lcd_panel_dev_config_t panel_config = {};
        panel_config.reset_gpio_num = GPIO_NUM_NC;
        panel_config.rgb_ele_order = LCD_RGB_ELEMENT_ORDER_RGB;
        panel_config.bits_per_pixel = 16;
        ESP_ERROR_CHECK(esp_lcd_new_panel_st7789(panel_io, &panel_config, &panel));

        esp_lcd_panel_reset(panel);
        tca6408_->SetOutputState(4, 0);
        esp_lcd_panel_init(panel);
        esp_lcd_panel_invert_color(panel, true);
        esp_lcd_panel_swap_xy(panel, DISPLAY_SWAP_XY);
        esp_lcd_panel_mirror(panel, DISPLAY_MIRROR_X, DISPLAY_MIRROR_Y);
        esp_lcd_panel_disp_on_off(panel, true);

#if CONFIG_USE_EMOTE_MESSAGE_STYLE
        display_ = new emote::EmoteDisplay(panel, panel_io, DISPLAY_WIDTH, DISPLAY_HEIGHT);
#else
        display_ = new SpiLcdDisplay(panel_io, panel,
            DISPLAY_WIDTH, DISPLAY_HEIGHT, DISPLAY_OFFSET_X, DISPLAY_OFFSET_Y,
            DISPLAY_MIRROR_X, DISPLAY_MIRROR_Y, DISPLAY_SWAP_XY);
#endif
    }

    void InitializeCamera() {
        tca6408_->SetOutputState(3, 0);
        vTaskDelay(100);
        tca6408_->SetOutputState(3, 1);
        tca6408_->SetOutputState(2, 0);

        esp_cam_ctlr_dvp_pin_config_t dvp_pin_config = {
            .data_width = CAM_CTLR_DATA_WIDTH_8,
            .data_io = {
                [0] = CAMERA_PIN_D0,
                [1] = CAMERA_PIN_D1,
                [2] = CAMERA_PIN_D2,
                [3] = CAMERA_PIN_D3,
                [4] = CAMERA_PIN_D4,
                [5] = CAMERA_PIN_D5,
                [6] = CAMERA_PIN_D6,
                [7] = CAMERA_PIN_D7,
            },
            .vsync_io = CAMERA_PIN_VSYNC,
            .de_io = CAMERA_PIN_HREF,
            .pclk_io = CAMERA_PIN_PCLK,
            .xclk_io = CAMERA_PIN_XCLK,
        };

        esp_video_init_sccb_config_t sccb_config = {
            .init_sccb = false,
            .i2c_handle = i2c_bus_,
            .freq = 100000,
        };

        esp_video_init_dvp_config_t dvp_config = {
            .sccb_config = sccb_config,
            .reset_pin = CAMERA_PIN_RESET,
            .pwdn_pin = CAMERA_PIN_PWDN,
            .dvp_pin = dvp_pin_config,
            .xclk_freq = XCLK_FREQ_HZ,
        };

        esp_video_init_config_t video_config = {
            .dvp = &dvp_config,
        };

        camera_ = new Esp32Camera(video_config);
    }

public:
    LichuangDevBoard() : boot_button_(BOOT_BUTTON_GPIO) {
#if LINGKONG_SELFTEST
        // ========================================================
        // 自检模式：屏/摄像头/WiFi/Application 全都不初始化，
        // 只跑元件自检（各项自己按需初始化自己的外设）。
        // 注意 st_run() 不会返回。
        // ========================================================
        ESP_LOGW(TAG, "================ SELF-TEST MODE ================");
        ESP_LOGW(TAG, "不启动 WiFi / Application / 屏 / 摄像头");
        ESP_LOGW(TAG, "BOOT 键单击换项，长按执行，结果看串口");
        st_run(&lingkong_selftest_config);
#else
        InitializePowerManager();
        InitializeI2c();
        InitializeSpi();
        InitializeSt7789Display();
        InitializeButtons();
        //InitializeCamera();

        // ★ 初始化电机
        motor1_.Init(MOTOR1_IN1, MOTOR1_IN2);
        motor2_.Init(MOTOR2_IN1, MOTOR2_IN2);

        // ★ 初始化舵机
        servo1_.Init(SERVO1_PIN, LEDC_CHANNEL_0);

        ESP_LOGI(TAG, "Motor and servo initialized!");
        ESP_LOGI(TAG, "✅ 运动控制系统已就绪，等待指令");
#endif
    }

    // ============================================================
    // ★ 公开运动控制接口（供 application.cc 调用）
    // ============================================================
    void MoveForward() {
        motor1_.Forward();
        motor2_.Forward();
    }

    void MoveBackward() {
        motor1_.Backward();
        motor2_.Backward();
    }

    void TurnLeft() {
        motor1_.Backward();
        motor2_.Forward();
    }

    void TurnRight() {
        motor1_.Forward();
        motor2_.Backward();
    }

    void Stop() {
        motor1_.Stop();
        motor2_.Stop();
    }

    void Wave() {
        servo1_.SetAngle(0);
        vTaskDelay(pdMS_TO_TICKS(300));
        servo1_.SetAngle(90);
        vTaskDelay(pdMS_TO_TICKS(300));
        servo1_.SetAngle(0);
    }

    void SetServoAngle(int angle) {
        servo1_.SetAngle(angle);
    }

    // ============================================================
    // 虚函数实现
    // ============================================================
    virtual AudioCodec* GetAudioCodec() override {
        static CustomAudioCodec audio_codec(i2c_bus_, tca6408_);
        return &audio_codec;
    }

    virtual Display* GetDisplay() override {
        return display_;
    }

    virtual bool GetBatteryLevel(int& level, bool& charging, bool& discharging) override {
        static bool last_discharging = false;
        charging = power_manager_->IsCharging();
        discharging = power_manager_->IsDischarging();
        if (discharging != last_discharging) {
            // power_save_timer_->SetEnabled(discharging);
            last_discharging = discharging;
        }
        level = power_manager_->GetBatteryLevel();
        return true;
    }

    virtual Camera* GetCamera() override {
        return camera_;
    }
};

DECLARE_BOARD(LichuangDevBoard);