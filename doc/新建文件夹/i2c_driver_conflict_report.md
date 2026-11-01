# 侦察报告：I2C 驱动冲突分析

**项目**: esp32-firmware (MOSS 550W / ESP32-S3)
**问题**: 启动时 `CONFLICT! driver_ng is not allowed to be used with this old driver` 崩溃重启
**日期**: 2026-07-07

---

## 1. 新版 I2C 驱动使用情况 (driver_ng: `driver/i2c_master.h`)

新版驱动 API 包括：`i2c_master_bus_config_t`、`i2c_new_master_bus()`、`i2c_master_bus_handle_t`、`i2c_master_bus_add_device()`、`i2c_master_transmit()`。

### 板级支持文件（所有使用 `driver/i2c_master.h` 的 board）

| 文件 | 行号 | API |
|------|------|-----|
| `main/boards/moss_550w/board_moss_550w.cc` | 22, 168, 205-218 | `#include "driver/i2c_master.h"`, `i2c_master_bus_handle_t i2c_bus_`, `i2c_master_bus_config_t`, `i2c_new_master_bus()` |
| `main/boards/aipi-lite/aipi-lite.cc` | 29, 70, 83 | `i2c_master_bus_handle_t`, `i2c_master_bus_config_t`, `i2c_new_master_bus()` |
| `main/boards/atk-dnesp32s3/atk_dnesp32s3.cc` | 21, 49, 57, 69 | `i2c_master_bus_handle_t`, `i2c_master_bus_config_t`, `i2c_new_master_bus()` |
| `main/boards/atk-dnesp32s3-box/atk_dnesp32s3_box.cc` | 85, 131 | `i2c_master_bus_handle_t` |
| `main/boards/esp-sparkbot/esp_sparkbot_board.cc` | 46, 54, 66 | `i2c_master_bus_handle_t`, `i2c_master_bus_config_t`, `i2c_new_master_bus()` |
| `main/boards/esp-spot-s3/esp_spot_s3_board.cc` | 28, 40, 52 | `i2c_master_bus_handle_t`, `i2c_master_bus_config_t`, `i2c_new_master_bus()` |
| `main/boards/esp-s3-lcd-ev-board-2/esp-s3-lcd-ev-board-2.cc` | 27, 130, 142 | 同上 |
| 其他所有 ESP32-S3 板级文件 | 各处 | 均使用 `driver/i2c_master.h`（新版） |

### 音频编解码器

| 文件 | 行号 | API |
|------|------|-----|
| `main/audio/codecs/box_audio_codec.cc` | 4 | `#include <driver/i2c_master.h>` |
| `main/audio/codecs/es8311_audio_codec.h` | 6 | `#include <driver/i2c_master.h>` |
| `main/audio/codecs/es8388_audio_codec.h` | 6 | `#include <driver/i2c_master.h>` |

### 公用设备层

| 文件 | 行号 | API |
|------|------|-----|
| `main/boards/common/i2c_device.h` | 3 | `#include <driver/i2c_master.h>`, `i2c_master_bus_handle_t` |
| `main/boards/common/i2c_device.cc` | 11-12, 17-18, 24 | `i2c_master_bus_add_device()`, `i2c_master_transmit()`, `i2c_master_transmit_receive()` |

---

## 2. 旧版 I2C 驱动使用情况 (old driver: `driver/i2c.h`)

旧版驱动 API 包括：`i2c_master_write_to_device()`（取端口号）、`i2c_driver_install()`、`i2c_param_config()`。

### MOSS 550W 相关

| 文件 | 行号 | API | 作用 |
|------|------|-----|------|
| `main/u8g2_esp32.c` | 2 | `#include "driver/i2c.h"` | **关键冲突源** |
| `main/u8g2_esp32.c` | 23-28 | `i2c_master_write_to_device(I2C_MASTER_NUM, addr, data, arg_int, ...)` | **关键冲突源** — 使用旧版 API 通过端口号发送数据 |

### 其他 board 中的旧版驱动引用（非 MOSS 550W）

| 文件 | 行号 | API |
|------|------|-----|
| `main/boards/waveshare-s3-dualeye-lcd-1.28/esp32-s3-dualeye-lcd-1.28.cc` | 11 | `#include <driver/i2c.h>` |
| `main/boards/icam-x-mini-4g/icam-x-mini-4g.cc` | 13 | `#include <driver/i2c.h>` |

### 音频编解码器（仅头文件包含，实际 I2C 通过 esp_codec_dev 完成）

| 文件 | 行号 | 备注 |
|------|------|------|
| `main/audio/codecs/es8374_audio_codec.h` | 6 | `#include <driver/i2c.h>` — 仅头文件引用，未在 MOSS 使用 |
| `main/audio/codecs/es8389_audio_codec.h` | 6 | `#include <driver/i2c.h>` — 仅头文件引用，未在 MOSS 使用 |

### managed_components 中的旧版驱动使用（测试代码）

