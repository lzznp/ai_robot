# MOSS 550W 小智AI终端 — 硬件综合开发文档

> **生成日期**: 2026-07-06
> **数据来源**: `FlyingProbeTesting.json`（飞针测试文件）、`20251208-BOM及组装材料清单.xlsx`（BOM 清单）
> **备注**: [x] 表示已确认，[ ] 表示需用户进一步确认

---

## 第 1 章：项目总览

### 1.1 项目信息

- **项目名称**: MOSS 550W 小智AI终端
- **基於开源项目**: 小智AI ESP32（xiaozhi）
- **[ ] 硬件版本号**: 待确认（PCB 文件未标注版本号）

### 1.2 核心功能概述

[x] **语音交互**: NS4168 功放 + INMP441 麦克风（I2S接口）
[x] **电机控制**: 2x 24BYJ48 步进电机，经 ULN2003 驱动
[x] **灯效控制**: 3x WS2812B-2020（板载）+ 2x WS2812B-4020（板载）+ 支持外接灯条
[x] **电量管理**: TP4057 充电 + MT3608B 升压
[x] **AI 视觉**: OV2640 摄像头（通过 FPC 连接）
[x] **OLED 显示**: 0.96" OLED 模块（I2C 接口）

### 1.3 关键芯片摘要

| 位号 | 型号 | 数量 | 功能 | 封装 |
|------|------|------|------|------|
| U8 | ESP32-S3-WROOM-1-N16R8 | 1 | 主控 MCU（WiFi/BLE，16MB Flash，8MB PSRAM） | 邮票孔模块 |
| U6 | 74HC595D | 1 | 串转并移位寄存器 | SOIC-16 |
| U7, U10 | ULN2003 | 2 | 达林顿管阵列（步进电机驱动） | SOP-16 |
| U12 | NS4168 | 1 | 3W D类音频功放 | ESOP-8 |
| U4 | TP4057 | 1 | 锂电池充电管理 IC | SOT-23-6 |
| U5 | AMS1117-3.3 | 1 | 3.3V LDO 稳压 | SOT-223 |
| U1 | ME6211C28M5G-N | 1 | 2.8V LDO（摄像头模拟供电） | SOT-23-5 |
| U2 | ME6211C15M5G-N | 1 | 1.5V LDO（摄像头数字 core 供电） | SOT-23-5 |
| U3 | MT3608B | 1 | 升压转换器（VBAT→5V） | SOT-23-6 |
| D1, D3 | SS34 | 2 | 肖特基二极管（电源路径） | SMA |
| Q1, Q2 | AO3401A | 2 | P-MOSFET（电源开关） | SOT-23 |
| FMLED1-3 | WS2812B-2020 | 3 | 2020封装智能LED | LED-SMD 2.0×2.0mm |
| FMLED4-5 | WS2812B-4020 | 2 | 4020封装智能LED | LED-SMD |
| U9, U11 | ZX-MX1.25-5PZZ | 2 | 步进电机接口（5P） | 插件 |
| CN3, CN4 | WAFER-XH2.54-5PZZ | 2 | 步进电机延长接口（5P） | 插件 |
| U13 | FH2.54-09-10PZS | 1 | 摄像头/显示模块接口（20P） | 插件 |

---

## 第 2 章：硬件架构摘要

### 2.1 主控芯片

| 项目 | 内容 |
|------|------|
| 型号 | [x] ESP32-S3-WROOM-1-N16R8 |
| 封装 | [x] 邮票孔模块（WIRELM-SMD） |
| Flash | [x] 16MB（N16） |
| PSRAM | [x] 8MB（R8） |
| 核心数 | [x] 双核 Xtensa LX7 @ 240MHz |
| WiFi/BLE | [x] 2.4G WiFi + BLE 5.0 |

> ESP32-S3-WROOM-1-N16R8 模块集成所有必要外围（晶振、Flash、PSRAM），通过邮票孔焊接到主板。此版本没有板载天线，使用模块内置 PCB 天线。

### 2.2 音频输入 (INMP441)

| 项目 | 内容 |
|------|------|
| 型号 | [x] INMP441 全向 MEMS 麦克风模块 |
| 接口类型 | [x] PDM 数字输出 |
| [ ] GPIO 连接 | 待确认（可能使用 GPIO12/GPIO13/GPIO14 之一） |
| 供电 | [x] 3.3V（从 H2 或 H3 接口取电） |

