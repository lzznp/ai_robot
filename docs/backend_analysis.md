# Xiaozhi-Server 后端架构分析

> 生成时间：2026-06-22  
> 分析范围：`core/connection.py` LLM 流式响应 → TTS 下发全链路

---

## 精简表格总览

| # | 问题 | 文件路径 | 行号 | 函数名 | 说明 |
|---|------|---------|------|--------|------|
| 1 | `_clean_response_garbage()` 在哪 | `core/connection.py` | 1608 | `_clean_response_garbage()` | **输入**: `text` (str) — LLM 原始响应文本。**输出**: `str` — 清理后的文本。`@staticmethod`，过滤仅由 JSON 闭合符号（`"'})）`）组成的行（≤8字符），并用正则清除末尾残留的 `"'}\]]` 符号 |
| 2 | LLM 流式返回后调用链 | `core/connection.py` → `core/providers/tts/base.py` → `core/handle/sendAudioHandle.py` | 详见下方流程图 | 见下方调用链 | 顺序: ① `llm.response()` ② 逐 chunk `tts_text_queue.put(TTSMessageDTO)` ③ `tts_text_priority_thread()` 消费 ④ `to_tts_stream()` ⑤ `handle_opus()` ⑥ `tts_audio_queue.put()` ⑦ `_audio_play_priority_thread()` ⑧ `sendAudioMessage()` ⑨ `sendAudio()` + `send_tts_message()` |
| 3 | LLM→tts_text_queue 之间有无钩子 | `core/connection.py` / `core/providers/tts/base.py` | — | `tts_one_sentence()` / `tts_text_priority_thread()` | **有现成钩子**：① `tts_one_sentence()` (base.py:276) 封装了 `tts_text_queue.put()`，可重写；② `tts_text_priority_thread()` (base.py:368) 是消费者线程，从队列取文本后调用 `to_tts_stream()`，是最佳自定义逻辑插入点；③ `handle_opus()` (base.py:116) 是 opus 编码后的回调 |
| 4 | 下发函数在哪个文件 | `core/handle/sendAudioHandle.py` | 266 / 333 | `send_tts_message()` / `send_display_message()` | 均通过 `await conn.websocket.send(json.dumps(message))` 发送 JSON 文本帧。`send_tts_message` 发送 `{"type":"tts","state":...,"session_id":...,"text":...}`；`send_display_message` 发送 `{"type":"stt","text":...,"session_id":...}` |
| 5 | 是否有通用 `send_command()` | — | — | — | **没有**。每种消息类型有独立函数：`send_tts_message()`（TTS状态）、`send_stt_message()`（语音识别显示）、`send_display_message()`（纯显示）、`sendAudio()`（音频二进制帧）、`sendAudioMessage()`（编排器）。所有函数直接调 `conn.websocket.send()`，无中间抽象层 |

---

## 详细调用链（问题 2 扩展）

