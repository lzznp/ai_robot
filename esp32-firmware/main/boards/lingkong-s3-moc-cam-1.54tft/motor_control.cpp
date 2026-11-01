#include "motor_control.h"

#define TAG "MotorControl"

void MotorControl::Init(gpio_num_t in1, gpio_num_t in2) {
    in1_ = in1;
    in2_ = in2;

    gpio_config_t io_conf = {
        .pin_bit_mask = (1ULL << in1) | (1ULL << in2),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    gpio_config(&io_conf);

    Stop();
}

void MotorControl::SetMotor(int in1_val, int in2_val) {
    gpio_set_level(in1_, in1_val);
    gpio_set_level(in2_, in2_val);
}

void MotorControl::Forward() {
    SetMotor(1, 0);  // IN1=1, IN2=0 → 正转
}

void MotorControl::Backward() {
    SetMotor(0, 1);  // IN1=0, IN2=1 → 反转
}

void MotorControl::Stop() {
    SetMotor(0, 0);  // IN1=0, IN2=0 → 停止
}

void MotorControl::Brake() {
    SetMotor(1, 1);  // IN1=1, IN2=1 → 制动
}