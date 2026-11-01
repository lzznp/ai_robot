# TTS 文字显示与语音播报节奏同步分析报告

> 侦察目标：LLM 流式响应 → 文字显示 → TTS 合成的数据流与节奏不一致根因  
> 侦察日期：2026-07-19  
> 覆盖版本：xiaozhi-server 当前工作树 + esp32-firmware `application.cc`

---

## 1. 关键代码位置

### 1.1 LLM 流式响应入口 — `connection.py`

| 位置 | 代码 | 说明 |
|------|------|------|
| L1168 | `def chat(self, query, depth=0)` | LLM 对话主入口，在线程池中执行 |
| L1179 | `self.dialogue.put(Message(role="user", content=query))` | 用户消息写入对话历史（一次性） |
| L1180-1186 | `tts_text_queue.put(TTSMessageDTO(FIRST, ACTION))` | TTS 队列放入空 FIRST 标记 |
| L1261-1325 | `for response in llm_responses:` | **流式循环**：逐 chunk 处理 LLM 响应 |
| L1307-1313 | `textUtils.get_emotion(self, content)` | 仅首个有内容的 chunk 触发（emotion_flag 控制） |
| L1317-1325 | **每个 chunk 都放入 `tts_text_queue`** | `self.tts.tts_text_queue.put(TTSMessageDTO(MIDDLE, TEXT, chunk))` |
| L1481-1484 | `text_buff = "".join(response_message)` | **流结束后**一次性拼接完整文本→写入 dialogue |
| L1486-1493 | `tts_text_queue.put(TTSMessageDTO(LAST, ACTION))` | TTS 队列放入空 LAST 标记 |

### 1.2 TTS 文本消化线程 — `base.py`

| 位置 | 代码 | 说明 |
|------|------|------|
| L368-409 | `def tts_text_priority_thread(self)` | 后台线程，消费 `tts_text_queue` |
| L385-389 | `ContentType.TEXT` 分支 | 将文本追加到 `tts_text_buff`，调 `_get_segment_text()` 找边界 |
| L483-520 | `def _get_segment_text(self)` | **流式分句核心**：在累积文本中找最后一个标点边界 |
| L490-493 | `first_sentence_punctuations` vs `punctuations` | 第一句用 `，~、,.!?；:`，后续句用 `。？！!；：` |
| L503-514 | 找到标点后返回 segment | 例如 `你好，` → 返回 `你好，` |
| L515-520 | 未找到标点时 | 返回 `None`，等待更多流数据 |
| L389 | `self.to_tts_stream(segment_text, ...)` | 每个 segment 独立发起 TTS 合成 |
| L138 | `self.tts_audio_queue.put((FIRST, None, original_text, ...))` | TTS 合成前先放入 **FIRST+文本** 到音频队列 |
| L118 | `self.tts_audio_queue.put((MIDDLE, opus_data, None, ...))` | 音频数据放入队列，**text 参数为 None** |

### 1.3 音频播放线程 — `base.py`

| 位置 | 代码 | 说明 |
|------|------|------|
| L411-469 | `def _audio_play_priority_thread(self)` | 后台线程，消费 `tts_audio_queue` |
| L458-461 | `asyncio.run_coroutine_threadsafe(sendAudioMessage(...))` | 每个音频包都发往 `sendAudioMessage` |

### 1.4 TTS 信令发送 — `sendAudioHandle.py`

| 位置 | 代码 | 说明 |
|------|------|------|
| L20-53 | `async def sendAudioMessage(conn, sentenceType, audios, text, ...)` | 分发音视频与状态 |
| L29-42 | **`if sentenceType == FIRST:`** → `send_tts_message("sentence_start", text)` | 仅 FIRST 类型触发文字显示 |
| L44 | `await sendAudio(conn, audios)` | 发送音频数据（MIDDLE 类型调用此行） |
| L50-53 | `if sentenceType == LAST:` → `send_tts_message("stop")` | 句尾发送停止信号 |
| L268-301 | `async def send_tts_message(conn, state, text=None)` | 构造 `{"type":"tts","state":"sentence_start","text":...}` 发往设备 |
| L270-271 | `if text is None and state == "sentence_start": return` | **text=None 时 sentence_start 静默跳过** |

