# 后台 WebSocket 消息处理 — 侦察报告

> 项目：小智多机器人调度系统 (xiaozhi-server)
> 日期：2026-07-01
> 目标：侦察 WebSocket 消息处理核心逻辑
> 方法：全量代码走读，不修改任何文件

---

## 一、WebSocket 服务入口

### 1.1 服务器启动

| 项目 | 路径 | 行号 |
|------|------|------|
| 应用入口 | `xiaozhi-server/app.py` | — |
| WebSocket服务器类 | `xiaozhi-server/core/websocket_server.py` | 第42行 |
| 服务器启动 | `websocket_server.py` `async def start()` | 第73行 |
| 新连接处理 | `websocket_server.py` `async def _handle_connection()` | 第83行 |
| ConnectionHandler创建 | `websocket_server.py` 第118-127行 | — |
| 连接主循环入口 | `connection.py` `async def handle_connection()` | 第335行 |

### 1.2 消息接收入口

**文件**: `xiaozhi-server/core/connection.py`

```python
# 第384-386行 — 主消息循环
try:
    async for message in self.websocket:
        await self._route_message(message)
```

所有来自固件的 WebSocket 消息（文本或二进制）都从这里进入。

---

## 二、消息路由核心 — `_route_message()`

**文件**: `xiaozhi-server/core/connection.py` **第477行**

```python
async def _route_message(self, message):
    """消息路由"""
    # ... (绑定状态检查) ...

    if isinstance(message, str):
        await handleTextMessage(self, message)          # 文本消息 → 处理器链
    elif isinstance(message, bytes):
        if self.vad is None or self.asr is None:
            return
        self.asr_audio_queue.put(message)               # 音频 → VAD/ASR 管道
```

**路由逻辑**：
- `str`（文本 JSON）→ `handleTextMessage()` → `TextMessageProcessor` → 按 `type` 分发
- `bytes`（音频二进制）→ `asr_audio_queue` → VAD 检测 → ASR 识别 → `startToChat()`
- MQTT 网关特殊处理：`_process_mqtt_audio_message()`（第512行），解析16字节头部

---

## 三、文本消息类型 — 完整清单

### 类型注册中心

**文件**: `xiaozhi-server/core/handle/textMessageType.py`（第1-13行）

```python
class TextMessageType(Enum):
    HELLO = "hello"
    ABORT = "abort"
    LISTEN = "listen"
    IOT = "iot"
    MCP = "mcp"
    SERVER = "server"
    PING = "ping"
```

### 处理器注册表

**文件**: `xiaozhi-server/core/handle/textMessageHandlerRegistry.py`（第10-55行）

以下7种消息类型被注册到全局 `TextMessageHandlerRegistry`：

---

### 3.1 `hello` — 客户端握手

**处理器**: `HelloTextMessageHandler`
**文件**: `xiaozhi-server/core/handle/textHandler/helloMessageHandler.py` 第1-17行
**实际处理函数**: `handleHelloMessage()`
**文件**: `xiaozhi-server/core/handle/helloHandle.py` 第36行起

```python
async def handleHelloMessage(conn, msg_json):
    """处理hello消息"""
    audio_params = msg_json.get("audio_params")
    if audio_params:
        conn.audio_format = format
        conn.welcome_msg["audio_params"] = audio_params
    features = msg_json.get("features")
    if features:
        conn.features = features
        if features.get("mcp"):
            asyncio.create_task(send_mcp_initialize_message(conn))
    await conn.websocket.send(json.dumps(conn.welcome_msg))
```

| 属性 | 值 |
|------|-----|
| 同步/异步 | **异步** |
| 调用类型 | `await handler.handle(conn, msg_json)` |
| 主要作用 | 处理设备首次连接握手，交换音频参数和功能特性 |
| 特殊分支 | 如果 `features.mcp=true`，异步初始化 MCP 客户端 |

**JSON 格式**:
```json
{
  "type": "hello",
  "audio_params": {"format": "opus", "sample_rate": 24000},
  "features": {"mcp": true, "emoji": true}
}
```

