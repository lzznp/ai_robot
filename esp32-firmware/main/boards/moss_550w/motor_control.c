// ============================================================
// 步进电机控制 - 实现
// 驱动芯片: 74HC595 + ULN2003
// 电机型号: 24BYJ48 (四相八拍)
//
// 硬件接线（经 FlyingProbeTesting.json 网表核实）:
//   GPIO03 → U6.11 (SHCP / SRCLK)
//   GPIO04 → U6.12 (STCP / RCLK)
//   GPIO05 → U6.14 (DS   / SER)
//   U6 Q0..Q3 → ULN2003 → 电机1 (U9 / CN3)
//   U6 Q4..Q7 → ULN2003 → 电机2 (U11 / CN4)
//
// 2026-10-19 修订（4 个 bug）:
//   [B1] 两个电机抢同一个队列、收到别人的命令就丢弃 ⇒ 改为每电机一个队列
//   [B2] motor_set_phase() 覆盖整个 595 输出字节，把另一个电机的相位清零
//        ⇒ 改为 hc595_modify() 只改自己那半个字节
//   [B3] hc595_write() 无互斥，两个任务并发时移位时钟交错 ⇒ 加互斥量
//   [B4] 1000/speed 在 speed>100 时算出 <10ms，pdMS_TO_TICKS 直接变 0
//        ⇒ 小于一个 tick 时改用 esp_rom_delay_us
// ============================================================

#include "motor_control.h"
#include "config.h"

#include "esp_log.h"
#include "esp_rom_sys.h"
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"

static const char *TAG = "MOTOR_CTRL";

// ============================================================
// 四相八拍时序表
// ============================================================
#define MOTOR_STEPS_PER_REV 512  // 24BYJ48 减速后每圈步数

static const uint8_t step_sequences[8][4] = {
    {1, 0, 0, 0},   // 拍0: A
    {1, 1, 0, 0},   // 拍1: AB
    {0, 1, 0, 0},   // 拍2: B
    {0, 1, 1, 0},   // 拍3: BC
    {0, 0, 1, 0},   // 拍4: C
    {0, 0, 1, 1},   // 拍5: CD
    {0, 0, 0, 1},   // 拍6: D
    {1, 0, 0, 1},   // 拍7: DA
};

// ============================================================
// 电机状态
// ============================================================
typedef struct {
    uint8_t phase;
    uint16_t step_count;
    volatile uint8_t running;
    uint8_t direction;
    uint16_t speed;
    uint32_t delay_acc_us;      // 延时误差累积（不足一个 tick 的余量带到下一步）
    TaskHandle_t task_handle;
    uint8_t hold;               // 走完是否保持力矩（2026-11-01）
} motor_state_t;

static motor_state_t motors[2] = {
    { .phase = 0, .step_count = 0, .running = 0, .direction = 0, .speed = 100, .task_handle = NULL },
    { .phase = 0, .step_count = 0, .running = 0, .direction = 0, .speed = 100, .task_handle = NULL },
};

// [B1] 每个电机一个独立队列，不再抢同一个
static QueueHandle_t motor_queue[2] = { NULL, NULL };

// [B3] 595 输出状态 + 互斥保护
static uint8_t hc595_current = 0;
static SemaphoreHandle_t s_hc595_mutex = NULL;

// ============================================================
// 74HC595 底层时序（必须已持锁）
// ============================================================
static void hc595_shift_out(uint8_t data)
{
    for (int i = 7; i >= 0; i--) {
        gpio_set_level(HC595_DS_GPIO, (data >> i) & 0x01);
        gpio_set_level(HC595_SHCP_GPIO, 1);
        gpio_set_level(HC595_SHCP_GPIO, 0);
    }
    gpio_set_level(HC595_STCP_GPIO, 1);
    gpio_set_level(HC595_STCP_GPIO, 0);
}

// 整体覆盖写出
static void hc595_write_locked(uint8_t data)
{
    if (s_hc595_mutex) xSemaphoreTake(s_hc595_mutex, portMAX_DELAY);
    hc595_current = data;
    hc595_shift_out(data);
    if (s_hc595_mutex) xSemaphoreGive(s_hc595_mutex);
}

// [B2] 只修改指定的位：先与 and_mask 清零，再或上 or_bits
static void hc595_modify(uint8_t and_mask, uint8_t or_bits)
{
    if (s_hc595_mutex) xSemaphoreTake(s_hc595_mutex, portMAX_DELAY);
    hc595_current = (uint8_t)((hc595_current & and_mask) | or_bits);
    hc595_shift_out(hc595_current);
    if (s_hc595_mutex) xSemaphoreGive(s_hc595_mutex);
}

// ============================================================
// 设置电机相序（只动自己那半个字节）
// ============================================================
static void motor_set_phase(uint8_t motor_id, uint8_t phase)
{
    if (motor_id > 1) return;

    const uint8_t *seq = step_sequences[phase];
    uint8_t bits = (uint8_t)(seq[0] | (seq[1] << 1) | (seq[2] << 2) | (seq[3] << 3));

    if (motor_id == 0) {
        hc595_modify(0xF0, bits);        // 保留高半字节（电机2）
    } else {
        hc595_modify(0x0F, (uint8_t)(bits << 4));  // 保留低半字节（电机1）
    }
    motors[motor_id].phase = phase;
}