### 1.5 固件端消息处理 — `application.cc`

| 位置 | 代码 | 说明 |
|------|------|------|
| L484-491 | `"sentence_start"` 处理 | `display->SetChatMessage("assistant", text)` — 显示助手文本 |
| L493-500 | `"stt"` 处理 | `display->SetChatMessage("user", text)` — 显示用户文本 |
| L501-507 | `"llm"` 处理 | `display->SetEmotion(emotion)` — 更新表情 |

### 1.6 SceneDispatcher 显示路径 — `scene_dispatcher.py`

| 位置 | 代码 | 说明 |
|------|------|------|
| L194-198 | `device_manager.send(target, {"type":"stt","text":text,...})` | **立即发送完整文本**（作为 stt 类型→显示为用户消息） |
| L200-204 | `connection_handler.tts.tts_one_sentence(..., content_detail=text)` | 同一文本通过 `tts_one_sentence` 触发分段 TTS 合成 |

### 1.7 `tts_one_sentence` 分句逻辑 — `base.py`

| 位置 | 代码 | 说明 |
|------|------|------|
| L276-302 | `def tts_one_sentence(self, conn, content_type, content_detail, ...)` | **整句一次性拆分成标点分段**：`re.split(r"([。！？!?；;\n])", content_detail)` |
| L292-302 | 每个 seg 放入 tts_text_queue | 每个标点段独立入队，独立合成 |

### 1.8 dialogue 写入时机 — `connection.py`

| 位置 | 代码 | 说明 |
|------|------|------|
| L1179 | `self.dialogue.put(Message(role="user", content=query))` | 用户文本一次性写入 |
| L1484 | `self.dialogue.put(Message(role="assistant", content=text_buff))` | **LLM 流结束后**一次性写入完整助手回复 |
| L1404 | `self.dialogue.put(Message(role="assistant", content=da_response))` | direct_answer 路径一次性写入 |
| L1429 | `self.dialogue.put(Message(role="assistant", content=streamed_text))` | 工具调用路径（流式文本部分）一次性写入 |
| L1521 | `self.dialogue.put(Message(role="assistant", content=text))` | 工具结果路径一次性写入 |

---

## 2. 数据流图

### 2.1 正常 LLM 流式路径（非 SceneDispatcher）

