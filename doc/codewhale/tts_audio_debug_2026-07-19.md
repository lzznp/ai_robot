# TTS 音频数据流诊断报告

> 日期：2026-07-19
> 核心文件：`core/providers/tts/base.py`, `core/handle/sendAudioHandle.py`, `core/scene_dispatcher.py`
> 当前症状：FIRST/LAST 信令正常（文字可显示），但无 MIDDLE 音频包（设备不发声）

---

## 1. 完整数据流链路图

```
┌─────────────────────────────────────────────────────────────────┐
│  【触发端】 SceneDispatcher.dispatch_actions()                  │
│  scene_dispatcher.py:104-108                                    │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  self.connection_handler.tts.tts_one_sentence(            │  │
│  │      conn, ContentType.TEXT, content_detail=full_text)    │  │
│  └──────────┬────────────────────────────────────────────────┘  │
└─────────────┼───────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│  【第一站】 TTSProviderBase.tts_one_sentence()                   │
│  base.py:276-294                                                │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  ★ MODIFIED: 把完整文本打包为一条 FIRST 消息               │  │
│  │  self.tts_text_queue.put(TTSMessageDTO(                   │  │
│  │      sentence_id=new_id,                                   │  │
│  │      sentence_type=SentenceType.FIRST,  ← 原来是 MIDDLE   │  │
│  │      content_type=ContentType.TEXT,                        │  │
│  │      content_detail=full_text,      ← 原来是逐段拆分     │  │
│  │  ))                                                        │  │
│  └──────────┬────────────────────────────────────────────────┘  │
└─────────────┼───────────────────────────────────────────────────┘
              │
              ▼  ← 队列边界 (tts_text_queue)
┌─────────────────────────────────────────────────────────────────┐
│  【第二站】 tts_text_priority_thread() 消费线程                   │
│  base.py:361-414                                                │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  收到 FIRST 消息 → 重置状态                               │  │
│  │  (processed_chars=0, tts_text_buff=[], is_first=True)     │  │
│  │                                                           │  │
│  │  ★ MODIFIED: 在 FIRST 分支中直接处理完整文本               │  │
│  │  1. tts_text_buff.append(full_text)    ← 放入缓冲区      │  │
│  │  2. _get_segment_text()                ← 按标点切分      │  │
│  │  3. if segment 存在:                                      │  │
│  │       to_tts_stream(segment, handle_opus)                 │  │
│  │  4. _process_remaining_text_stream(handle_opus) ← 处理剩余│  │
│  │  5. 主动放入 LAST 到 tts_audio_queue                      │  │
│  └──────────┬────────────────────────────────────────────────┘  │
└─────────────┼───────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│  【第三站】 to_tts_stream() —— 文本→音频合成                     │
│  base.py:123-191                    ← ★ 音频生成的核心！       │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  1. MarkdownCleaner.clean_markdown(text)                 │  │
│  │  2. correct_words 正则替换                                │  │
│  │  3. asyncio.run(self.text_to_speak(text, output_file))    │  │
│  │     └── EdgeTTS / 其他 TTS 提供商的实际 API 调用          │  │
│  │                                                           │  │
│  │  ┌─── 分支 A: delete_audio_file=True (默认) ──────────┐  │  │
│  │  │  text_to_speak 返回 audio_bytes                    │  │  │
│  │  │  ┌─ if audio_bytes:  ← ★★★ 这里容易断！ ★★★     │  │  │
│  │  │  │   tts_audio_queue.put(FIRST, None, text)       │  │  │
│  │  │  │   audio_bytes_to_data_stream(bytes, callback=   │  │  │
│  │  │  │       opus_handler=handle_opus)                │  │  │
│  │  │  │     → 每帧 Opus 调用 handle_opus               │  │  │
│  │  │  └─ else: 重试, 5次后放弃                          │  │  │
│  │  └───────────────────────────────────────────────────┘  │  │
│  │                                                           │  │
│  │  ┌─── 分支 B: delete_audio_file=False ────────────────┐  │  │
│  │  │  text_to_speak 写入 tmp_file                       │  │  │
│  │  │  tts_audio_queue.put(FIRST, None, text)  ★ 总是放!│  │  │
│  │  │  _process_audio_file_stream(tmp_file, callback=    │  │  │
│  │  │       opus_handler=handle_opus)                    │  │  │
│  │  └───────────────────────────────────────────────────┘  │  │
│  └──────────┬────────────────────────────────────────────────┘  │
└─────────────┼───────────────────────────────────────────────────┘
              │
              ▼  ← 队列边界 (tts_audio_queue)
┌─────────────────────────────────────────────────────────────────┐
│  【第四站】 _audio_play_priority_thread() 音频播放线程            │
│  base.py:416-474                                                │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  从 tts_audio_queue 取消息                                │  │
│  │  根据 sentence_type 分发：                                 │  │
│  │  ┌─ FIRST:  → sendAudioMessage(conn, FIRST, None, text)  │  │
│  │  ├─ MIDDLE: → sendAudioMessage(conn, MIDDLE, bytes, None)│  │
│  │  └─ LAST:   → sendAudioMessage(conn, LAST, [], text)     │  │
│  └──────────┬────────────────────────────────────────────────┘  │
└─────────────┼───────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│  【第五站】 sendAudioMessage() —— 信令+音频分发                   │
│  sendAudioHandle.py:20-53                                       │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  ● FIRST: send_tts_message("sentence_start", text)       │  │
│  │           → 客户端显示文字                                  │  │
│  │           sendAudio(conn, None) → 直接返回                  │  │
│  │                                                           │  │
│  │  ● MIDDLE: sendAudio(conn, opus_bytes)  ← ★ 音频走这里！ │  │
│  │            → _send_audio_with_rate_control                 │  │
│  │              → _do_send_audio(conn, bytes)                │  │
│  │                → conn.websocket.send(opus_packet)         │  │
│  │                                                           │  │
│  │  ● LAST: sendAudio(conn, []) → 直接返回                    │  │
│  │          send_tts_message("stop")                         │  │
│  │          → 客户端停止播放                                   │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. 关键代码位置速查表

| 环节 | 文件 | 行号 | 函数/代码 |
|------|------|------|-----------|
| TTS 触发 | `scene_dispatcher.py` | 104-108 | `dispatch_actions()` → `tts_one_sentence()` |
| 文本入列 | `base.py` | 276-294 | `tts_one_sentence()` — **用户修改点** |
| TTS 消费 | `base.py` | 361-414 | `tts_text_priority_thread()` — **用户修改点** |
| 文本切分 | `base.py` | 488-525 | `_get_segment_text()` |
| 文本→音频 | `base.py` | 123-191 | `to_tts_stream()` — **音频生成核心** |
| Opus推入队列 | `base.py` | 116-118 | `handle_opus()` |
| 剩余文本处理 | `base.py` | 557-573 | `_process_remaining_text_stream()` |
| 音频消费 | `base.py` | 416-474 | `_audio_play_priority_thread()` |
| 信令/音频发送 | `sendAudioHandle.py` | 20-53 | `sendAudioMessage()` — **用户修改点** |
| 速率控制 | `sendAudioHandle.py` | 105-133 | `sendAudio()` |
| 实际 WebSocket 发送 | `sendAudioHandle.py` | 247-353 | `_do_send_audio()` |
| 实际 TTS API | `edge.py` | 27-40 | `text_to_speak()` — 真正的 TTS 调用 |
| **TTS 存根** | **`default.py`** | **13-14** | **`text_to_speak()` — 仅打印错误！** |

---

## 3. 诊断：音频数据流断开点

### 症状还原

音频队列的理想内容：
```
[FIRST(None, text), MIDDLE(opus1), MIDDLE(opus2), ..., LAST([], text)]
           ↑                          ↑                         ↑
       sentence_start           音频数据包                    stop 信令
       文字显示成功              用户听不到                文字显示结束
