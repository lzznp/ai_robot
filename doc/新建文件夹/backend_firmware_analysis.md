# 后端与固件协议分析报告

> 生成时间：2026-06-22  
> 分析范围：`xiaozhi-server/` (后端) + `esp32-firmware/main/` (固件)

---

## 目录

1. [协议对齐分析](#1-协议对齐分析)
2. [LLM 调用链追踪](#2-llm-调用链追踪)
3. [固件原子指令清单](#3-固件原子指令清单)
4. [拦截器方案设计](#4-拦截器方案设计)

---

## 1. 协议对齐分析

### 1.1 后端 WebSocket 下发消息格式

后端通过 WebSocket 连接下发两种类型数据：

| 数据类型 | 格式 | 说明 |
|----------|------|------|
| **二进制帧** | Opus 编码音频 | 直接下发，无元数据或协议版本 1/2/3 头部 |
| **文本 JSON** | `{"type": "...", ...}` | 用于状态通知、控制指令 |

#### JSON 消息类型清单（后端→固件）

消息由 `core/handle/sendAudioHandle.py` (`send_tts_message` 函数，第 266-299 行) 和 `core/utils/textUtils.py` (`get_emotion` 函数，第 84-106 行) 等模块下发。

| type | 字段 | 发送源文件:行号 | 说明 |
|------|------|----------------|------|
| `tts` | `state: "start"` | `sendAudioHandle.py:85` | TTS 开始 |
| `tts` | `state: "sentence_start"`, `text` | `sendAudioHandle.py:38,42` | 句子开始 + 文本 |
| `tts` | `state: "stop"` | `sendAudioHandle.py:51` | TTS 结束 |
| `llm` | `emotion`, `text` (emoji) | `textUtils.py:94-103` | 表情/情绪通知 |
| `mcp` | `payload` (JSON-RPC 2.0) | `helloHandle.py:56-58` | MCP 协议设备控制 |

**后端 TTS JSON 格式模板**（`sendAudioHandle.py:270-272`）：

```json
{
  "type": "tts",
  "state": "start | sentence_start | stop",
  "session_id": "xxx"
}
// sentence_start 时附加:
{
  "type": "tts",
  "state": "sentence_start",
  "text": "要显示的文本",
  "session_id": "xxx"
}
```

**后端 LLM 情绪格式模板**（`textUtils.py:94-103`）：

```json
{
  "type": "llm",
  "text": "😀",
  "emotion": "happy",
  "session_id": "xxx"
}
```

**后端 MCP 格式模板**（通过 `helloHandle.py:58` 发送初始化请求，通过 `core/handle/textHandler/mcpMessageHandler.py` 回复）：

```json
{
  "type": "mcp",
  "session_id": "xxx",
  "payload": {
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "self.light.set_rgb",
      "arguments": { "r": 255, "g": 0, "b": 0 }
    },
    "id": 1
  }
}
```

### 1.2 固件 WebSocket 接收解析

固件解析代码位于 `esp32-firmware/main/protocols/websocket_protocol.cc`，`OnData` 回调（第 111-165 行）。

**解析逻辑**（第 111-163 行）：

```cpp
websocket_->OnData([this](const char* data, size_t len, bool binary) {
    if (binary) {
        // → 音频数据处理（opus 解码播放）
        ...
    } else {
        // 解析 JSON
        auto root = cJSON_Parse(data);
        auto type = cJSON_GetObjectItem(root, "type");
        if (strcmp(type->valuestring, "hello") == 0) {
            ParseServerHello(root);        // 特殊处理 hello
        } else {
            if (on_incoming_json_ != nullptr) {
                on_incoming_json_(root);    // 委托给 application.cc
            }
        }
    }
});
```

**JSON 路由注册**：`application.cc` 第 445-533 行，`OnIncomingJson` lambda：

```cpp
protocol_->OnIncomingJson([this, display](const cJSON* root) {
    auto type = cJSON_GetObjectItem(root, "type");
    if (strcmp(type, "tts") == 0) {
        // 处理 state: start / stop / sentence_start
    } else if (strcmp(type, "stt") == 0) {
        // 显示用户语音识别文本
    } else if (strcmp(type, "llm") == 0) {
        // 读取 emotion 字段 → display->SetEmotion()
    } else if (strcmp(type, "mcp") == 0) {
        // MCP 指令 → McpServer::ParseMessage()
    } else if (strcmp(type, "system") == 0) {
        // 系统命令（reboot）
    } else if (strcmp(type, "alert") == 0) {
        // 报警消息（状态 + 消息 + 表情 + 震动音）
    } else if (strcmp(type, "custom") == 0) {
        // 自定义消息（需编译开启 CONFIG_RECEIVE_CUSTOM_MESSAGE）
    }
});
```

**固件支持的 type 字段**：

| type | 解析位置 | 处理逻辑 |
|------|----------|----------|
| `hello` | `websocket_protocol.cc:153` | `ParseServerHello()` |
| `tts` | `application.cc:448-475` | state=start/stop/sentence_start |
| `stt` | `application.cc:476-483` | 显示用户文本于屏幕 |
| `llm` | `application.cc:484-490` | 读取 `emotion`，`display->SetEmotion()` |
| `mcp` | `application.cc:491-495` | 委托 `McpServer::ParseMessage()` |
| `system` | `application.cc:496-508` | 支持 `command: "reboot"` |
| `alert` | `application.cc:509-517` | 报警 + 声音播放 |
| `custom` | `application.cc:518-529` | 自定义显示（需编译启用） |

### 1.3 格式对比与差异

| 方面 | 后端下发 | 固件解析 | 是否对齐 |
|------|---------|---------|---------|
| **TTS start** | `{"type":"tts","state":"start"}` | `strcmp(state,"start")==0` | ✅ 一致 |
| **TTS sentence_start** | `{"type":"tts","state":"sentence_start","text":"..."}` | `strcmp(state,"sentence_start")==0`, 取 `text` | ✅ 一致 |
| **TTS stop** | `{"type":"tts","state":"stop"}` | `strcmp(state,"stop")==0` | ✅ 一致 |
| **LLM emotion** | `{"type":"llm","emotion":"happy","text":"😀"}` | 读取 `emotion` 字段 | ⚠️ `text` 字段在固件端被忽略 |
| **MCP** | `{"type":"mcp","payload":{...}}` | 解析 `payload` 内 JSON-RPC | ✅ 一致 |
| **STT** | 未发送 STT | 支持解析 `stt` 类型 | ⚠️ 后端暂不下发此类型（是设备→服务器方向） |
| **alert** | 后端未生成此消息 | 固件支持 | ❌ 后端未实现 |
| **custom** | 后端未生成此消息 | 固件支持（需编译开关） | ❌ 后端未实现 |
| **system** | 后端未生成 reboot | 固件支持 | ❌ 后端未实现（重启由 MCP 触发） |

**关键差异总结**：

1. **`llm` 消息中的 `text` 字段**：后端在 `textUtils.py:98` 发送 `"text": emoji`，但固件在 `application.cc:485` 只读取 `emotion` 字段，`text`（emoji 字符）不会被使用。固件 `display->SetEmotion()` 需要一个预定义的表情名称字符串（如 "happy"），而不是 emoji 字符本身。
2. **`alert` / `custom` / `system`**：固件支持但后端没有对应的发送逻辑，属于未使用的协议能力。
3. **二进制帧流控**：后端通过 `AudioRateController` 进行帧级流控（`sendAudioHandle.py:121-131`），固件端无对应流控，收到即解码播放。

---

## 2. LLM 调用链追踪

### 2.1 完整调用链

```
用户语音输入
    ↓
[ASR] 语音识别 → 文本
    ↓
connection.py:332-365  _route_message()
    ↓ 文本消息
connection.py:353  handleTextMessage(conn, message)
    ↓ 路由到文本类型
textMessageProcessor.py:21-38  process_message()
    ↓ 根据 type 分发
helloHandle.py / receiveAudioHandle.py → 根据上下文触发
    ↓
connection.py:908  chat(query, depth=0)
    ↓
connection.py:973-981  LLM 流式响应 (self.llm.response / response_with_functions)
    ↓
connection.py:1000  for response in llm_responses:
    ↓
[流式循环] 解析每个 chunk:
    ├── connection.py:1046-1052 → 提取 emotion → textUtils.get_emotion()
    │   └── 发送 {"type":"llm","emotion":"happy","text":"😀"} WebSocket 消息
    ├── connection.py:1057-1063 → 文本放入 tts.tts_text_queue (TTSMessageDTO)
    │   └── 当 tool_call_flag = False（无工具调用）
    └── connection.py:1015-1017 → 工具调用累积 (tool_calls_list)
    ↓
[工具调用分支]:
    connection.py:1158-1347  处理工具调用 → 执行 → 递归 chat(None, depth+1)
    ↓
[非工具调用分支]:
    最终 chat() 返回前发送 LAST 标记
    ↓
[TTS 处理线程] base.py:368-409  tts_text_priority_thread()
    ↓ 从 tts_text_queue 消费 TTSMessageDTO
    ├── ContentType.TEXT → to_tts_stream() → TTS API → opus 数据
    ├── ContentType.FILE → 直接播放音频文件
    └── SentenceType.FIRST/LAST → 状态标记
    ↓ 音频数据放入 tts_audio_queue
    ↓
[TTS 音频线程] base.py:411-469  _audio_play_priority_thread()
    ↓ 从 tts_audio_queue 消费
    ↓ 调用 sendAudioMessage()
sendAudioHandle.py:20-53  sendAudioMessage()
    ├── 发送 {"type":"tts","state":"sentence_start","text":"..."} (WebSocket)
    ├── sendAudio() → Opus 二进制帧 (WebSocket)
    └── 最后一条: {"type":"tts","state":"stop"} (WebSocket)
```

### 2.2 关键文件与行号

| 环节 | 文件 | 行号 | 函数/代码 |
|------|------|------|-----------|
| 消息路由 | `core/handle/textMessageProcessor.py` | 21-38 | `process_message()` |
| Hello 处理 | `core/handle/helloHandle.py` | 42-60 | `handleHelloMessage()` |
| LLM 调用入口 | `core/connection.py` | 908-991 | `self.chat()` |
| LLM 流式解析 | `core/connection.py` | 1000-1064 | LLM stream loop |
| 情感提取 | `core/connection.py` | 1046-1052 | `emotion_flag` + `get_emotion()` |
| 情感发送 | `core/utils/textUtils.py` | 84-106 | `get_emotion()` |
| TTS 文本队列 | `core/connection.py` | 1057-1063 | `tts_text_queue.put()` |
| TTS 文本线程 | `core/providers/tts/base.py` | 368-409 | `tts_text_priority_thread()` |
| TTS 音频线程 | `core/providers/tts/base.py` | 411-469 | `_audio_play_priority_thread()` |
| sendAudioMessage | `core/handle/sendAudioHandle.py` | 20-53 | `sendAudioMessage()` |
| sendAudio | `core/handle/sendAudioHandle.py` | 103-131 | `sendAudio()` |
| WebSocket 发送 | `core/handle/sendAudioHandle.py` | 266-299 | `send_tts_message()` |
| 工具调用执行 | `core/connection.py` | 1158-1347 | tool call handling |

### 2.3 现有钩子/扩展点

| 钩子点 | 类型 | 位置 | 功能 |
|--------|------|------|------|
| **LLM 响应流解析** | 流式迭代器 | `connection.py:1000` | 每个 LLM chunk 经过此循环 |
| **emotion_flag** | 单次标记 | `connection.py:1046` | 每轮对话第一次文本时触发情感发送 |
| **TTSMessageDTO** | 队列 DTO | `core/providers/tts/dto/dto.py:26-43` | 可扩展字段 |
| **ContentType.ACTION** | 枚举值 | `dto.py:16` | 动作类型（当前仅做标记） |
| **SentenceType** | 枚举值 | `dto.py:5-9` | FIRST / MIDDLE / LAST 三个阶段 |
| **textUtils.get_emotion()** | 函数 | `textUtils.py:84-106` | emoji→emotion 映射，可替换 |
| **handleTextMessageRegistry** | 注册表模式 | `textMessageHandlerRegistry.py:15-47` | 可注册新的消息类型处理器 |
| **MCPClient / send_mcp_initialize_message** | 扩展点 | `device_mcp.py` | 可添加新的 MCP 功能 |

**现有钩子的局限性**：

- 当前 `emotion` 是从 LLM 回复文本中的 emoji 字符映射而来，**没有从 LLM 输出中解析结构化 JSON 剧本的能力**。
- LLM 流式输出的文本直接入 TTS 队列，**没有"文本解析为指令+纯文本"的阶段**。
- 工具调用 (`tool_calls`) 通过 LLM function calling 机制，在 `connection.py:1158-1347` 中处理，但与 TTS 文本流是两套独立的处理路径。

---

## 3. 固件原子指令清单

### 3.1 原子指令分类

固件通过两种通道接收指令：
1. **JSON 消息**（WebSocket 文本帧）：`type` 字段分发
2. **MCP 协议**（`type: "mcp"` 内的 JSON-RPC 2.0）：`tools/call` 方法

#### 3.1.1 JSON 消息指令（application.cc:445-533）

| type | 字段 | 效果 | 文件:行号 |
|------|------|------|-----------|
| `tts` | `state: "start"` | 进入 Speaking 状态 | `application.cc:450-456` |
| `tts` | `state: "stop"` | 结束 Speaking → Idle/Listening | `application.cc:457-466` |
| `tts` | `state: "sentence_start"`, `text` | 显示文本于屏幕 | `application.cc:467-474` |
| `stt` | `text` | 显示用户语音文本 | `application.cc:476-483` |
| `llm` | `emotion` | `display->SetEmotion(emotion)` | `application.cc:484-490` |
| `mcp` | `payload` (JSON-RPC) | `McpServer::ParseMessage()` | `application.cc:491-495` |
| `system` | `command: "reboot"` | 重启设备 | `application.cc:496-508` |
| `alert` | `status`, `message`, `emotion` | 报警+声音 | `application.cc:509-517` |
| `custom` | `payload` | 自定义显示 | `application.cc:518-529` |

#### 3.1.2 MCP 工具指令（mcp_server.cc + board 注册）

**通用 MCP 工具**（`mcp_server.cc:33-126`, `AddCommonTools()`）：

| 工具名 | 参数 | 功能 | 适用范围 |
|--------|------|------|---------|
| `self.get_device_status` | 无 | 获取设备实时状态 | 所有设备 |
| `self.audio_speaker.set_volume` | `volume: 0-100` | 设置音量 | 所有设备 |
| `self.screen.set_brightness` | `brightness: 0-100` | 设置屏幕亮度 | 有背光设备 |
| `self.screen.set_theme` | `theme: "light"/"dark"` | 切换主题 | 有 LVGL 设备 |
| `self.camera.take_photo` | `question` | 拍照并解释 | 有摄像头设备 |

**用户级 MCP 工具**（`mcp_server.cc:128-303`, `AddUserOnlyTools()`）：

| 工具名 | 参数 | 功能 |
|--------|------|------|
| `self.get_system_info` | 无 | 获取系统信息 |
| `self.reboot` | 无 | 重启系统 |
| `self.upgrade_firmware` | `url` | 从 URL 升级固件 |
| `self.screen.get_info` | 无 | 获取屏幕信息 |
| `self.screen.snapshot` | `url`, `quality` | 截屏上传 |
| `self.screen.preview_image` | `url` | 预览图片 |
| `self.assets.set_download_url` | `url` | 设置资源下载 URL |

**板级特定 MCP 工具**（各 board 的 `InitializeTools()`）：

**ESP-Hi (机器狗)** — `esp32-firmware/main/boards/esp-hi/esp_hi.cc:300-397`：

| 工具名 | 参数 | 功能 |
|--------|------|------|
| `self.dog.basic_control` | `action: forward/backward/turn_left/turn_right/stop`, `speed`, `steps` | 基础运动 |
| `self.dog.advanced_control` | `action: sway_back_forth/lay_down/sway/retract_legs/shake_hand/shake_back_legs/jump_forward`, `speed` | 扩展运动 |
| `self.light.get_power` | 无 | 查询灯状态 |
| `self.light.turn_on` | 无 | 开灯 |
| `self.light.turn_off` | 无 | 关灯 |
| `self.light.set_rgb` | `r:0-255`, `g:0-255`, `b:0-255` | 设置 RGB 灯 |

**Electron-Bot** — `esp32-firmware/main/boards/electron-bot/electron_bot_controller.cc:147-343`：

| 工具名 | 参数 | 功能 |
|--------|------|------|
| `self.electron.hand_action` | `action:1-4`, `hand:1-3`, `steps`, `speed`, `amount` | 手部动作 |
| `self.electron.body_turn` | `steps`, `speed`, `direction:1-3`, `angle:0-90` | 身体转向 |
| `self.electron.head_move` | `action:1-5`, `steps`, `speed`, `angle` | 头部运动 |
| `self.electron.stop` | 无 | 立即停止 |
| `self.electron.get_status` | 无 | 获取机器人状态 |
| `self.electron.set_trim` | `servo_type`, `trim_value:-30~30` | 舵机微调校准 |
| `self.electron.get_trims` | 无 | 获取舵机微调值 |
| `self.battery.get_level` | 无 | 获取电池电量 |

### 3.2 表情（Emotion）名称清单

`display->SetEmotion(name)` 支持的表情名称，通过 `display/emote_display.h` 的 `EmoteDisplay` 实现：

| emotion 名称 | 对应 emoji | 说明 |
|-------------|-----------|------|
| `happy` | 😀 | 开心 |
| `sad` | 😢 | 悲伤 |
| `angry` | 😠 | 生气 |
| `neutral` | 😐 | 中性 |
| `sleepy` | 😴 | 困倦 |
| `surprised` | 😲 | 惊讶 |
| `triangle_exclamation` | ⚠️ | 警告（用于错误状态） |
| `circle_xmark` | ❌ | 错误（用于 alert） |
| _其他_ | | 由各 board 的 GIF/图片资源定义 |

⚠️ **重要**：`SetEmotion()` 接收的是**字符串名称**（如 `"happy"`），而不是 emoji 字符。后端 `textUtils.py:98` 发送的 `"text": "😀"` 固件不会使用。

### 3.3 是否支持"指令+音频同时执行"

**当前架构**：

| 场景 | 是否支持 | 说明 |
|------|---------|------|
| **TTS 播放中下 MCP 指令** | ✅ 是 | MCP 通过独立的 JSON 消息通道，与 TTS 音频流独立；`application.cc:491-495` 处理 MCP 时不阻塞 |
| **TTS 播放中下 llm 情感** | ✅ 是 | `application.cc:484-490` 直接调用 `display->SetEmotion()`，立即生效 |
| **同一消息同时携带音频和指令** | ❌ 否 | 后端单次 `sendAudioMessage` 只发送 TTS 文本+音频 OR 消息体，没有"音频+指令"的复合消息格式 |
| **指令中引用 TTS 文本** | ❌ 否 | LLM 生成的"剧本"（如 `{"emotion":"happy","text":"你好"}`）在后端被拆分为两条消息独立下发，无关联 |

**结论**：当前架构中，指令（emotion/MCP）与音频在传输层面可以并行，但在**业务语义层面**没有绑定关系。例如，LLM 回复 "你好啊😀" 会被拆解为：
1. TTS 音频播放 "你好啊"
2. `llm` 消息设置 emotion="happy"

两者**可能存在时序偏差**——情感可能在文字朗读中/后才设置到设备。

---

## 4. 拦截器方案设计

### 4.1 核心问题

LLM 返回的纯文本流中可能包含 JSON 剧本（如 `{"emotion":"happy","text":"你好啊"}`），但现有架构没有解析能力。要实现"拦截 LLM 返回、解析 JSON 剧本、分拆下发"，需要在 LLM 流到 TTS 队列的路上加**拦截器**。

### 4.2 方案 A：LLM 流解析拦截器（推荐）

**插入点**：`connection.py:1057`，LLM 流式文本入 TTS 队列之前。

```python
# 现有代码 (connection.py:1054-1063):
if content is not None and len(content) > 0:
    if not tool_call_flag:
        response_message.append(content)
        self.tts.tts_text_queue.put(
            TTSMessageDTO(
                sentence_id=current_sentence_id,
                sentence_type=SentenceType.MIDDLE,
                content_type=ContentType.TEXT,
                content_detail=content,
            )
        )

# 修改为:
if content is not None and len(content) > 0:
    if not tool_call_flag:
        response_message.append(content)
        # --- 拦截器开始 ---
        parsed = self._parse_script_content(content)
        if parsed:
            # 有剧本指令，拆分下发
            if parsed.get("emotion"):
                # 立即发送 emotion 到固件
                await self._send_emotion(parsed["emotion"])
            if parsed.get("text"):
                # 仅将纯文本送入 TTS
                self.tts.tts_text_queue.put(...)
            if parsed.get("action"):
                # 发送 MCP 动作指令
                await self._send_mcp_action(parsed["action"])
        else:
            # 纯文本，正常入队列
            self.tts.tts_text_queue.put(...)
        # --- 拦截器结束 ---
```

**改动量**：
- `connection.py`: 修改约 20 行，新增 `_parse_script_content()` 和 `_send_mcp_action()` 方法约 40 行
- **总改动约 60 行**

**优点**：
- 时机最精准——LLM 文本刚产生时即可拦截
- 不改变 TTS 内部逻辑
- 可以流式积累文本再解析（跨 chunk 合并）
- 与现有的 `emotion_flag` 机制兼容

**缺点**：
- 需要自己处理 JSON 解析的跨 chunk 拼合
- 如果 LLM 输出的 JSON 格式不一致，容错处理较复杂
- 流式环境下，emotion 可能在 TTS 第一句话开始前就发送，导致"先变表情再说话"

### 4.3 方案 B：TTS 消息 DTO 阶段拦截器

**插入点**：`core/providers/tts/base.py:385-389`，在 `tts_text_priority_thread()` 消费 TTSMessageDTO 时。

**原理**：在 TTS 文本处理线程中，对 `ContentType.TEXT` 的消息内容做二次解析，发现 JSON 剧本则拆分为多个 DTO 重新入队。

```python
# 修改 base.py:385-389
elif ContentType.TEXT == message.content_type:
    # --- 拦截器 ---
    parsed = self._parse_and_split_script(message.content_detail)
    if parsed:
        # 有剧本，将拆分的指令重新入队
        for sub_msg in parsed:
            self.tts_text_queue.put(sub_msg)
        continue  # 跳过当前消息的正常处理
    # --- 拦截器结束 ---
    self.tts_text_buff.append(message.content_detail)
    segment_text = self._get_segment_text()
    ...
```

**改动量**：
- `base.py`: 新增 `_parse_and_split_script()` 约 30 行，修改处理逻辑约 15 行
- 需要一个新的队列消息类型（如 `ContentType.COMMAND`）或复用现有的 `ContentType.ACTION`
- **总改动约 50 行**

**优点**：
- 不影响 LLM 流式主循环
- 可以访问完整的句子（`tts_text_priority_thread` 工作在线程中，可以累积完整句子）
- 与流控机制天然兼容

**缺点**：
- 解析在 TTS 线程中，向设备发指令需要跨线程调用 `asyncio.run_coroutine_threadsafe`
- 修改 TTS 内部逻辑，需要理解 `TTSMessageDTO` 和队列的完整生命周期
- 如果在 FIRST 消息后才插入指令，表情/动作可能比语音晚

### 4.4 方案 C：专用的"剧本解析 Agent"中间层

**插入点**：在 `connection.py:908` 的 `chat()` 函数中，LLM 流完全结束后的回调处。

**原理**：不修改 LLM 流的主路径。在 `chat()` 递归或返回前，将完整的 LLM 回复文本经过一个**剧本解析函数**，由它决定最终下发哪些指令。

```python
# chat() 函数末尾，所有 LLM 流和工具调用完成后
if not tool_call_flag and depth == 0:
    full_text = "".join(response_message)  # 完整的 LLM 回复
    # --- 剧本解析 ---
    script = self._parse_script_from_response(full_text)
    if script:
        # 先并发下发所有指令
        await self._execute_script_actions(script)
        # 纯文本部分由 TTS 播放（已被 stream 入队列）
    # --- 解析结束 ---
```

**改动量**：
- `connection.py`: 新增 `_parse_script_from_response()` 约 50 行，新增 `_execute_script_actions()` 约 30 行
- 需要定义剧本格式（JSON schema）
- **总改动约 80 行**

**优点**：
- 有完整的 LLM 回复文本可用，无需跨 chunk 拼合
- 可以安排指令的发射顺序（先发 emotion，再发 MCP 动作，同时播放 TTS）
- 与现有代码的侵入最小
- 可以设计复杂的剧本格式（时间线、并发指令组）

**缺点**：
- 解析发生在 TTS 已经开始播放之后（因为文本已流式送入 TTS 队列）
- 指令总是**滞后于 TTS 语音**，无法实现"先做动作再说语音"
- 如果想实现前置指令，需要修改流式逻辑，**缓存文本**直到确定是否为剧本

### 4.5 方案对比

| 维度 | A: LLM 流解析 | B: TTS DTO 拦截 | C: 后处理解析 |
|------|---------------|-----------------|--------------|
| **插入点** | `connection.py:1057` | `base.py:385` | `connection.py` chat 末尾 |
| **是否可前置执行动作** | ✅ 是，可在 TTS 前发送 emotion | ❌ 否，先入队列再解析 | ❌ 否，TTS 已开始 |
| **可访问完整文本** | ❌ 需跨 chunk 拼合 | ✅ 是（线程中累积） | ✅ 是 |
| **跨 chunk JSON 拼合** | 需要 | 不需要 | 不需要 |
| **与现有流控兼容性** | ✅ 完全兼容 | ✅ 兼容 | ⚠️ 需注意时序 |
| **改动量** | ~60 行 | ~50 行 | ~80 行 |
| **风险** | 低 | 中（TTS 内部改动） | 低 |
| **实现难度** | 中 | 中 | 低 |

### 4.6 推荐方案

**短期推荐方案 A**（LLM 流解析拦截器）。理由：

1. 在 LLM 文本产生时立即处理，可以**在 TTS 之前先发送 emotion/MCP 指令**，实现"先变表情、再说话"的体验
2. 与现有 `emotion_flag` 逻辑完全兼容，可以复用
3. 不影响 TTS 音视频流的稳定性和延迟
4. 使用正则或 JSON 片段检测器拼合跨 chunk 的剧本，容错性好

**实现建议**：

1. 在 `connection.py` 的 `chat()` 方法中添加一个 `_script_buffer` 用于积累跨 chunk 的 JSON 片段
2. 每收到一个 LLM chunk，尝试从 `content` 中匹配 `{}` 包裹的 JSON 块
3. 如果匹配成功，解析剧本，拆分为：emotion 指令（立即 WebSocket 发送）+ 纯文本（入 TTS 队列）+ MCP 动作（通过 `send_mcp_initialize_message` 通道发送）
4. 剧本优先使用 LLM 的 `function_call` 机制——让 LLM 调用一个 `self._script_action` 函数来下发结构化指令，而不是从文本中解析 JSON

**远期推荐**：使用 LLM 的 `function_call` 机制（方案 C 的变体），让 LLM 通过 tool calling 直接下发结构化动作，而非从文本流中提取 JSON。现有代码已在 `connection.py:1158-1347` 中完整支持工具调用，只需注册一个新工具即可。

---

## 附录 A：文件索引

| 文件 | 关键行 | 内容 |
|------|--------|------|
| `xiaozhi-server/core/connection.py` | 907-1347 | LLM 调用链核心 |
| `xiaozhi-server/core/handle/sendAudioHandle.py` | 20-340 | 音频+消息下发 |
| `xiaozhi-server/core/providers/tts/base.py` | 276-636 | TTS 处理线程 |
| `xiaozhi-server/core/providers/tts/dto/dto.py` | 1-43 | 数据结构定义 |
| `xiaozhi-server/core/utils/textUtils.py` | 84-106 | 表情发送函数 |
| `xiaozhi-server/core/handle/textMessageProcessor.py` | 1-38 | 文本消息路由 |
| `esp32-firmware/main/application.cc` | 445-533 | JSON 消息处理 |
| `esp32-firmware/main/protocols/websocket_protocol.cc` | 111-165 | WebSocket 数据接收 |
| `esp32-firmware/main/mcp_server.cc` | 33-565 | MCP 服务器实现 |
| `esp32-firmware/main/display/display.h` | 28-58 | Display 抽象接口 |
| `esp32-firmware/main/device_state.h` | 1-15 | 设备状态枚举 |
| `esp32-firmware/main/boards/esp-hi/esp_hi.cc` | 300-397 | 机器狗 MCP 工具 |
| `esp32-firmware/main/boards/electron-bot/electron_bot_controller.cc` | 147-343 | Electron Bot MCP 工具 |