```
LLM 流式响应
   │
   ├── [chunk 1] "你好，"
   │    ├── response_message.append("你好，")  ← 累加
   │    ├── tts_text_queue.put(MIDDLE, TEXT, "你好，")
   │    │    └── tts_text_priority_thread
   │    │         └── tts_text_buff += "你好，"
   │    │         └── _get_segment_text() → 找到"，" → 返回 "你好，"
   │    │         └── to_tts_stream("你好，")
   │    │              ├── tts_audio_queue.put(FIRST, None, "你好，")
   │    │              ├── text_to_speak("你好，")  ← TTS 合成耗时
   │    │              └── tts_audio_queue.put(MIDDLE, opus, None)
   │    │                   └── _audio_play_priority_thread
   │    │                        ├── sendAudioMessage(FIRST, None, "你好，")
   │    │                        │    └── send_tts_message("sentence_start", "你好，")
   │    │                        │         └── ws.send({"type":"tts","state":"sentence_start","text":"你好，"})
   │    │                        │              └── [固件] SetChatMessage("assistant", "你好，")
   │    │                        └── sendAudioMessage(MIDDLE, opus, None)
   │    │                             └── sendAudio(opus) → ws.send(opus_bytes)
   │    │
   │    └── textUtils.get_emotion()  ← 仅首个 chunk 触发
   │
   ├── [chunk 2] "今天天气真不错"
   │    ├── response_message.append("今天天气真不错")  ← 累加
   │    └── tts_text_queue.put(MIDDLE, TEXT, "今天天气真不错")
   │         └── tts_text_buff += "今天天气真不错"
   │         └── _get_segment_text() → 无标点 → 返回 None（等待更多数据）
   │
   ├── [chunk 3] "。你吃饭了吗？"
   │    ├── response_message.append("。你吃饭了吗？")
   │    ├── tts_text_queue.put(MIDDLE, TEXT, "。你吃饭了吗？")
   │    │    └── tts_text_buff += "。你吃饭了吗？"
   │    │    └── _get_segment_text() → 找到"。" → 返回 "今天天气真不错。"
   │    │    └── to_tts_stream("今天天气真不错。")  ← 第二段 TTS 合成耗时
   │    │         └── ... (同上，送 sentence_start + opus)
   │    │
   │    └── _get_segment_text() → 找到"？" → 返回 "你吃饭了吗？"  ← 第三段
   │         └── to_tts_stream("你吃饭了吗？")  ← 第三段 TTS 合成耗时
   │
   └── [流结束]
        ├── response_message 全部累加完毕
        ├── dialogue.put(assistant, "你好，今天天气真不错。你吃饭了吗？")  ← 一次性写入完整文本
        └── tts_text_queue.put(LAST, ACTION)
             └── tts_audio_queue.put(LAST, [], ...)
                  └── send_tts_message("stop")
```

### 2.2 SceneDispatcher 路径

```
POST /api/text (或 startToChat → process_with_scene)
   │
   ├── scene_dispatcher.process(text, device_id)
   │    └── world.process(text) → ["瓦力: 你好，今天天气真不错！"]
   │    └── 解析 → actions = [{"type":"tts","text":"你好，今天天气真不错！","target":"..."}]
   │
   └── dispatch_actions(actions)
        │
        ├── device_manager.send(target, {"type":"stt","text":"你好，今天天气真不错！",...})
        │    └── ws.send(json)  ← 完整文本一次性到达设备
        │         └── [固件] SetChatMessage("user", "你好，今天天气真不错！")
        │              ↑ 屏幕立即显示完整句子（但角色是 user）
        │
        └── connection_handler.tts.tts_one_sentence(self, TEXT, content_detail="你好，今天天气真不错！")
             └── re.split([。！？!?；;\n]) → ["你好，今天天气真不错！"]
             └── tts_text_queue.put(MIDDLE, TEXT, "你好，今天天气真不错！")
                  └── tts_text_priority_thread
                       └── _get_segment_text() → 无标点（整句只有一个"！"） → 等待
                       └── [收到 LAST 时] → _process_remaining_text → 返回"你好，今天天气真不错！"
                       └── to_tts_stream("你好，今天天气真不错！")
                            ├── text_to_speak("你好，今天天气真不错！")  ← 整句 TTS 合成耗时
                            ├── tts_audio_queue.put(FIRST, None, "你好，今天天气真不错！")
                            │    └── send_tts_message("sentence_start", "你好，今天天气真不错！")
                            │         └── [固件] SetChatMessage("assistant", "你好，今天天气真不错！")
                            └── tts_audio_queue.put(MIDDLE, opus, None)
                                 └── sendAudio(MIDDLE, opus) → ws.send(opus_bytes)
```

---

## 3. 一次性 vs 增量/流式操作对照

