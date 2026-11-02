#include "wifi_board.h"
#include "display/lcd_display.h"

#include "application.h"
#include "button.h"
#include "config.h"
#include "wifi_station.h"

#include <driver/i2c_master.h>
#include <driver/spi_common.h>
#include <esp_lcd_panel_io.h>
#include <esp_lcd_panel_ops.h>
#include <esp_lcd_panel_vendor.h>
#include <esp_lcd_gc9a01.h>
#include <esp_ldo_regulator.h>
#include <esp_log.h>

#include "doly_audio_codec.h"

#define TAG "DolyBoard"

/**
 * doly 板 —— ESP32-P4 + 两颗 ESP32 之外的东西值得说明：
 *
 * 1) **P4 没有内置 WiFi**。这块板子靠 SDIO 外挂的 C6 上网，而 SDIO 需要
 *    LDO 通道 4 先给 3.3V，否则 WiFi 起不来。MIPI 摄像头另需通道 3 给 2.5V。
 *    ⇒ 构造函数里第一件事就是把这两路电放出来（顺序不能挪到 WiFi 之后）。
 *
 * 2) 双 240x240 GC9A01 圆屏，共用一根背光（GPIO16）。第一阶段只驱动 LCD1。
 *
 * 3) 电机/舵机/灯/红外/IMU 的引脚已经在 config.h 里备好了，但这一阶段**不驱动**，
 *    留到第二阶段做自检和 MCP 工具时再接（一次只加一个变量）。
 */
class DolyBoard : public WifiBoard {
private:
    Button boot_button_;
    i2c_master_bus_handle_t i2c_bus_ = nullptr;
    Display* display_ = nullptr;
    PwmBacklight* backlight_ = nullptr;

    /* P4 的外设供电闸门，缺一不可 */
    void EnableLdoPower() {
        static esp_ldo_channel_handle_t sdio_chan = NULL;
        esp_ldo_channel_config_t sdio_cfg = {
            .chan_id = 4,
            .voltage_mv = 3300,
        };
        ESP_ERROR_CHECK(esp_ldo_acquire_channel(&sdio_cfg, &sdio_chan));
        ESP_LOGI(TAG, "LDO ch4 3.3V on (SDIO / WiFi 供电)");

        static esp_ldo_channel_handle_t mipi_chan = NULL;
        esp_ldo_channel_config_t mipi_cfg = {
            .chan_id = 3,
            .voltage_mv = 2500,
        };
        ESP_ERROR_CHECK(esp_ldo_acquire_channel(&mipi_cfg, &mipi_chan));
        ESP_LOGI(TAG, "LDO ch3 2.5V on (MIPI 供电)");
    }

    /* codec（ES8311/ES7243E）和以后的摄像头 SCCB 共用这条总线，端口 1 */
    void InitializeI2c() {
        i2c_master_bus_config_t i2c_bus_cfg = {
            .i2c_port = (i2c_port_t)1,
            .sda_io_num = AUDIO_CODEC_I2C_SDA_PIN,
            .scl_io_num = AUDIO_CODEC_I2C_SCL_PIN,
            .clk_source = I2C_CLK_SRC_DEFAULT,
            .glitch_ignore_cnt = 7,
            .intr_priority = 0,
            .trans_queue_depth = 0,
            .flags = {
                .enable_internal_pullup = 1,
            },
        };
        ESP_ERROR_CHECK(i2c_new_master_bus(&i2c_bus_cfg, &i2c_bus_));
        ESP_LOGI(TAG, "I2C port 1 ready (SDA=%d SCL=%d)",
                 (int)AUDIO_CODEC_I2C_SDA_PIN, (int)AUDIO_CODEC_I2C_SCL_PIN);
    }

