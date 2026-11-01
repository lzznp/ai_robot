# dooirobot 源码分析 — 完整度与复用评估

**日期**: 2026-06-29
**项目**: `D:\study\ai_robot\dooirobot`

---

## 1. 源码完整度分析

### 1.1 文件分类清单

#### A. 硬件驱动类（7 对文件 = 14 个）

| 文件 | 功能 | 完整度 | 备注 |
|---|---|---|---|
| `app_servo.c/h` | 舵机 PWM 控制 | ✅ 完整 | 通用舵机驱动 |
| `app_motor.c/h` | 双电机差速控制 | ✅ 完整 | 履带机器人专用 |
| `app_led.c/h` | WS2812 RGB LED 控制 | ✅ 完整 | 通用 WS2812 驱动 |
| `app_imu.c/h` | BMI260 IMU 姿态检测 | ✅ 完整 | 含倾斜检测 |
| `imu_bmi260.c/h` | BMI260 传感器驱动 | ✅ 完整 | 寄存器级驱动 |
| `ir.c/h` | 红外传感器 | ✅ 完整 | Doly 头部红外 |
| `power_manager.c/h` | 电池管理 | ✅ 完整 | 充放电检测 |

#### B. UI/显示类（7 个文件）

| 文件 | 功能 | 完整度 | 备注 |
|---|---|---|---|
| `dooi_display.h/cc` | Doly 显示适配 | ✅ 完整 | 继承 `LvglDisplay`，含 `SetEmotion` 实现 |
| `display_hal.c/h` | 双屏硬件抽象 | ✅ 完整 | Doly 双屏初始化 |
| `app_ui.c/h` | 屏幕管理器 | ✅ 完整 | 多屏幕切换、空闲超时 |
| `ui_emoji.c` | **21 种 LVGL 表情*** | ✅ 完整 | 纯算法，**无硬件依赖** |
| `ui_wakeup_ack.c` | 唤醒确认 UI | ✅ 完整 | Doly 特定 |
| `lv_font_notosans_cs_medium_14.c` | LVGL 字体 | ✅ 完整 | 开源字体 |

#### C. 业务逻辑类（4 个文件）

| 文件 | 功能 | 完整度 | 备注 |
|---|---|---|---|
| `app_action_seq.c/h` | 动作序列引擎 | ✅ **完整** | 独立 FreeRTOS 任务，**可复用** |
| `app_ui_logic.c/h` | 事件驱动状态机 | ✅ 完整 | **可参考**设计模式 |
| `app_mcp_tool.cc/h` | MCP 工具注册 | ✅ 完整 | JSON→动作解析，**可复用** |
| `app_periphral.c/h` | 外设初始化 | ✅ 完整 | Doly 引脚配置 |

#### D. 主程序类（3 个文件）

| 文件 | 功能 | 完整度 | 备注 |
|---|---|---|---|
| `dooirobot.cc` | 板卡定义 | ✅ 完整 | 继承 `WifiBoard`，使用 xiaozhi 框架 |
| `dooi_audio_codec.c/h` | 音频编解码 | ✅ 完整 | ES8311+ES7243E 双芯片 |
| `dooi_camera.cc/h` | 摄像头 | ✅ 完整 | OV5647 MIPI CSI |

#### E. 配置类（2 个文件）

| 文件 | 功能 | 完整度 | 备注 |
|---|---|---|---|
| `config.h` | 引脚定义 | ✅ 完整 | Doly ESP32-P4 引脚 |
| `config.json` | SDK 配置 | ✅ 完整 | 含 ESP-Hosted (WiFi offload) 等 |

### 1.2 缺失的关键文件

| 缺失文件 | 重要性 | 影响 |
|---|---|---|
| **`CMakeLists.txt`** | 🔴 **致命** | 不能独立编译。必须依赖 xiaozhi 框架的 `main/CMakeLists.txt` |
| `partitions.csv` | 🟡 重要 | 存在 `partitions/32m.csv` 但未与 CMake 关联 |
| `Kconfig.projbuild` | 🟡 重要 | 无自定义 Kconfig 配置 |
| `sdkconfig` / `sdkconfig.defaults` | 🟡 重要 | `config.json` 提供等效配置，但非标准格式 |
| `main.cc` / `app_main.cpp` | 🟢 可有可无 | Doly 继承 `WifiBoard`，由 xiaozhi 框架提供 |
| `lvgl_display.h` / `gfx.h` | 🔴 **外部依赖** | 这些文件不在 dooirobot 目录中，属于 xiaozhi 框架 |

### 1.3 外部依赖分析

dooirobot **不能独立编译**，它依赖 xiaozhi 固件框架（`esp32-firmware/main/`）：

