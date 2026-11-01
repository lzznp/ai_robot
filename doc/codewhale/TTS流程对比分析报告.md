# TTS 流程对比分析报告

> 侦察时间：2026-07-19
> 对比范围：`xiaozhi-server-old/`（原始备份） vs `xiaozhi-server/`（当前工作目录）
> 核心文件：`core/connection.py` (chat方法)、`core/providers/tts/base.py`、`core/handle/sendAudioHandle.py`、`core/handle/receiveAudioHandle.py`、`core/handle/textHandler/listenMessageHandler.py`

---

## 1. 原始版本的 TTS 流程详解

### 1.1 整体时序（原始版本）

```
用户语音输入
    ↓
ASR 识别文本
    ↓
startToChat(conn, text)
    │
    ├─ send_stt_message(conn, text)          ← (A) 发送 TYPE=stt, text=用户输入
    │      ├── websocket.send({type:"stt", text:用户输入})   → 客户端显示"识别结果"
    │      └── send_tts_message(conn, "start")               → 客户端进入"准备接收"状态
    │
    ├─ conn.client_abort = False
    │
    └─ conn.executor.submit(conn.chat, text)  ← (B) 启动 LLM 流式对话
            │
            └── chat(query, depth=0):
                    │
                    ├── tts_text_queue.put(sentence_id, FIRST, ACTION)   ← (C) 通知TTS线程：新句子开始
                    │
                    ├── LLM 流式响应开始
                    │   for each chunk from LLM:
                    │       │
                    │       └── tts_text_queue.put(sentence_id, MIDDLE, TEXT, chunk)  ← (D) 流式文本分块入队
                    │
                    ├── tts_text_queue.put(sentence_id, LAST, ACTION)    ← (E) 通知TTS线程：句子结束
                    │
                    └── [如果工具调用结果需要TTS] → tts_one_sentence()
```

```
TTS 消费线程 (tts_text_priority_thread):
    │
    ├── 收到 FIRST → 重置状态、缓冲区、计数器
    │
    ├── 每个 MIDDLE TEXT 消息：
    │      ├── tts_text_buff.append(chunk)                    ← 追加到缓冲区
    │      ├── _get_segment_text()                            ← (F) 按标点符号切分
    │      │      └── 从 current_text 中找到最后一个标点位置
    │      │      └── 切片 segment = text[:last_punct+1]
    │      │      └── 更新 processed_chars
    │      │      └── 第一句话用宽松标点集（含逗号）
    │      │
    │      └── if segment_text:
    │             └── to_tts_stream(segment_text)             ← (G) 调用 TTS 合成 + 入音频队列
    │                    │
    │                    ├── MarkdownCleaner → 纠错词替换
    │                    ├── text_to_speak(text)              ← 实际 TTS API 调用
    │                    └── tts_audio_queue.put(FIRST, None, original_text, sentence_id)
    │                                                          ← (H) 信号：音频已就绪
    │
    └── 收到 LAST → _process_remaining_text_stream()          ← 将剩余文本也合成
                   → tts_audio_queue.put(LAST, ...)            → 标记结束
```

```
音频播放线程 (_audio_play_priority_thread):
    │
    ├── 从 tts_audio_queue 取消息
    │
    ├── if sentence_type == FIRST:
    │      └── sendAudioMessage(conn, FIRST, audio, text)    ← (I) 发送音频 + 信令
    │             │
    │             ├── send_tts_message(conn, "sentence_start", text)
    │             │      └── websocket.send({type:"tts", state:"sentence_start", text})
    │             │                                            ← 客户端显示字幕
    │             └── sendAudio(conn, audio)                   ← 发送音频帧
    │
    ├── if sentence_type == MIDDLE:
    │      └── sendAudio(conn, audio)                         ← 只发音频
    │
    └── if sentence_type == LAST:
           ├── sendAudio(conn, audio)
           └── send_tts_message(conn, "stop")                 ← (J) 停止信号
                  └── websocket.send({type:"tts", state:"stop"})
                  └── clearSpeakStatus()
```

### 1.2 原始版本的关键特征

| 环节 | 行为 |
|------|------|
| **分句策略** | **流式分句**：LLM 输出流式文本 → 每个 chunk 进入 `tts_text_buff` → `_get_segment_text()` 按标点切分（第一句话逗号即切，后续只有句号/问号/感叹号/分号才切）→ 合成音频 |
| **合成方式** | **流式合成**：切分出的每段文本立即调用 `to_tts_stream()` 进行 TTS 合成，合成完即入音频队列 |
| **sentence_start 时机** | **TTS 合成后、音频发送前**：`sendAudioMessage()` 中，FIRST 类型的消息会先发送 `sentence_start` 信令（包含当前句文本），然后发送音频帧 |
| **STT 消息时机** | **LLM 调用前**：`startToChat()` 中第一时间发送 `{type:"stt", text:用户输入}` + `{type:"tts", state:"start"}`，客户端立即显示用户说了什么，然后才开始 LLM 对话 |
| **文字/语音同步** | **天然同步**：每段文本在合成完成后立即发送 `sentence_start` + 音频，文字和语音打包在一起发送 |
| **中断处理** | **自然中断**：新对话时 `send_stt_message` 先发 `tts start`，然后 `handleAbortMessage` 已先打断了前一轮的 TTS |

