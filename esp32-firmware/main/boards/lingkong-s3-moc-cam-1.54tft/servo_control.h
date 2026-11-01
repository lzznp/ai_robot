#ifndef SERVO_CONTROL_H
#define SERVO_CONTROL_H

#include <driver/ledc.h>
#include <driver/gpio.h>

class ServoControl {
public:
    void Init(gpio_num_t pin, ledc_channel_t channel = LEDC_CHANNEL_0);
    void SetAngle(int angle);

private:
    gpio_num_t pin_;
    ledc_channel_t channel_;
};

#endif