    void InitializeGc9a01Display() {
        ESP_LOGI(TAG, "Init LCD1: GC9A01 240x240 on SPI2");
        spi_bus_config_t buscfg = {};
        buscfg.mosi_io_num = LCD1_PIN_MOSI;
        buscfg.miso_io_num = GPIO_NUM_NC;
        buscfg.sclk_io_num = LCD1_PIN_SCLK;
        buscfg.quadwp_io_num = GPIO_NUM_NC;
        buscfg.quadhd_io_num = GPIO_NUM_NC;
        buscfg.max_transfer_sz = DISPLAY_WIDTH * DISPLAY_HEIGHT * sizeof(uint16_t);
        ESP_ERROR_CHECK(spi_bus_initialize(SPI2_HOST, &buscfg, SPI_DMA_CH_AUTO));

        esp_lcd_panel_io_handle_t io_handle = NULL;
        esp_lcd_panel_io_spi_config_t io_config = {};
        io_config.cs_gpio_num = LCD1_PIN_CS;      /* 板上不接 CS */
        io_config.dc_gpio_num = LCD1_PIN_DC;
        io_config.spi_mode = 0;
        io_config.pclk_hz = 80 * 1000 * 1000;
        io_config.trans_queue_depth = 10;
        io_config.lcd_cmd_bits = 8;
        io_config.lcd_param_bits = 8;
        ESP_ERROR_CHECK(esp_lcd_new_panel_io_spi(SPI2_HOST, &io_config, &io_handle));

        esp_lcd_panel_dev_config_t panel_config = {};
        panel_config.reset_gpio_num = LCD1_PIN_RST;
        panel_config.rgb_endian = LCD_RGB_ENDIAN_BGR;
        panel_config.bits_per_pixel = 16;
        esp_lcd_panel_handle_t panel_handle = NULL;
        ESP_ERROR_CHECK(esp_lcd_new_panel_gc9a01(io_handle, &panel_config, &panel_handle));
        ESP_ERROR_CHECK(esp_lcd_panel_reset(panel_handle));
        ESP_ERROR_CHECK(esp_lcd_panel_init(panel_handle));
        ESP_ERROR_CHECK(esp_lcd_panel_disp_on_off(panel_handle, true));

        display_ = new SpiLcdDisplay(io_handle, panel_handle,
                                     DISPLAY_WIDTH, DISPLAY_HEIGHT,
                                     DISPLAY_OFFSET_X, DISPLAY_OFFSET_Y,
                                     DISPLAY_MIRROR_X, DISPLAY_MIRROR_Y, DISPLAY_SWAP_XY);
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
    }

    /* 上电时把执行器引脚摆到安全状态（**硬件事实，不是能力**）：
     *   - 舵机电源闸门 GPIO10 拉高：不拉，任何舵机指令都不会动
     *   - 电机 4 路先全低：避免上电瞬间乱转（MOSS 那次的教训）
     *   - 灯数据脚先低：WS2812 上电不发数据就该是灭的
     * 真正的"前进/挥手"由后台能力库下发的引脚流决定，这里只保证初始是停的。 */
    void InitializeActuatorPins() {
        const gpio_num_t kOutputsLow[] = {
            APP_MOTOR_PIN_L_A, APP_MOTOR_PIN_L_B,
            APP_MOTOR_PIN_R_A, APP_MOTOR_PIN_R_B,
            LED_GPIO_LEFT, LED_GPIO_RIGHT,
        };
        uint64_t mask = 0;
        for (auto p : kOutputsLow) {
            mask |= (1ULL << (int)p);
        }
        gpio_config_t io = {};
        io.pin_bit_mask = mask;
        io.mode = GPIO_MODE_OUTPUT;
        io.pull_up_en = GPIO_PULLUP_DISABLE;
        io.pull_down_en = GPIO_PULLDOWN_DISABLE;
        io.intr_type = GPIO_INTR_DISABLE;
        ESP_ERROR_CHECK(gpio_config(&io));
        for (auto p : kOutputsLow) {
            gpio_set_level(p, 0);
        }

        /* 舵机电源闸门单独拉高 */
        gpio_config_t pwr = {};
        pwr.pin_bit_mask = (1ULL << (int)SERVO_PIN_PWR_CTRL);
        pwr.mode = GPIO_MODE_OUTPUT;
        pwr.intr_type = GPIO_INTR_DISABLE;
        ESP_ERROR_CHECK(gpio_config(&pwr));
        gpio_set_level(SERVO_PIN_PWR_CTRL, 1);
        ESP_LOGI(TAG, "执行器引脚就绪：电机/灯=低，舵机电源(GPIO%d)=高", (int)SERVO_PIN_PWR_CTRL);
    }

public:
    DolyBoard() : boot_button_(BOOT_BUTTON_GPIO) {
        /* 供电 -> I2C -> 背光 -> 屏 -> 按键。供电必须最先。 */
        EnableLdoPower();

        backlight_ = new PwmBacklight(LCD_PIN_BL, false);
        backlight_->SetBrightness(40, false);

        InitializeI2c();
        InitializeGc9a01Display();
        InitializeActuatorPins();
        InitializeButtons();
    }

    virtual AudioCodec* GetAudioCodec() override {
        static DolyAudioCodec audio_codec(
            i2c_bus_,
            AUDIO_INPUT_SAMPLE_RATE,
            AUDIO_OUTPUT_SAMPLE_RATE,
            AUDIO_I2S_GPIO_MCLK,
            AUDIO_I2S_GPIO_BCLK,
            AUDIO_I2S_GPIO_WS,
            AUDIO_I2S_GPIO_DOUT,
            AUDIO_I2S_GPIO_DIN,
            AUDIO_CODEC_PA_PIN,
            AUDIO_CODEC_ES8311_ADDR,
            AUDIO_CODEC_ES7243E_ADDR,
            AUDIO_INPUT_REFERENCE);
        return &audio_codec;
    }

    virtual Display* GetDisplay() override { return display_; }

    virtual Backlight* GetBacklight() override { return backlight_; }
};

DECLARE_BOARD(DolyBoard);
