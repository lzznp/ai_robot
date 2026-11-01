#ifndef UI_EMOJI_DUALEYE_H
#define UI_EMOJI_DUALEYE_H

#ifdef __cplusplus
extern "C" {
#endif

#include <lvgl.h>

/**
 * @brief 初始化双屏 LVGL 表情系统
 * @param disp_left  左显示屏（显示左眼）
 * @param disp_right 右显示屏（显示右眼）
 */
void ui_emoji_init(lv_disp_t *disp_left, lv_disp_t *disp_right);

/**
 * @brief 切换表情（线程安全）
 * @param name 表情名称，如 "happy", "sad", "angry" 等
 */
void ui_emoji_set_expression(const char *name);

/**
 * @brief 表情刷新（应在 LVGL timer 中周期性调用）
 */
void ui_emoji_update(void);

#ifdef __cplusplus
}
#endif

#endif