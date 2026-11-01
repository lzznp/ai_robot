// ============================================================
// 步进电机控制 - 实现
// 驱动芯片: 74HC595 + ULN2003
// 电机型号: 24BYJ48 (四相八拍)
// 最后更新: 2026-07-06
// ============================================================

#include "motor_control.h"
#include "config.h"

#include "esp_log.h"
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"

static const char *TAG = "MOTOR_CTRL";

// ============================================================
// 四相八拍时序表
// 每拍对应一个相序, 共8拍
// 1 = 该相导通, 0 = 该相关断
// ============================================================
#define MOTOR_STEPS_PER_REV 512  // 24BYJ48 减速后每圈步数 (512步/圈)

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
// 电机状态结构体
// ============================================================
typedef struct {
    uint8_t phase;              // 当前相位 (0-7)
    uint16_t step_count;        // 当前电机位置 (步数)
    uint8_t running;            // 是否在运行
    uint8_t direction;          // 当前方向
    uint16_t speed;             // 速度 (步/秒)
    TaskHandle_t task_handle;   // 任务句柄
} motor_state_t;

static motor_state_t motors[2] = {
    { .phase = 0, .step_count = 0, .running = 0, .direction = 0, .speed = 100, .task_handle = NULL },
    { .phase = 0, .step_count = 0, .running = 0, .direction = 0, .speed = 100, .task_handle = NULL },
};

static QueueHandle_t motor_queue = NULL;

// ============================================================
// 74HC595 当前输出状态 (软件维护，因为芯片不支持读取)
// ============================================================
static uint8_t hc595_current = 0;

// ============================================================
// 74HC595 底层驱动 (写入并记录当前状态)
// ============================================================
static void hc595_write(uint8_t data)
{
    hc595_current = data;  // 记录当前输出状态

    // 逐位发送 (MSB first)
    for (int i = 7; i >= 0; i--) {
        gpio_set_level(HC595_DS_GPIO, (data >> i) & 0x01);
        gpio_set_level(HC595_SHCP_GPIO, 1);
        gpio_set_level(HC595_SHCP_GPIO, 0);
    }
    // 锁存输出
    gpio_set_level(HC595_STCP_GPIO, 1);
    gpio_set_level(HC595_STCP_GPIO, 0);
}

// ============================================================
// 读取当前 74HC595 输出值 (从软件维护的变量读取)
// ============================================================
static uint8_t hc595_read_current(void)
{
    return hc595_current;
}

// ============================================================
// 设置电机相序
// ============================================================
static void motor_set_phase(uint8_t motor_id, uint8_t phase)
{
    if (motor_id > 1) return;

    const uint8_t *seq = step_sequences[phase];

    // 74HC595 输出布局:
    // Q0-Q3 → 电机1 (A/B/C/D)
    // Q4-Q7 → 电机2 (A/B/C/D)
    uint8_t data = 0;

    if (motor_id == 0) {
        data |= (seq[0] << 0);  // Q0 = 电机1 A相
        data |= (seq[1] << 1);  // Q1 = 电机1 B相
        data |= (seq[2] << 2);  // Q2 = 电机1 C相
        data |= (seq[3] << 3);  // Q3 = 电机1 D相
    } else {
        data |= (seq[0] << 4);  // Q4 = 电机2 A相
        data |= (seq[1] << 5);  // Q5 = 电机2 B相
        data |= (seq[2] << 6);  // Q6 = 电机2 C相
        data |= (seq[3] << 7);  // Q7 = 电机2 D相
    }

    hc595_write(data);
    motors[motor_id].phase = phase;
}

// ============================================================
// 释放电机 (所有相关断)
// ============================================================
void motor_release(uint8_t motor_id)
{
    if (motor_id > 1) return;
    // 将该电机的所有相设置为0
    uint8_t data = hc595_read_current();
    if (motor_id == 0) {
        data &= 0xF0;  // 清除 Q0-Q3
    } else {
        data &= 0x0F;  // 清除 Q4-Q7
    }
    hc595_write(data);
    ESP_LOGI(TAG, "Motor %d released", motor_id);
}

