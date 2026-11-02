// ============================================================
// selftest.h — 元件自检框架（板子无关的引擎）
//
// 为什么要有这一层：
//   判定"元件/接线坏没坏"和判定"整机能不能连服务器"是两件事。
//   应用层固件（WiFi→后台→设备在线）会把任何元件问题淹没成"连不上"。
//   本框架只依赖串口，所以任何一项失败都只可能是:
//     ① 接线  ② 器件  ③ 引脚定义写错
//
// 分工（三台共用同一套引擎）：
//   本组件  : 交互（BOOT 键换项/执行）+ 通用打印/扫描助手
//   各板文件: boards/<板>/selftest_items.c —— 只写"这张板有哪些项、每项干什么"
//
// 用法:
//   1. config.h 里 <板>_SELFTEST = 1
//   2. idf.py -p COMx flash monitor
//   3. BOOT 键单击换项，长按执行
// ============================================================

#ifndef ST_SELFTEST_H
#define ST_SELFTEST_H

#ifdef __cplusplus
extern "C" {
#endif

// 一个自检项：标题（不带序号，序号由引擎打印）+ 执行函数
// 执行函数返回 void：判据由人看串口文字判定（每项必须打印"看到什么算通过"）
typedef struct {
    const char *title;
    void (*run)(void);
} st_item_t;

// 一张板的自检配置
typedef struct {
    const char *board_name;     // 打印在横幅上
    int boot_gpio;              // 交互按键（按下为低、内部上拉）
    const st_item_t *items;     // 项表
    int item_count;             // 项数（序号打印成 x/item_count）
} st_config_t;

/**
 * 进入自检循环。**不会返回**。
 *  副作用：不启动 Application（WiFi / WebSocket / 音频都不初始化）
 *  交互：单击（<800ms）= 下一项；长按（>=800ms）= 执行当前项
 */
void st_run(const st_config_t *cfg);

#ifdef __cplusplus
}
#endif

#endif  // ST_SELFTEST_H