> **[ ] 待确认**: 麦克风通过 2.54-3P 杜邦线与主板连接，但飞针文件中未明确显示 GPIO 到麦克风的直接连接。麦克风可能连接至 H2（GPIO13、3V3、GND）或 H3（GPIO12、GPIO14、GND、3V3）扩展接口。

### 2.3 音频输出 (NS4168)

| 项目 | 内容 |
|------|------|
| 功放芯片 | [x] NS4168（D 类 3W 功放） |
| 封装 | [x] ESOP-8 |
| 接口类型 | [x] I2S 数字输入 |
| 喇叭接口 | [x] PH2.0-2P 连接器（CN5: SPK+/SPK-） |
| 功放供电 | [x] +5V（升压后） |

**I2S 引脚分配**:

| 信号 | ESP32 GPIO | NS4168 引脚 |
|------|------------|-------------|
| [x] I2S_DIN | GPIO09 | U12_2 |
| [x] I2S_BCLK | GPIO10 | U12_3 |
| [x] I2S_LRCK | GPIO11 | U12_4 |

### 2.4 电机驱动

| 项目 | 内容 |
|------|------|
| 驱动芯片 | [x] 2x ULN2003（U7、U10） |
| 电机型号 | [x] 24BYJ48 步进电机（5V DC，4相5线） |
| 电机数量 | [x] 2个 |
| 控制方式 | [x] 74HC595 串转并 → ULN2003 → 电机 |
| 接口 | [x] ZX-MX1.25-5PZZ（5P 连接器）× 2 |

**控制链路**:

```
ESP32 GPIO03(SHCP) ──┐
ESP32 GPIO04(STCP) ──┤
ESP32 GPIO05(DS) ────┤
                     ▼
              74HC595D (U6)
                     │
     ┌───────────────┴───────────────┐
     ▼                               ▼
U7 ULN2003 (电机1)             U10 ULN2003 (电机2)
     │                               │
     ▼                               ▼
CN3 → U9 (ZX-MX1.25-5P)      CN4 → U11 (ZX-MX1.25-5P)
     │                               │
     ▼                               ▼
24BYJ48 电机1                  24BYJ48 电机2
```

**74HC595 控制信号**:

| 信号 | ESP32 GPIO | 74HC595 引脚 | 说明 |
|------|------------|-------------|------|
| [x] SHCP | GPIO03 | U6_11 | 移位时钟 |
| [x] STCP | GPIO04 | U6_12 | 存储/锁存时钟 |
| [x] DS | GPIO05 | U6_14 | 串行数据输入 |
| [x] OE | (GND) | U6_13 | 输出使能（常开） |
| [x] MR | (+5V) | U6_10 | 主复位（无效） |

**电机相序映射**:

| 74HC595 输出 → ULN2003 输入 | ULN2003 输出 → 电机线 |
|-----------------------------|----------------------|
| **电机1 (U7)** |
| U6_15 (Q0) → U7_4 (IN1_1) | U7_13 → OUT1_1 → CN3_2 → U9_2 → 电机1 |
| U6_1 (Q1) → U7_5 (IN1_2) | U7_12 → OUT1_2 → CN3_3 → U9_3 → 电机1 |
| U6_2 (Q2) → U7_6 (IN1_3) | U7_11 → OUT1_3 → CN3_4 → U9_4 → 电机1 |
| U6_3 (Q3) → U7_7 (IN1_4) | U7_10 → OUT1_4 → CN3_5 → U9_5 → 电机1 |
| **电机2 (U10)** |
| U6_4 (Q4) → U10_4 (IN2_1) | U10_13 → OUT2_1 → CN4_2 → U11_2 → 电机2 |
| U6_5 (Q5) → U10_5 (IN2_2) | U10_12 → OUT2_2 → CN4_3 → U11_3 → 电机2 |
| U6_6 (Q6) → U10_6 (IN2_3) | U10_11 → OUT2_3 → CN4_4 → U11_4 → 电机2 |
| U6_7 (Q7) → U10_7 (IN2_4) | U10_10 → OUT2_4 → CN4_5 → U11_5 → 电机2 |

> 电机电源: +5V 通过 U9_1 / U11_1 提供。

### 2.5 灯效控制 (WS2812)