```

当前实际队列内容（据症状推断）：
```
[FIRST(None, text), LAST([], text)]     ← 或 [LAST([], text)] 仅一个
           ↑                                        ↑
      句子显示                                    立即 stop
```

**MIDDLE 完全缺失 → 根本原因是 `handle_opus()` 从未被调用。**

### 三种最可能的断点

#### 断点 A：`to_tts_stream` 内部的 `text_to_speak` 失败（概率最高）

```python
# base.py:133-146 (Path A, delete_audio_file=True)
audio_bytes = asyncio.run(self.text_to_speak(text, None))
if audio_bytes:              # ← 断点：audio_bytes 为 None 或 b""
    tts_audio_queue.put(FIRST, None, ...)
    audio_bytes_to_data_stream(audio_bytes, callback=opus_handler)
    #                                    ^^^^
    #                            handle_opus 从未被调用
    break
else:
    max_repeat_time -= 1      # 重试 5 次，全部失败
```

**`asyncio.run(self.text_to_speak(...))` 失败的原因：**

| 子原因 | 触发条件 | 表现 |
|--------|---------|------|
| EdgeTTS 网络不可达 | TTS API 无法连接 | 抛异常 → 重试 → 5次后放弃 |
| EdgeTTS 配置错误 | `voice` 参数无效/API 密钥无效 | 抛异常 → 重试 → 5次后放弃 |
| `asyncio.run()` 运行时错误 | Python ≥3.12 在已有事件循环的线程中调用 | `RuntimeError` → 重试 → 放弃 |
| 返回空字节流 | 文本为空或 TTS 服务返回空 | `audio_bytes = b""` → `if audio_bytes:` 为 False |

#### 断点 B：`get_string_no_punctuation_or_emoji` 返回空字符串（概率中）

如果 `_get_segment_text()` 返回空字符串，`to_tts_stream` 不会被调用。
同一文本传给 `_process_remaining_text_stream()` 也被过滤掉。

```python
# base.py:508-514 (in _get_segment_text)
segment_text_raw = current_text[:last_punct_pos+1]
segment_text = textUtils.get_string_no_punctuation_or_emoji(segment_text_raw)
#              ^^ 如果此函数过滤掉所有字符 → "" → falsy
```

#### 断点 C：`_get_segment_text` 返回 None 且 `_process_remaining_text_stream` 也返回空（概率低）

仅当文本不含任何标点且 `_process_remaining_text_stream` 中的 `get_string_no_punctuation_or_emoji` 也过滤为空时发生。典型情况：纯符号文本。

---

## 4. 诊断日志（建议添加）

### 4.1 添加在 `to_tts_stream` 入口和出口

**base.py:123 (to_tts_stream 入口)** — 确认文本内容：
```python
def to_tts_stream(self, text, opus_handler=None):
    logger.bind(tag=TAG).info(f"[TTS_DIAG] to_tts_stream 收到文本: len={len(text)}, text={text[:50]}")
    original_text = text
    # ... 原有代码