// ============================================================
// 释放电机（所有相关断）
// ============================================================
void motor_release(uint8_t motor_id)
{
    if (motor_id > 1) return;
    hc595_modify(motor_id == 0 ? 0xF0 : 0x0F, 0x00);
    ESP_LOGI(TAG, "电机%d: 释放相位（全部断电）", motor_id + 1);
}

// ============================================================
// [B6] 一步的延时 —— 让出 CPU，同时靠累积补偿保证平均速度
//
// 踩过的两个坑：
//   ① pdMS_TO_TICKS(16) 在 100Hz tick 下 = 1 tick = 10ms，60 步/秒 被压成 100 步/秒
//   ② 改用 esp_rom_delay_us 忙等后：电机任务绑在 core 0、优先级 5，
//      xQueueSend 后立刻抢占同核的调用者（app_main，优先级 1），
//      忙等 2 秒不放手 ⇒ 调用者的日志变成在末尾打印，而且生产固件里会卡住音频。
//
// 现在的做法：用 vTaskDelay 让出 CPU，把「不足一个 tick 的余量」记到
// delay_acc_us 里带到下一步 ⇒ 单步有 ±10ms 抖动，但长期平均速度准确。
// ============================================================
static void step_delay(uint8_t motor_id)
{
    uint16_t speed = motors[motor_id].speed;
    if (speed < 1) speed = 1;

    uint32_t period_us = 1000000u / speed;
    uint32_t acc = motors[motor_id].delay_acc_us + period_us;

    TickType_t ticks = pdMS_TO_TICKS(acc / 1000u);
    if (ticks == 0) {
        // 还不够一个 tick：这一步不睡，欠账留到下一步
        motors[motor_id].delay_acc_us = acc;
        return;
    }

    vTaskDelay(ticks);

    uint32_t slept_us = (uint32_t)ticks * (uint32_t)portTICK_PERIOD_MS * 1000u;
    motors[motor_id].delay_acc_us = (acc > slept_us) ? (acc - slept_us) : 0;
}

// ============================================================
// 电机控制任务（每个电机一个）
// ============================================================
static void motor_task(void *arg)
{
    uint8_t motor_id = (uint8_t)(intptr_t)arg;

    while (1) {
        uint32_t cmd;
        if (xQueueReceive(motor_queue[motor_id], &cmd, portMAX_DELAY) != pdTRUE) {
            continue;
        }

        uint8_t direction = (cmd >> 16) & 0xFF;
        uint16_t steps = cmd & 0xFFFF;

        motors[motor_id].running = 1;
        motors[motor_id].direction = direction;

        if (steps == 0xFFFF) {
            // 持续旋转
            while (motors[motor_id].running) {
                uint8_t next = (direction == MOTOR_CW)
                                   ? (uint8_t)((motors[motor_id].phase + 1) % 8)
                                   : (uint8_t)((motors[motor_id].phase + 7) % 8);
                motor_set_phase(motor_id, next);
                motors[motor_id].step_count++;
                step_delay(motor_id);
            }
        } else {
            // 指定步数
            for (uint16_t i = 0; i < steps && motors[motor_id].running; i++) {
                uint8_t next = (direction == MOTOR_CW)
                                   ? (uint8_t)((motors[motor_id].phase + 1) % 8)
                                   : (uint8_t)((motors[motor_id].phase + 7) % 8);
                motor_set_phase(motor_id, next);
                motors[motor_id].step_count++;
                step_delay(motor_id);
            }
            motors[motor_id].running = 0;
            /* 2026-11-01：走完是否松劲，由 hold 标志决定。
             * MOSS 是悬挂音响，垂直轴断电后可能被重力带走 ⇒ 需要 hold=1 保持力矩。
             * 代价是 ULN2003/电机持续通电发热，所以默认仍是 0（松劲）。 */
            if (motors[motor_id].hold) {
                ESP_LOGI(TAG, "电机%d: 走完，保持力矩（不释放相位）", motor_id + 1);
            } else {
                motor_release(motor_id);
            }
        }
    }
}