| 项目 | 内容 |
|------|------|
| 板载 LED | [x] 3x WS2812B-2020（FMLED1~FMLED3） |
| 板载 LED | [x] 2x WS2812B-4020（FMLED4~FMLED5） |
| 外接灯条接口 | [x] FMH1（2020 灯条: +5V, DATA, GND） |
| 外接灯条接口 | [x] FMH2（4020 灯条: +5V, DATA, GND） |
| 灯条供电 | [x] 5V_LED2020 和 5V_LED4020（独立供电） |

**[ ] 待确认 — LED 数据链路**:

飞针文件中，LED 数据输入信号 `NET_5` 仅连接到 FMLED3_1，未发现对应的 ESP32 GPIO 直接连接。可能的连接方式：

1. **通过 PCB 内层走线或 0Ω 电阻跳接**：`NET_5` 可能通过未在飞针文件中体现的内层走线连接到某个 GPIO（如 GPIO06、GPIO07、GPIO48）。
2. **通过扩展排针连接**：H5（GPIO07）或 H6（GPIO48）可能是 LED 数据入口。
3. **[ ] 待用户确认**：请确认 WS2812 LED 数据输入的实际 GPIO。

**LED 级联顺序（推断）**：

```
[DATA IN] → NET_5 → FMLED3(DIN) → NET_4 → FMLED2(DIN) → NET_3 → FMLED1(DIN)
                                                                        │
                                                                   NET_1 (DOUT)
                                                                        │
                                                                   FMH1(数据)
                                                                   [外接灯条]

[数据源] → NET_2 → FMLED4(DIN) → NET_6 → FMLED5(DIN) → NET_7
                                                    (FMLED5 DOUT → 可能到 FMH2)
```

> **注意**: 2020 LED（FMLED1~FMLED3）和 4020 LED（FMLED4~FMLED5）使用不同的数据路径（NET_1~NET_5 vs NET_2~NET_7），可能需要两个独立的 RMT 通道控制。

### 2.6 电源管理

#### 电源架构总览

```
USB Type-C (5V)
    │
    ├──→ TP4057 (U4) ──→ 锂电池 (3.7V)
    │       │                   │
    │       ├ CHRG (充电指示)    ├ MT3608B (U3) ──→ +5V (升压)
    │       └ STBY (充满指示)    │                  │
    │                            │          ┌───────┴───────┐
    │                            │          ▼               ▼
    │                            │     NS4168功放     电机连接器
    │                            │     (U12)           (U9/U11)
    │                            │
    │                   ┌────────┴───────┐
    │                   ▼                ▼
    │             ME6211-2.8V(U1)   ME6211-1.5V(U2)
    │                   │                │
    │                   ▼                ▼
    │              VDD_2V8(AVDD)    VDD_1V5(DVDD)
    │              (摄像头模拟供)    (摄像头数字core)
    │
    ├──→ AMS1117-3.3 (U5) ──→ 3.3V
    │                           │
    │                    ┌──────┴──────┐
    │                    ▼             ▼
    │              ESP32-S3        OLED/其他
    │
    └──→ 电压检测 (ADC)
         GPIO06: USB_5V检测 (100k+100k分压)
         GPIO08: VBATT检测 (100k+100k分压)
```

#### 电源芯片明细

| 位号 | 型号 | 功能 | 输入 | 输出 | 封装 |
|------|------|------|------|------|------|
| [x] U4 | TP4057 | 锂电池充电管理 | USB_5V | VBATT (4.2V) | SOT-23-6 |
| [x] U3 | MT3608B | 升压转换器 | VBATT (3.7V) | VBAT_5V (~5V) | SOT-23-6 |
| [x] U5 | AMS1117-3.3 | 3.3V LDO | +5V | 3.3V | SOT-223 |
| [x] U1 | ME6211C28M5G-N | 2.8V LDO | VBAT | VDD_2V8 | SOT-23-5 |
| [x] U2 | ME6211C15M5G-N | 1.5V LDO | VBAT | VDD_1V5 | SOT-23-5 |

#### 电源路径说明

| 通道 | 说明 |
|------|------|
| **USB 供电** | Type-C 输入 5V → AMS1117-3.3 给 ESP32 供电；USB_5V 同时给 TP4057 充电 |
| **电池供电** | 3.7V 锂电池 → MT3608B 升压至 5V → 系统供电 |
| **电源路径管理** | D1(SS34) + Q1(AO3401A) 实现 VBAT_5V 与 USB_5V 之间的选择（SEL_5V） |
| **摄像头供电** | VBAT → ME6211C28 → 2.8V (AVDD)；VBAT → ME6211C15 → 1.5V (DVDD) |
| [x] **充电指示** | TP4057_CHRG → LED2(红)；TP4057_STBY → LED1(绿) |
| [ ] **升压使能** | MT3608B EN 引脚（NET_42）连接方式未明确 |

