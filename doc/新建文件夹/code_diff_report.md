# xiaozhi-server 代码改动分析报告

> 分析日期：2026-07-04
> 对比版本：`xiaozhi-server-old/`（原始版） ↔ `xiaozhi-server/`（当前工作版）
> 总文件量基准：原始版 ~1655 行 connection.py, ~227 行 websocket_server.py；当前版 ~1830 行 connection.py, ~249 行 websocket_server.py

---

## 1. 新增文件

以下文件在原始版本（`xiaozhi-server-old/`）中不存在，仅在当前版本（`xiaozhi-server/`）中存在：

| 文件名 | 路径 | 行数 | 说明 |
|--------|------|------|------|
| **character.py** | `core/character.py` | ~100 行 | 多角色调度核心类，定义角色（名字、性格、系统提示词、工作记忆） |
| **llm_adapter.py** | `core/llm_adapter.py` | ~60 行 | 适配器，将小智 LLM 接口包装成 Character 期望的 `llm_client(messages) → str` |
| **world.py** | `core/world.py` | ~100 行 | 世界调度器，管理所有角色，根据用户输入识别目标角色并驱动其回应 |

**文件变更总数：+3 个 .py 文件，~260 行新增代码。**

---

## 2. 删除文件

**无。** 原始版本中的所有 .py 文件在当前版本中均保留。

---

## 3. 修改文件对比

### 3.1 core/websocket_server.py

- **旧版行数**：227 行
- **新版行数**：249 行
- **变更量**：+22 行

| 改动位置 | 改动内容 | 影响评估 |
|---------|---------|---------|
| `__init__`（第 70 行） | **新增** `self.connections = {}`：设备ID → ConnectionHandler 字典 | ⚠️ **关键改动**。为多设备路由提供了基础数据结构，但仅用 device_id 做 key，未抽象为独立管理类 |
| `_handle_connection()`（第 118–153 行） | **新增** 从 headers/URL 中提取 `device_id` → 设置到 handler → 注册到 `self.connections` → 断开时清理 | ⚠️ 连接生命周期管理与设备路由耦合在 websocket_server 层。`cleanup` 使用了两个不同的 `if` 分支判断 WebSocket 状态，逻辑上多余但无功能错误 |
| `_handle_connection()` 的 `try/finally` | **结构重构**：旧版 handler 的 try 块直接包裹 `handler.handle_connection`，新版将其与认证分离，中间插入了 device_id 注册逻辑 | ⚠️ 引入 device_id 空值检查 warning，但回退路径不明确 |

**与旧版共同部分**：`SuppressInvalidHandshakeFilter`、`update_config`、`_handle_auth`、`_http_response` 均未改动。

---

### 3.2 core/connection.py ⭐

- **旧版行数**：1655 行
- **新版行数**：1830 行
- **变更量**：+175 行

这是改动量最大、影响最核心的文件。

| 改动位置（新版行号） | 改动内容 | 影响评估 |
|---------------------|---------|---------|
| L47–49（import） | **新增** `from core.world import World` 和 `from core.character import Character` | 引入多角色调度依赖 |
| L144–146（`__init__`） | **新增** `self.world = None`、`self.pending_responses = []` | 每个连接持有一个 world 实例和待分发列表 |
| L201–243（新方法） | **新增** `_init_world()`：初始化 World，注册 3 个硬编码角色（MOSS、Doly、瓦力），设置默认角色为"瓦力" | ⚠️ **风险点**：角色注册完全硬编码在代码中，且角色数据（prompt、voice_id）不含从 config.yaml 读取的逻辑 |
| L245–285+（新方法） | **新增** `_dispatch_world_results()`：用硬编码的 `device_id_map` 将角色回应路由到指定设备 | ⚠️ **风险点**：`device_id_map` 全部指向同一个 MAC 地址 (`58:e6:c5:58:0c:58`)——所有角色回应均发到双目屏。这是临时硬编码，非真实多设备调度 |
| L492–508（`_route_message`） | **新增** `type: "llm"` 消息直通转发——如果收到 JSON 消息 `{"type": "llm", "target": "xxx", ...}`，直接转发到目标连接的 WebSocket | ⚠️ 引入了 llm 消息的透传路由，这是新架构中消息中转的雏形，但缺乏安全校验（未验证 target 是否合法） |
| L526–537（新方法） | **新增** `process_with_world()` 和 `set_pending_responses()`——供 receiveAudioHandle 调用的 World 处理接口 | 为 World 调度提供了桥梁方法 |
| `_initialize_components()` 内部（约 L496–527） | **新增** `_init_world()` 调用（在组件初始化流程中） | World 在后台初始化流程中被创建 |

**旧版核心逻辑（chat/llm 流式处理/工具调用/记忆保存）未改动**。

---

