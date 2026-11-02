// ============================================================
// wali_items.c — 瓦力（qebabe-xiaoche 硬件）自检项表
//
// 交互和 MOSS 一样：单击 BOOT 换项，长按 BOOT（>=0.8s）执行当前项。
//
// ★ 引脚全部来自 2026-10-22 实测（见 工作文档\瓦力-硬件台账.md v3），
//   不是作者 config.h —— 作者的资料和这块板实物对不上：
//     config.h 说：电机 12/13/14/21、灯 18、舵机无
//     实测是：      电机 A = 13/14，电机 B = 17/18，舵机 = 11(左) 12(右)
//   还有：板上有电源开关，不打开也能连 COM（USB 供电），但电机/舵机不动。
//
// 屏 41/42（SSD1306 I2C）、音频 4/5/6 + 7/15/16、按键 0/47/40/39
// 这几组是原厂固件下已经正常工作的，沿用作者定义。
// ============================================================

#include <stdio.h>
#include <stdbool.h>
#include <stddef.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "esp_err.h"
#include "esp_heap_caps.h"
#include "driver/gpio.h"
#include "driver/i2c_master.h"
#include "driver/ledc.h"
#include "esp_lcd_panel_io.h"
#include "esp_lcd_panel_vendor.h"
#include "esp_lcd_panel_ops.h"

#include "config.h"             // 本工程的 config.h（WALI 引脚）
#include "selftest.h"
#include "selftest_helpers.h"

// ------------------------------------------------------------
// 电机：TC1508 双路 H 桥，IN 一高一低 = 转，两低 = 停
// ------------------------------------------------------------
static void motor_drive(int in1, int in2, int level1, int level2)
{
    gpio_set_level((gpio_num_t)in1, level1);
    gpio_set_level((gpio_num_t)in2, level2);
}