**回复格式**:
```json
{
  "type": "hello",
  "session_id": "...",
  "audio_params": {...},
  "transport": "websocket"
}
```

---

### 3.2 `abort` — 客户端打断/中止

**处理器**: `AbortTextMessageHandler`
**文件**: `xiaozhi-server/core/handle/textHandler/abortMessageHandler.py` 第1-17行
**实际处理函数**: `handleAbortMessage()`
**文件**: `xiaozhi-server/core/handle/abortHandle.py` 第9-23行

```python
async def handleAbortMessage(conn):
    conn.client_abort = True         # 打断LLM/TTS任务
    conn.clear_queues()              # 清空所有队列
    await conn.websocket.send(json.dumps({
        "type": "tts", "state": "stop", "session_id": conn.session_id
    }))
    conn.clearSpeakStatus()
```

| 属性 | 值 |
|------|-----|
| 同步/异步 | **异步** |
| 主要作用 | 停止当前对话，清空 TTS 队列，通知固件停止播放 |

**JSON 格式**:
```json
{"type": "abort"}
```

---

### 3.3 `listen` — 音频采集状态控制

**处理器**: `ListenTextMessageHandler`
**文件**: `xiaozhi-server/core/handle/textHandler/listenMessageHandler.py` 第1-67行

**三种子状态**:

| state | 行号 | 逻辑 |
|-------|------|------|
| `start` | 第24行 | 设备切回录音模式，`conn.reset_audio_states()` |
| `stop` | 第26行 | 客户端说话结束，触发 ASR 识别 |
| `detect` | 第37行 | 文本检测结果（含唤醒词），触发 `startToChat()` |

**`detect` 状态的核心分支**（第42-67行）:

```python
elif msg_json["state"] == "detect":
    if "text" in msg_json:
        original_text = msg_json["text"]
        # 分支1：纯唤醒词且关闭唤醒词回复 → 只更新状态，不回答
        if is_wakeup_words and not enable_greeting:
            await send_stt_message(conn, original_text)
            await send_tts_message(conn, "stop", None)
        # 分支2：唤醒词+开启回复 → 发送"嘿，你好呀"
        elif is_wakeup_words:
            await startToChat(conn, "嘿，你好呀")
        # 分支3：正常文本 → 直接走 LLM 流程
        else:
            await startToChat(conn, original_text)
```

| 属性 | 值 |
|------|-----|
| 同步/异步 | **异步** |
| 主要作用 | 客户端(固件)报告录音状态和文本检测结果 |

**JSON 格式**:
```json
{"type": "listen", "state": "start"}
{"type": "listen", "state": "stop"}
{"type": "listen", "state": "detect", "text": "今天天气怎么样", "mode": "auto"}
```

---

### 3.4 `iot` — 设备IOT状态上报

**处理器**: `IotTextMessageHandler`
**文件**: `xiaozhi-server/core/handle/textHandler/iotMessageHandler.py` 第1-24行

```python
async def handle(self, conn, msg_json):
    if "descriptors" in msg_json:
        asyncio.create_task(handleIotDescriptors(conn, msg_json["descriptors"]))
    if "states" in msg_json:
        asyncio.create_task(handleIotStatus(conn, msg_json["states"]))
```

| 属性 | 值 |
|------|-----|
| 同步/异步 | **异步**，内部创建 `asyncio.create_task` |
| 处理函数 | `handleIotDescriptors()` 和 `handleIotStatus()` |
| 所在文件 | `core/providers/tools/device_iot.py` |

**JSON 格式**:
```json
{"type": "iot", "descriptors": {...}}
{"type": "iot", "states": {...}}
```

---

### 3.5 `mcp` — MCP协议消息

**处理器**: `McpTextMessageHandler`
**文件**: `xiaozhi-server/core/handle/textHandler/mcpMessageHandler.py` 第1-20行

```python
async def handle(self, conn, msg_json):
    if "payload" in msg_json:
        asyncio.create_task(
            handle_mcp_message(conn, conn.mcp_client, msg_json["payload"])
        )
```