---

## 2. 当前版本的 TTS 流程详解

### 2.1 整体时序（当前版本，SceneDispatcher 路径）

```
用户语音输入
    ↓
ASR 识别文本
    ↓
startToChat(conn, text)
    │
    ├── [意图处理、打断等...]
    │
    └── if conn.scene_dispatcher:                              ← SceneDispatcher 路径
           │
           ├── result = conn.process_with_scene(text)
           │      │
           │      └── scene_dispatcher.process(text, device_id)
           │             │
           │             ├── self.llm_adapter(messages)        ← (A) 同步调用 LLM，等全部返回
           │             │
           │             └── return {"actions": [{
           │                     "type": "tts",
           │                     "text": 完整响应,             ← 一次性拿到完整文本
           │                     "target": target_device,
           │                     "role": target_role
           │                 }], "response": 完整响应, ...}
           │
           ├── dispatch_actions(actions)
           │      │
           │      └── tts_one_sentence(conn, ContentType.TEXT, content_detail=完整响应)
           │             │
           │             └── re.split(r"([。！？!?；;\n])", 完整响应)    ← (B) 按标点切分
           │                    └── for each seg:
           │                           tts_text_queue.put(MIDDLE, TEXT, seg)  ← (C) 分段入TTS队列
           │
           ├── send_stt_message(conn, response_text)          ← (D) 发送 STT = 响应文本!
           │
           └── return
```

```
TTS 消费线程：与原始版本相同
    ├── 但没有 FIRST 消息 → 状态未重置！
    └── MIDDLE 文本 → _get_segment_text() → to_tts_stream() → 合成 → 入音频队列
```

```
音频播放线程：与原始版本相同
    ├── FIRST → send_tts_message("sentence_start", text) + sendAudio()
    ├── MIDDLE → sendAudio()
    └── LAST → sendAudio() + send_tts_message("stop")
```

### 2.2 关键问题：当前 SceneDispatcher 路径缺失了什么？

对比原始版本的正常路径（A→J），SceneDispatcher 路径：

| 环节 | 原始版本 | 当前版本 | 问题 |
|------|---------|---------|------|
| STT 消息发送 | `send_stt_message(conn, 用户输入)` **在 LLM 前** | `send_stt_message(conn, 响应文本)` **在 LLM 后** | (1) 用户输入**从不显示** (2) 响应文本在 `sentence_start` 之前先被 `stt` 类型发送，**文字全部先显示** |
| FIRST 消息 | `tts_text_queue.put(FIRST, ACTION)` 重置状态 | **没有 FIRST 消息** | TTS 线程的缓冲区、计数器、标志未被重置 |
| 分句方式 | 流式边收边切 | 一次性 `re.split` 按标点先切好再入队 | 切出的 seg 包含标点（如 `["你好", "。", "今天", "？"]`），很多 seg 是纯标点或空串 |
| `sentence_start` 时机 | 每段音频合成后发 | 与原始版本相同（TTS 合成后） | 本身正确，但文本已先由 `send_stt_message` 全部展示了 |
| 中断恢复 | `chat()` 内部处理 | **SceneDispatcher 行为内无中断处理** | `client_abort` 未在 SceneDispatcher 同步 LLM 调用中检查 |

---

## 3. 差异点对比表

| 维度 | 原始版本 | 当前版本 | 影响 |
|------|---------|---------|------|
| **LLM 调用方式** | 流式 (`response` 迭代器) | SceneDispatcher 中同步（`llm_adapter.__call__` 收集全部） | 当前版本要等 LLM 全部返回后才开始 TTS 处理 |
| **STT 显示内容** | 用户输入文本（`actual_text`） | SceneDispatcher 路径：**响应文本**（`response_text`） | **BUG：用户输入不会被显示；响应文本先全部显示到 stt 区域** |
| **STT 发送时机** | LLM 开始前 | SceneDispatcher 路径：LLM 完成后 | **切断了"用户说话→显示文本→开始处理"的连贯体验** |
| **TTS 分句方式** | 流式 `_get_segment_text()` 按标点切分 | `tts_one_sentence()` 中 `re.split` 按标点切分 | 当前的分句产生大量纯标点段（`。`、`！`等）入 TTS 队列，可能导致资源浪费 |
| **FIRST 信号** | 每次对话前发送 FIRST 重置 TTS 状态 | SceneDispatcher 路径：**无 FIRST 信号** | `is_first_sentence`、`tts_text_buff`、`processed_chars` 等状态未重置 |
| **`sentence_start` 信令** | 每句 TTS 合成完成后发送 | 同原始版本（代码相同） | 本身无差异 |
| **正文显示同步** | 每段 TTS 合成完 → `sentence_start(text)` + 音频 | `send_stt_message(响应文本)` 先展示全部文字 → 然后 `sentence_start` 逐段发 | **文字先全部显示，然后语音才逐段播报** |
| **中断检查** | `chat()` 中每个 LLM chunk 检查 `client_abort` | SceneDispatcher 同步 LLM 调用中无中断检查 | 用户打断后，LLM 仍会继续消耗 token |
| **Fallback 路径** | N/A | 回退路径（`send_stt_message(用户输入) + chat()`）与原版一致 | 此路径正常 |