```

**base.py:135-138 (text_to_speak 之后)** — 确认音频是否生成：
```python
audio_bytes = asyncio.run(self.text_to_speak(text, None))
logger.bind(tag=TAG).info(f"[TTS_DIAG] text_to_speak 返回: len={len(audio_bytes) if audio_bytes else 0}, type={type(audio_bytes)}")
if audio_bytes:
    # ...
```

**base.py:146 (audio_bytes_to_data_stream 之后)** — 确认音频转换：
```python
audio_bytes_to_data_stream(audio_bytes, ..., callback=opus_handler)
logger.bind(tag=TAG).info(f"[TTS_DIAG] audio_bytes_to_data_stream 完成")
```

### 4.2 添加在 `handle_opus`

**base.py:116** — 确认 Opus 帧是否进入队列：
```python
def handle_opus(self, opus_data: bytes):
    logger.bind(tag=TAG).info(f"[TTS_DIAG] handle_opus 被调用! len={len(opus_data)}")
    # ... 原有代码
```

### 4.3 添加在 `_audio_play_priority_thread`

**base.py:462-467** — 确认音频队列消费：
```python
logger.bind(tag=TAG).info(f"[TTS_DIAG] audio_play 出队: type={sentence_type}, text={text[:20] if text else 'None'}, audio_len={len(audio_datas) if isinstance(audio_datas, bytes) else 'N/A'}")
future = asyncio.run_coroutine_threadsafe(...)
```

### 4.4 添加在 `tts_text_priority_thread` 的 FIRST 分支

**base.py:378-391** — 确认切分结果：
```python
if ContentType.TEXT == message.content_type and message.content_detail:
    self.tts_text_buff.append(message.content_detail)
    segment_text = self._get_segment_text()
    logger.bind(tag=TAG).info(f"[TTS_DIAG] FIRST处理: segment_text={segment_text[:30] if segment_text else 'None'}")
    if segment_text:
        self.to_tts_stream(segment_text, opus_handler=self.handle_opus)
    has_remaining = self._process_remaining_text_stream(opus_handler=self.handle_opus)
    logger.bind(tag=TAG).info(f"[TTS_DIAG] FIRST处理: remaining={has_remaining}")
```

### 4.5 添加入口在 `sendAudioMessage`

**sendAudioHandle.py:20-22** — 确认音频队列消费到的消息类型：
```python
async def sendAudioMessage(conn, sentenceType, audios, text, sentence_id=None):
    conn.logger.bind(tag=TAG).info(f"[TTS_DIAG] sendAudioMessage: type={sentenceType}, text={text[:30] if text else 'None'}, audio_len={len(audios) if audios else 0}")
```

---

## 5. 修复建议

### 5.1 P0 修复：在 `to_tts_stream` 中对 `text_to_speak` 失败做兜底

**base.py:133-147** 修改：
```python
audio_bytes = asyncio.run(self.text_to_speak(text, None))
if audio_bytes:
    self.tts_audio_queue.put((SentenceType.FIRST, None, original_text, getattr(self, 'current_sentence_id', None)))
    audio_bytes_to_data_stream(
        audio_bytes, file_type=self.audio_file_type, is_opus=True,
        callback=opus_handler, sample_rate=self.conn.sample_rate,
        opus_encoder=self.opus_encoder,
    )
else:
    logger.bind(tag=TAG).error(f"[TTS] ❌ text_to_speak 返回空, text={original_text[:50]}")
    max_repeat_time -= 1