> **注意**: USB_5V 和 VBAT_5V 通过肖特基二极管 D3（SS34）和 P-MOSFET Q1（AO3401A）进行电源路径选择。D3 阳极接 USB_5V，Q1 栅极受 SEL_5V 控制。

---

## 第 3 章：引脚映射表 (GPIO Map)

### 3.1 ESP32-S3 GPIO 分配表

以下为 `FlyingProbeTesting.json` "pins" 部分提取的所有 GPIO 对应关系：

| ESP32 Pin# | 网络名称 | 连接元件 | 功能说明 |
|------------|----------|----------|----------|
| U8_1 | GND | — | 地 |
| U8_2 | 3V3 | C19-22, H2, H4, U5, 等多个器件 | 3.3V 供电 |
| U8_3 | CAM_RST | U13_3, C23, NC2, R17 | 摄像头复位 |
| U8_4 | GPIO04 | U6_12 | 74HC595 STCP（存储/锁存时钟） |
| U8_5 | GPIO05 | U6_14 | 74HC595 DS（串行数据） |
| U8_6 | GPIO06 | R21 (100k→USB_5V), R24 (100k→GND) | **USB_5V 电压检测 (ADC)** |
| U8_7 | GPIO07 | H5_2 | 扩展排针 H5（可能为 LED 数据或 UART） |
| U8_8 | CAM_PCLK | U13_14 | 摄像头像素时钟 |
| U8_9 | CAM_D4 | U13_13 | 摄像头数据位 4 |
| U8_10 | CAM_D6 | U13_12 | 摄像头数据位 6 |
| U8_11 | CAM_D5 | U13_11 | 摄像头数据位 5 |
| U8_12 | GPIO08 | R20 (100k→VBATT), R23 (100k→GND), C25 | **电池电压检测 (ADC)** |
| U8_13 | USB_DN | USB1 (Type-C) | USB D- |
| U8_14 | USB_DP | USB1 (Type-C) | USB D+ |
| U8_15 | GPIO03 | U6_11 | 74HC595 SHCP（移位时钟） |
| U8_16 | CAM_D2 | U13_20 | 摄像头数据位 2 |
| U8_17 | GPIO09 | U12_2 | **I2S_DIN（NS4168 音频数据）** |
| U8_18 | GPIO10 | U12_3 | **I2S_BCLK（NS4168 位时钟）** |
| U8_19 | GPIO11 | U12_4 | **I2S_LRCK（NS4168 左右声道时钟）** |
| U8_20 | GPIO12 | H3_1 | 扩展排针 H3（可能为麦克风 PDM_CLK） |
| U8_21 | GPIO13 | H2_1 | 扩展排针 H2（可能为麦克风 PDM_DATA） |
| U8_22 | GPIO14 | H3_2 | 扩展排针 H3 |
| U8_23 | CAM_XCLK | U13_9 | 摄像头主时钟 |
| U8_24 | CAM_PWDN | U13_6 | 摄像头掉电控制 |
| U8_25 | GPIO48 | H6_2 | 扩展排针 H6 |
| U8_26 | CAM_D1 | U13_18 | 摄像头数据位 1 |
| U8_27 | BOOT | SW2 (TS24CA) | BOOT 按键（GPIO0） |
| U8_28 | NET_50 | (仅测试点/PAD) | — |
| U8_29 | NET_51 | (仅测试点/PAD) | — |
| U8_30 | NET_52 | (仅测试点/PAD) | — |
| U8_31 | CAM_VSYNC | U13_5 | 摄像头场同步 |
| U8_32 | CAM_HREF | U13_8 | 摄像头行同步 |
| U8_33 | CAM_D7 | U13_10 | 摄像头数据位 7 |
| U8_34 | CAM_D3 | U13_15 | 摄像头数据位 3 |
| U8_35 | CAM_D0 | U13_16 | 摄像头数据位 0 |
| U8_36 | NET_53 | (仅测试点/PAD) | — |
| U8_37 | NET_54 | (仅测试点/PAD) | — |
| U8_38 | GPIO02 | U13_17, H4_1, R16(1k) | **I2C_SCL（OLED/摄像头 I2C 时钟）** |
| U8_39 | GPIO01 | U13_19, H4_2, R15(1k) | **I2C_SDA（OLED/摄像头 I2C 数据）** |