---

## 4. 根因分析

### 问题现象：文字先全部显示，语音后分段播报

**根本原因：`send_stt_message` 被错误地传递了响应文本。**

在 SceneDispatcher 路径中（`receiveAudioHandle.py` 第92行）：

```python
if response_text:
    await send_stt_message(conn, response_text)  # ← 错误！应该用 actual_text
```

`send_stt_message` 的功能是：
1. 向客户端发送 `{type: "stt", text: 用户输入}` → 客户端显示"你说的是：..."
2. 向客户端发送 `{type: "tts", state: "start"}` → 客户端进入接收状态

当传入 `response_text` 时：
1. 客户端显示的是完整的 LLM 响应文本（**全部文字一下出现**）
2. 客户端进入接收状态
3. 之后 `dispatch_actions` → `tts_one_sentence` → TTS 合成 → 逐段发送 `sentence_start` + 音频
4. 用户看到：文字全部已显示，但语音在慢慢播

### 问题现象：语音播报频繁被中断

**多个原因叠加：**

1. **`send_stt_message` 中发送了 `tts "start"`** → 这会触发客户端的打断逻辑（视客户端实现而定，可能清除前一轮的音频缓冲区）
2. **SceneDispatcher 路径没有发送 FIRST 重置 TTS 状态** → `is_first_sentence` 可能为 False 导致分句使用严格标点集（不含逗号），影响流式合成节奏
3. **`tts_one_sentence` 的 `re.split` 分句方式产生空段和标点段** → 这些段进入 TTS 队列后可能被快速处理完成，导致多段声音密集播放，相互打断
4. **原始版本的中断保护（`client_abort` 检查）在 SceneDispatcher 的同步 LLM 调用中缺位**

---

## 5. 修复建议

### 修复一（最关键）：修正 `send_stt_message` 参数

**文件：** `xiaozhi-server/core/handle/receiveAudioHandle.py` 第92行

```python
# 当前（错误）：
if response_text:
    await send_stt_message(conn, response_text)

# 修复后：
# 先发送用户输入文本的 STT 消息（让客户端显示用户说了什么）
await send_stt_message(conn, actual_text)
```

**效果：** 用户输入正确显示在 STT 区域，`tts "start"` 在 LLM 处理前发送，符合原始设计语义。

### 修复二：SceneDispatcher 路径发送 `tts "start"` 信号

当前 SceneDispatcher 路径缺失了 `tts "start"` 信号（该信号由 `send_stt_message` 内部触发）。

**建议在 `process_with_scene` 之前发送 `send_tts_message(conn, "start", None)`**

```python
# 在 receiveAudioHandle.py SceneDispatcher 路径开头
await send_tts_message(conn, "start", None)  # 通知客户端开始接收
result = await conn.process_with_scene(actual_text)
```

### 修复三：修复 FIRST 信号的缺失

**SceneDispatcher 路径应当发送一个 FIRST 消息给 TTS 队列，以重置状态。**

```python
# 在 scene_dispatcher.py 的 process() 或 dispatch_actions() 中
self.tts.tts_text_queue.put(
    TTSMessageDTO(
        sentence_id=sentence_id,
        sentence_type=SentenceType.FIRST,
        content_type=ContentType.ACTION,
    )
)
```

### 修复四：修复 `tts_one_sentence` 的分段逻辑

当前 `tts_one_sentence` 使用 `re.split(r"([。！？!?；;\n])", content_detail)` 会产生相邻的标点段：

```python
# 输入："你好。今天天气真好！"
# 输出：["你好", "。", "今天天气真好", "！", ""]
```

标点段（`。`、`！`）被当作独立的 TEXT 段送入 TTS 队列。虽然有 `_get_segment_text()` 过滤，但会增加不必要的处理。

**建议：将标点合并到前一个文本段中：**

