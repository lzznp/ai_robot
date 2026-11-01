#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include <lvgl.h>
#include "ui_emoji_dualeye.h"

/* --- 颜色与基础尺寸定义 --- */
#define EMOJI_COLOR            lv_color_hex(0x00E5FF) // Nomi 科技青
#define PAGE_BG_COLOR          0x000000
#define EYE_DEFAULT_W          60
#define EYE_DEFAULT_H          100
#define EYE_RADIUS_MAX         100

typedef enum {
    EMOJI_NEUTRAL, EMOJI_HAPPY, EMOJI_LAUGHING, EMOJI_FUNNY, EMOJI_SAD,
    EMOJI_ANGRY, EMOJI_CRYING, EMOJI_LOVING, EMOJI_EMBARRASSED, EMOJI_SURPRISED,
    EMOJI_SHOCKED, EMOJI_THINKING, EMOJI_WINKING, EMOJI_COOL, EMOJI_RELAXED,
    EMOJI_DELICIOUS, EMOJI_KISSY, EMOJI_CONFIDENT, EMOJI_SLEEPY, EMOJI_SILLY,
    EMOJI_CONFUSED, EMOJI_MAX
} emoji_type_t;

typedef struct {
    int32_t w;
    int32_t h;
    int32_t angle;   // 旋转 (0.1度)
    int32_t x_ofs;   // X轴偏移
    int32_t y_ofs;   // Y轴偏移
} eye_state_t;

typedef struct {
    lv_obj_t *eye_obj;
    eye_state_t current_state;
} eye_widgets_t;

static struct {
    eye_widgets_t left;
    eye_widgets_t right;
    char current_emoji_name[32];
    emoji_type_t target_type;
    bool needs_refresh;
} emoji_ctx = {0};

static SemaphoreHandle_t s_emoji_mutex = NULL;

static const char* emoji_names[] = {
    "neutral", "happy", "laughing", "funny", "sad", "angry", "crying", "loving",
    "embarrassed", "surprised", "shocked", "thinking", "winking", "cool", "relaxed",
    "delicious", "kissy", "confident", "sleepy", "silly", "confused"
};

/* --- 动画回调 --- */
static void anim_w_cb(void *var, int32_t v) {
    if (v < 6) v = 6;
    lv_obj_set_width((lv_obj_t *)var, v);
    lv_obj_set_style_transform_pivot_x((lv_obj_t *)var, v / 2, 0);
}
static void anim_h_cb(void *var, int32_t v) {
    if (v < 6) v = 6;
    lv_obj_set_height((lv_obj_t *)var, v);
    lv_obj_set_style_transform_pivot_y((lv_obj_t *)var, v / 2, 0);
}
static void anim_angle_cb(void *var, int32_t v) { lv_obj_set_style_transform_rotation((lv_obj_t *)var, v, 0); }
static void anim_x_cb(void *var, int32_t v) { lv_obj_set_style_translate_x((lv_obj_t *)var, v, 0); }
static void anim_y_cb(void *var, int32_t v) { lv_obj_set_style_translate_y((lv_obj_t *)var, v, 0); }