| 操作 | 发生时机 | 一次性/增量 | 数据内容 |
|------|---------|------------|---------|
| LLM 流式接收 | 流式循环 L1261-1325 | **增量**（每个 chunk） | 逐字/词/短语 |
| `response_message.append()` | 每个非工具调用的 chunk | **增量** | 逐 chunk |
| `tts_text_queue.put(MIDDLE, TEXT, chunk)` | 每个非工具调用的 chunk | **增量** | 逐 chunk |
| `_get_segment_text()` 分句 | tts_text_priority_thread 内 | **增量 + 标点边界** | 按标点分割的 segment |
| `to_tts_stream(segment)` | 每找到一个标点 segment | **分段** | 标点分隔的文本段 |
| `text_to_speak()` TTS 合成 | 每个 segment 调用 | **分段** | 每个 segment 独立合成 |
| `send_tts_message("sentence_start", text)` | 每个 `to_tts_stream` 的 FIRST | **分段**（仅 FIRST 触发） | 当前 segment 文本 |
| `sendAudio(opus)` | `handle_opus` 每次回调 | **增量**（每帧音频） | Opus 音频帧 |
| `dialogue.put(assistant, text_buff)` | **流结束后** L1484 | **一次性** | 完整拼接文本 |
| `send_stt_message(actual_text)` | startToChat 开头 L229 | **一次性** | 用户原始文本 |
| SceneDispatcher: `send(type="stt")` | dispatch_actions | **一次性** | 完整响应文本 |
| SceneDispatcher: `tts_one_sentence()` | dispatch_actions | **一次性拆→分段合成** | 拆标点后逐段合成 |
| `textUtils.get_emotion()` | 首个有内容 chunk | **一次性**（emotion_flag 控制） | 仅首次 |

---

## 4. 根因分析

### 🔴 根因 1：文字显示与 TTS 合成共用文本但时序不同步（致命）

**核心矛盾**：
- **文字显示**（`sentence_start`）的数据来自 TTS 合成结果的回调，**仅在 `to_tts_stream()` 完成 TTS 合成后才发送**
- **但文本在 `handle_opus` 回调中被丢弃**（`text=None`），所以 `sentence_start` 文本来自 `to_tts_stream()` 中预先放入的 `FIRST` 条目
- **每条 TTS 合成独立耗时**：`text_to_speak()` 调用外部 TTS API 有网络延迟

**结果**：每个 segment 的 `sentence_start` 文本**必须等待该 segment 的 TTS 合成完成**才能发出。但合成是分段的，所以文字更新是"跳变式"的：第一个 segment 合成完→显示第一段文本→等第二段合成完→显示更多文本。这个过程如果是"你好，"（短）+"今天天气真不错。"（长），就会出现"你好"先出现、卡顿、再出现"今天天气真不错"的现象。

### 🔴 根因 2：SceneDispatcher 路径中 STT 消息瞬间下发完整文本

**位置**：`scene_dispatcher.py:194-198`

```python
await self.device_manager.send(target, {
    "type": "stt",        # ← 显示为用户消息，不是助手消息
    "text": text,         # ← 完整文本
    "session_id": self.connection_handler.session_id
})
```

这个 `type: "stt"` 消息不经过 TTS 队列，直接被 `DeviceManager.send()` 发出。设备固件在 `application.cc:493` 将其处理为 `SetChatMessage("user", text)`。文本**瞬间显示**在屏幕上。

然后 `tts_one_sentence(text)` 才触发 TTS 合成，音频需要排队、合成、播放。一个立即到，一个慢半拍，形成"文字先出，语音后补"的撕裂感。

⚠️ **额外 bug**：`type:"stt"` 在固件端被渲染为 **user 消息**（`SetChatMessage("user", ...)`），不是 assistant 消息。这意味着助手回复的内容被错误标记为用户说的。

### 🔴 根因 3：流式 LLM 路径下 `sentence_start` 只对 FIRST 类型生效

**位置**：`base.py:138` + `sendAudioHandle.py:29-42`

`to_tts_stream()` 在合成前先放入：
```python
self.tts_audio_queue.put((SentenceType.FIRST, None, original_text, current_sentence_id))
```

然后音频流以 MIDDLE 类型放入。`sendAudioMessage` 仅在 `sentenceType == FIRST` 时调用 `send_tts_message("sentence_start", text)`。因此**每段 TTS 合成仅触发一次文字更新**。