| 属性 | 值 |
|------|-----|
| 同步/异步 | **异步**，内部创建 `asyncio.create_task` |
| 处理函数 | `handle_mcp_message()` |
| 所在文件 | `core/providers/tools/device_mcp.py` |

**JSON 格式**:
```json
{"type": "mcp", "payload": {...}}
```

---

### 3.6 `server` — 服务端管理指令

**处理器**: `ServerTextMessageHandler`
**文件**: `xiaozhi-server/core/handle/textHandler/serverMessageHandler.py` 第1-65行

两种 action：

| action | 行号 | 逻辑 |
|--------|------|------|
| `update_config` | 第37行 | 从API重新拉取配置并初始化组件 |
| `restart` | 第62行 | 重启服务器 |

```python
# 验证 secret
post_secret = msg_json.get("content", {}).get("secret", "")
secret = conn.config["manager-api"].get("secret", "")
```

| 属性 | 值 |
|------|-----|
| 同步/异步 | **异步** |
| 安全机制 | 需要 `secret` 密钥验证 |
| 触发条件 | 仅当 `conn.read_config_from_api == True` 时有效 |

**JSON 格式**:
```json
{"type": "server", "action": "update_config", "content": {"secret": "..."}}
{"type": "server", "action": "restart", "content": {"secret": "..."}}
```

---

### 3.7 `ping` — 心跳保活

**处理器**: `PingMessageHandler`
**文件**: `xiaozhi-server/core/handle/textHandler/pingMessageHandler.py` 第1-48行

```python
async def handle(self, conn, msg_json):
    if not conn.config.get("enable_websocket_ping", False):
        return  # 功能未启用则忽略
    pong_message = {
        "type": "pong",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
    }
    await conn.websocket.send(json.dumps(pong_message))
```

| 属性 | 值 |
|------|-----|
| 同步/异步 | **异步** |
| 可配置 | 通过 `enable_websocket_ping` 开关 |
| 回复对象 | 发送 `{"type": "pong", "timestamp": "..."}` |

**JSON 格式**:
```json
{"type": "ping"}
```

**回复格式**:
```json
{"type": "pong", "timestamp": "2026-07-01 12:00:00"}
```

---

### 消息类型汇总表

| type | 处理器类 | 实际处理函数 | 文件 | 行号 | 异步? |
|------|----------|-------------|------|------|-------|
| `hello` | `HelloTextMessageHandler` | `handleHelloMessage()` | `helloHandle.py` | 第36行 | ✅ |
| `abort` | `AbortTextMessageHandler` | `handleAbortMessage()` | `abortHandle.py` | 第9行 | ✅ |
| `listen` | `ListenTextMessageHandler` | 内置按 state 分支 | `textHandler/listenMessageHandler.py` | 第18行 | ✅ |
| `iot` | `IotTextMessageHandler` | `handleIotDescriptors/Status()` | `textHandler/iotMessageHandler.py` | 第14行 | ✅ (create_task) |
| `mcp` | `McpTextMessageHandler` | `handle_mcp_message()` | `textHandler/mcpMessageHandler.py` | 第15行 | ✅ (create_task) |
| `server` | `ServerTextMessageHandler` | 内置按 action 分支 | `textHandler/serverMessageHandler.py` | 第20行 | ✅ |
| `ping` | `PingMessageHandler` | 内置回复 pong | `textHandler/pingMessageHandler.py` | 第21行 | ✅ |

> **未识别的 type**：`TextMessageProcessor` 第28行打出 `收到未知类型消息` 日志，不 panic。

---

## 四、音频消息处理管道（字节流）

### 4.1 处理链路

```
固件原始音频(bytes)
    │
    ▼
_route_message() [connection.py:512]
    │
    ├─ MQTT网关? → _process_mqtt_audio_message() 解析16字节头部
    │                [connection.py:562]
    │
    └─ 普通WS → asr_audio_queue.put(message)
                    │
                    ▼
                VAD检测 (vad.is_vad) → have_voice
                    │
                    ▼
                ASR.receive_audio() → 积累音频
                    │
                    ▼ (voice_stop时)
                ASR.handle_voice_stop() → 识别文本
                    │
                    ▼
                startToChat(conn, text) [receiveAudioHandle.py:49]
```