| 文件 | 行号 | API |
|------|------|-----|
| `managed_components/wvirgil123__sscma_client/src/sscma_client_io_i2c.c` | 14 | `#include "driver/i2c.h"` |
| 同上 | 132, 150, 183, 205, 238, 271 | `i2c_master_write_to_device()` 旧版风格 |
| `managed_components/espressif__esp_codec_dev/test_apps/codec_dev_test/main/test_board.c` | 82, 86 | `i2c_param_config()`, `i2c_driver_install()` |
| 其他 test_apps | 各处 | 测试用例使用旧版 API |

---

## 3. 冲突分析结论

### 冲突源

**`u8g2_esp32.c`** 是导致 MOSS 550W 板子启动崩溃的根本原因。

### 详细原因

```
Moss550WBoard 构造函数调用顺序：
  1. InitGpio()
  2. InitI2c()      ← 使用 driver/i2c_master.h (新版) → i2c_new_master_bus() → I2C_NUM_0 ✅ 成功
  3. InitAdc()
  4. InitDisplay()  → U8g2Display()
       → u8g2_InitDisplay()
         → u8g2_esp32_i2c_tx()   ← 使用 driver/i2c.h (旧版)
           → i2c_master_write_to_device(I2C_MASTER_NUM, ...) → 检测到 I2C_NUM_0 
             已被新版驱动占用 → CONFLICT! abort()
```

- `board_moss_550w.cc` 第 22 行：`#include "driver/i2c_master.h"`（新版驱动）
- `board_moss_550w.cc` 第 218 行：`i2c_new_master_bus()` 用新版驱动初始化 I2C_NUM_0
- `u8g2_esp32.c` 第 2 行：`#include "driver/i2c.h"`（旧版驱动）
- `u8g2_esp32.c` 第 23 行：`i2c_master_write_to_device(I2C_MASTER_NUM, ...)` 旧版 API 尝试写入已由新版驱动的总线

**ESP-IDF V5.x 的限制**：新版 I2C 驱动（driver_ng）和旧版 I2C 驱动不能在同一端口上混合使用。旧版 `i2c_master_write_to_device()` 会自动检测总线状态，发现已被新版驱动占用后直接 abort()。

### 项目总体分析

- **小智固件核心组件**：几乎所有 board 文件、I2cDevice 工具类、大部分音频编解码器都使用**新版驱动** `driver/i2c_master.h`
- **异常文件**：`u8g2_esp32.c` 是唯一在 `main/` 下使用 `driver/i2c.h`（旧版）并**实际执行 I2C 通信**的文件
- 其他引用旧版驱动的文件（es8374/es8389 头文件、waveshare-dualeye、icam-x-mini）要么未在 MOSS 编译中使用，要么只是头文件包含未实际产生 I2C 传输

---

## 4. 推荐解决方案

### 方案 A（推荐）：统一为新版 I2C 驱动

将 `u8g2_esp32.c` 改为使用新版 `driver/i2c_master.h` API，通过 `u8x8_SetUserPtr()` 传递总线句柄。

#### 需要修改的文件及具体修改

##### 修改 1：`main/u8g2_esp32.c`

**1a. 修改头文件包含**

```c
// 旧 (第2行)
#include "driver/i2c.h"

// 新
#include "driver/i2c_master.h"
```

**1b. 添加全局变量存储总线句柄**

```c
// 在 I2C_MASTER_TIMEOUT_MS 定义之后添加
static i2c_master_bus_handle_t g_u8g2_i2c_bus = NULL;
```

**1c. 新增初始化函数（给 board 层调用）**

```c
// 新增：在文件末尾
void u8g2_esp32_set_i2c_bus(i2c_master_bus_handle_t bus) {
    g_u8g2_i2c_bus = bus;
}
i2c_master_bus_handle_t u8g2_esp32_get_i2c_bus(void) {
    return g_u8g2_i2c_bus;
}
```

**1d. 重写 I2C 发送回调**

```c
case U8X8_MSG_BYTE_SEND: {
    uint8_t *data = (uint8_t *)arg_ptr;
    uint8_t addr = u8x8_GetI2CAddress(u8x8) >> 1;

    // 使用新版驱动 API
    i2c_master_dev_handle_t dev_handle;
    i2c_device_config_t dev_cfg = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = addr,
        .scl_speed_hz = 400000,
    };
    ESP_ERROR_CHECK(i2c_master_bus_add_device(g_u8g2_i2c_bus, &dev_cfg, &dev_handle));
    esp_err_t ret = i2c_master_transmit(dev_handle, data, arg_int, I2C_MASTER_TIMEOUT_MS);
    i2c_master_bus_rm_device(dev_handle);

    if (ret != ESP_OK) {
        ESP_LOGW(TAG, "I2C send failed: %s", esp_err_to_name(ret));
        return 0;
    }
    break;
}
```

> **性能优化**：为避免每次传输都 add/remove device，可在 `U8X8_MSG_BYTE_INIT` 时创建 device handle 并暂存，在 `U8X8_MSG_BYTE_END_TRANSFER` 时移除。

##### 修改 2：`main/u8g2_esp32.c` 顶部 — 声明新函数

