// ============================================================
// selftest_items.cc — 月球车（lingkong-s3-moc-cam-1.54tft）自检项表
//
// 引擎在 components/selftest/（交互 + 打印助手），这里只写"这张板有哪几项、
// 每项怎么测、判据是什么"。
//
// 这张板的实物状态（2026-10-22 用户确认）：
//   · 测过：2 个电机、1 个舵机
//   · 没测：灯（4 路灯 + 车厢灯带）、屏（只临时点过，驾驶室中控没实现）
//   · 不用：摄像头
//
// ★ 为什么项表里没有"灯组"：
//   config.h 有 LED_1..4_PIN(GPIO4/5/6/7) 和 LED_STRIP_PIN(GPIO8) 的宏，但
//   板级代码里**从来没有驱动它们的代码**，且车厢灯板用的什么芯片（WS2812？
//   普通灯珠？）也不知道 ⇒ 判据写不出来。按规矩（判据写不出来就不写测试），
//   这一项不做；等确认灯板型号后再补。
//   好消息：这台不用摄像头，所以 GPIO3/4/5/6/7/8 那些"和摄像头撞脚"的问题
//   对它不存在。
//
// 引脚真相（boards/lingkong-s3-moc-cam-1.54tft/config.h + 板级 .cc 核实）：
//   I2C    : **port 1**，SDA=GPIO21  SCL=GPIO14（板上是外部上拉，代码里
//            enable_internal_pullup=0）；TCA6408 IO 扩展在 0x20
//   电机 1 : TC118S  IN1=GPIO1   IN2=GPIO2
//   电机 2 : TC118S  IN1=GPIO12  IN2=GPIO13
//   舵机   : GPIO3，LEDC_TIMER_0 / CH0，50Hz，12bit
//   屏     : ST7789 240×320，SPI3_HOST  MOSI=GPIO48  SCLK=GPIO45  DC=GPIO47
//            CS=NC；背光由 TCA6408 的 bit4 控制（写 0 = 亮）
//   电池   : ADC1_CH9（= GPIO10，由 PowerManager 使用）
// ============================================================

#include <stdio.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "esp_err.h"
#include "esp_log.h"
#include "esp_heap_caps.h"
#include "esp_adc/adc_oneshot.h"

#include "driver/i2c_master.h"
#include "driver/spi_master.h"
#include "esp_lcd_panel_io.h"
#include "esp_lcd_panel_vendor.h"
#include "esp_lcd_panel_ops.h"

#include "config.h"
#include "motor_control.h"
#include "servo_control.h"
#include "selftest.h"
#include "selftest_helpers.h"

// ------------------------------------------------------------
// 项 1：I2C 扫描
//   这条总线上应该有：ES8311(0x18)、TCA6408(0x20)、可能还有 ES7243E(0x10)、
//   触摸 FT5x06(0x38)、以及 1.54" 屏如果它是 I2C 版的话（本板 ST7789 走 SPI）
// ------------------------------------------------------------
static void item_i2c(void)
{
    st_i2c_scan(1, (int)AUDIO_CODEC_I2C_SDA_PIN, (int)AUDIO_CODEC_I2C_SCL_PIN,
                "（本板 I2C port 1，外部上拉）");
    printf("\n判据（看到什么算通过）：\n");
    printf("  · 扫到 0x18 = ES8311 音频 codec 在 —— 说话能出声的前提\n");
    printf("  · 扫到 0x20 = TCA6408 IO 扩展在 —— 背光/功放/摄像头复位都靠它\n");
    printf("  · 扫到 0x38 = 触摸 FT5x06 在（没装触摸就没有）\n");
    printf("  · 一个都没有 -> 先量 GPIO21/GPIO14 到模块的通断 + 3V3 供电\n");
}

// ------------------------------------------------------------
// 项 2、3：单个电机（TC118S：IN1/IN2 一个高一个低 = 转）
// ------------------------------------------------------------
static void test_motor(const char *name, int in1, int in2)
{
    MotorControl m;
    m.Init((gpio_num_t)in1, (gpio_num_t)in2);

    printf("%s: IN1=GPIO%d  IN2=GPIO%d\n", name, in1, in2);
    printf("  正转 1.5 秒 ...\n");
    m.Forward();
    vTaskDelay(pdMS_TO_TICKS(1500));

    printf("  停 0.8 秒 ...\n");
    m.Stop();
    vTaskDelay(pdMS_TO_TICKS(800));

    printf("  反转 1.5 秒 ...\n");
    m.Backward();
    vTaskDelay(pdMS_TO_TICKS(1500));

    m.Stop();
    printf("  停。\n");

    printf("\n判据（看到什么算通过）：\n");
    printf("  · 轮子先正着转、停、再反着转 -> TC118S 这一路全通\n");
    printf("  · 只有单向转 -> 另一根 IN 线没接/虚焊\n");
    printf("  · 完全不转 -> 量电机两端电压；查 TC118S 的 VM 供电（电池）\n");
    printf("  · 转起来但很慢/发烫 -> 电池电压低或电机卡住\n");
}

