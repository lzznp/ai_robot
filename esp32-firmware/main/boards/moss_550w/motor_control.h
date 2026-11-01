// ============================================================
// 步进电机控制 - 头文件
// 驱动芯片: 74HC595 + ULN2003
// 电机型号: 24BYJ48 (四相八拍)
// ============================================================

#ifndef MOTOR_CONTROL_H
#define MOTOR_CONTROL_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// 电机编号
#define MOTOR_1     0
#define MOTOR_2     1

// 旋转方向
#define MOTOR_CW    0   // 顺时针
#define MOTOR_CCW   1   // 逆时针

// ============================================================
// API 函数
// ============================================================

// 初始化步进电机控制
void motor_control_init(void);

// 设置电机速度 (步数/秒)
void motor_set_speed(uint8_t motor_id, uint16_t steps_per_sec);

// 电机持续旋转
void motor_rotate(uint8_t motor_id, uint8_t direction);

// 电机停止
void motor_stop(uint8_t motor_id);

// 电机步进指定步数 (阻塞)
void motor_step(uint8_t motor_id, uint8_t direction, uint16_t steps);

// 释放电机 (所有相断电)
void motor_release(uint8_t motor_id);

// 紧急停止 (两个电机同时停止)
void motor_emergency_stop(void);

// 电机状态查询
uint8_t motor_is_running(uint8_t motor_id);
uint16_t motor_get_position(uint8_t motor_id);

#ifdef __cplusplus
}
#endif

#endif // MOTOR_CONTROL_H