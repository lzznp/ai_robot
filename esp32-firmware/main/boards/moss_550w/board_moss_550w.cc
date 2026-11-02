// ============================================================
// board_moss_550w.cc — MOSS 550W 板卡完整实现
//
// 硬件配置（经 FlyingProbeTesting.json 网表 + 电路图核实）:
//   - 主控: ESP32-S3-WROOM-1-N16R8  (U8)
//   - 扬声器: NS4168 I2S 功放 (U12), GPIO09/10/11
//   - 麦克风: INMP441 PDM, 外接在 H2(GPIO13) / H3(GPIO12) 排针上
//   - 电机: 74HC595(U6/U10) → ULN2003(U7/U10) → 24BYJ48 步进 ×2 (U9/U11/CN3/CN4)
//           GPIO03=SHCP  GPIO04=STCP  GPIO05=DS
//   - 灯带: 板上 5 颗 FMLED，数据线在 FMH1/FMH2 焊盘，
//           需跳线到 H5(GPIO07) / H6(GPIO48) 才能由软件驱动
//   - 屏幕: **板上没有屏**，外接在 H4 排针 (GPIO02/GPIO01/3V3/GND, 4线 I2C)
//           且该 I2C 与摄像头 SCCB(U13) 共用总线，板上有 R15/R16 上拉
//   - 摄像头: FPC1(26pin) / U13 / H1(40pin)
//
// ⚠️ 网表里 GPIO01 在模块 pin39、GPIO02 在 pin38；
//    而 ESP32-S3-WROOM-1 官方引脚表是 pin38=IO1、pin39=IO2 —— 顺序相反。
//    到底哪个对，用 selftest 的 I2C A/B 两次扫描对照即可定案。
//
// ⚠️ 原 board_moss_550w.cc 里有一段"开机 3 秒后自动把两个电机各转一圈"
//    的自测（TestMotor），2026-10-19 已移除：
//    总装状态下第一次上电，限位没装好就是顶死齿轮 / 烧 ULN2003。
//    电机现在只响应指令（或 selftest 模式下的长按）。
// ============================================================

#include "wifi_board.h"
#include "codecs/no_audio_codec.h"
#include "application.h"
#include "button.h"
#include "config.h"
#include "led/gpio_led.h"
#include "display/oled_display.h"     // ★ 2026-10-31：外挂 I2C OLED（SSD1306）
#include "esp32_camera.h"             // ★ 2026-10-31：DVP 摄像头（插 U13）
#include "motor_control.h"
#include "selftest.h"        // components/selftest/（三台共用的自检引擎）

// MOSS 自己的项表（boards/moss_550w/selftest_items.c 里定义）
extern "C" const st_config_t moss_selftest_config;

#include <wifi_station.h>
#include <esp_log.h>
#include <driver/gpio.h>
#include <driver/i2c_master.h>        // ★ OLED 用的 I2C 主总线
#include <esp_lcd_panel_ops.h>
#include <esp_lcd_panel_vendor.h>

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
#define AUDIO_I2S_MIC_GPIO_SCK   MIC_BCK_GPIO     // GPIO_NUM_12
#endif
#ifndef AUDIO_I2S_MIC_GPIO_DIN
#define AUDIO_I2S_MIC_GPIO_DIN   MIC_DIN_GPIO     // GPIO_NUM_13
#endif

class Moss550WBoard : public WifiBoard {
private:
    Button boot_button_;

    // ============================================================
    // ★ 2026-10-31 新增：外挂 I2C OLED（SSD1306）
    //
    //   历史：我们这版固件以前 GetDisplay() 直接返回 nullptr（"无显示"），
    //   所以屏一直黑。而原厂固件（xiaozhi_for_550W）是支持它的——从原厂
    //   镜像里能扒到 "Adding OLED display / Install SSD1306 driver /
    //   SSD1306 driver installed / Turning display on"，说明它就是
    //   一块 I2C SSD1306，挂在 H4（GPIO01/GPIO02 那条 I2C 上）。
    //
    //   照 bread-compact-wifi 的标准三件套实现：
    //     InitializeDisplayI2c() → InitializeSsd1306Display() → GetDisplay()
    //
    //   ⚠️ 已知风险：SSD1306 默认地址 0x3C 与摄像头 OV5640 的 SCCB 地址相同，
    //   而两者共用同一条 I2C 总线。当前固件不初始化摄像头，所以 0x3C 归屏用；
    //   以后要同时用摄像头，必须先把地址冲突解决（换 OLED 地址或分开总线）。
    // ============================================================
    i2c_master_bus_handle_t display_i2c_bus_ = nullptr;
    esp_lcd_panel_io_handle_t panel_io_ = nullptr;
    esp_lcd_panel_handle_t panel_ = nullptr;
    Display* display_ = nullptr;