static void item_motor1(void) { test_motor("电机 1", (int)MOTOR1_IN1, (int)MOTOR1_IN2); }
static void item_motor2(void) { test_motor("电机 2", (int)MOTOR2_IN1, (int)MOTOR2_IN2); }

// ------------------------------------------------------------
// 项 4：差速转向（左转 = 电机1 反转 + 电机2 正转，原地打转）
//   这一项验的是"两路能同时动"，不是单路。
// ------------------------------------------------------------
static void item_turn(void)
{
    MotorControl m1;
    MotorControl m2;
    m1.Init((gpio_num_t)MOTOR1_IN1, (gpio_num_t)MOTOR1_IN2);
    m2.Init((gpio_num_t)MOTOR2_IN1, (gpio_num_t)MOTOR2_IN2);

    printf("左转（原地）：电机1 反转 + 电机2 正转，1.5 秒\n");
    m1.Backward();
    m2.Forward();
    vTaskDelay(pdMS_TO_TICKS(1500));
    m1.Stop();
    m2.Stop();
    vTaskDelay(pdMS_TO_TICKS(500));

    printf("右转（原地）：电机1 正转 + 电机2 反转，1.5 秒\n");
    m1.Forward();
    m2.Backward();
    vTaskDelay(pdMS_TO_TICKS(1500));
    m1.Stop();
    m2.Stop();
    printf("  停。\n");

    printf("\n判据（看到什么算通过）：\n");
    printf("  · 车原地左转再原地右转 -> 两路电机能同时独立动作，差速成立\n");
    printf("  · 两个轮子同向转（往一个方向跑）-> 某一路 IN 线接反了，换线\n");
    printf("  · 只有一个轮子动 -> 另一路没接上（回上一项单独查）\n");
}

// ------------------------------------------------------------
// 项 5：舵机（GPIO3，LEDC 50Hz）
// ------------------------------------------------------------
static void item_servo(void)
{
    ServoControl s;
    s.Init((gpio_num_t)SERVO1_PIN, LEDC_CHANNEL_0);

    const int angles[] = {0, 90, 180, 90, 0};
    for (size_t i = 0; i < sizeof(angles) / sizeof(angles[0]); i++) {
        printf("  角度 %d°\n", angles[i]);
        s.SetAngle(angles[i]);
        vTaskDelay(pdMS_TO_TICKS(800));
    }

    printf("\n判据（看到什么算通过）：\n");
    printf("  · 舵机臂从一头转到另一头再回来，全程平滑 -> PWM 链通\n");
    printf("  · 完全不动但没发热 -> 信号线(GPIO%d)断，或舵机没供电\n", (int)SERVO1_PIN);
    printf("  · 抖动/发烫/一直顶到一头 -> 脉宽不对或舵机行程有限位\n");
    printf("  · 注意：0°和 180°是理论值，实际舵机可能只到 10°~170°\n");
}

// ------------------------------------------------------------
// 项 6：屏（ST7789 240×320 + TCA6408 背光）
//   判据很硬：满屏红 -> 绿 -> 蓝，眼睛看得见就是全通。
// ------------------------------------------------------------
static esp_err_t tca6408_write_reg(i2c_master_bus_handle_t bus, uint8_t reg, uint8_t val)
{
    i2c_device_config_t dev_cfg = {};
    dev_cfg.dev_addr_length = I2C_ADDR_BIT_LEN_7;
    dev_cfg.device_address = 0x20;
    dev_cfg.scl_speed_hz = 100 * 1000;

    i2c_master_dev_handle_t dev = NULL;
    esp_err_t err = i2c_master_bus_add_device(bus, &dev_cfg, &dev);
    if (err != ESP_OK) {
        return err;
    }
    uint8_t buf[2] = {reg, val};
    err = i2c_master_transmit(dev, buf, sizeof(buf), 100);
    i2c_master_bus_rm_device(dev);
    return err;
}

