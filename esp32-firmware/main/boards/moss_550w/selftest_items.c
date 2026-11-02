// ============================================================
// selftest_items.c — MOSS 550W 的自检项表（板相关，只有这一份）
//
// 引擎在 components/selftest/ 里（交互 + 打印助手），本文件只回答
// "这张板有哪几项、每项怎么测、判据是什么"。
//
// 引脚真相（网表 + 实测双确认，见 工作文档\MOSS-硬件台账.md）：
//   I2C  SDA=GPIO2  SCL=GPIO1（与摄像头 SCCB 共用总线，板上无屏）
//   电机 74HC595(U6/U10: GPIO3/4/5) -> ULN2003 -> 24BYJ48 ×2
//   灯   灯带1 GPIO7(3颗) / 灯带2 GPIO48(2颗)，数据线在 FMH1/FMH2 焊盘
//   ADC  电池 GPIO8=ADC1_CH7 / USB 检测 GPIO6=ADC1_CH5
// ============================================================

#include <stdio.h>
#include <stdbool.h>
#include <stddef.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "esp_err.h"
#include "esp_adc/adc_oneshot.h"

#include "config.h"
#include "motor_control.h"
#include "selftest.h"
#include "selftest_helpers.h"

#include <led_strip.h>   // espressif/led_strip：真实 WS2812 驱动（RMT）

// ------------------------------------------------------------
// 项 3、4：步进电机点动
// ------------------------------------------------------------
static void test_motor(unsigned char motor_id)
{
    static bool inited = false;
    if (!inited) {
        motor_control_init();
        inited = true;
        vTaskDelay(pdMS_TO_TICKS(100));
    }

    motor_set_speed(motor_id, 60);   // 慢一点，方便观察
    printf("电机%d: 开始正转 128 步（≈1/4 圈，60 步/秒，约 2 秒）\n", motor_id + 1);
    motor_step(motor_id, MOTOR_CW, 128);

    // 轮询等待（motor_step 是非阻塞的）
    for (int i = 0; i < 100 && motor_is_running(motor_id); i++) {
        vTaskDelay(pdMS_TO_TICKS(50));
    }

    printf("电机%d: 结束，累计位置 = %u 步\n", motor_id + 1,
           (unsigned)motor_get_position(motor_id));
    printf("\n判据：\n");
    printf("  · 转了        -> 595 / ULN2003 / 电机 这一段是好的\n");
    printf("  · 不转但发烫  -> 相序或 ULN2003 某一路有问题\n");
    printf("  · 完全不响    -> 查 +5V 供电与 U6 的 10 脚(/MR)、13 脚(/OE)\n");
    printf("\n★ 角度换算（很重要，别把“转得少”当成“没转”）：\n");
    printf("   128 步  @ 512 步/圈  = 90°      （很明显）\n");
    printf("   128 步  @ 4096 步/圈 = 11.25°   （几乎看不出来！）\n");
    printf("   24BYJ48 类减速步进常见每圈是 4096 步（8 拍），\n");
    printf("   而本代码的 MOTOR_STEPS_PER_REV 写的是 512 —— 可能偏小 8 倍。\n");
    printf("   ⇒ 想确认，就**再长按几次**（位置会累加）：\n");
    printf("     累计到 512 步 = 一圈(512/圈) 或 45°(4096/圈)，一定能看出来。\n");
}

static void item_motor1(void) { test_motor(MOTOR_1); }
static void item_motor2(void) { test_motor(MOTOR_2); }

// ------------------------------------------------------------
// 项 5：LED —— 真实 WS2812 驱动（RMT 数据流）
//
// 不能用"GPIO 静态翻转"：灯珠要 800kHz 数据流，静态电平只会被当成无效数据。
// 颜色出来 = 灯珠好 + 数据线通。
// ------------------------------------------------------------
static void strip_fill(led_strip_handle_t h, uint32_t n, unsigned char r,
                       unsigned char g, unsigned char b)
{
    for (uint32_t i = 0; i < n; i++) {
        led_strip_set_pixel(h, i, r, g, b);
    }
    led_strip_refresh(h);
}