### 3.2 扩展排针定义

| 排针 | 引脚1 | 引脚2 | 引脚3 | 引脚4 | 用途推测 |
|------|-------|-------|-------|-------|----------|
| H2 | GPIO13 | 3V3 | GND | — | 麦克风 PDM 或传感器 |
| H3 | GPIO12 | GPIO14 | GND | — | 麦克风 PDM 或传感器 |
| H4 | GPIO02(SCL) | GPIO01(SDA) | 3V3 | GND | **I2C 接口 (OLED 模块)** |
| H5 | +5V | GPIO07 | GND | — | LED 数据/UART/1-Wire |
| H6 | +5V | GPIO48 | GND | — | 扩展用途 |

### 3.3 摄像头接口 (U13 + FPC1) 信号分配

| 信号 | 方向 | U13 pin | FPC1 pin | 说明 |
|------|------|---------|----------|------|
| 3V3 | 供电 | 4 | — | 摄像头模块供电 |
| GND | 地 | 2, 7 | 10, 23 | 地 |
| DOVDD_2V8 | 供电 | — | 14 | I/O 供电 (2.8V) |
| DVDD_1V5 | 供电 | — | 15 | Core 供电 (1.5V) |
| AVDD_2V8 | 供电 | — | 21 | 模拟供电 (2.8V) |
| CAM_LDO_CE | 输出 | 1 | — | 摄像头 LDO 使能 |
| CAM_RST | 输出 | 3 | — | 摄像头复位 (低有效) |
| CAM_PWDN | 输出 | 6 | — | 摄像头掉电模式 |
| CAM_VSYNC | 输入 | 5 | — | 场同步 |
| CAM_HREF | 输入 | 8 | — | 行同步 |
| CAM_PCLK | 输入 | 14 | — | 像素时钟 |
| CAM_XCLK | 输出 | 9 | — | 主时钟 (ESP32 提供) |
| CAM_D0~D7 | 输入 | 16,26,20,15,13,11,12,10 | — | 8位并行数据 |
| GPIO01 | I2C | 19 | — | I2C_SDA (摄像头配置) |
| GPIO02 | I2C | 17 | — | I2C_SCL (摄像头配置) |

> FPC1 是一个 24-pin FPC 连接器，主要提供摄像头模块所需的电源（2.8V/1.5V 来自主板 LDO）和一些备用信号。

### 3.4 C 语言 config.h 草案代码

将以下内容保存为 `main/boards/moss_550w/config.h`：