static void item_display(void)
{
    printf("屏: ST7789 %dx%d  SPI3  MOSI=GPIO%d  SCLK=GPIO%d  DC=GPIO%d\n",
           DISPLAY_WIDTH, DISPLAY_HEIGHT, (int)DISPLAY_SDA, (int)DISPLAY_SCL,
           (int)DISPLAY_DC);
    printf("背光: TCA6408(0x20) bit4，写 0 = 亮\n\n");

    // ---- 1) I2C + TCA6408 背光 ----
    i2c_master_bus_config_t i2c_cfg = {};
    i2c_cfg.i2c_port = 1;
    i2c_cfg.sda_io_num = AUDIO_CODEC_I2C_SDA_PIN;
    i2c_cfg.scl_io_num = AUDIO_CODEC_I2C_SCL_PIN;
    i2c_cfg.clk_source = I2C_CLK_SRC_DEFAULT;
    i2c_cfg.glitch_ignore_cnt = 7;
    i2c_cfg.flags.enable_internal_pullup = 0;

    i2c_master_bus_handle_t bus = NULL;
    esp_err_t err = i2c_new_master_bus(&i2c_cfg, &bus);
    printf("  I2C 总线: %s\n", esp_err_to_name(err));
    if (err != ESP_OK) {
        printf("  [X] I2C 起不来，屏这一项没法测（背光在 TCA6408 上）\n");
        return;
    }

    err = tca6408_write_reg(bus, 0x03, 0x00);        // 全部当输出
    printf("  TCA6408 配置为输出: %s\n", esp_err_to_name(err));
    tca6408_write_reg(bus, 0x01, 0xFF);              // 先全部拉高
    err = tca6408_write_reg(bus, 0x01, 0xFF & ~(1 << 4));  // bit4=0 -> 背光亮
    printf("  背光(bit4)拉低: %s\n\n", esp_err_to_name(err));

    // ---- 2) SPI + ST7789 ----
    spi_bus_config_t buscfg = {};
    buscfg.mosi_io_num = DISPLAY_SDA;
    buscfg.miso_io_num = GPIO_NUM_NC;
    buscfg.sclk_io_num = DISPLAY_SCL;
    buscfg.quadwp_io_num = GPIO_NUM_NC;
    buscfg.quadhd_io_num = GPIO_NUM_NC;
    buscfg.max_transfer_sz = DISPLAY_WIDTH * 40 * sizeof(uint16_t);
    err = spi_bus_initialize(SPI3_HOST, &buscfg, SPI_DMA_CH_AUTO);
    printf("  SPI 总线: %s\n", esp_err_to_name(err));
    if (err != ESP_OK) {
        printf("  [X] SPI 起不来，后面不用测了\n");
        return;
    }

    esp_lcd_panel_io_handle_t panel_io = NULL;
    esp_lcd_panel_io_spi_config_t io_config = {};
    io_config.cs_gpio_num = DISPLAY_CS;
    io_config.dc_gpio_num = DISPLAY_DC;
    io_config.spi_mode = 3;
    io_config.pclk_hz = 40 * 1000 * 1000;   // 自检用 40MHz，比正常固件的 80MHz 稳
    io_config.trans_queue_depth = 10;
    io_config.lcd_cmd_bits = 8;
    io_config.lcd_param_bits = 8;
    err = esp_lcd_new_panel_io_spi((esp_lcd_spi_bus_handle_t)SPI3_HOST, &io_config, &panel_io);
    printf("  panel_io: %s\n", esp_err_to_name(err));
    if (err != ESP_OK) {
        printf("  [X] panel_io 创建失败\n");
        return;
    }

    esp_lcd_panel_handle_t panel = NULL;
    esp_lcd_panel_dev_config_t panel_config = {};
    panel_config.reset_gpio_num = GPIO_NUM_NC;
    panel_config.rgb_ele_order = LCD_RGB_ELEMENT_ORDER_RGB;
    panel_config.bits_per_pixel = 16;
    err = esp_lcd_new_panel_st7789(panel_io, &panel_config, &panel);
    printf("  panel(ST7789): %s\n", esp_err_to_name(err));
    if (err != ESP_OK) {
        printf("  [X] ST7789 驱动装不上\n");
        return;
    }

    esp_lcd_panel_reset(panel);
    esp_lcd_panel_init(panel);
    esp_lcd_panel_invert_color(panel, true);
    esp_lcd_panel_disp_on_off(panel, true);
    printf("  面板已初始化并点亮\n\n");

    // ---- 3) 满屏刷红/绿/蓝 ----
    const uint16_t colors[] = {0xF800, 0x07E0, 0x001F};  // 红 绿 蓝（RGB565）
    const char *names[] = {"红", "绿", "蓝"};
    const int CHUNK = 40;   // 每次画 40 行，省内存

    uint16_t *line = (uint16_t *)heap_caps_malloc(DISPLAY_WIDTH * CHUNK * sizeof(uint16_t),
                                                 MALLOC_CAP_DMA);
    if (line == NULL) {
        printf("  [X] 显存分配失败\n");
        return;
    }

    for (int c = 0; c < 3; c++) {
        printf("  -> 满屏%s (0.9 秒)\n", names[c]);
        for (int i = 0; i < DISPLAY_WIDTH * CHUNK; i++) {
            line[i] = colors[c];
        }
        for (int y = 0; y < DISPLAY_HEIGHT; y += CHUNK) {
            esp_lcd_panel_draw_bitmap(panel, 0, y, DISPLAY_WIDTH, y + CHUNK, line);
        }
        vTaskDelay(pdMS_TO_TICKS(900));
    }
    heap_caps_free(line);

    printf("\n判据（看到什么算通过）：\n");
    printf("  · 屏上依次出现满屏红、绿、蓝 -> SPI + ST7789 + 背光 + TCA6408 全通\n");
    printf("  · 全黑但上面三步都打印 OK -> 背光没起来（TCA6408 bit4）或排线松\n");
    printf("  · 颜色反了（红变青）-> 面板 invert_color 需要关掉\n");
    printf("  · 花屏/条纹 -> SPI 降速（把 40MHz 改成 20MHz）或 MOSI/SCLK 有虚焊\n");
    printf("  · 只有半屏/偏色 -> 分辨率或 rgb_ele_order 不对（BGR/RGB）\n");
}