static void item_led(void)
{
    printf("用真实 WS2812 驱动（RMT）点亮两组灯带\n");
    printf("  灯带1: GPIO%d × %d 颗      灯带2: GPIO%d × %d 颗\n",
           (int)LED_1313_GPIO, (int)LED_1313_NUM,
           (int)LED_4020_GPIO, (int)LED_4020_NUM);
    printf("  依次显示: 红 -> 绿 -> 蓝 -> 白 -> 熄灭（各 0.7 秒，亮度 24/255 不刺眼）\n\n");

    led_strip_handle_t s1 = NULL;
    led_strip_handle_t s2 = NULL;

    led_strip_config_t cfg = {0};
    cfg.led_model = LED_MODEL_WS2812;
    cfg.color_component_format = LED_STRIP_COLOR_COMPONENT_FMT_GRB;

    led_strip_rmt_config_t rmt = {0};
    rmt.resolution_hz = 10 * 1000 * 1000;   // 10 MHz

    cfg.strip_gpio_num = LED_1313_GPIO;
    cfg.max_leds = LED_1313_NUM;
    esp_err_t e1 = led_strip_new_rmt_device(&cfg, &rmt, &s1);

    cfg.strip_gpio_num = LED_4020_GPIO;
    cfg.max_leds = LED_4020_NUM;
    esp_err_t e2 = led_strip_new_rmt_device(&cfg, &rmt, &s2);

    printf("  初始化: 灯带1 = %s   灯带2 = %s\n\n",
           esp_err_to_name(e1), esp_err_to_name(e2));

    if (s1 == NULL && s2 == NULL) {
        printf("  [X] 两组都创建失败：RMT 通道可能被别的功能占用\n");
        return;
    }

    // ---- 关键：分组单独点亮，才能分清是哪一组没接 ----
    printf("\n========== 分步测试（请盯住灯，看哪一步有反应）==========\n");

    printf("[步骤1] 只点亮 灯带1 —— GPIO%d / %d 颗 —— 红     (1.2 秒)\n",
           (int)LED_1313_GPIO, (int)LED_1313_NUM);
    if (s1) strip_fill(s1, LED_1313_NUM, 24, 0, 0);
    vTaskDelay(pdMS_TO_TICKS(1200));
    if (s1) led_strip_clear(s1);
    printf("[步骤1] 熄灭。<- 这一步有没有红？(有 = 灯带1 通)\n\n");

    printf("[步骤2] 只点亮 灯带2 —— GPIO%d / %d 颗 —— 绿     (1.2 秒)\n",
           (int)LED_4020_GPIO, (int)LED_4020_NUM);
    if (s2) strip_fill(s2, LED_4020_NUM, 0, 24, 0);
    vTaskDelay(pdMS_TO_TICKS(1200));
    if (s2) led_strip_clear(s2);
    printf("[步骤2] 熄灭。<- 这一步有没有绿？(有 = 灯带2 通)\n\n");

    printf("========== 分步结束，下面两组一起跑一遍 ==========\n");

    struct { const char *name; unsigned char r, g, b; } colors[] = {
        {"红", 24, 0, 0},
        {"绿", 0, 24, 0},
        {"蓝", 0, 0, 24},
        {"白", 24, 24, 24},
    };

    for (size_t i = 0; i < sizeof(colors) / sizeof(colors[0]); i++) {
        printf("  -> %s\n", colors[i].name);
        if (s1) strip_fill(s1, LED_1313_NUM, colors[i].r, colors[i].g, colors[i].b);
        if (s2) strip_fill(s2, LED_4020_NUM, colors[i].r, colors[i].g, colors[i].b);
        vTaskDelay(pdMS_TO_TICKS(700));
    }

    if (s1) led_strip_clear(s1);
    if (s2) led_strip_clear(s2);
    printf("  -> 熄灭\n\n");

    printf("判据（按上面的分步结果对号入座）：\n");
    printf("  · 步骤1 红 + 步骤2 绿 都亮 -> 两组都通，这一项通过\n");
    printf("  · 只有步骤1 亮            -> 灯带1(GPIO%d) 通，灯带2(GPIO%d) 数据线没接\n",
           (int)LED_1313_GPIO, (int)LED_4020_GPIO);
    printf("  · 只有步骤2 亮            -> 灯带2(GPIO%d) 通，灯带1(GPIO%d) 数据线没接\n",
           (int)LED_4020_GPIO, (int)LED_1313_GPIO);
    printf("  · 两步都不亮              -> 一组数据线都没接（量下面两条通断）：\n");
    printf("                               FMH1.2 <-> H5.2(GPIO%d)\n", (int)LED_1313_GPIO);
    printf("                               FMH2.2 <-> H6.2(GPIO%d)\n", (int)LED_4020_GPIO);
    printf("  · 颜色不对（红显示成绿）  -> 灯珠是 RGB 不是 GRB，改 color_component_format\n");
    printf("  · 某组只有部分灯珠亮      -> 该组串联中间断了（灯珠或焊点）\n");

    if (s1) led_strip_del(s1);
    if (s2) led_strip_del(s2);
}