// ============================================================
// 电机控制任务
// ============================================================
static void motor_task(void *arg)
{
    uint8_t motor_id = (uint8_t)(intptr_t)arg;

    while (1) {
        // 等待队列消息
        uint32_t cmd;
        if (xQueueReceive(motor_queue, &cmd, portMAX_DELAY) == pdTRUE) {
            // 检查目标电机
            uint8_t target_id = (cmd >> 24) & 0xFF;
            if (target_id != motor_id) continue;

            // 解析命令
            uint8_t direction = (cmd >> 16) & 0xFF;
            uint16_t steps = cmd & 0xFFFF;

            if (steps == 0xFFFF) {
                // 持续旋转模式
                motors[motor_id].running = 1;
                motors[motor_id].direction = direction;

                while (motors[motor_id].running) {
                    uint8_t next_phase;
                    if (direction == MOTOR_CW) {
                        next_phase = (motors[motor_id].phase + 1) % 8;
                    } else {
                        next_phase = (motors[motor_id].phase + 7) % 8;
                    }
                    motor_set_phase(motor_id, next_phase);
                    motors[motor_id].step_count++;
                    int delay_ms = 1000 / motors[motor_id].speed;
                    vTaskDelay(pdMS_TO_TICKS(delay_ms));
                }
            } else {
                // 步进指定步数
                motors[motor_id].running = 1;
                motors[motor_id].direction = direction;

                for (uint16_t i = 0; i < steps && motors[motor_id].running; i++) {
                    uint8_t next_phase;
                    if (direction == MOTOR_CW) {
                        next_phase = (motors[motor_id].phase + 1) % 8;
                    } else {
                        next_phase = (motors[motor_id].phase + 7) % 8;
                    }
                    motor_set_phase(motor_id, next_phase);
                    motors[motor_id].step_count++;
                    int delay_ms = 1000 / motors[motor_id].speed;
                    vTaskDelay(pdMS_TO_TICKS(delay_ms));
                }

                motors[motor_id].running = 0;
                // 停止后释放相序
                motor_release(motor_id);
            }
        }
    }
}

// ============================================================
// 初始化步进电机控制
// ============================================================
void motor_control_init(void)
{
    // 配置 GPIO 为推挽输出 + 高驱动能力
    gpio_config_t io_conf = {
        .pin_bit_mask = (1ULL << HC595_SHCP_GPIO) |
                        (1ULL << HC595_STCP_GPIO) |
                        (1ULL << HC595_DS_GPIO),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&io_conf));

    // ★ 新增：设置 GPIO 驱动能力为最高 (3 = 最高)
    // 注意：ESP32-S3 的 drive strength 范围是 0-3
    for (int i = 0; i < 3; i++) {
        gpio_set_drive_capability(HC595_SHCP_GPIO, GPIO_DRIVE_CAP_3);
        gpio_set_drive_capability(HC595_STCP_GPIO, GPIO_DRIVE_CAP_3);
        gpio_set_drive_capability(HC595_DS_GPIO, GPIO_DRIVE_CAP_3);
    }

    // 创建队列 (用于跨任务通信)
    motor_queue = xQueueCreate(10, sizeof(uint32_t));
    if (motor_queue == NULL) {
        ESP_LOGE(TAG, "Failed to create motor queue");
        return;
    }

    // 创建两个电机控制任务
    for (int i = 0; i < 2; i++) {
        xTaskCreatePinnedToCore(
            motor_task,
            "motor_task",
            2048,
            (void *)(intptr_t)i,
            5,
            &motors[i].task_handle,
            i % 2
        );
        if (motors[i].task_handle == NULL) {
            ESP_LOGE(TAG, "Failed to create motor task %d", i);
        }
    }

    // 初始化 74HC595 输出全部为低
    hc595_write(0x00);

    ESP_LOGI(TAG, "Motor control initialized");
}

// ============================================================
// 设置电机速度
// ============================================================
void motor_set_speed(uint8_t motor_id, uint16_t steps_per_sec)
{
    if (motor_id > 1) return;
    if (steps_per_sec < 1) steps_per_sec = 1;
    if (steps_per_sec > 500) steps_per_sec = 500;  // 限制最高速度
    motors[motor_id].speed = steps_per_sec;
    ESP_LOGI(TAG, "Motor %d speed set to %d steps/sec", motor_id, steps_per_sec);
}

// ============================================================
// 电机持续旋转
// ============================================================
void motor_rotate(uint8_t motor_id, uint8_t direction)
{
    if (motor_id > 1) return;
    if (motors[motor_id].running) {
        motor_stop(motor_id);
    }
    // 发送命令: 0xFF 表示持续旋转
    uint32_t cmd = (motor_id << 24) | (direction << 16) | 0xFFFF;
    xQueueSend(motor_queue, &cmd, 0);
    ESP_LOGI(TAG, "Motor %d rotating %s", motor_id, direction ? "CCW" : "CW");
}

// ============================================================
// 电机停止
// ============================================================
void motor_stop(uint8_t motor_id)
{
    if (motor_id > 1) return;
    motors[motor_id].running = 0;
    motor_release(motor_id);
    ESP_LOGI(TAG, "Motor %d stopped", motor_id);
}

// ============================================================
// 电机步进指定步数 (阻塞)
// ============================================================
void motor_step(uint8_t motor_id, uint8_t direction, uint16_t steps)
{
    if (motor_id > 1) return;
    if (motors[motor_id].running) {
        motor_stop(motor_id);
    }
    // 发送命令
    uint32_t cmd = (motor_id << 24) | (direction << 16) | (steps & 0xFFFF);
    xQueueSend(motor_queue, &cmd, 0);
    ESP_LOGI(TAG, "Motor %d stepping %d steps %s",
             motor_id, steps, direction ? "CCW" : "CW");
}

// ============================================================
// 紧急停止 (两个电机同时停止)
// ============================================================
void motor_emergency_stop(void)
{
    motors[0].running = 0;
    motors[1].running = 0;
    hc595_write(0x00);  // 所有相关断
    ESP_LOGI(TAG, "Emergency stop!");
}

// ============================================================
// 电机状态查询
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