    void InitializeDisplayI2c() {
        i2c_master_bus_config_t bus_config = {
            .i2c_port = (i2c_port_t)I2C_PORT,
            .sda_io_num = DISPLAY_SDA,
            .scl_io_num = DISPLAY_SCL,
            .clk_source = I2C_CLK_SRC_DEFAULT,
            .glitch_ignore_cnt = 7,
            .intr_priority = 0,
            .trans_queue_depth = 0,
            .flags = {
                .enable_internal_pullup = 1,
            },
        };
        ESP_ERROR_CHECK(i2c_new_master_bus(&bus_config, &display_i2c_bus_));
    }

    void InitializeSsd1306Display() {
        esp_lcd_panel_io_i2c_config_t io_config = {
            .dev_addr = DISPLAY_I2C_ADDR,
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
            .scl_speed_hz = I2C_CLOCK_SPEED,
        };

        ESP_ERROR_CHECK(esp_lcd_new_panel_io_i2c_v2(display_i2c_bus_, &io_config, &panel_io_));

        ESP_LOGI(TAG, "Install SSD1306 driver");
        esp_lcd_panel_dev_config_t panel_config = {};
        panel_config.reset_gpio_num = -1;
        panel_config.bits_per_pixel = 1;

        esp_lcd_panel_ssd1306_config_t ssd1306_config = {
            .height = static_cast<uint8_t>(DISPLAY_HEIGHT),
        };
        panel_config.vendor_config = &ssd1306_config;

        ESP_ERROR_CHECK(esp_lcd_new_panel_ssd1306(panel_io_, &panel_config, &panel_));
        ESP_LOGI(TAG, "SSD1306 driver installed");

        ESP_ERROR_CHECK(esp_lcd_panel_reset(panel_));
        if (esp_lcd_panel_init(panel_) != ESP_OK) {
            ESP_LOGE(TAG, "Failed to initialize display");
            display_ = new NoDisplay();
            return;
        }
        ESP_ERROR_CHECK(esp_lcd_panel_invert_color(panel_, false));

        ESP_LOGI(TAG, "Turning display on");
        ESP_ERROR_CHECK(esp_lcd_panel_disp_on_off(panel_, true));

        display_ = new OledDisplay(panel_io_, panel_, DISPLAY_WIDTH, DISPLAY_HEIGHT,
                                   DISPLAY_MIRROR_X, DISPLAY_MIRROR_Y);
    }

    // ============================================================
    // ★ 2026-10-31 新增：DVP 摄像头（插在 U13 20 针座）
    //
    //   注意 SCCB 复用 display_i2c_bus_（init_sccb = false，不另建总线）。
    //   如果摄像头 SCCB 地址与 OLED 的 0x3C 相同，会在这里暴露出问题。
    //   初始化失败不会崩（Esp32Camera 构造函数自己 log 后返回）。
    // ============================================================
    Esp32Camera* camera_ = nullptr;

    void InitializeCamera() {
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
            .init_sccb = false,                  // 复用屏那条 I2C
            .i2c_handle = display_i2c_bus_,
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

        ESP_LOGI(TAG, "Initializing DVP camera...");
        camera_ = new Esp32Camera(video_config);
    }

    // ============================================================
    // BOOT 按键初始化（正常固件模式）
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

public:
    Moss550WBoard() : boot_button_(BOOT_BUTTON_GPIO) {
        ESP_LOGI(TAG, "Initializing MOSS 550W Board...");

#if MOSS_SELFTEST
        // ========================================================
        // 自检模式：不启动 Application，不进 WiFi，只跑外设自检
        // 引擎在 components/selftest/，项表在 selftest_items.c
        // 注意 st_run() 不会返回
        // ========================================================
        ESP_LOGW(TAG, "================ SELF-TEST MODE ================");
        ESP_LOGW(TAG, "不启动 WiFi / Application");
        ESP_LOGW(TAG, "BOOT 键单击换项，长按执行，结果看串口");
        st_run(&moss_selftest_config);
#else
        // 屏先初始化：Application 起来之前就要能用
        InitializeDisplayI2c();
        InitializeSsd1306Display();
        InitializeCamera();          // ★ 摄像头（失败不崩，只打日志）
        InitializeButtons();
        ESP_LOGI(TAG, "MOSS 550W Board initialized successfully!");
#endif
    }