### 3.3 core/world.py ⭐（新增文件）

| 方法 | 行数 | 说明 |
|------|------|------|
| `__init__` | ~30 | 初始化角色字典、全局历史（最近 50 条）、默认角色 |
| `add_to_history(speaker, content)` | ~8 | 向全局历史追加消息 |
| `add_character(character)` | ~10 | 注册角色；第一个注册的角色成为默认 |
| `set_default(name)` | ~6 | 设置默认角色 |
| `detect_target(user_input)` | ~30 | **核心路由逻辑**：@ 匹配 → 开头匹配 → 关键词匹配 → 默认。包含同音字容错（瓦力/瓦丽/威力） |
| `process(user_input)` | ~25 | 全流程：记录用户消息 → 识别目标 → 角色回应 → 记录到历史 → 返回格式化结果 |
| `get_all_states` / `load_all_states` | ~10 | 状态持久化接口 |

**设计评价**：这是一个**场景角色调度器的简化原型**——通过关键词识别将用户输入路由到不同角色。但当前实现是针对"角色"而非"场景/设备"的路由，且角色配置完全硬编码。

---

### 3.4 core/character.py ⭐（新增文件）

| 方法 | 行数 | 说明 |
|------|------|------|
| `__init__` | ~20 | 名字、系统提示词、音色、性格特征、工作记忆（最近 5 轮） |
| `build_system_prompt()` | ~20 | 注入性格描述 + 全局历史中"其他人说的话" |
| `build_messages()` | ~10 | 构建 LLM 消息列表（system + 工作记忆 + 当前输入） |
| `say()` | ~30 | **核心方法**：调用 `llm_client(messages)` 获取回复，存入工作记忆 |
| `get_state` / `load_state` | ~15 | 状态序列化 |

**设计评价**：角色模型实现清晰。`say()` 对 `llm_client` 的调用通过 `LLMAdapter` 适配，间接依赖 `connection.py` 的 `self.llm`。

---

### 3.5 core/llm_adapter.py ⭐（新增文件）

- 实现 `__call__(messages) → str`，将小智 LLM 的 `response(session_id, messages)` 流式收集为完整字符串
- 支持 `response`、`chat` 两种回退方法
- **不直接参与调度**，仅作为 Character → LLM 的桥梁

**风险点**：`session_id` 可能为 `None`（未在 `_init_world()` 中设置），依赖连接创建后设置。

---

### 3.6 core/handle/receiveAudioHandle.py

- **旧版**：~181 行
- **新版**：209 行
- **变更量**：+28 行

| 改动位置 | 改动内容 | 影响评估 |
|---------|---------|---------|
| L16–20（import） | **新增** World、Character、ContentType、TTSMessageDTO、SentenceType 导入 | 增加依赖 |
| L91–128（`startToChat` 中段） | **新增** World 调度分支：`if hasattr(conn, 'world') and conn.world:` → 调用 `world.process()` → 用 `send_stt_message()` + `tts.tts_one_sentence()` 将结果送到目标设备 | ⚠️ **Key 改动**。当 World 存在时，`startToChat` 完全跳过原有 LLM 流程。目标设备 ID 硬编码为 `"58:e6:c5:58:0c:58"`（双目屏），备选查找逻辑从 `server.connections` 字典中搜索 |
| L129 | **新增** `return`：World 分支 return 后，原有逻辑不走 | World 模式排他，不兼容原有 LLM chat 流程 |

**问题**：如果 conn.world 存在但 `world.process()` 返回空列表，`startToChat` 会直接 return，用户输入被静默丢弃。

---

### 3.7 core/handle/textMessageHandler.py

- **未改动**。新旧版本完全一致。

---

### 3.8 core/handle/helloHandle.py

- **旧版**：156 行
- **新版**：156 行
- **未改动**。新旧版本内容完全一致（handleHelloMessage、checkWakeupWords、wakeupWordsResponse）。

---

### 3.9 admin_mic.py

- **不存在于任一版本**。
- `admin_mic` 仅在 server.log 中作为 `device-id` 头部值出现（`device-id: admin_mic`），是一个客户端连接时的设备标识，不是独立的 Python 文件。

---

### 3.10 config.yaml

- **两个版本行数相同**（1170 行），内容几乎完全一致。
- **唯一实质性改动**：

| 配置项 | 旧值 | 新值 |
|-------|------|------|
| `close_connection_no_voice_time` | 120（2 分钟） | **1800（30 分钟）** |

- 改动了静默超时断开时间，从 2 分钟延长到 30 分钟。这可能是为了方便调试和长时间测试多设备场景。

---

### 3.11 app.py

- **未改动**。新旧版本完全一致。

---

## 4. 风险评估

### 4.1 对 SceneDispatcher / DeviceManager 接入的影响