static void motor_init(int in1, int in2)
{
    gpio_config_t out = {
        .pin_bit_mask = (1ULL << in1) | (1ULL << in2),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    gpio_config(&out);
    motor_drive(in1, in2, 0, 0);
}

static void test_motor(const char *name, int in1, int in2)
{
    motor_init(in1, in2);

    printf("%s: IN1=GPIO%d  IN2=GPIO%d\n", name, in1, in2);

    printf("  正转 1.5 秒（IN1=1 IN2=0）...\n");
    motor_drive(in1, in2, 1, 0);
    vTaskDelay(pdMS_TO_TICKS(1500));

    printf("  停 0.8 秒 ...\n");
    motor_drive(in1, in2, 0, 0);
    vTaskDelay(pdMS_TO_TICKS(800));

    printf("  反转 1.5 秒（IN1=0 IN2=1）...\n");
    motor_drive(in1, in2, 0, 1);
    vTaskDelay(pdMS_TO_TICKS(1500));

    motor_drive(in1, in2, 0, 0);
    printf("  停。\n");

    printf("\n判据（看到什么算通过）：\n");
    printf("  · 先正转、停、再反转 -> 这一路 H 桥 + 电机全通\n");
    printf("  · 只单向转 -> 另一根 IN 线没接/虚焊\n");
    printf("  · 完全不转 -> ①电源开关打开了没 ②量电机两端电压\n");
    printf("  · 转但很慢/发烫 -> 电池电压低或电机卡住\n");
}

// ------------------------------------------------------------
// 舵机：50Hz / 1.5ms 中位；0°→90°→180°→90°
// ------------------------------------------------------------
static void servo_set(ledc_channel_t ch, int angle)
{
    if (angle < 0) angle = 0;
    if (angle > 180) angle = 180;
    // 13bit(8192)/50Hz -> 20ms；0.5ms=205, 2.5ms=1024
    uint32_t duty = 205 + (uint32_t)((1024 - 205) * angle / 180);
    ledc_set_duty(LEDC_LOW_SPEED_MODE, ch, duty);
    ledc_update_duty(LEDC_LOW_SPEED_MODE, ch);
}

static void servo_init(int pin, ledc_channel_t ch)
{
    ledc_timer_config_t timer = {
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .duty_resolution = LEDC_TIMER_13_BIT,
        .timer_num = LEDC_TIMER_0,
        .freq_hz = 50,
        .clk_cfg = LEDC_AUTO_CLK,
    };
    ledc_timer_config(&timer);

    ledc_channel_config_t c = {
        .gpio_num = pin,
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .channel = ch,
        .intr_type = LEDC_INTR_DISABLE,
        .timer_sel = LEDC_TIMER_0,
        .duty = 0,
        .hpoint = 0,
    };
    ledc_channel_config(&c);
    servo_set(ch, 90);
}

static void test_servo(const char *name, int pin, ledc_channel_t ch)
{
    servo_init(pin, ch);
    printf("%s: GPIO%d\n", name, pin);

    const int angles[] = {0, 90, 180, 90, 0};
    for (size_t i = 0; i < sizeof(angles) / sizeof(angles[0]); i++) {
        printf("  角度 %d°\n", angles[i]);
        servo_set(ch, angles[i]);
        vTaskDelay(pdMS_TO_TICKS(800));
    }

    printf("\n判据（看到什么算通过）：\n");
    printf("  · 舵机臂从一头转到另一头再回来，平滑 -> PWM 链通\n");
    printf("  · 完全不动 -> ①电源开关 ②舵机三线（5V/GND/信号）顺序\n");
    printf("  · 抖动/顶到一头不动 -> 舵机行程限位，属正常\n");
    printf("  · 注意：0°/180° 是理论值，实际可能只到 10°~170°\n");
}

// ------------------------------------------------------------
// 屏：SSD1306 I2C（41/42），满屏红→绿→蓝
// ------------------------------------------------------------
static void test_display(void)
{
    printf("屏: SSD1306  I2C  SDA=GPIO%d  SCL=GPIO%d  %dx%d\n",
           (int)WALI_I2C_SDA, (int)WALI_I2C_SCL, WALI_DISPLAY_WIDTH, WALI_DISPLAY_HEIGHT);

    i2c_master_bus_config_t i2c_cfg = {
        .i2c_port = I2C_NUM_0,
        .sda_io_num = WALI_I2C_SDA,
        .scl_io_num = WALI_I2C_SCL,
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .glitch_ignore_cnt = 7,
        .flags = { .enable_internal_pullup = 1 },
    };
    i2c_master_bus_handle_t bus = NULL;
    esp_err_t err = i2c_new_master_bus(&i2c_cfg, &bus);
    printf("  I2C 总线: %s\n", esp_err_to_name(err));
    if (err != ESP_OK) {
        printf("  [X] I2C 起不来\n");
        return;
    }

    esp_lcd_panel_io_handle_t io = NULL;
    esp_lcd_panel_io_i2c_config_t io_cfg = {
        .dev_addr = WALI_DISPLAY_ADDR,
        .control_phase_bytes = 1,
        .dc_bit_offset = 6,
        .lcd_cmd_bits = 8,
        .lcd_param_bits = 8,
        .scl_speed_hz = 400 * 1000,
    };
    err = esp_lcd_new_panel_io_i2c(bus, &io_cfg, &io);
    printf("  panel_io(0x%02X): %s\n", WALI_DISPLAY_ADDR, esp_err_to_name(err));
    if (err != ESP_OK) {
        printf("  [X] 屏没应答（地址不对/没接/没供电）\n");
        return;
    }

    esp_lcd_panel_handle_t panel = NULL;
    esp_lcd_panel_dev_config_t pcfg = {
        .reset_gpio_num = -1,
        .bits_per_pixel = 1,
    };
    esp_lcd_panel_ssd1306_config_t ssd_cfg = {
        .height = WALI_DISPLAY_HEIGHT,
    };
    pcfg.vendor_config = &ssd_cfg;
    err = esp_lcd_new_panel_ssd1306(io, &pcfg, &panel);
    printf("  panel(SSD1306): %s\n", esp_err_to_name(err));
    if (err != ESP_OK) return;

    esp_lcd_panel_reset(panel);
    esp_lcd_panel_init(panel);
    esp_lcd_panel_disp_on_off(panel, true);
    printf("  面板已初始化并点亮\n\n");

    const uint16_t colors[] = {0x00, 0xFF};   // 1bpp：0=黑 0xFF=亮
    for (int c = 0; c < 2; c++) {
        printf("  -> 满屏 %s (0.8 秒)\n", c == 0 ? "灭(黑)" : "亮(白)");
        size_t px = WALI_DISPLAY_WIDTH * WALI_DISPLAY_HEIGHT / 8;
        uint8_t *buf = (uint8_t *)heap_caps_malloc(px, MALLOC_CAP_DMA);
        if (buf == NULL) { printf("  [X] 缓冲分配失败\n"); return; }
        for (size_t i = 0; i < px; i++) buf[i] = (uint8_t)colors[c];
        esp_lcd_panel_draw_bitmap(panel, 0, 0, WALI_DISPLAY_WIDTH, WALI_DISPLAY_HEIGHT, buf);
        heap_caps_free(buf);
        vTaskDelay(pdMS_TO_TICKS(800));
    }

    printf("\n判据：\n");
    printf("  · 屏先全黑再全亮（或反过来）-> I2C + SSD1306 全通\n");
    printf("  · 完全没变化 -> ①地址不是 0x3C ②尺寸选错(32/64) ③排线\n");
    printf("  · 只有半屏/花屏 -> WALI_DISPLAY_HEIGHT 设错（32 或 64）\n");
}

// ------------------------------------------------------------
// 按键电平：BOOT(0) / 触摸(47) / 音量+(40) / 音量-(39)
// ------------------------------------------------------------
static void test_buttons(void)
{
    const struct { int pin; const char *name; } btns[] = {
        {0,  "BOOT"},
        {47, "触摸键"},
        {40, "音量+"},
        {39, "音量-"},
    };
    const int n = (int)(sizeof(btns) / sizeof(btns[0]));

    for (int i = 0; i < n; i++) {
        gpio_config_t in = {
            .pin_bit_mask = (1ULL << btns[i].pin),
            .mode = GPIO_MODE_INPUT,
            .pull_up_en = GPIO_PULLUP_ENABLE,
            .pull_down_en = GPIO_PULLDOWN_DISABLE,
            .intr_type = GPIO_INTR_DISABLE,
        };
        gpio_config(&in);
    }

    printf("现在依次按下每个键，看屏幕上哪一行从 1 变 0：\n");
    printf("（BOOT 键长按会触发「执行」，请短促按）\n\n");
    for (int round = 0; round < 12; round++) {
        printf("  ");
        for (int i = 0; i < n; i++) {
            printf("%s=%d  ", btns[i].name, gpio_get_level((gpio_num_t)btns[i].pin));
        }
        printf("\n");
        fflush(stdout);
        vTaskDelay(pdMS_TO_TICKS(500));
    }

    printf("\n判据：\n");
    printf("  · 按哪个键，哪一列变 0 -> 该键通\n");
    printf("  · 一直不变 -> 该键没接/接在别的脚（这个要单独查）\n");
}

// ------------------------------------------------------------
// 项包装
// ------------------------------------------------------------
static void item_motor_a(void) { test_motor("电机 A", WALI_MOTOR_A_IN1, WALI_MOTOR_A_IN2); }
static void item_motor_b(void) { test_motor("电机 B", WALI_MOTOR_B_IN1, WALI_MOTOR_B_IN2); }
static void item_servo_l(void) { test_servo("左手舵机", WALI_SERVO_L_PIN, LEDC_CHANNEL_1); }
static void item_servo_r(void) { test_servo("右手舵机", WALI_SERVO_R_PIN, LEDC_CHANNEL_2); }
static void item_i2c(void)
{
    st_i2c_scan(0, (int)WALI_I2C_SDA, (int)WALI_I2C_SCL, "（瓦力：屏/触摸总线）");
    printf("\n判据：扫到 0x3C = SSD1306 屏在线\n");
}
static void item_sysinfo(void) { st_print_sysinfo(); }

static const st_item_t kWaliItems[] = {
    {"系统信息（芯片 / MAC / 内存）",              item_sysinfo},
    {"I2C 扫描：SDA=GPIO41  SCL=GPIO42",          item_i2c},
    {"电机 A：GPIO13/GPIO14  正转-停-反转",        item_motor_a},
    {"电机 B：GPIO17/GPIO18  正转-停-反转",        item_motor_b},
    {"左手舵机：GPIO11  0°-90°-180°-90°-0°",      item_servo_l},
    {"右手舵机：GPIO12  0°-90°-180°-90°-0°",      item_servo_r},
    {"屏：SSD1306 满屏黑/白",                     test_display},
    {"按键电平：BOOT/触摸/音量±",                  test_buttons},
};

extern "C" const st_config_t wali_selftest_config = {
    .board_name = "瓦力 wali（qebabe 硬件，引脚实测）",
    .boot_gpio  = 0,
    .items      = kWaliItems,
    .item_count = (int)(sizeof(kWaliItems) / sizeof(kWaliItems[0])),
};
