#include "code_interpreter.h"
#include "board.h"
#include "esp_log.h"
#include "driver/gpio.h"
#include "driver/ledc.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char* TAG = "CodeInterpreter";

bool CodeInterpreter::Execute(cJSON* steps_json) {
    if (!cJSON_IsArray(steps_json)) {
        ESP_LOGE(TAG, "steps is not an array");
        return false;
    }

    int step_count = cJSON_GetArraySize(steps_json);
    ESP_LOGI(TAG, "Executing %d steps", step_count);

    for (int i = 0; i < step_count; i++) {
        cJSON* step = cJSON_GetArrayItem(steps_json, i);
        if (!step) continue;

        // 解析 op
        cJSON* op_json = cJSON_GetObjectItem(step, "op");
        if (!op_json) {
            ESP_LOGW(TAG, "Step %d missing 'op' field", i);
            continue;
        }

        std::string op = op_json->valuestring;
        ESP_LOGI(TAG, "Step %d: %s", i, op.c_str());

        if (op == "gpio_write") {
            // 参数：pin, value, duration_ms
            cJSON* pin = cJSON_GetObjectItem(step, "pin");
            cJSON* value = cJSON_GetObjectItem(step, "value");
            cJSON* duration = cJSON_GetObjectItem(step, "duration");

            if (pin && value && duration) {
                GpioWrite(pin->valueint, value->valueint, duration->valueint);
            } else {
                ESP_LOGE(TAG, "gpio_write missing params");
            }
        }
        else if (op == "pwm_write") {
            // 参数：pin, value, duration_ms
            cJSON* pin = cJSON_GetObjectItem(step, "pin");
            cJSON* value = cJSON_GetObjectItem(step, "value");
            cJSON* duration = cJSON_GetObjectItem(step, "duration");

            if (pin && value && duration) {
                PwmWrite(pin->valueint, value->valueint, duration->valueint);
            }
        }
        else if (op == "delay") {
            cJSON* ms = cJSON_GetObjectItem(step, "ms");
            if (ms) {
                Delay(ms->valueint);
            }
        }
        else if (op == "loop") {
            cJSON* times = cJSON_GetObjectItem(step, "times");
            cJSON* code_block = cJSON_GetObjectItem(step, "code_block");
            if (times && code_block) {
                Loop(times->valueint, code_block);
            }
        }
        else {
            ESP_LOGW(TAG, "Unknown op: %s", op.c_str());
        }
    }

    return true;
}

bool CodeInterpreter::GpioWrite(int pin, int value, int duration_ms) {
    ESP_LOGI(TAG, "GPIO %d -> %d for %d ms", pin, value, duration_ms);
    gpio_set_level((gpio_num_t)pin, value);
    if (duration_ms > 0) {
        vTaskDelay(pdMS_TO_TICKS(duration_ms));
        gpio_set_level((gpio_num_t)pin, 0);
    }
    return true;
}

bool CodeInterpreter::PwmWrite(int pin, int value, int duration_ms) {
    ESP_LOGI(TAG, "PWM %d -> %d for %d ms", pin, value, duration_ms);
    // 使用 ledc 或 mcpwm 驱动
    // 具体实现根据板子而定
    return true;
}

bool CodeInterpreter::Delay(int ms) {
    vTaskDelay(pdMS_TO_TICKS(ms));
    return true;
}

bool CodeInterpreter::Loop(int times, cJSON* code_block) {
    for (int i = 0; i < times; i++) {
        Execute(code_block);
    }
    return true;
}