```python
def tts_one_sentence(self, conn, content_type, content_detail=None, ...):
    # 保留标点在文本段中
    segments = re.split(r"(?<=[。！？!?；;\n])", content_detail)
    segments = [s for s in segments if s.strip()]
    for seg in segments:
        self.tts_text_queue.put(
            TTSMessageDTO(...)
        )
```

### 修复五（可选）：SceneDispatcher 也使用流式 LLM

当前 SceneDispatcher 调用 `llm_adapter(messages)` 是同步阻塞的，要等 LLM 完整返回。这丢失了流式 TTS 的实时性。

**建议：如果流式体验重要，SceneDispatcher 也使用流式 LLM，边收文本边喂给 TTS。**

但这需要较大的重构（修改 LLMAdapter 接口），可以放在后期优化。

---

## 6. 推荐修复优先级

| 优先级 | 修复项 | 文件 | 改动量 | 效果 |
|--------|--------|------|--------|------|
| **P0** | 修复一：`send_stt_message` 参数 | `receiveAudioHandle.py` 第92行 | 1行 | 修复"文字全显"核心问题 |
| **P1** | 修复三：添加 FIRST 信号 | `scene_dispatcher.py` 或 `connection.py` | ~10行 | 修复 TTS 状态未重置问题 |
| **P2** | 修复二：添加 `tts "start"` 信号 | `receiveAudioHandle.py` | 1行 | 修复客户端状态同步 |
| **P3** | 修复四：优化分句逻辑 | `base.py` 的 `tts_one_sentence` | ~5行 | 减少空段和标点段处理 |
| **P4** | 修复五：流式 LLM | `scene_dispatcher.py` + `llm_adapter.py` | 较大 | 提升实时体验 |

---

## 7. 时序图对比

### 原始版本（正常）

```
用户输入
   │
   ▼
[STT] → 显示: "你说：xxx"
[TTS start] → 客户端准备接收
   │
LLM 流式开始 ──────────────►
   │                          │
   ├─ chunk1 ──► TTS队列       │
   │              ├─ 合成     │
   │              └─ sent_start("你好") + 音频  ← 文字和语音几乎同时
   │                          │
   ├─ chunk2 ──► TTS队列       │
   │              ├─ 合成     │
   │              └─ sent_start("今天天气真好") + 音频
   │                          │
   └─ ...                     │
                              │
[TTS stop] ◄──────────────────┘
```

### 当前版本（SceneDispatcher 路径，有 BUG）

```
用户输入
   │
   ▼
LLM 同步调用 ─► 等待完整响应 ──►
                                    │
                                    响应完成:
                                    │
                                    ├─ send_stt_message(响应文本)
                                    │      → 显示: 完整响应文本 ← 文字全部显示
                                    │      → [TTS start]
                                    │
                                    ├─ tts_one_sentence(完整响应)
                                    │      → 分段入队
                                    │      → 逐段合成
                                    │      → sent_start("你好") + 音频
                                    │      → sent_start("今天天气真好") + 音频  ← 语音滞后
                                    │
                                    └─ [TTS stop]
```

### 修复后的 SceneDispatcher 路径

```
用户输入
   │
   ▼
send_stt_message(用户输入) → 显示: "你说：xxx"
[TTS start] → 客户端准备接收
   │
LLM 同步调用 ─► 等待完整响应 ──►
                                    │
                                    响应完成:
                                    │
                                    ├─ FIRST → TTS 状态重置
                                    │
                                    └─ tts_one_sentence(完整响应)
                                           → 分段入队（含标点在文本中）
                                           → 逐段合成
                                           → sent_start("你好") + 音频
                                           → sent_start("今天天气真好") + 音频
                                           → [TTS stop]
```

---

## 8. 结论

| 项目 | 结论 |
|------|------|
| **原始版本分句方式** | 流式 `_get_segment_text()` 按标点切分，第一句宽松（含逗号），后续严格（句号/问号/感叹号） |
| **原始版本合成方式** | 流式：切分一段 → 立即合成 → 立即发送 `sentence_start` + 音频 |
| **原始版本 sentence_start 时机** | TTS 合成完成后，音频发送前 |
| **原始版本 STT 时机** | LLM 开始前，用于显示用户输入 + 触发 `tts start` |
| **原始版本同步机制** | 每段文字单独打包 `sentence_start(text)` + 音频，天然同步 |
| **当前版本关键差异** | (1) `send_stt_message` 传了响应文本而非用户文本 (2) 无 FIRST 信号 (3) `re.split` 分句不干净 (4) 同步 LLM 调用阻塞了流式 |

**一句话结论：当前 SceneDispatcher 路径中 `send_stt_message(conn, response_text)` 是导致"文字先全显、语音后分段播"的直接原因。** 这个调用原本应该传 `actual_text`（用户输入），却传了 `response_text`（完整 LLM 响应），使得客户端一次性显示了全部文字。P0 修复只需改这一行参数。