// ------------------------------------------------------------
// 项 7：电池 ADC（ADC1_CH9）
// ------------------------------------------------------------
static void item_adc(void)
{
    adc_oneshot_unit_handle_t unit = NULL;
    adc_oneshot_unit_init_cfg_t ucfg = {};
    ucfg.unit_id = POWER_ADC_UNIT;
    ucfg.ulp_mode = ADC_ULP_MODE_DISABLE;
    if (adc_oneshot_new_unit(&ucfg, &unit) != ESP_OK) {
        printf("  [X] ADC 单元初始化失败\n");
        return;
    }

    adc_oneshot_chan_cfg_t ccfg = {};
    ccfg.atten = ADC_ATTEN_DB_12;
    ccfg.bitwidth = ADC_BITWIDTH_DEFAULT;
    adc_oneshot_config_channel(unit, (adc_channel_t)POWER_ADC_CHANNEL, &ccfg);

    printf("  ADC1 通道 %d（config.h 的 POWER_ADC_CHANNEL）\n", (int)POWER_ADC_CHANNEL);
    printf("  序号   raw\n");
    for (int i = 0; i < 5; i++) {
        int v = -1;
        adc_oneshot_read(unit, (adc_channel_t)POWER_ADC_CHANNEL, &v);
        printf("   %d    %4d\n", i, v);
        vTaskDelay(pdMS_TO_TICKS(200));
    }

    printf("\n判据（看到什么算通过）：\n");
    printf("  · 插着电池时 raw 稳定在中间某个值 -> 分压电路正常\n");
    printf("  · raw 一直是 0 或接近满量程 -> 分压电阻/接线异常\n");
    printf("  · 拔电池后 raw 明显降到 0 -> 反向对照成立，这条链可信\n");
    printf("  · 注意：raw 不是电压，没标定前只看趋势\n");

    adc_oneshot_del_unit(unit);
}

static void item_sysinfo(void) { st_print_sysinfo(); }

// ------------------------------------------------------------
// 月球车项表（序号由引擎打印成 x/item_count）
// ------------------------------------------------------------
static const st_item_t kLingkongItems[] = {
    {"系统信息（芯片 / MAC / 内存）",                     item_sysinfo},
    {"I2C 扫描：port1  SDA=GPIO21  SCL=GPIO14",           item_i2c},
    {"电机 1：正转 -> 停 -> 反转（GPIO1/GPIO2）",          item_motor1},
    {"电机 2：正转 -> 停 -> 反转（GPIO12/GPIO13）",        item_motor2},
    {"差速转向：原地左转 -> 原地右转",                     item_turn},
    {"舵机：0° -> 90° -> 180° -> 90° -> 0°（GPIO3）",      item_servo},
    {"屏：ST7789 满屏红/绿/蓝 + TCA6408 背光",             item_display},
    {"电池 ADC（ADC1 通道 9）",                           item_adc},
};

extern "C" const st_config_t lingkong_selftest_config = {
    .board_name = "月球车 / lingkong-s3-moc-cam-1.54tft",
    .boot_gpio  = (int)BOOT_BUTTON_GPIO,
    .items      = kLingkongItems,
    .item_count = (int)(sizeof(kLingkongItems) / sizeof(kLingkongItems[0])),
};