添加头文件声明：

```c
// 新增函数声明
void u8g2_esp32_set_i2c_bus(i2c_master_bus_handle_t bus);
i2c_master_bus_handle_t u8g2_esp32_get_i2c_bus(void);
```

##### 修改 3：`main/boards/moss_550w/board_moss_550w.cc`

在 `InitI2c()` 成功后，将 I2C 总线句柄传递给 u8g2：

```cpp
// 在第 223 行之后添加
esp_err_t InitI2c() {
    // ... 原有代码 ...
    ESP_LOGI(TAG, "I2C initialized successfully");

    // 将总线句柄传递给 u8g2
    u8g2_esp32_set_i2c_bus(i2c_bus_);

    return ESP_OK;
}
```

---

### 方案 B（备选）：全部统一为旧版 I2C 驱动

此方案不推荐，因为整个框架和所有其他 board 都使用新版驱动，改回旧版会引入大量不兼容修改。

---

## 5. 补充发现

### 5.1 `g_i2c_bus` 全局变量的检查

**搜索范围**：整个 `esp32-firmware/` 目录
**结果**：**不存在**名为 `g_i2c_bus` 的全局变量。

所有其他 board 都将 I2C 总线句柄作为类成员存储（如 `i2c_bus_`、`codec_i2c_bus_`），通过 `I2cDevice` 类或直接传递给音频编解码器。MOSS 550W 也需要类似的机制。

### 5.2 `board_moss_550w.cc` 中的 `g_i2c_bus` 定义/初始化

- `i2c_bus_` 在第 168 行定义为 `Moss550WBoard` 类的私有成员（`i2c_master_bus_handle_t i2c_bus_ = nullptr`）
- 在第 218 行通过 `i2c_new_master_bus()` 初始化
- **但该句柄从未传递给 u8g2** — 这是问题的直接原因

### 5.3 `main/CMakeLists.txt` 中 U8g2 的链接

- 第 732 行：`file(GLOB U8G2_SOURCES "../components/u8g2/csrc/*.c")` — 正确包含 u8g2 库源码
- 第 735 行：`"u8g2_esp32.c"` — 正确添加到编译
- 第 739 行：`"../components/u8g2/csrc"` — 正确添加头文件路径
- U8g2 的编译链接没有问题，问题仅在于运行时 I2C 驱动版本冲突

### 5.4 其他可能抢占 I2C 总线的组件

| 组件 | 是否影响 MOSS 550W | 说明 |
|------|-------------------|------|
| **sscma_client** (SSCMA/AI 传感器) | 否 | 使用旧版 `driver/i2c.h` 但未在 MOSS 配置中启用 |
| **es8374/es8389 音频编解码器** | 否 | MOSS 使用 `NoAudioCodecSimplexPdm`，不包含这些 codec |
| **esp_codec_dev** | 否 | 这些 managed 组件中的旧版驱动代码只在 test_apps 中 |
| **摄像头 (OV2640)** | 否 | config.h 中定义了摄像头引脚但 board 代码中未初始化摄像头 |
| **esp_lcd_panel_io_i2c** | 否 | 新版驱动，且 MOSS 不使用 LCD 面板 |

### 5.5 其他 board 中的潜在冲突

除了 MOSS 550W，以下 board 也在使用 `driver/i2c.h`（旧版）：

1. **waveshare-s3-dualeye-lcd-1.28** (`main/boards/waveshare-s3-dualeye-lcd-1.28/esp32-s3-dualeye-lcd-1.28.cc` 第 11 行)
2. **icam-x-mini-4g** (`main/boards/icam-x-mini-4g/icam-x-mini-4g.cc` 第 13 行)

如果这些 board 同时也使用新版驱动初始化 I2C 总线，可能遇到相同的问题。

### 5.6 关于 DISPLAY_I2C_ADDR

config.h 第 28 行设置 `DISPLAY_I2C_ADDR 0x3D`，但注释说"如果不行改成 0x3D"。SSD1306/SSD1315 的典型 I2C 地址是 **0x3C**（写地址）。代码中 `u8x8_GetI2CAddress(u8x8) >> 1` 的默认值取决于 u8g2 库的初始化，如果与硬件不匹配也可能导致显示异常，但这是次要问题。

---

## 6. 紧急修复步骤（精简版）

1. **修改 `main/u8g2_esp32.c`**：
   - `#include "driver/i2c.h"` → `#include "driver/i2c_master.h"`
   - 用 `i2c_master_bus_add_device()` + `i2c_master_transmit()` 替换 `i2c_master_write_to_device()`
   - 添加全局 `g_u8g2_i2c_bus` 存储总线句柄

2. **修改 `main/boards/moss_550w/board_moss_550w.cc`**：
   - 在 `InitI2c()` 成功后调用 `u8g2_esp32_set_i2c_bus(i2c_bus_)`
   - 添加对应头文件声明或 extern 声明

3. **重新编译并烧录验证**

---

*报告完毕 — 所有结论基于源码分析和 ESP-IDF V5.x I2C 驱动行为。*