/* --- Q弹动画引擎 --- */
static void anim_eye_to_state(eye_widgets_t *eye_data, eye_state_t target, uint32_t time_ms, uint32_t delay_ms) {
    if (!eye_data || !eye_data->eye_obj) {
        ESP_LOGW("EmojiDualEye", "⚠️ anim_eye_to_state: eye_data or eye_obj is NULL");
        return;
    }
//    ESP_LOGI("EmojiDualEye", "🔄 anim_eye_to_state: obj=%p, target={%d,%d,%d,%d,%d}, time=%dms, delay=%dms",
//        eye_data->eye_obj, target.w, target.h, target.angle, target.x_ofs, target.y_ofs, time_ms, delay_ms);


    if (!eye_data || !eye_data->eye_obj) return;
    lv_obj_t *obj = eye_data->eye_obj;
    eye_data->current_state = target;

    lv_anim_t a;
    lv_anim_init(&a);
    lv_anim_set_var(&a, obj);
    lv_anim_set_time(&a, time_ms);
    lv_anim_set_delay(&a, delay_ms);
    lv_anim_set_path_cb(&a, lv_anim_path_overshoot);

    lv_anim_set_values(&a, lv_obj_get_width(obj), target.w);
    lv_anim_set_exec_cb(&a, anim_w_cb);
    lv_anim_start(&a);

    lv_anim_set_values(&a, lv_obj_get_height(obj), target.h);
    lv_anim_set_exec_cb(&a, anim_h_cb);
    lv_anim_start(&a);

    lv_anim_set_values(&a, lv_obj_get_style_transform_rotation(obj, 0), target.angle);
    lv_anim_set_exec_cb(&a, anim_angle_cb);
    lv_anim_start(&a);

    lv_anim_set_values(&a, lv_obj_get_style_translate_x(obj, 0), target.x_ofs);
    lv_anim_set_exec_cb(&a, anim_x_cb);
    lv_anim_start(&a);

    lv_anim_set_values(&a, lv_obj_get_style_translate_y(obj, 0), target.y_ofs);
    lv_anim_set_exec_cb(&a, anim_y_cb);
    lv_anim_start(&a);
}

/* --- 表情状态映射表 --- */
static void render_emoji_logic(emoji_type_t type) {
    ESP_LOGI("EmojiDualEye", "🎨 render_emoji_logic 被调用, type=%d", type);
    eye_state_t l_state = {EYE_DEFAULT_W, EYE_DEFAULT_H, 0, 0, 0};
    eye_state_t r_state = {EYE_DEFAULT_W, EYE_DEFAULT_H, 0, 0, 0};
    uint32_t anim_time = 300;

    switch(type) {
        case EMOJI_HAPPY:
        case EMOJI_LAUGHING:
        case EMOJI_DELICIOUS:
            l_state = (eye_state_t){65, 50, 0, 0, -15};
            r_state = (eye_state_t){65, 50, 0, 0, -15};
            break;
        case EMOJI_ANGRY:
            l_state = (eye_state_t){45, 120, 400, 25, 15};
            r_state = (eye_state_t){45, 120, -400, -25, 15};
            anim_time = 200;
            break;
        case EMOJI_SAD:
        case EMOJI_CRYING:
            l_state = (eye_state_t){45, 110, -350, -15, 25};
            r_state = (eye_state_t){45, 110, 350, 15, 25};
            anim_time = 450;
            break;
        case EMOJI_SURPRISED:
            l_state = (eye_state_t){65, 120, 0, 0, -15};
            r_state = (eye_state_t){65, 120, 0, 0, -15};
            anim_time = 250;
            break;
        case EMOJI_SHOCKED:
            l_state = (eye_state_t){25, 25, 0, 0, 0};
            r_state = (eye_state_t){25, 25, 0, 0, 0};
            anim_time = 150;
            break;
        case EMOJI_COOL:
        case EMOJI_CONFIDENT:
            l_state = (eye_state_t){65, 55, 100, 0, 20};
            r_state = (eye_state_t){65, 55, 100, 0, 20};
            break;
        case EMOJI_FUNNY:
        case EMOJI_SILLY:
        case EMOJI_CONFUSED:
            l_state = (eye_state_t){40, 40, -150, 0, -10};
            r_state = (eye_state_t){75, 75, 150, 0, 10};
            break;
        case EMOJI_WINKING:
        case EMOJI_KISSY:
            l_state = (eye_state_t){60, 12, 0, 0, 15};
            r_state = (eye_state_t){65, 105, 0, 0, -10};
            break;
        case EMOJI_EMBARRASSED:
            l_state = (eye_state_t){50, 75, 0, 35, 15};
            r_state = (eye_state_t){50, 75, 0, 35, 15};
            break;
        case EMOJI_THINKING:
            l_state = (eye_state_t){55, 65, 0, 25, -25};
            r_state = (eye_state_t){55, 65, 0, 25, -25};
            break;
        case EMOJI_SLEEPY:
        case EMOJI_RELAXED:
            l_state = (eye_state_t){65, 12, 0, 0, 25};
            r_state = (eye_state_t){65, 12, 0, 0, 25};
            anim_time = 600;
            break;
        case EMOJI_LOVING:
            l_state = (eye_state_t){75, 90, 0, 0, 0};
            r_state = (eye_state_t){75, 90, 0, 0, 0};
            break;
        default:
            break;
    }

    anim_eye_to_state(&emoji_ctx.left, l_state, anim_time, 0);
    anim_eye_to_state(&emoji_ctx.right, r_state, anim_time, 30);
}