```c
// ============================================================
// MOSS 550W 硬件配置文件
// 基于 ESP32-S3-WROOM-1-N16R8
// 生成自 FlyingProbeTesting.json + BOM 分析
// ============================================================

#ifndef MOSS_550W_CONFIG_H
#define MOSS_550W_CONFIG_H

// --- I2C (OLED / 摄像头配置) ---
#define I2C_SDA_GPIO      1   // GPIO01: I2C_SDA (R15=1kΩ pull-up)
#define I2C_SCL_GPIO      2   // GPIO02: I2C_SCL (R16=1kΩ pull-up)
#define I2C_PORT          I2C_NUM_0

// --- 音频 (I2S → NS4168) ---
#define I2S_DIN_GPIO      9   // GPIO09: NS4168 数据输入
#define I2S_BCLK_GPIO     10  // GPIO10: NS4168 位时钟
#define I2S_LRCK_GPIO     11  // GPIO11: NS4168 左右声道时钟
#define I2S_PORT          I2S_NUM_0

// --- 74HC595 (步进电机控制) ---
#define HC595_SHCP_GPIO   3   // GPIO03: 移位时钟
#define HC595_STCP_GPIO   4   // GPIO04: 存储/锁存时钟
#define HC595_DS_GPIO     5   // GPIO05: 串行数据

// --- 步进电机 ---
// 注: 电机相序通过 74HC595 → ULN2003 控制
// 时序定义在 motor_sequences.h

// --- 电池/电压检测 (ADC) ---
#define USB_VOLTAGE_ADC   ADC1_GPIO6_CHANNEL   // GPIO06: USB_5V 分压检测 (100k+100k)
#define VBATT_ADC         ADC1_GPIO8_CHANNEL   // GPIO08: VBATT 分压检测 (100k+100k)

// --- WS2812 LED ---
// [待确认] LED 数据 GPIO
// #define LED_2020_DATA_GPIO  7   // GPIO07? (WS2812B-2020 灯条数据)
// #define LED_4020_DATA_GPIO  48  // GPIO48? (WS2812B-4020 灯条数据)
// #define LED_RMT_CHANNEL     RMT_CHANNEL_0

// --- 摄像头 (OV2640) ---
#define CAM_PIN_PWDN      GPIO_NUM_NC  // U8_24: CAM_PWDN (通过 U13 连接)
#define CAM_PIN_RST       GPIO_NUM_NC  // U8_3:  CAM_RST (通过 U13 连接)
#define CAM_PIN_VSYNC     GPIO_NUM_NC  // U8_31: CAM_VSYNC
#define CAM_PIN_HREF      GPIO_NUM_NC  // U8_32: CAM_HREF
#define CAM_PIN_PCLK      GPIO_NUM_NC  // U8_8:  CAM_PCLK
#define CAM_PIN_XCLK      GPIO_NUM_NC  // U8_23: CAM_XCLK
#define CAM_PIN_D0        GPIO_NUM_NC  // U8_35: CAM_D0
#define CAM_PIN_D1        GPIO_NUM_NC  // U8_26: CAM_D1
#define CAM_PIN_D2        GPIO_NUM_NC  // U8_16: CAM_D2
#define CAM_PIN_D3        GPIO_NUM_NC  // U8_34: CAM_D3
#define CAM_PIN_D4        GPIO_NUM_NC  // U8_9:  CAM_D4
#define CAM_PIN_D5        GPIO_NUM_NC  // U8_11: CAM_D5
#define CAM_PIN_D6        GPIO_NUM_NC  // U8_10: CAM_D6
#define CAM_PIN_D7        GPIO_NUM_NC  // U8_33: CAM_D7

// --- BOOT 按键 ---
#define BOOT_BUTTON_GPIO  0   // GPIO0 (ESP32 内置)

// --- 扩展排针 ---
// H2: GPIO13, 3V3, GND
// H3: GPIO12, GPIO14, GND
// H5: +5V, GPIO07, GND
// H6: +5V, GPIO48, GND

#endif // MOSS_550W_CONFIG_H
```

---

## 第 4 章：问题与注意事项

### 4.1 GPIO 引脚冲突检测

| GPIO | 功能 | 潜在冲突 | 说明 |
|------|------|----------|------|
| GPIO01 (I2C_SDA) | U13_19 / H4 | — | 同时连接摄像头模块和外部 I2C 排针，注意总线电容 |
| GPIO02 (I2C_SCL) | U13_17 / H4 | — | 同上 |
| [ ] GPIO06 | ADC (USB检测) | ESP32-S3 默认 FSPIQ | 如果使用 Octal SPI PSRAM 可能冲突，但 N16R8 使用 Quad SPI，无冲突 |
| [ ] GPIO07 | H5 扩展排针 | ESP32-S3 默认 FSPID | Quad SPI 无冲突 |
| [ ] GPIO08 | ADC (电池检测) | ESP32-S3 默认 FSPICLK | Quad SPI 无冲突 |
| GPIO12 | H3 排针 | — | 无内置上拉（注意 boot 模式选择） |
| GPIO48 | H6 排针 | — | ESP32-S3 可用 GPIO |

> **[ ] 需确认**: 上述 GPIO 冲突仅针对使用 Quad SPI Flash 的标准 ESP32-S3-WROOM-1 模块。如果模块配置改为 Octal SPI，则 GPIO06-11 将被 SPI 占用，不可用作普通 GPIO。

### 4.2 不明确的连接或命名

1. **[ ] LED 数据输入**: `NET_5`（WS2812 数据输入）仅连接到 FMLED3_1，未发现与 ESP32 GPIO 的直接连接。请确认 LED 控制 GPIO。

2. **[ ] MT3608B 使能**: `NET_42`（MT3608B 升压 EN 引脚）仅连接到 U3_6，未发现控制信号来源。可能连接到固定电平（高）使升压常开。

