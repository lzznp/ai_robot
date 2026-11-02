// ============================================================
// selftest.c — 自检引擎（板子无关）
//
// 只干三件事：打印横幅 / 轮询 BOOT 键 / 分发到板子给的项表。
// 具体测什么、判据是什么，全在各板的 selftest_items.c 里。
//
// 全部用 printf 走串口，不走 ESP_LOG
// （ESP_LOG 带级别前缀和颜色，判读时反而乱）
// ============================================================

#include "selftest.h"

#include <stdio.h>
#include <stdbool.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "driver/gpio.h"

#include "selftest_helpers.h"

// 长按判定的阈值：>= 这个时长算"执行"，否则算"翻下一项"
#define ST_LONG_PRESS_MS 800

static const st_config_t *s_cfg = NULL;
static int s_index = 0;

static void print_banner(void)
{
    printf("\n");
    printf("=================================================\n");
    printf("  %s  元件自检模式   (不连接 WiFi/后台)\n", s_cfg->board_name);
    printf("-------------------------------------------------\n");
    printf("  共 %d 项\n", s_cfg->item_count);
    printf("  BOOT 键 单击 = 下一项\n");
    printf("  BOOT 键 长按 = 执行当前项\n");
    printf("  串口波特率 115200  (idf.py monitor)\n");
    printf("=================================================\n");
    printf("\n");
}

static void print_current(void)
{
    printf("\n>>> [%d/%d %s]\n", s_index, s_cfg->item_count,
           s_cfg->items[s_index].title);
    printf("    长按 BOOT 执行，单击换下一项\n");
}

static void run_current(void)
{
    st_print_sep();
    printf(">>> 执行: %d/%d %s\n", s_index, s_cfg->item_count,
           s_cfg->items[s_index].title);
    s_cfg->items[s_index].run();
    st_print_sep();
}

void st_run(const st_config_t *cfg)
{
    s_cfg = cfg;
    s_index = 0;

    print_banner();

    gpio_config_t io = {0};
    io.pin_bit_mask = (1ULL << cfg->boot_gpio);
    io.mode = GPIO_MODE_INPUT;
    io.pull_up_en = GPIO_PULLUP_ENABLE;
    io.pull_down_en = GPIO_PULLDOWN_DISABLE;
    io.intr_type = GPIO_INTR_DISABLE;
    gpio_config(&io);

    printf("[i] BOOT 键 = GPIO%d，未按下时应为高电平 1\n", cfg->boot_gpio);
    printf("[i] 当前读数 = %d\n", gpio_get_level((gpio_num_t)cfg->boot_gpio));

    // 上电先把第 0 项跑一遍（系统信息无副作用）
    run_current();
    print_current();

    bool prev_level = 1;
    TickType_t press_tick = 0;

    while (true) {
        int level = gpio_get_level((gpio_num_t)cfg->boot_gpio);

        if (prev_level == 1 && level == 0) {
            // 按下沿
            press_tick = xTaskGetTickCount();
            printf("[键] 按下...\n");
        } else if (prev_level == 0 && level == 1) {
            // 松开沿
            TickType_t held = xTaskGetTickCount() - press_tick;
            if (held >= pdMS_TO_TICKS(ST_LONG_PRESS_MS)) {
                // 长按 -> 执行
                run_current();
            } else {
                // 单击 -> 换项
                s_index = (s_index + 1) % cfg->item_count;
                print_current();
            }
        }

        prev_level = (level != 0);
        vTaskDelay(pdMS_TO_TICKS(20));
    }
}