```cpp
// dooirobot.cc 的外部引用：
#include "wifi_board.h"        // ← xiaozhi 框架
#include "codecs/..."          // ← xiaozhi 框架
#include "display/display.h"   // ← xiaozhi 框架
#include "display/lcd_display.h"
#include "application.h"       // ← xiaozhi 框架
#include "lvgl_display.h"      // ← xiaozhi 框架（DooiDisplay 继承）
```

| 外部组件 | 所属项目 | 是否已提供 |
|---|---|---|
| `wifi_board.h`, `board.h` | xiaozhi 框架 | ❌ dooirobot 目录中没有 |
| `application.h` | xiaozhi 框架 | ❌ |
| `display.h`, `lcd_display.h` | xiaozhi 框架 | ❌ |
| `lvgl_display.h` | xiaozhi 框架 | ❌ |
| `codecs/es8311_audio_codec.h` | xiaozhi 框架 | ❌ |
| `mcp_server.h` | xiaozhi 框架 | ❌ |
| `button.h` | xiaozhi 框架 | ❌ |

**结论**：dooirobot 是 xiaozhi 框架的一个**板级插件**，不是独立项目。

---

## 2. 表情系统完整调用链

```
服务端 → {"type":"llm","emotion":"happy"}
    │
    ▼
application.cc → display->SetEmotion("happy")        [xiaozhi 框架]
    │
    ▼
dooi_display.cc → DooiDisplay::SetEmotion("happy")   [dooirobot]
    │
    ▼  (经由 app_ui_logic 事件队列)
    │
app_ui_logic.c → APP_EVT_CHAT_MESSAGE / APP_EVT_STATE_SPEAKING
    │
    ▼  (事件处理 → LED + 舵机 + 屏幕)
    │
    ├── app_led_set_breathing(...)                     ← 呼吸灯
    ├── app_servo_set_target_angle(...)                 ← 舵机动作
    └── screen_set_current(SCREEN_EMOJI)               ← 切换到表情屏
          │
          ▼
        emoji_load() → create_eye(左眼) + create_eye(右眼)  [ui_emoji.c]
          │
          ▼
        ui_emoji_set_expression("happy")
          │  (仅标记 needs_refresh = true, 线程安全)
          ▼
        emoji_update() → render_emoji_logic(EMOJI_HAPPY)
          │  (在 LVGL timer 中执行)
          ▼
        anim_eye_to_state(left, {w=65, h=50, ...}, 300ms)
        anim_eye_to_state(right, {w=65, h=50, ...}, 330ms)
          │  lv_anim_path_overshoot (Q弹曲线)
          ▼
        LVGL 硬件渲染 → 屏幕显示
```

### 2.1 谁调用 ui_emoji_set_expression()

**调用方搜索**（仅在 dooirobot 范围内）：

| 调用位置 | 文件 | 触发条件 |
|---|---|---|
| `emoji_on_key_event()` | `ui_emoji.c:344` | 物理按键测试（循环切换所有表情） |
| 通过 `app_ui.h` API | `app_ui.h` 声明 | 未搜索到其他直接调用 |

### 2.2 表情与 TTS 的联动

dooirobot 的表情系统**不直接**与 TTS 语音播报联动。表情的触发路径是：

```
TTS 播报 → 服务端发 {"type":"llm","emotion":"happy"}
  → 固件 application.cc 处理
  → display->SetEmotion("happy")
  → DooiDisplay::SetEmotion()  → 表情切换
```

表情切换**不等待** TTS 语音播放完成或开始，两者是独立的。

### 2.3 表情与 LED/舵机的联动

在 `app_ui_logic.c` 中：

```c
static void on_state_listening(const app_event_t *evt) {
    app_led_set_breathing(0x0080FF, 2000, true);   // LED 呼吸
    app_servo_set_target_angle(SERVO_TARGET_BOTH, 135, 1500); // 舵机
}

static void on_state_speaking(const app_event_t *evt) {
    // 仅切换状态，表情由 service 端独立控制
    set_conv_state(APP_EVT_STATE_SPEAKING);
}
```

LED 和舵机由**对话状态**（Listening/Speaking/Standby）触发，不是由具体表情驱动。

---

## 3. 商业秘密级别评估

### 3.1 通用技术（无可争议的开源/标准做法）

| 代码 | 说明 | 复用建议 |
|---|---|---|
| LVGL 表情参数表（21 种 5 维参数） | **公开表情设计的数学表达**，非核心算法 | ✅ **可直接复制** |
| `lv_anim_path_overshoot` 曲线 | LVGL 标准 API | ✅ **可直接使用** |
| `app_action_seq.h` 数据结构 | 动作序列的 C 结构体定义 | ✅ **可直接复制** |
| 宏定义 `DEFINE_SEQUENCE`, `ACT_SERVO` 等 | 编译期代码生成手法 | ✅ **可直接复制** |
| MCP 工具 JSON 解析 | 标准 JSON→结构体的数据映射 | ✅ **可直接参考** |
| 双屏初始化 | 标准 SPI + LVGL 初始化流程 | ✅ **可直接参考** |

