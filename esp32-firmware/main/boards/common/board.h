#ifndef BOARD_H
#define BOARD_H

#include <http.h>
#include <web_socket.h>
#include <mqtt.h>
#include <udp.h>
#include <string>
#include <network_interface.h>

#include "led/led.h"
#include "backlight.h"
#include "camera.h"
#include "assets.h"


void* create_board();
class AudioCodec;
class Display;
class Board {
private:
    Board(const Board&) = delete; // 禁用拷贝构造函数
    Board& operator=(const Board&) = delete; // 禁用赋值操作

protected:
    Board();
    std::string GenerateUuid();

    // 软件生成的设备唯一标识
    std::string uuid_;

public:
    static Board& GetInstance() {
        static Board* instance = static_cast<Board*>(create_board());
        return *instance;
    }

    virtual ~Board() = default;
    virtual std::string GetBoardType() = 0;
    virtual std::string GetUuid() { return uuid_; }
    virtual Backlight* GetBacklight() { return nullptr; }
    virtual Led* GetLed();
    virtual AudioCodec* GetAudioCodec() = 0;
    virtual bool GetTemperature(float& esp32temp);
    virtual Display* GetDisplay();
    virtual Camera* GetCamera();
    virtual NetworkInterface* GetNetwork() = 0;
    virtual void StartNetwork() = 0;
    virtual const char* GetNetworkStateIcon() = 0;
    virtual bool GetBatteryLevel(int &level, bool& charging, bool& discharging);
    virtual std::string GetSystemInfoJson();
    virtual void SetPowerSaveMode(bool enabled) = 0;
    virtual std::string GetBoardJson() = 0;
    virtual std::string GetDeviceStatusJson() = 0;

    // ============================================================
    // ★ 运动控制接口（默认空实现，不影响其他板子）
    // 子类可以重写这些方法来实现具体的运动功能
    // ============================================================
    virtual void MoveForward() {}
    virtual void MoveBackward() {}
    virtual void TurnLeft() {}
    virtual void TurnRight() {}
    virtual void Stop() {}
    virtual void Wave() {}
    virtual void SetServoAngle(int angle) {}

    // ============================================================
    // ★ 步进电机（芯片级，2026-11-01）
    //
    // 为什么不能走 gpio/pwm：步进要**相序 + 串行移位**（MOSS 是 74HC595 + ULN2003），
    // 一步 = 26 次电平操作、16ms 内做完；靠后台发 gpio 动作既跟不上节拍，
    // 又会踩掉 595 上与另一台电机共享的半个字节。跟 ws2812 是同一类问题。
    //
    // 参数（全部是硬件事实，不含“左转/前进”这类语义）：
    //   motor      : 第几路（0 = 第 1 路，1 = 第 2 路）
    //   steps      : 步数，**带符号**：正 = 一个方向，负 = 反方向
    //   speed_hz   : 每秒多少步
    //   hold_torque: 走完是否保持力矩（悬挂机构怕重力下垂就 true；发热就 false）
    //
    // 要求：**非阻塞**（把命令丢给驱动就返回）。等它走完由应用层的延时机制处理。
    // ============================================================
    virtual void StepMotor(int motor, int steps, int speed_hz, bool hold_torque) {}
};

#define DECLARE_BOARD(BOARD_CLASS_NAME) \
void* create_board() { \
    return new BOARD_CLASS_NAME(); \
}

#endif // BOARD_H