但多个 segment 的 `sentence_start` 会**依次覆盖**设备的显示内容（因为 `SetChatMessage` 是替换式的）。所以屏幕上的助手消息会逐个 segment 跳变更新，而不是平滑滚动。

### 🟡 根因 4：TTS 合成与文本流共用 `tts_text_buff`，但不同步

**位置**：`base.py:385-389` + `base.py:483-520`

`tts_text_priority_thread` 将 LLM 流式 chunk 累加到 `tts_text_buff`，然后 `_get_segment_text()` 查找标点边界。这个机制本身是合理的，但：

1. **如果 LLM chunk 很小且不包含标点**（如逐字流式），`_get_segment_text()` 会一直返回 `None`
2. TTS 合成不会启动，直到收到包含标点的 chunk 或收到 LAST
3. **用户听到第一个词之前可能有明显延迟**（等待标点出现才合成）

### 🟢 根因 5：`handle_opus` 回调中文本丢失

**位置**：`base.py:116-118`

```python
def handle_opus(self, opus_data: bytes):
    self.tts_audio_queue.put((SentenceType.MIDDLE, opus_data, None, ...))
```

第三个参数 `text` 硬编码为 `None`。而 `sendAudioMessage` 中 `send_tts_message("sentence_start", text)` 在 `text=None` 时会**静默跳过**（`sendAudioHandle.py:270`）。所以流式合成场景下 `sentence_start` 的文本完全来自 `to_tts_stream()` 预先放入的 `FIRST` 条目，而不是回调中的实时文本。

### 🟢 根因 6：`emotion_flag` 与节奏无关

**位置**：`connection.py:1259, 1307-1313`

`emotion_flag` 是一个对话轮次内的单次触发开关，只控制 `textUtils.get_emotion()` 是否执行。该函数发送一个独立的 `{"type":"llm","text":emoji,"emotion":emotion}` WebSocket 消息。它与 TTS 文字显示节奏**无关**，不影响同步问题。

---

## 5. 修复建议

### 5.1 🥇 首推：先积累完整句子再合成（整句合成模式）

**思路**：TTS 不要拆分段，等收到完整句子（以句号/问号等结尾）后再合成，并一次性下发文本显示。

**修改 `connection.py` chat 方法**：

```python
# 修改前：每个 LLM chunk 立即入 TTS 队列
self.tts.tts_text_queue.put(TTSMessageDTO(
    sentence_id=current_sentence_id,
    sentence_type=SentenceType.MIDDLE,
    content_type=ContentType.TEXT,
    content_detail=content,
))

# 修改后：将所有 chunk 累积到缓冲区，检测到完整句子时再入队
self._stream_buffer += content
# 检测句子边界（。！？等）
while True:
    match = re.search(r'[。！？!?\n]', self._stream_buffer)
    if match:
        sentence = self._stream_buffer[:match.end()]
        self._stream_buffer = self._stream_buffer[match.end():]
        self.tts.tts_text_queue.put(TTSMessageDTO(
            sentence_id=current_sentence_id,
            sentence_type=SentenceType.FIRST,  # ← 改为 FIRST
            content_type=ContentType.TEXT,
            content_detail=sentence,
        ))
    else:
        break
# 流结束时处理剩余的 buffer
```

这样每个完整句子是一次 TTS 合成，文字显示（`sentence_start`）和语音播报的节奏一致。

### 5.2 🥈 SceneDispatcher 路径修复：移除单独的 STT 消息

**修改 `scene_dispatcher.py` dispatch_actions**：

```python
# 修改前：先发 STT（完整文本）再触发 TTS
await self.device_manager.send(target, {
    "type": "stt",
    "text": text,
    "session_id": self.connection_handler.session_id
})
self.connection_handler.tts.tts_one_sentence(
    self.connection_handler,
    ContentType.TEXT,
    content_detail=text
)

# 修改后：不提前发 STT，让 TTS 的 sentence_start 自然携带文本
self.connection_handler.tts.tts_one_sentence(
    self.connection_handler,
    ContentType.TEXT,
    content_detail=text
)
# 如果确实需要即时显示，用 type: "tts" + state: "sentence_start" 代替 type: "stt"
```

