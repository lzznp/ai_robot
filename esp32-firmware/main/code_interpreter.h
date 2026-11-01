#pragma once

#include <cJSON.h>
#include <functional>
#include <vector>

// 指令类型枚举
enum class OpCode {
    GPIO_WRITE,
    PWM_WRITE,
    DELAY,
    LOOP,
    I2C_WRITE,
    I2C_READ,
    UART_WRITE,
    CONDITION,
    GPIO_READ,
    ADC_READ,
};

// 单条指令结构
struct Instruction {
    OpCode op;
    std::vector<int> params;  // 参数列表，可变长度
};

class CodeInterpreter {
public:
    // 执行代码流（JSON 数组）
    static bool Execute(cJSON* steps_json);

    // 执行单条指令
    static bool ExecuteInstruction(const Instruction& inst);

private:
    // 各个指令的实现
    static bool GpioWrite(int pin, int value, int duration_ms);
    static bool PwmWrite(int pin, int value, int duration_ms);
    static bool Delay(int ms);
    static bool Loop(int times, cJSON* code_block);
    static bool I2cWrite(int addr, int reg, int value);
    // ... 其他指令
};