// ============================================================
// 初始化
// ============================================================
void motor_control_init(void)
{
    if (motor_queue[0] != NULL) {
        ESP_LOGW(TAG, "already initialized");
        return;
    }

    if (s_hc595_mutex == NULL) {
        s_hc595_mutex = xSemaphoreCreateMutex();
        if (s_hc595_mutex == NULL) {
            ESP_LOGE(TAG, "创建互斥量失败");
            return;
        }
    }

    gpio_config_t io_conf = {
        .pin_bit_mask = (1ULL << HC595_SHCP_GPIO) |
                        (1ULL << HC595_STCP_GPIO) |
                        (1ULL << HC595_DS_GPIO),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&io_conf));

    // 74HC595 由 3.3V 驱动、5V 供电，时钟沿要干净：给最高驱动能力
    gpio_set_drive_capability(HC595_SHCP_GPIO, GPIO_DRIVE_CAP_3);
    gpio_set_drive_capability(HC595_STCP_GPIO, GPIO_DRIVE_CAP_3);
    gpio_set_drive_capability(HC595_DS_GPIO, GPIO_DRIVE_CAP_3);

    // 上电先全部清零，避免电机上电自己动
    hc595_write_locked(0x00);

    /* 2026-11-01：垂直轴（motor=0）**不需要**靠通电保持力矩 —— 用户实测：
     * 给它断电后机构自己就停住（不会因重力回落），所以 hold 保持默认 0（走完松劲），
     * 避免白发热。要临时保持力矩仍可发 release:false。 */

    for (int i = 0; i < 2; i++) {
        motor_queue[i] = xQueueCreate(10, sizeof(uint32_t));
        if (motor_queue[i] == NULL) {
            ESP_LOGE(TAG, "Fail to create motor %d queue", i);
            return;
        }
        if (xTaskCreatePinnedToCore(
                motor_task, "motor_task", 3072, (void *)(intptr_t)i,
                5, &motors[i].task_handle, i % 2) != pdPASS) {
            ESP_LOGE(TAG, "Fail to create motor %d task", i);
        }
    }

    ESP_LOGI(TAG, "Motor control initialized (dual queue, mutex protected)");
}

// ============================================================
// 设置速度
// ============================================================
void motor_set_speed(uint8_t motor_id, uint16_t steps_per_sec)
{
    if (motor_id > 1) return;
    if (steps_per_sec < 1) steps_per_sec = 1;
    if (steps_per_sec > 500) steps_per_sec = 500;
    motors[motor_id].speed = steps_per_sec;
    ESP_LOGI(TAG, "电机%d: 速度 = %d 步/秒", motor_id + 1, steps_per_sec);
}

// ============================================================
// 持续旋转
// ============================================================
void motor_rotate(uint8_t motor_id, uint8_t direction)
{
    if (motor_id > 1 || motor_queue[motor_id] == NULL) return;
    motors[motor_id].running = 0;          // 先让当前动作退出循环
    vTaskDelay(pdMS_TO_TICKS(1));
    motors[motor_id].running = 1;
    motors[motor_id].direction = direction;
    uint32_t cmd = ((uint32_t)motor_id << 24) | ((uint32_t)direction << 16) | 0xFFFFu;
    xQueueSend(motor_queue[motor_id], &cmd, 0);
    ESP_LOGI(TAG, "电机%d: 持续旋转 %s", motor_id + 1, direction ? "CCW反转" : "CW正转");
}

// ============================================================
// 停止
// ============================================================
void motor_stop(uint8_t motor_id)
{
    if (motor_id > 1) return;
    motors[motor_id].running = 0;
    motor_release(motor_id);
    ESP_LOGI(TAG, "电机%d: 已停止", motor_id + 1);
}

// ============================================================
// 步进指定步数
// 注意：本函数**不阻塞**，只把命令丢进队列就返回。
//       需要等它走完，就轮询 motor_is_running() 或 motor_get_position()。
// ============================================================
void motor_step(uint8_t motor_id, uint8_t direction, uint16_t steps)
{
    if (motor_id > 1 || motor_queue[motor_id] == NULL) return;
    motors[motor_id].running = 0;          // 打断上一次
    vTaskDelay(pdMS_TO_TICKS(1));
    uint32_t cmd = ((uint32_t)motor_id << 24) | ((uint32_t)direction << 16) | (steps & 0xFFFFu);
    xQueueSend(motor_queue[motor_id], &cmd, 0);
    ESP_LOGI(TAG, "电机%d: 步进 %d 步 %s", motor_id + 1, steps, direction ? "CCW反转" : "CW正转");
}

// ============================================================
// 紧急停止
// ============================================================
void motor_emergency_stop(void)
{
    motors[0].running = 0;
    motors[1].running = 0;
    hc595_write_locked(0x00);
    ESP_LOGW(TAG, "EMERGENCY STOP");
}

// ============================================================
// 状态查询
// ============================================================
uint8_t motor_is_running(uint8_t motor_id)
{
    if (motor_id > 1) return 0;
    return motors[motor_id].running;
}

uint16_t motor_get_position(uint8_t motor_id)
{
    if (motor_id > 1) return 0;
    return motors[motor_id].step_count;
}

// ============================================================
// 设置"走完是否保持力矩"（2026-11-01）
//   hold = 1 → 走到目标步数后不释放相位，靠持续通电顶住负载
//   hold = 0 → 释放（缺省）
// 注意：只影响**下一次**固定步数移动的收尾；已经在跑的不受影响。
// ============================================================
void motor_set_hold(uint8_t motor_id, uint8_t hold)
{
    if (motor_id > 1) return;
    motors[motor_id].hold = hold ? 1 : 0;
}