### 4.2 `startToChat()` 核心逻辑

**文件**: `xiaozhi-server/core/handle/receiveAudioHandle.py` 第49-133行

```python
async def startToChat(conn, text):
    # 1. 检查绑定状态
    if conn.need_bind: await check_bind_device(conn); return

    # 2. 检查输出上限
    if check_device_output_limit(...): await max_out_size(conn); return

    # 3. 打断正在进行的对话
    if conn.client_is_speaking: await handleAbortMessage(conn)

    # 4. 意图识别（退出/唤醒词/function_call）
    intent_handled = await handle_user_intent(conn, text)
    if intent_handled: return

    # 5. ★ World 多角色调度（新版）
    if hasattr(conn, 'world') and conn.world:
        results = conn.world.process(text)
        # 分发给对应设备...
        return

    # 6. 走标准 LLM 流程（旧版）
    conn.executor.submit(conn.chat, actual_text)     # 线程池执行
```

---

## 五、LLM 调用入口

### 5.1 标准 LLM 调用

**文件**: `xiaozhi-server/core/connection.py` **第1067行**

```python
def chat(self, query, depth=0):
    # depth=0: 新会话，生成 sentence_id
    # depth>0: 递归调用（工具链结果回传）
```

**内部调用**:

| 模式 | 行号 | 调用方法 |
|------|------|---------|
| function_call 模式 | 第1135行 | `self.llm.response_with_functions(...)` |
| 普通模式 | 第1143行 | `self.llm.response(...)` |

### 5.2 LLM 响应流处理

```python
# 第1160行 — 流式迭代
for response in llm_responses:
    if self.client_abort: break        # 打断检查

    # 提取情感 (每轮只取首次)
    textUtils.get_emotion(self, content)

    # 普通文本 → 放入 TTS 队列
    self.tts.tts_text_queue.put(TTSMessageDTO(
        sentence_id=current_sentence_id,
        sentence_type=SentenceType.MIDDLE,
        content_type=ContentType.TEXT,
        content_detail=content,
    ))

    # function_call → 处理工具调用链
```

### 5.3 工具调用递归

```python
# 第1245-1377行 — 工具调用处理
self._handle_function_result(tool_results, depth, streamed_text)
# 在 _handle_function_result 中，如果 action == Action.REQLLM
# 会递归调用 chat()，depth + 1（第1467行起）
```

**最大递归深度**: 5（第1091行 `MAX_DEPTH = 5`）

---

## 六、TTS 转换入口

### 6.1 TTS 队列入口

LLM 流式响应文本通过 **`tts_text_queue`** 送入 TTS 引擎：

```python
# connection.py 第1217行
self.tts.tts_text_queue.put(TTSMessageDTO(
    sentence_id=current_sentence_id,
    sentence_type=SentenceType.MIDDLE,
    content_type=ContentType.TEXT,
    content_detail=content,          # LLM 输出的文本片段
))
```

**DTO 定义**: `core/providers/tts/dto/dto.py`
- `TTSMessageDTO` 包含: `sentence_id`, `sentence_type`, `content_type`, `content_detail`

### 6.2 TTS 引擎核心方法

**文件**: `xiaozhi-server/core/providers/tts/base.py` **第276行**

```python
def tts_one_sentence(self, conn, content_type, content_detail=None):
    """单句 TTS 合成入口"""
    # 从 tts_text_queue 消费 TTSMessageDTO
    # 调用具体的 TTS 提供商（Azure/Edge/Baidu 等）
    # 结果放入 tts_audio_queue
```

TTS 后台线程持续消费 `tts_text_queue`，合成音频放入 `tts_audio_queue`。

---

## 七、向固件发送消息的出口

所有发往固件的消息最终通过 `conn.websocket.send()` 发送。以下为三大出口：

### 7.1 音频数据发送

**文件**: `xiaozhi-server/core/handle/sendAudioHandle.py` **第247-261行**

