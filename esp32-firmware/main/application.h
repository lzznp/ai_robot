#ifndef _APPLICATION_H_
#define _APPLICATION_H_

#include <freertos/FreeRTOS.h>
#include <freertos/event_groups.h>
#include <freertos/task.h>
#include <esp_timer.h>

#include <string>
#include <mutex>
#include <deque>
#include <queue>
#include <memory>
#include <functional>

#include "protocol.h"
#include "ota.h"
#include "audio_service.h"
#include "device_state_event.h"


#define MAIN_EVENT_SCHEDULE (1 << 0)
#define MAIN_EVENT_SEND_AUDIO (1 << 1)
#define MAIN_EVENT_WAKE_WORD_DETECTED (1 << 2)
#define MAIN_EVENT_VAD_CHANGE (1 << 3)
#define MAIN_EVENT_ERROR (1 << 4)
#define MAIN_EVENT_CHECK_NEW_VERSION_DONE (1 << 5)
#define MAIN_EVENT_CLOCK_TICK (1 << 6)


enum AecMode {
    kAecOff,
    kAecOnDeviceSide,
    kAecOnServerSide,
};

// ============================================================
// ★ 新增：任务项结构（用于任务队列）
// ============================================================
struct TaskItem {
    std::string type;        // "tts", "gpio", "pwm", "servo", "move", "delay", "emotion"
    std::string text;        // TTS 文本
    std::string emotion;     // 表情
    int gpio_pin = -1;
    int gpio_level = 0;
    int duration_ms = 0;     // 延时毫秒 / 移动持续时间 / gpio、pwm 的保持时长
    int servo_angle = 0;
    std::string move_dir;    // forward/backward/left/right/stop

    /* ---- 引脚级 PWM：芯片级通用动作，与具体板子无关 ----
     * 一组字段覆盖两种用法：
     *   脉宽模式（舵机）：pwm_use_duty = false，用 pwm_pulse_us 换算占空比
     *   占空比模式（调速）：pwm_use_duty = true，用 pwm_duty_pct
     * "前进""挥手"这类**语义**不在这里，由后台能力库定义成一串指令流。 */
    int  pwm_pin = -1;
    int  pwm_freq_hz = 50;
    int  pwm_pulse_us = 0;
    int  pwm_duty_pct = 0;
    bool pwm_use_duty = false;

    /* ---- 芯片级 WS2812 灯带 ----
     * 为什么必须单独一个动作：WS2812 不吃"电平"，它要 800kHz 的串行数据流，
     * gpio/pwm 都点不亮它。同样只给硬件事实（哪个脚、几颗、什么颜色），
     * 不给"开灯/关灯/呼吸"这类语义 —— 语义归后台能力库。 */
    int  ws_pin = -1;          // 数据线引脚
    int  ws_count = 1;         // 灯珠数量
    int  ws_r = 0;             // 0~255
    int  ws_g = 0;
    int  ws_b = 0;

    /* ---- 摄像头（芯片级触发，不做语义）----
     * 为什么需要这个动作：MCP 的 self.camera.take_photo 必须由 LLM 主动调工具才触发，
     * 想单独验证"驱动能不能出图"就需要一个不依赖对话的入口。
     * op = "capture"（默认，只抓一帧）/ "explain"（抓帧并上传后台视觉接口）。 */
    std::string cam_op;

    /* ---- 步进电机（芯片级，2026-11-01）----
     * 只给硬件事实：第几路、走多少步、多快、走完是否保持力矩。
     * 不给"左转/抬头"这类语义 —— 语义归后台能力库。
     * 也不能用 gpio/pwm 代替：步进要 8 拍相序 + 74HC595 串行移位，
     * 一步 26 次电平操作、16ms 内完成（与 ws2812 同一类问题）。 */
    int  st_motor = 0;         // 0 = 第 1 路，1 = 第 2 路
    int  st_steps = 0;         // 带符号：正 = CW，负 = CCW
    int  st_speed_hz = 60;     // 每秒步数
    bool st_hold = false;      // 走完是否保持力矩（对应 JSON 的 release 取反）
};

class Application {
public:
    static Application& GetInstance() {
        static Application instance;
        return instance;
    }
    // 删除拷贝构造函数和赋值运算符
    Application(const Application&) = delete;
    Application& operator=(const Application&) = delete;

    void Start();
    void MainEventLoop();
    DeviceState GetDeviceState() const { return device_state_; }
    bool IsVoiceDetected() const { return audio_service_.IsVoiceDetected(); }
    void Schedule(std::function<void()> callback);
    void SetDeviceState(DeviceState state);
    void Alert(const char* status, const char* message, const char* emotion = "", const std::string_view& sound = "");
    void DismissAlert();
    void AbortSpeaking(AbortReason reason);
    void ToggleChatState();
    void StartListening();
    void StopListening();
    void Reboot();
    void WakeWordInvoke(const std::string& wake_word);
    bool UpgradeFirmware(Ota& ota, const std::string& url = "");
    bool CanEnterSleepMode();
    void SendMcpMessage(const std::string& payload);
    void SetAecMode(AecMode mode);
    AecMode GetAecMode() const { return aec_mode_; }
    void PlaySound(const std::string_view& sound);
    AudioService& GetAudioService() { return audio_service_; }

private:
    Application();
    ~Application();

    std::mutex mutex_;
    std::deque<std::function<void()>> main_tasks_;
    std::unique_ptr<Protocol> protocol_;
    EventGroupHandle_t event_group_ = nullptr;
    esp_timer_handle_t clock_timer_handle_ = nullptr;
    volatile DeviceState device_state_ = kDeviceStateUnknown;
    ListeningMode listening_mode_ = kListeningModeAutoStop;
    AecMode aec_mode_ = kAecOff;
    std::string last_error_message_;
    AudioService audio_service_;

    bool has_server_time_ = false;
    bool aborted_ = false;
    int clock_ticks_ = 0;
    TaskHandle_t check_new_version_task_handle_ = nullptr;
    TaskHandle_t main_event_loop_task_handle_ = nullptr;

    // ============================================================
    // ★ 新增：任务队列相关
    // ============================================================
    std::queue<TaskItem> task_queue_;
    bool task_running_ = false;
    esp_timer_handle_t task_timer_handle_ = nullptr;

    void OnWakeWordDetected();
    void CheckNewVersion(Ota& ota);
    void CheckAssetsVersion();
    void ShowActivationCode(const std::string& code, const std::string& message);
    void SetListeningMode(ListeningMode mode);

    // ============================================================
    // ★ 新增：Command 指令执行器
    // ============================================================
    void ExecuteCommand(cJSON* payload);
    void PlayTtsDirectly(const std::string& text);
    void AppendTask(const TaskItem& task);
    void ProcessNextTask();
    void ExecuteTask(const TaskItem& task);
    void StartTaskTimer();
    void StopTaskTimer();
    void ProcessNextTaskAfterDelay(int delay_ms);
    static void TaskTimerCallback(void* arg);
};


class TaskPriorityReset {
public:
    TaskPriorityReset(BaseType_t priority) {
        original_priority_ = uxTaskPriorityGet(NULL);
        vTaskPrioritySet(NULL, priority);
    }
    ~TaskPriorityReset() {
        vTaskPrioritySet(NULL, original_priority_);
    }

private:
    BaseType_t original_priority_;
};

#endif // _APPLICATION_H_