3. **[ ] 麦克风 PDM 连接**: INMP441 麦克风的 PDM_CLK 和 PDM_DATA 未在飞针文件中明确体现，可能通过 H2/H3 排针连接。建议确认 GPIO12/GPIO13/GPIO14 的具体分配。

4. **[ ] 摄像头 LDO 使能**: `CAM_LDO_CE`（U13_1 / PAD18）由 R22(10kΩ) 上拉到 3V3，默认可能使能摄像头供电，不受 ESP32 控制。

5. **[ ] NET_50/51/52/53/54**: 这 5 个 ESP32 引脚（U8_28~U8_30、U8_36~U8_37）仅连接测试点 PAD，未连接任何功能器件。

### 4.3 与小智官方板型 `lichuang_esp32-s3_dev` 的差异

| 项目 | lichuang_esp32-s3_dev | MOSS 550W |
|------|----------------------|-----------|
| 主控 | ESP32-S3 (同) | ESP32-S3-WROOM-1-N16R8 |
| 音频功放 | MAX98357 (I2S) | **NS4168 (I2S)** — 引脚兼容但增益/输出功率不同 |
| 麦克风 | INMP441 (PDM) | INMP441 (PDM) |
| 电机驱动 | 无 | **2x ULN2003 + 74HC595** |
| LED | WS2812 (单路) | WS2812B-2020 + WS2812B-4020 **双路独立控制** |
| 电池管理 | 无 | **TP4057 + MT3608B 完整方案** |
| 摄像头 | 无 | **OV2640 并行接口** |
| 电源 | USB 5V → AMS1117-3.3 | 完整电源管理（充电+升压+双LDO） |
| I2C_SDA/SCL | GPIO1/GPIO2 或其他 | GPIO01/GPIO02 |
| I2S | GPIO9-11 或其他 | GPIO09/10/11 |

### 4.4 移植到小智固件时的注意事项

1. **音频功放差异**: NS4168 与 MAX98357 虽然都是 I2S 输入 D 类功放，但增益设置不同。MAX98357 通过 GAIN 引脚设置，而 NS4168 通过内部寄存器或外部电阻设置。需确认 NS4168 增益设置并调整 I2S 音量参数。

2. **步进电机驱动**: 小智固件默认不含步进电机驱动逻辑。需要新增 74HC595 + ULN2003 电机驱动模块。建议：
   - 使用 MCP (Model Context Protocol) 服务器接口，将电机控制暴露为 MCP 工具
   - 实现 24BYJ48 的四相八拍驱动时序
   - 注意电机工作时 +5V 电源电流较大（约 2×200mA），需确保升压片能够提供足够电流

3. **WS2812 LED 控制**: 小智固件已有 WS2812 驱动（RMT），但需适配双路独立数据线。需要确认实际的 LED 控制 GPIO（当前为 [待确认]）。

4. **OV2640 摄像头**: 小智固件可能不含摄像头驱动。需要新增 esp32-camera 库集成：
   - 配置 D0-D7 并行接口
   - 通过 I2C（GPIO01/02）配置 OV2640 寄存器
   - 注意 2.8V/1.5V 供电来自板载 LDO，与 ESP32 的 3.3V I/O 电平匹配

5. **电池管理**: 需要新增 ADC 驱动读取 GPIO06（USB电压）和 GPIO08（电池电压），并在电量低时执行安全关机。

6. **I2C 总线**: GPIO01/02 同时连接摄像头和 OLED（通过 H4 排针），注意 I2C 地址冲突。OV2640 的 I2C 地址为 0x30（7位 0x60），OLED（SSD1306 等）通常为 0x3C（7位 0x78），不冲突。

---

## 第 5 章：开发建议

### 5.1 建议的 board 目录结构

```
esp32-firmware/main/boards/moss_550w/
├── config.h              # GPIO 引脚定义（参考 3.4 节）
├── board_init.c / .h     # 板级初始化（GPIO、I2C、I2S、ADC）
├── motor_control.c / .h  # 步进电机驱动（74HC595 + ULN2003）
├── led_control.c / .h    # WS2812 LED 控制（双路 RMT）
├── battery_monitor.c / .h # 电池/USB 电压检测
├── camera.c / .h         # OV2640 摄像头驱动（可选）
├── audio.c / .h          # NS4168 I2S 音频输出（继承自小智固件）
└── CMakeLists.txt        # 编译配置
```

### 5.2 需要重点关注和测试的功能模块