/* --- 创建眼睛对象 --- */
static void create_eye(lv_obj_t *parent, eye_widgets_t *eye, int x_offset) {
    lv_obj_t *cont = lv_obj_create(parent);
    lv_obj_set_size(cont, 240, 240);
    lv_obj_set_style_bg_opa(cont, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(cont, 0, 0);
    lv_obj_center(cont);
    lv_obj_clear_flag(cont, LV_OBJ_FLAG_SCROLLABLE);

    eye->eye_obj = lv_obj_create(cont);
    lv_obj_set_size(eye->eye_obj, EYE_DEFAULT_W, EYE_DEFAULT_H);
    lv_obj_set_style_radius(eye->eye_obj, EYE_RADIUS_MAX, 0);
    lv_obj_set_style_bg_color(eye->eye_obj, EMOJI_COLOR, 0);
    lv_obj_set_style_bg_opa(eye->eye_obj, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(eye->eye_obj, 0, 0);

    lv_obj_align(eye->eye_obj, LV_ALIGN_CENTER, x_offset, 0);
    lv_obj_set_style_transform_pivot_x(eye->eye_obj, EYE_DEFAULT_W / 2, 0);
    lv_obj_set_style_transform_pivot_y(eye->eye_obj, EYE_DEFAULT_H / 2, 0);

    eye->current_state = (eye_state_t){EYE_DEFAULT_W, EYE_DEFAULT_H, 0, 0, 0};
}

/* --- 外部 API：初始化 --- */
void ui_emoji_init(lv_disp_t *disp_left, lv_disp_t *disp_right) {
    // ★★★ 创建互斥量 ★★★
    if (s_emoji_mutex == NULL) {
        s_emoji_mutex = xSemaphoreCreateMutex();
        if (s_emoji_mutex == NULL) {
            ESP_LOGE("EmojiDualEye", "❌ 创建互斥量失败！");
            return;
        }
        ESP_LOGI("EmojiDualEye", "✅ 表情互斥量创建成功");
    }

    lv_obj_t *scr_left = lv_disp_get_scr_act(disp_left);
    lv_obj_t *scr_right = lv_disp_get_scr_act(disp_right);

    create_eye(scr_left, &emoji_ctx.left, -40);
    create_eye(scr_right, &emoji_ctx.right, 40);

    // ★ 设置大小 + 保存 current_state
    eye_state_t neutral = {60, 100, 0, 0, 0};

    emoji_ctx.left.current_state = neutral;
    emoji_ctx.right.current_state = neutral;

    lv_obj_set_width(emoji_ctx.left.eye_obj, 60);
    lv_obj_set_height(emoji_ctx.left.eye_obj, 100);
    lv_obj_set_width(emoji_ctx.right.eye_obj, 60);
    lv_obj_set_height(emoji_ctx.right.eye_obj, 100);

    // ★★★ 自测试：每隔 2 秒自动切换表情 ★★★
    static const char* test_emojis[] = {
        "neutral", "happy", "sad", "angry", "thinking",
        "sleepy", "shocked", "winking", "loving", "cool"
    };
    static const int emoji_count = sizeof(test_emojis) / sizeof(test_emojis[0]);

    lv_timer_create([](lv_timer_t* timer) {
        static int idx = 0;
        const char* emoji = test_emojis[idx % emoji_count];
        ESP_LOGI("EmojiDualEye", "🔄 自测试: 切换到 %s", emoji);
        ui_emoji_set_expression(emoji);
        idx++;
    }, 2000, NULL);  // 每 2 秒切换一次
}

/* --- 外部 API：切换表情 --- */
void ui_emoji_set_expression(const char* name) {

    ESP_LOGI("EmojiDualEye", "🎯 set_expression called: %s", name ? name : "null");

    if (name == NULL || s_emoji_mutex == NULL) return;


    // ★ 如果不在列表中，默认 "neutral"
    int idx = -1;
    for (int i = 0; i < EMOJI_MAX; i++) {
        if (strcmp(name, emoji_names[i]) == 0) {
            idx = i;
            break;
        }
    }
    if (idx < 0) {
        // 未知表情 → 静默 fallback 到 neutral
        name = "neutral";
        idx = EMOJI_NEUTRAL;
    }

    if (xSemaphoreTake(s_emoji_mutex, pdMS_TO_TICKS(100)) == pdTRUE) {
        strncpy(emoji_ctx.current_emoji_name, name, 31);
        emoji_ctx.target_type = (emoji_type_t)idx;
        emoji_ctx.needs_refresh = true;
        xSemaphoreGive(s_emoji_mutex);
        ESP_LOGI("EmojiDualEye", "Set expression: %s", name);
    }
}

/* --- 外部 API：更新（应在 LVGL 定时器中调用） --- */
void ui_emoji_update(void) {

    static int count = 0;
    if (++count % 100 == 0) {
        ESP_LOGI("EmojiDualEye", "🔄 ui_emoji_update running (count=%d)", count);
    }
    if (s_emoji_mutex == NULL) return;

    if (emoji_ctx.needs_refresh) {
        ESP_LOGI("EmojiDualEye", "🔄 检测到 needs_refresh，准备切换表情");
        emoji_type_t type = EMOJI_NEUTRAL;
        if (xSemaphoreTake(s_emoji_mutex, pdMS_TO_TICKS(10)) == pdTRUE) {
            type = emoji_ctx.target_type;
            emoji_ctx.needs_refresh = false;
            xSemaphoreGive(s_emoji_mutex);
        }
        ESP_LOGI("EmojiDualEye", "🎨 调用 render_emoji_logic, type=%d", type);
        render_emoji_logic(type);
        ESP_LOGI("EmojiDualEye", "✅ render_emoji_logic 执行完成");
    }

    /* 智能眨眼逻辑 */
    static uint32_t next_blink = 0;
    bool can_blink = (emoji_ctx.target_type != EMOJI_SLEEPY &&
                      emoji_ctx.target_type != EMOJI_RELAXED &&
                      emoji_ctx.target_type != EMOJI_SHOCKED &&
                      emoji_ctx.target_type != EMOJI_WINKING);

    if (can_blink && lv_tick_get() > next_blink) {
        lv_anim_t a;
        lv_anim_init(&a);

        lv_anim_set_time(&a, 100);
        lv_anim_set_path_cb(&a, lv_anim_path_ease_out);

        lv_anim_set_var(&a, emoji_ctx.left.eye_obj);
        lv_anim_set_values(&a, emoji_ctx.left.current_state.h, 8);
        lv_anim_set_exec_cb(&a, anim_h_cb);
        lv_anim_start(&a);

        lv_anim_set_var(&a, emoji_ctx.right.eye_obj);
        lv_anim_set_values(&a, emoji_ctx.right.current_state.h, 8);
        lv_anim_start(&a);

        lv_anim_set_time(&a, 250);
        lv_anim_set_delay(&a, 80);
        lv_anim_set_path_cb(&a, lv_anim_path_overshoot);

        lv_anim_set_var(&a, emoji_ctx.left.eye_obj);
        lv_anim_set_values(&a, 8, emoji_ctx.left.current_state.h);
        lv_anim_start(&a);

        lv_anim_set_var(&a, emoji_ctx.right.eye_obj);
        lv_anim_set_delay(&a, 100);
        lv_anim_set_values(&a, 8, emoji_ctx.right.current_state.h);
        lv_anim_start(&a);

        next_blink = lv_tick_get() + 2500 + (rand() % 3500);
    }

    // ★ 移除 lv_timer_handler()，由 LVGL 任务处理
}