```

### 5.2 P0 辅助：即使 `text_to_speak` 失败也要放一个 FIRST 信令

在 `to_tts_stream` 的开头或 `tts_text_priority_thread` 中，确保 FIRST 信令一定发出：

**base.py:378** 补充：
```python
if message.sentence_type == SentenceType.FIRST:
    self.current_sentence_id = message.sentence_id
    # ... 重置状态 ...

    # ★ 先放一个 FIRST 信令到音频队列，保证 sentence_start 一定发出
    self.tts_audio_queue.put(
        (SentenceType.FIRST, None, message.content_detail, message.sentence_id)
    )

    if ContentType.TEXT == message.content_type and message.content_detail:
        # ... 原有处理 ...
```

### 5.3 P1 修复：恢复 `tts_one_sentence` 的分句逻辑（可选）

当前改动把整段文本作为一个 FIRST。如果 TTS 服务有文本长度限制（如 EdgeTTS 通常 300 字符以内），需要恢复分句：

**base.py:291** 修改回分句版本（保留标点在文本段中）：
```python
def tts_one_sentence(self, conn, content_type, content_detail=None, content_file=None, sentence_id=None):
    if not sentence_id:
        ...
    # 按标点切分，保留标点在前一个段中
    segments = re.split(r"(?<=[。！？!?；;\n])", content_detail)
    segments = [s for s in segments if s.strip()]
    if not segments:
        segments = [content_detail]  # 无标点时的兜底
    for i, seg in enumerate(segments):
        st = SentenceType.FIRST if i == 0 else SentenceType.MIDDLE
        self.tts_text_queue.put(
            TTSMessageDTO(
                sentence_id=sentence_id, sentence_type=st,
                content_type=content_type, content_detail=seg.strip(),
                content_file=content_file,
            )
        )
```

### 5.4 P2 修复：检查 `get_string_no_punctuation_or_emoji` 行为

在 `_get_segment_text` 和 `_process_remaining_text_stream` 中添加保护：

```python
segment_text = textUtils.get_string_no_punctuation_or_emoji(segment_text_raw)
if not segment_text:
    # 如果用现有文本被过滤为空，尝试直接用原始文本
    segment_text = segment_text_raw
```

---

## 6. 快速自检清单

按此顺序排查，找到哪个环节断了：

| # | 检查点 | 方法 | 预期 |
|---|--------|------|------|
| 1 | `tts_one_sentence` 是否被调用 | 在 scene_dispatcher `dispatch_actions` 加日志 | ✅ 调用 |
| 2 | `FIRST` 消息是否进入 `tts_text_queue` | 在 `tts_text_priority_thread` 入口加日志 | ✅ 收到 FIRST |
| 3 | `_get_segment_text()` 切分结果 | 加日志看 segment_text | ✅ 非空非None |
| 4 | `to_tts_stream()` 是否被调用 | 函数入口加日志 | ✅ 被调用 |
| 5 | `text_to_speak()` 返回值 | 在调用后加日志 | ✅ 返回非空 bytes |
| 6 | `handle_opus()` 是否被调用 | 函数入口加日志 | ✅ 被调用 |
| 7 | `MIDDLE` 消息是否进入 `tts_audio_queue` | 在 `handle_opus` 加日志 | ✅ 有数据 |
| 8 | `sendAudioMessage` 是否收到 MIDDLE | 函数入口加日志 | ✅ 收到 |
| 9 | `sendAudio()` → `_do_send_audio()` → ws.send | 每一步加日志 | ✅ Opus 包发出 |

**如果在第 5 步就断了：** 问题在 TTS 服务本身（EdgeTTS 网络/配置问题）。检查 `config.yaml` 中 EdgeTTS 配置是否正确、网络是否可达。

**如果在第 6 步或第 7 步断了：** 问题在 `audio_bytes_to_data_stream` 未能正确调用 callback。检查 `audio_bytes_to_data_stream` 的实现和音频格式兼容性。

**如果在第 9 步断了：** 问题在 WebSocket 连接（已经关闭或异常），查看 `_do_send_audio` 中的 `[TTS] ❌` 错误日志。

---

## 7. 结论

```
症状: FIRST/LAST 信令正常 → 文字能显示
      无 MIDDLE 音频包    → 设备不发声
                            
根因: handle_opus() 从未被调用
      → 意味着 to_tts_stream 中没有产生 Opus 帧
      → 意味着 text_to_speak 返回空或失败
      → 最可能: EdgeTTS 配置/网络/运行时问题
      → 或: 修改后的 tts_text_priority_thread 中
            _get_segment_text() 返回空文本
```

**建议立即添加第 4 节中的诊断日志，重启服务，发起一次对话，然后查看日志。** 根据 `[TTS_DIAG]` 输出可以精确定位到断点。