```python
async def _do_send_audio(conn, opus_packet, flow_control):
    if conn.conn_from_mqtt_gateway:
        # MQTT网关模式：带16字节头部
        await _send_to_mqtt_gateway(conn, opus_packet, timestamp, sequence)
    else:
        # 普通WS模式：直接发送原始Opus包
        await conn.websocket.send(opus_packet)     # ← 原始二进制音频
```

### 7.2 TTS 状态消息发送

**文件**: `xiaozhi-server/core/handle/sendAudioHandle.py` **第268-301行**

```python
async def send_tts_message(conn, state, text=None):
    message = {
        "type": "tts",
        "state": state,           # "start" / "sentence_start" / "stop"
        "session_id": conn.session_id,
    }
    if text is not None:
        message["text"] = textUtils.check_emoji(text)
    await conn.websocket.send(json.dumps(message))   # ← JSON控制消息
```

### 7.3 STT (语音转文字) 状态发送

**文件**: `xiaozhi-server/core/handle/sendAudioHandle.py` **第304-329行**

```python
async def send_stt_message(conn, text):
    stt_text = textUtils.get_string_no_punctuation_or_emoji(text)
    await conn.websocket.send(json.dumps({
        "type": "stt",
        "text": stt_text,
        "session_id": conn.session_id,
    }))
```

### 7.4 情感/表情下发出口

**文件**: `xiaozhi-server/core/connection.py` **第323-331行**（`_send_emotion_to_device`）

```python
await ws.send(json.dumps({
    "type": "llm",
    "emotion": emotion,          # "happy" / "neutral" / "sad"
    "session_id": self.session_id
}))
```

---

## 八、消息处理调用链路图（文本版）

### 8.1 上行消息（固件 → 服务器）

```
固件 → WebSocket
         │
         ▼
WebSocketServer._handle_connection() [websocket_server.py:83]
         │
         ▼
ConnectionHandler.handle_connection() [connection.py:335]
         │
         ├── async for message in websocket ───→ _route_message() [connection.py:477]
         │
         ├── str (JSON文本) ───────────────────→ handleTextMessage() [textHandle.py]
         │       │                                       │
         │       │                              TextMessageProcessor.process_message()
         │       │                              [textMessageProcessor.py]
         │       │                                       │
         │       │                              json.loads() → msg_json.get("type")
         │       │                                       │
         │       │                              ┌── "hello"  → HelloTextMessageHandler
         │       │                              ├── "abort"  → AbortTextMessageHandler
         │       │                              ├── "listen" → ListenTextMessageHandler
         │       │                              ├── "iot"    → IotTextMessageHandler
         │       │                              ├── "mcp"    → McpTextMessageHandler
         │       │                              ├── "server" → ServerTextMessageHandler
         │       │                              └── "ping"   → PingMessageHandler
         │
         └── bytes (音频) ──────────────────→ asr_audio_queue
                      │
                      ▼
                VAD 检测 → ASR 识别 → startToChat() [receiveAudioHandle.py:49]
                      │
                      ├── handle_user_intent() [intentHandler.py:20]
                      │     ├── check_direct_exit()
                      │     ├── checkWakeupWords() → 唤醒词回复
                      │     └── analyze_intent_with_llm() → intent分析
                      │
                      ├── ★ World 调度 [receiveAudioHandle.py:92]
                      │     └── conn.world.process(text) → 多角色分发
                      │
                      └── conn.chat(actual_text) [connection.py:1067]
                            │
                            ▼
                      LLM.response() / LLM.response_with_functions()
                            │
                            ▼
                      流式处理文本 + 工具调用
```

### 8.2 下行消息（服务器 → 固件）

```
LLM 流式文本
      │
      ▼
tts_text_queue ──→ TTS后台线程 ──→ tts_one_sentence()
      │                                   │
      │                                   ▼
      │                          tts_audio_queue
      │                                   │
      ▼                                   ▼
send_tts_message()              sendAudioMessage()
(sentence_start/stop)           (Opus音频包)
      │                                   │
      │                                   ▼
      │                          _do_send_audio()
      │                                   │
      ▼                                   ▼
conn.websocket.send(json)       conn.websocket.send(binary)
      │                                   │
      ▼                                   ▼
固件收到 {"type": "tts", ...}    固件收到 Opus 音频帧
```

