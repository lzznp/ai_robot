#ifndef MOTOR_CONTROL_H
#define MOTOR_CONTROL_H

#include <driver/gpio.h>
#include <esp_log.h>

class MotorControl {
public:
    void Init(gpio_num_t in1, gpio_num_t in2);
    void Forward();
    void Backward();
    void Stop();
    void Brake();  // 急停

private:
    gpio_num_t in1_;
    gpio_num_t in2_;
    void SetMotor(int in1_val, int in2_val);
};

#endif