| 风险 | 级别 | 说明 |
|------|------|------|
| `websocket_server.py` 的 `self.connections` 字典过于简单 | 🔴 高 | 它是一个 `dict[str, ConnectionHandler]`，无并发保护、无连接状态管理、无多 key 查找能力。SceneDispatcher/DeviceManager 需要更健壮的设备注册表 |
| `receiveAudioHandle.py` 中的 World 分支排他逻辑 | 🔴 高 | `startToChat` 中一旦 World 被初始化，**所有用户输入都先经 World 处理**，原有 LLM chat 流程完全被短路。如果 World 初始化失败，`conn.world` 为 None，自动走旧逻辑；但如果 World 初始化成功但角色配置错误，用户交互将不可用 |
| 硬编码的 device_id_map | 🔴 高 | `_dispatch_world_results()` 中的设备路由表、`receiveAudioHandle.py` 中的目标设备 ID (`58:e6:c5:58:0c:58`) 均为硬编码。新架构必须改为动态配置或从 DeviceManager 查询 |
| 角色配置硬编码 | 🟡 中 | `_init_world()` 中的 MOSS/Doly/瓦力配置完全在代码中，未从 `config.yaml` 读取。新架构应通过 config 或 API 注入角色定义 |
| `type: "llm"` 消息透传缺乏安全校验 | 🟡 中 | `_route_message` 中的直通转发没有验证 target 设备是否属于当前用户，可能导致消息越权 |

### 4.2 已包含的多设备路由 / 角色调度雏形

| 功能 | 所在文件 | 说明 |
|------|---------|------|
| **设备注册表** | `websocket_server.connections` | device_id → ConnectionHandler 映射，是 DeviceManager 的雏形 |
| **消息直通转发** | `connection._route_message` | 支持 type=llm 消息直接路由到其他设备 |
| **角色识别与路由** | `world.detect_target()` | 基于关键词将用户输入路由到不同角色（Character），可扩展为路由到不同设备/场景 |
| **跨设备 TTS 下发** | `receiveAudioHandle.startToChat` L119–125 | 将 World 调度结果通过 `send_stt_message` + `tts_one_sentence` 下发到目标设备的 WebSocket 连接 |

---

## 5. 复用建议

### 5.1 可以直接保留不动的文件

| 文件 | 理由 |
|------|------|
| `app.py` | 完全未改动，启动逻辑与新架构兼容 |
| `core/handle/textMessageHandler.py` | 抽象基类，未改动 |
| `core/handle/helloHandle.py` | 未改动，且与新场景调度无关 |
| `core/auth.py` | 未在改动范围内，认证逻辑独立 |
| `core/http_server.py` | 未在改动范围内 |
| `config.yaml` | 仅 `close_connection_no_voice_time` 改动，可保留新值或根据场景需求调整 |

### 5.2 需要小心修改的文件

| 文件 | 风险地区 | 建议 |
|------|---------|------|
| `core/connection.py` | World 初始化 + `_route_message` 直通 + 硬编码角色配置 | **建议保留 `chat()`、`_initialize_components()`、记忆/意图等核心逻辑不动**。World 相关方法应抽取到独立的调度模块，或通过 SceneDispatcher 接口注入 |
| `core/websocket_server.py` | `self.connections` 字典 | 建议将 `self.connections` 替换或包装为 DeviceManager 的实例，对外暴露统一接口 |
| `core/handle/receiveAudioHandle.py` | World 排他分支 | 将 World 调度分离到独立的 Handler（如 `worldDispatchHandle.py`），在更高层级的路由中决定走 World 还是 LLM |

### 5.3 建议重写的文件

| 文件 | 理由 |
|------|------|
| `core/world.py` | **已有模型可作为 SceneDispatcher 的参考**，但当前实现是基于"多角色"而非"多设备/多场景"的调度。建议保留 `detect_target()` 的设计模式，但重写为场景路由逻辑 |
| `core/character.py` | 如果新架构中角色定义从代码配置移到 config/DB，建议重写 `__init__` 和 `build_system_prompt` 的初始化逻辑 |
| `core/llm_adapter.py` | 如果 SceneDispatcher 不采用 Character→LLM 的调用模式，此文件可废弃。如果保留，建议注入 `session_id` |

### 5.4 总体建议

```
保留层（不动）       → app.py, textMessageHandler.py, helloHandle.py, auth.py, http_server.py
                                                                 
适配层（小心改）     → connection.py（保留 chat/记忆/工具调用核心）
                     → websocket_server.py（connections → DeviceManager）
                     → receiveAudioHandle.py（World 分支 → 独立 Handler）
                                                                  
重写层（参考原型）   → world.py（→ SceneDispatcher）
                     → character.py（→ 场景/设备配置）
                     → llm_adapter.py（按实际接口调整）
```

---

*报告生成完成。*
