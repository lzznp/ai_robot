#include "servo_control.h"
#include <esp_log.h>

#define TAG "ServoControl"

void ServoControl::Init(gpio_num_t pin, ledc_channel_t channel) {
    pin_ = pin;
    channel_ = channel;

    ledc_timer_config_t timer_conf = {
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .duty_resolution = LEDC_TIMER_12_BIT,
        .timer_num = LEDC_TIMER_0,
        .freq_hz = 50,
        .clk_cfg = LEDC_AUTO_CLK,
    };
    ledc_timer_config(&timer_conf);

    ledc_channel_config_t channel_conf = {
        .gpio_num = pin_,
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .channel = channel_,
        .intr_type = LEDC_INTR_DISABLE,
        .timer_sel = LEDC_TIMER_0,
        .duty = 0,
        .hpoint = 0,
    };
    ledc_channel_config(&channel_conf);

    SetAngle(90);
    ESP_LOGI(TAG, "Servo initialized on GPIO %d", pin);
}

void ServoControl::SetAngle(int angle) {
    if (angle < 0) angle = 0;
    if (angle > 180) angle = 180;

    // 0° → 0.5ms (102/4096)
    // 90° → 1.5ms (307/4096)
    // 180° → 2.5ms (512/4096)
    int duty = 102 + (angle * (512 - 102) / 180);
    ledc_set_duty(LEDC_LOW_SPEED_MODE, channel_, duty);
    ledc_update_duty(LEDC_LOW_SPEED_MODE, channel_);

    ESP_LOGD(TAG, "Set angle to %d° (duty=%d)", angle, duty);
}