### 8.3 完整端到端链路（listen → LLM → TTS → 固件）

```
固件: {"type":"listen","state":"detect","text":"今天天气怎么样"}
  │
  ▼  [服务器接收]
ListenTextMessageHandler.handle()
  │
  ▼  [intent检查]
handle_user_intent()
  ├─ checkWakeupWords → 非唤醒词，跳过
  └─ analyze_intent_with_llm → 返回无意图 → 继续
  │
  ▼  [LLM调用]
conn.chat("今天天气怎么样")        ← 线程池执行
  │
  ▼  [LLM流式响应]
LLM.response(dialogue)
  │
  ├─ textUtils.get_emotion()  → 发送表情到固件: {"type":"llm","emotion":"happy"}
  ├─ tts_text_queue.put(text) → TTS合成
  └─ 流式文本累积
  │
  ▼  [TTS合成]
TTS.consume_queue()
  ├─ TTS提供商(Edge/Azure) → Opus音频
  └─ tts_audio_queue.put(opus)
  │
  ▼  [发送到固件]
send_tts_message("sentence_start", "今天天气不错")  → {"type":"tts","state":"sentence_start","text":"今天天气不错"}
sendAudio(opus_packets)                             → 原始Opus二进制
send_tts_message("stop")                            → {"type":"tts","state":"stop"}
```

---

## 九、关键发现与架构特征

### 9.1 设计模式
- **策略模式**：`TextMessageHandler` 抽象基类 + 7个具体处理器，通过 `TextMessageHandlerRegistry` 注册
- **生产者-消费者模式**：`tts_text_queue` (LLM→TTS) 和 `tts_audio_queue` (TTS→发送)
- **异步非阻塞**：所有消息处理均为 `async/await`；长时间任务（LLM调用）通过 `ThreadPoolExecutor` 投递

### 9.2 新旧架构并存
- **旧版**：`startToChat()` → `conn.chat()` 单机器人模式
- **新版（World）**：`startToChat()` → `conn.world.process(text)` → 多角色调度

### 9.3 消息类型扩展点
- 新消息类型只需：定义枚举 → 实现Handler类 → 注册到 `TextMessageHandlerRegistry`

### 9.4 未发现的 type 处理
- `TextMessageProcessor` 第33行处理未知type：打 `收到未知类型消息` 日志，不抛出异常

---

## 附录：关键文件一览

| 文件 | 核心职责 |
|------|----------|
| `app.py` | 应用入口 |
| `websocket_server.py` | WebSocket服务器，连接管理 |
| `connection.py` | 连接处理器，消息路由，LLM/TTS编排 |
| `handle/textHandle.py` | 文本消息分发入口 |
| `handle/textMessageProcessor.py` | JSON消息解析+type路由 |
| `handle/textMessageHandlerRegistry.py` | 处理器注册中心 |
| `handle/textMessageType.py` | 消息类型枚举 |
| `handle/textMessageHandler.py` | 处理器抽象基类 |
| `handle/textHandler/*.py` | 7个具体处理器实现 |
| `handle/helloHandle.py` | hello消息处理 |
| `handle/abortHandle.py` | abort消息处理 |
| `handle/receiveAudioHandle.py` | 音频接收+startToChat |
| `handle/sendAudioHandle.py` | 音频+状态发送到固件 |
| `handle/intentHandler.py` | 意图识别 |
| `handle/reportHandle.py` | 聊天记录上报 |
| `handle/textHandler/listenMessageHandler.py` | listen消息（核心） |
| `providers/tts/base.py` | TTS引擎基类，tts_one_sentence |
| `providers/tools/device_iot.py` | IOT描述符/状态处理 |
| `providers/tools/device_mcp.py` | MCP协议消息处理 |
| `world.py` | World多角色调度器 |
| `character.py` | 角色定义 |