### 3.2 产品特定实现（需修改才能复用）

| 代码 | 说明 | 复用建议 |
|---|---|---|
| `app_servo.c` | Doly 舵机 IO 引脚和 PWM 参数 | ⏩ **参考算法，替换引脚** |
| `app_motor.c` | 履带底盘差速控制 | ⏩ **参考 API 设计，替换驱动** |
| `app_led.c` | WS2812 RGB LED | ⏩ **通用 WS2812，可直接复用** |
| `app_ui.c` | Doly 屏幕管理器 | ⏩ **参考多屏切换逻辑** |
| `app_periphral.c` | 外设引脚初始化 | ⏩ **参考初始化顺序** |

### 3.3 可能含未公开协议/保密信息

| 代码 | 风险点 |
|---|---|
| `config.json` | 含 ESP-Hosted (WiFi offload to ESP32-C6) 配置 — **产品架构细节** |
| `dooi_camera.cc` | OV5647 MIPI CSI 配置 — 可能含特定调试参数 |
| `imu_bmi260_config.h` | BMI260 寄存器配置 — 可能含自家校准参数 |

### 3.4 整体评估

| 维度 | 结论 |
|---|---|
| **更像技术参考还是完整产品代码** | **技术参考 + 产品代码的混合体** |
| | 它能编译运行（依赖 xiaozhi 框架时），但缺少独立构建能力 |
| **版权风险** | 中低风险。核心算法（表情参数、动作序列）属于标准 LVGL/C 技术 |
| **复用时最大风险** | 1. `config.json` 含 WiFi offload 架构细节（可能含未公开协议） |
| | 2. 动作序列引擎与 Doly 特定硬件耦合，难以直接复用 |

---

## 4. 复用建议

### 4.1 可直接安全复用的部分

| 组件 | 提取位置 | 使用方式 |
|---|---|---|
| **21 种表情 5 维参数表** | `ui_emoji.c:105-200` | 复制到新的 `.cc` 文件，替换 `set_screen` 和 `create_eye` |
| **Q弹动画引擎** | `ui_emoji.c:71-102` | 复制 `anim_eye_to_state()` 函数 |
| **表情枚举和名称映射** | `ui_emoji.c:17-53` | 复制 `emoji_type_t` 和 `emoji_names[]` |
| **自动眨眼逻辑** | `ui_emoji.c:288-327` | 复制眨眼算法 |
| **动作序列数据结构** | `app_action_seq.h:12-70` | 复制类型定义和宏 |
| **MCP 工具 JSON 解析器** | `app_mcp_tool.cc:28-168` | 复制 10 种动作类型的 JSON→struct 解析 |
| **事件驱动状态机模式** | `app_ui_logic.c` | **参考设计**，不要直接复制代码 |

### 4.2 可参考但不直接复用的设计

| 设计 | 说明 | 适配方式 |
|---|---|---|
| 动作序列引擎 | FreeRTOS 任务 + 消息队列 + Handler 表 | 保留架构，替换 Handler |
| 状态机事件驱动 | `app_ui_logic_post()` 事件队列 | 保留接口设计，替换业务逻辑 |
| 多屏管理器 | `app_ui.c` 的 `screen_manager` | 保留概念，重写实现 |
| MCP 工具注册 | `app_mcp_tool.cc:172-273` 的 `AddTool` 模式 | 保留调用方式，修改工具内容 |

### 4.3 确认不使用的部分（Doly 独占）

| 文件 | 理由 |
|---|---|
| `dooirobot.cc` | Doly ESP32-P4 引脚和摄像头配置 |
| `dooi_audio_codec.cc` | ES8311+ES7243E 双芯片音频 |
| `dooi_camera.cc` | OV5647 MIPI CSI |
| `imu_bmi260.*` | BMI260 传感器 |
| `ir.*` | Doly 头部红外 |
| `power_manager.*` | Doly 电池管理 |
| `config.json` | ESP-Hosted WiFi offload 架构 |

### 4.4 当前已有代码 vs dooirobot 差距

| 功能 | 你已有的 | dooirobot 提供的 | 差距 |
|---|---|---|---|
| 表情系统 | GFX EAF 动画 + emote.json | **LVGL 纯软件 21 种表情** | ✅ 已互补移植 |
| 动作序列 | 固件中无独立动作引擎 | 完整 FreeRTOS 动作序列引擎 | 可复用数据结构 + 宏 |
| 状态机 | `SetDeviceState()` switch-case | 事件驱动 + 状态处理器注册表 | 可参考设计 |
| MCP 工具 | 基础 `McpServer` 框架 | 自定义动作工具 complete | 可复用 JSON 解析 |
| 眼动动画 | 无 | 5 维参数 + Q弹 + 自动眨眼 | ✅ 已移植 |