| 优先级 | 模块 | 风险点 |
|--------|------|--------|
| 🔴 高 | **电源管理** | MT3608B 升压稳定性、电池充放电路径切换 |
| 🔴 高 | **步进电机** | 74HC595 时序、ULN2003 驱动电流、相序正确性 |
| 🟡 中 | **音频功放** | NS4168 与 MAX98357 的差异调试 |
| 🟡 中 | **LED 灯效** | 双路 WS2812 独立控制、5V 供电稳定性 |
| 🟢 低 | **摄像头** | OV2640 并行接口时序、I2C 配置 |
| 🟢 低 | **OLED 显示** | I2C 地址确认、显示内容适配 |

### 5.3 推荐优先开发的驱动模块

按照硬件基础→核心交互→扩展功能的顺序，建议开发顺序：

1. **第一阶段 — 基础设施**
   - [x] `board_init.c` — GPIO 初始化（已完成引脚分析）
   - [ ] `i2c_init` — I2C 总线初始化（GPIO01/02）
   - [ ] `i2s_init` — I2S 音频接口初始化（GPIO09/10/11）
   - [ ] `adc_init` — ADC 通道初始化（GPIO06/08）

2. **第二阶段 — 核心交互**
   - [ ] `led_control.c` — WS2812 LED 灯效驱动
   - [ ] `motor_control.c` — 步进电机驱动（74HC595 + ULN2003）
   - [ ] 音频播放测试（NS4168）

3. **第三阶段 — 扩展功能**
   - [ ] `battery_monitor.c` — 电池电量显示与低电告警
   - [ ] 摄像头驱动集成（OV2640）
   - [ ] OLED 显示（表情、状态信息）

4. **第四阶段 — 系统集成**
   - [ ] MCP 服务集成（将电机、LED、摄像头暴露为 MCP 工具）
   - [ ] WebSocket 通信与设备管理
   - [ ] OTA 升级支持

---

## 附录 A：BOM 关键物料清单

| 序号 | 位号 | 型号/规格 | 数量 | 封装 | 功能 |
|------|------|-----------|------|------|------|
| 1 | U8 | ESP32-S3-WROOM-1-N16R8 | 1 | 邮票孔 | 主控 |
| 2 | U6 | 74HC595D | 1 | SOIC-16 | 串转并 |
| 3 | U7,U10 | ULN2003 | 2 | SOP-16 | 电机驱动 |
| 4 | U12 | NS4168 | 1 | ESOP-8 | 音频功放 |
| 5 | U4 | TP4057 | 1 | SOT-23-6 | 充电管理 |
| 6 | U5 | AMS1117-3.3 | 1 | SOT-223 | 3.3V LDO |
| 7 | U1 | ME6211C28M5G-N | 1 | SOT-23-5 | 2.8V LDO |
| 8 | U2 | ME6211C15M5G-N | 1 | SOT-23-5 | 1.5V LDO |
| 9 | U3 | MT3608B | 1 | SOT-23-6 | 升压转换器 |
| 10 | FMLED1-3 | WS2812B-2020 | 3 | 2.0×2.0mm | LED灯效 |
| 11 | FMLED4-5 | WS2812B-4020 | 2 | 4020 | LED灯效 |
| 12 | D1,D3 | SS34 | 2 | SMA | 肖特基二极管 |
| 13 | Q1,Q2 | AO3401A | 2 | SOT-23 | P-MOSFET |
| 14 | USB1 | TYPE-C16PIN | 1 | USB-C | 充电/数据 |
| 15 | CN5 | PH2.0-2P | 1 | 插件 | 喇叭接口 |

## 附录 B：未使用的 ESP32 引脚

以下 ESP32 引脚仅连接测试焊盘（PAD），未连接任何功能器件，可自由分配：

| ESP32 引脚 | 网络名 | 建议用途 |
|------------|--------|----------|
| U8_28 | NET_50 | 通用 GPIO |
| U8_29 | NET_51 | 通用 GPIO |
| U8_30 | NET_52 | 通用 GPIO |
| U8_36 | NET_53 | 通用 GPIO |
| U8_37 | NET_54 | 通用 GPIO |

> 以上 5 个引脚可以提供额外的 UART、SPI、PWM、或传感器接口。

---

*本文档基于 FlyingProbeTesting.json 和 BOM 清单自动分析生成，所有 [待确认] 标记处需要结合原理图和实际硬件验证。*