    virtual ~Moss550WBoard() {}

    // ============================================================
    // 音频编解码器
    //   I2S_NUM_1 → 扬声器 (NS4168, 标准 I2S TX)
    //   I2S_NUM_0 → 麦克风 (INMP441, PDM RX)
    // ============================================================
    virtual AudioCodec* GetAudioCodec() override {
        static NoAudioCodecSimplexPdm audio_codec(
            AUDIO_INPUT_SAMPLE_RATE,          // 16000
            AUDIO_OUTPUT_SAMPLE_RATE,         // 16000
            AUDIO_I2S_SPK_GPIO_BCLK,          // GPIO_NUM_10
            AUDIO_I2S_SPK_GPIO_LRCK,          // GPIO_NUM_9
            AUDIO_I2S_SPK_GPIO_DOUT,          // GPIO_NUM_11
            AUDIO_I2S_MIC_GPIO_SCK,           // GPIO_NUM_12
            AUDIO_I2S_MIC_GPIO_DIN            // GPIO_NUM_13
        );
        return &audio_codec;
    }

    // ============================================================
    // 显示：外挂 I2C OLED（SSD1306）。没接屏/初始化失败时为 NoDisplay
    // ============================================================
    virtual Display* GetDisplay() override {
        return display_;
    }

    // ============================================================
    // 摄像头：MCP 的 self.camera.take_photo 会走这里
    // ============================================================
    virtual Camera* GetCamera() override {
        return camera_;
    }

    // ============================================================
    // LED
    //   ⚠️ 2026-10-31 重要变更：不再用 GpioLed(GPIO7)。
    //
    //   原因：GPIO7 是第一组 WS2812 灯带的数据脚（H5），而 GpioLed 会用
    //   LEDC 在该脚上输出 4kHz PWM 当"状态指示灯"。这个 PWM 波形对
    //   WS2812 是垃圾数据 —— 实测表现：上电后那颗灯珠**常亮白色**，
    //   而且和 ws2812 动作抢同一个引脚。
    //
    //   现在的要求：**上电不亮**，灯效一律由后台发 ws2812 指令驱动
    //   （亮/变色/呼吸都由指令流决定，固件里不写语义）。
    //   所以这里返回 NoLed，GPIO7/GPIO48 全部让给灯带。
    // ============================================================
    virtual Led* GetLed() override {
        static NoLed no_led;
        return &no_led;
    }

    // ============================================================
    // 步进电机（动作 stepper 的落地，2026-11-01）
    //
    //   motor       : 0 = 第 1 路，1 = 第 2 路（哪个是水平/垂直要实测，代码不做假设）
    //   steps       : 带符号，正 = MOTOR_CW，负 = MOTOR_CCW
    //   speed_hz    : 每秒步数（驱动里默认 100，这里按指令给）
    //   hold_torque : 走完是否保持力矩（悬挂机构怕重力下垂时 true）
    //
    //   **非阻塞**：motor_step() 只是把命令丢进该电机的队列，由驱动自己的任务走完；
    //   等它走完是应用层用"估算时间 + 延时"处理的（见 application.cc 的 stepper 分支）。
    // ============================================================
    virtual void StepMotor(int motor, int steps, int speed_hz, bool hold_torque) override {
        if (motor < 0 || motor > 1 || steps == 0) {
            return;
        }
        motor_control_init();          // 幂等：已初始化会直接返回

        int n = steps > 0 ? steps : -steps;
        if (n > 1024) n = 1024;        // 安全上限，防撞机械限位

        motor_set_speed((uint8_t)motor, (uint16_t)(speed_hz > 0 ? speed_hz : 60));
        motor_set_hold((uint8_t)motor, hold_torque ? 1 : 0);
        motor_step((uint8_t)motor,
                   steps > 0 ? MOTOR_CW : MOTOR_CCW,
                   (uint16_t)n);
    }
};

DECLARE_BOARD(Moss550WBoard);