### 5.3 🥉 `to_tts_stream` 中使用真实的文本参数

**修改 `base.py:138` 和 `base.py:187`**：

```python
# 修改前：text 在 handle_opus 中为 None
self.tts_audio_queue.put((SentenceType.FIRST, None, original_text, ...))

# 修改：将 original_text 通过回调传给 handle_opus
self.tts_audio_queue.put((SentenceType.FIRST, None, original_text, ...))
# handle_opus 中保留 text（但不一定需要改，因为 FIRST 已经传达了文本）
```

### 5.4 流式文字显示跟随 TTS 节奏（增量显示）

**修改 `sendAudioHandle.py:sendAudioMessage`**：在非 `FIRST` 类型时也发送 `sentence_start`

```python
# 在 sendAudio 前增加：每个非空的 text 都推送
if sentenceType != SentenceType.FIRST and text is not None and text.strip():
    await send_tts_message(conn, "sentence_start", text)
```

但这样做会频繁推送小段文本，取决于 LLM chunk 大小。更好的方式是在 `_get_segment_text()` 返回有效 segment 时才推送。

### 5.5 对话历史写入改为增量

**位置**：`connection.py:1484`

当前 `dialogue.put(assistant, text_buff)` 在流结束后一次性写入。对于超长对话这可能不是问题，但如果希望在流式过程中就更新历史（以便发生打断时历史更准确），可以改为：

```python
# 在每个 chunk 处理时增量写入 dialogue
if not tool_call_flag and content is not None and len(content) > 0:
    self.dialogue.put(Message(role="assistant", content=content))
```

但需注意对话历史中出现"半句话"的问题，建议与打断处理配合使用。

---

## 6. 总结

| 侦察项 | 结论 |
|--------|------|
| LLM 响应是整段还是流式分片？ | **流式分片**（`connection.py:1261` 逐 chunk） |
| dialogue 写入时机？ | **一次性写入**完整合并文本（`connection.py:1484`，流结束后） |
| `display->SetChatMessage` 触发时机？ | 固件端由 `{"type":"tts","state":"sentence_start"}` 触发（`application.cc:484-491`），**每段 TTS 合成完成后发送一次** |
| TTS 合成按整句还是流式分片？ | `tts_text_priority_thread` 中按 **标点边界分片**（`_get_segment_text`），但 LLM chunk 粒度不确定 |
| 文字显示和 TTS 合成是否共用同一个文本流？ | **共用 `tts_text_queue`**，但分道扬镳：文字通过 `sentence_start` 推送，音频通过 `opus` 帧推送。SceneDispatcher 路径额外走 `DeviceManager.send(type="stt")` 旁路 |
| `get_emotion` 和 `emotion_flag` 是否影响节奏？ | **无关**。一次性触发，独立消息通道 |

### 根因一句话总结

> **TTS 按标点分段独立合成**（每个 segment 独立 `text_to_speak` 调用），而 **SceneDispatcher 路径提前发送完整文本**（`type:"stt"` 旁路）或 **流式路径的 `sentence_start` 只能跟随 segment 分批到达**。文字先到、音频后补的撕裂感由此产生。

### 修复优先级

| 优先级 | 方案 | 效果 |
|--------|------|------|
| 🔴 P0 | 5.1 整句合成模式 | 彻底消除文字快于语音的问题 |
| 🔴 P0 | 5.2 移除 STT 旁路 | 消除 SceneDispatcher 路径的文本提前显示 |
| 🟡 P1 | 5.4 文字跟随节奏 | 替换式文字更新改为逐步追加 |
| 🟢 P2 | 5.5 增量 dialogue 写入 | 打断恢复更准确 |