```
┌─────────────────────────────────────────────────────────────────┐
│  core/connection.py :: chat()                                   │
│                                                                 │
│  ① llm.response() / llm.response_with_functions()    [975/983] │
│     ↓ 流式 yield                                                │
│  ② 逐 chunk 推入队列                                           │
│     ├─ 非 function_call 模式:                                   │
│     │   tts_text_queue.put(TTSMessageDTO(MIDDLE, TEXT, chunk))  │
│     │   [1057-1064]                                             │
│     └─ function_call + direct_answer 模式:                      │
│         _extract_direct_answer_response()  [1024]               │
│         _clean_response_garbage()           [1031]               │
│         tts_text_queue.put(...)             [1034-1041]          │
│                                                                 │
│  ③ direct_answer 结束后:                                       │
│     ├─ _clean_response_garbage(remaining)    [1130]              │
│     ├─ tts_text_queue.put(remaining)         [1132]              │
│     └─ store_tts_text() + dialogue.put()    [1142-1143]         │
│                                                                 │
│  ④ 真实工具调用结果处理:                                       │
│     _handle_function_result()  [1216]                           │
│     └→ tts_one_sentence()       [1257]                          │
│         └→ tts_text_queue.put() [base.py:294]                   │
│                                                                 │
│  ⑤ 发送 LAST 标记 (depth==0):                                  │
│     tts_text_queue.put(TTSMessageDTO(LAST, ACTION))   [1225]    │
└──────────────────────┬──────────────────────────────────────────┘
                       │ Queue
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  core/providers/tts/base.py :: tts_text_priority_thread()       │
│                                                                 │
│  ⑥ 消费 tts_text_queue                           [368]          │
│     ├─ FIRST → 初始化缓冲区                                     │
│     ├─ MIDDLE + TEXT → tts_text_buff 累积                       │
│     │   └→ _get_segment_text() → to_tts_stream()  [389]        │
│     └─ LAST  → _process_remaining_text_stream()  [398]         │
│                                                                 │
│  ⑦ to_tts_stream() 各子类实现（如 huoshan_double_stream.py）   │
│     └→ 拿到 PCM/opus → handle_opus(opus_data)    [base.py:116] │
│         └→ tts_audio_queue.put((MIDDLE, opus_data, ...))        │
│                                                                 │
│  ⑧ tts_audio_queue → _audio_play_priority_thread()  [411]      │
│     └→ asyncio.run_coroutine_threadsafe(                        │
│           sendAudioMessage(conn, type, audios, text, id)  [459] │
│         )                                                       │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  core/handle/sendAudioHandle.py                                 │
│                                                                 │
│  ⑨ sendAudioMessage()                            [20]           │
│     ├─ send_tts_message(conn, "sentence_start", text)  [42]    │
│     ├─ sendAudio(conn, audios)                      [44]        │
│     │   └→ conn.websocket.send(header + opus_packet)           │
│     └─ IF LAST: send_tts_message(conn, "stop")      [51]        │
│         └→ conn.websocket.send(json.dumps({type:"tts",...}))   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 钩子扩展点（问题 3 详解）

| 钩子位置 | 文件 | 行号 | 类型 | 说明 |
|---------|------|------|------|------|
| `tts_one_sentence()` | `core/providers/tts/base.py` | 276 | 方法重写 | 子类可重写此方法，在文本进入 `tts_text_queue` 前插入预处理（如情感标签注入、敏感词过滤） |
| `tts_text_priority_thread()` | `core/providers/tts/base.py` | 368 | 线程逻辑 | 消费队列的主循环，可在 `to_tts_stream()` 调用前/后插入逻辑。子类都有独立实现（如 `huoshan_double_stream.py:270`、`xunfei_stream.py:152`） |
| `handle_opus()` | `core/providers/tts/base.py` | 116 | 回调方法 | opus 编码完成回调，在音频入 `tts_audio_queue` 之前触发 |
| `sendAudioMessage()` | `core/handle/sendAudioHandle.py` | 20 | 函数包装 | 音频下发前的最后一道关口，可在此注入下发前的逻辑 |

**注意**：`connection.py` 中 `chat()` 方法直接调用 `self.tts.tts_text_queue.put()`（无中间函数），因此需要在 **TTS 类的消费者侧**（而非生产者侧）插入钩子。

---

## 下发消息 JSON 格式汇总（问题 4&5 补充）

| 消息类型 | 发送函数 | JSON 结构 |
|---------|---------|-----------|
| TTS 状态 | `send_tts_message(conn, state, text)` | `{"type":"tts","state":"start\|sentence_start\|stop","session_id":"...","text":"..."}` |
| STT 显示 | `send_stt_message(conn, text)` | `{"type":"stt","text":"...","session_id":"..."}` |
| 纯显示 | `send_display_message(conn, text)` | `{"type":"stt","text":"...","session_id":"..."}` |
| 音频数据 | `sendAudio(conn, audios)` | 二进制帧: `[16字节头 + opus数据]` |
| Hello 欢迎 | `helloHandle.py:60` | `conn.welcome_msg` (服务器配置的欢迎 JSON) |
| MCP 初始化 | `send_mcp_initialize_message(conn)` | MCP 协议初始化消息 |
| Ping 响应 | `pingMessageHandler.py:42` | `{"type":"pong","session_id":"..."}` |

**所有下发均直接调用 `await conn.websocket.send(...)`，无可复用的通用 `send_command()` 封装。**