// ------------------------------------------------------------
// 项 6：ADC
// ------------------------------------------------------------
static void item_adc(void)
{
    adc_oneshot_unit_handle_t unit = NULL;
    adc_oneshot_unit_init_cfg_t ucfg = {0};
    ucfg.unit_id = ADC_UNIT_1;
    ucfg.ulp_mode = ADC_ULP_MODE_DISABLE;
    if (adc_oneshot_new_unit(&ucfg, &unit) != ESP_OK) {
        printf("  [X] ADC 单元初始化失败\n");
        return;
    }

    adc_oneshot_chan_cfg_t ccfg = {0};
    ccfg.atten = ADC_ATTEN_DB_12;
    ccfg.bitwidth = ADC_BITWIDTH_DEFAULT;

    // 网表核实：GPIO8 -> ADC1_CH7（电池分压 R20/R23）
    //           GPIO6 -> ADC1_CH5（USB 5V 分压 R21/R24）
    adc_oneshot_config_channel(unit, ADC_CHANNEL_7, &ccfg);
    adc_oneshot_config_channel(unit, ADC_CHANNEL_5, &ccfg);

    printf("  序号   电池 GPIO8(CH7)    USB GPIO6(CH5)\n");
    for (int i = 0; i < 5; i++) {
        int vb = -1, vu = -1;
        adc_oneshot_read(unit, ADC_CHANNEL_7, &vb);
        adc_oneshot_read(unit, ADC_CHANNEL_5, &vu);
        printf("   %d       %4d              %4d\n", i, vb, vu);
        vTaskDelay(pdMS_TO_TICKS(200));
    }

    printf("\n判据（raw 值，未标定，看变化趋势即可）：\n");
    printf("  · 拔插 USB 时 USB 那列明显变化 -> 分压电路正常\n");
    printf("  · 电池那列长时间为 0 或满量程 -> 分压/接线异常\n");

    adc_oneshot_del_unit(unit);
}

// ------------------------------------------------------------
// 项 1、2：I2C 扫描（A/B 反向对照）
// ------------------------------------------------------------
static void item_i2c_a(void)
{
    // MOSS 的 I2C_PORT 是 I2C_NUM_0；这里直接写端口号 0，
    // 免得为了一个宏给 config.h 加 i2c 头文件依赖。
    st_i2c_scan(0, (int)I2C_SDA_GPIO, (int)I2C_SCL_GPIO,
                "（现行 config.h 的写法）");
}

static void item_i2c_b(void)
{
    st_i2c_scan(0, (int)I2C_SCL_GPIO, (int)I2C_SDA_GPIO,
                "（与上面相反，用来验证引脚定义是否反了）");
    printf("对照法：A、B 两次里哪一次扫到 0x3C，config.h 就照哪一次写。\n");
}

static void item_sysinfo(void) { st_print_sysinfo(); }

// ------------------------------------------------------------
// MOSS 550W 项表（序号由引擎打印成 x/item_count）
// ------------------------------------------------------------
static const st_item_t kMossItems[] = {
    {"系统信息（芯片 / MAC / 内存）",                          item_sysinfo},
    {"I2C 扫描 A：SDA=GPIO2  SCL=GPIO1  （现行 config.h）",     item_i2c_a},
    {"I2C 扫描 B：SDA=GPIO1  SCL=GPIO2  （对调试一次）",        item_i2c_b},
    {"步进电机 1：正转 128 步（≈1/4 圈）",                      item_motor1},
    {"步进电机 2：正转 128 步（≈1/4 圈）",                      item_motor2},
    {"灯组：真实 WS2812 驱动（红/绿/蓝/白）",                    item_led},
    {"ADC 读数：电池 GPIO8 / USB 检测 GPIO6",                   item_adc},
};

const st_config_t moss_selftest_config = {
    .board_name = "MOSS 550W",
    .boot_gpio  = (int)BOOT_BUTTON_GPIO,
    .items      = kMossItems,
    .item_count = (int)(sizeof(kMossItems) / sizeof(kMossItems[0])),
};
