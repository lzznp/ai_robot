# 侦察报告：连接断开逻辑 & World 引用位置

> **侦察时间**: 2026-07-17  
> **搜索范围**: `xiaozhi-server/` 核心源码  
> **目标**: 断开逻辑定位、World/Character/LLMAdapter/SceneDispatcher 引用溯源

---

## 一、连接断开逻辑

### 1.1 双重超时机制

代码中**存在两套独立运行的超时断开机制**，互不感知：

| 机制 | 位置 | 触发方式 | 行为 |
|------|------|----------|------|
| `_check_timeout()` | `connection.py:1783-1812` | 后台 `asyncio.Task`（每 10 秒轮询） | 直接 `await self.close(ws)` |
| `no_voice_close_connect()` | `receiveAudioHandle.py:234-258` | 每次收到音频帧时调用（`handleAudioMessage` 第 36 行） | 发送告别语 → `close_after_chat` → 正常关闭 |

**关键代码位置：**

```
connection.py:194-195   —— timeout_seconds 计算（+60 秒加成）
connection.py:197       —— timeout_task 初始化
connection.py:414-415   —— 在 handle_connection 中启动 _check_timeout 任务
connection.py:1783-1812 —— _check_timeout 实现（10s 间隔，比较 time - last_activity）
connection.py:1627-1709 —— close() 方法（清理 VAD/ASR/TTS/线程池 + 关闭 ws）

receiveAudioHandle.py:36    —— 每帧音频调用 no_voice_close_connect
receiveAudioHandle.py:234-258 —— no_voice_close_connect 实现
```

### 1.2 超时时间配置

| 配置项 | 类型 | 位置 | 当前值 | 说明 |
|--------|------|------|--------|------|
| `close_connection_no_voice_time` | **config.yaml 可配** | `config.yaml:61` | `86400`（24 小时） | 单位：秒；默认 `120` |
| `enable_websocket_ping` | **config.yaml 可配** | `config.yaml:75` | `false` | WebSocket 心跳开关 |

**硬编码偏差：**

- `connection.py:194-195`：实际值 = `config.get("close_connection_no_voice_time", 120) + 60`  
  → 例如配置 120，实际是 180 秒
- `receiveAudioHandle.py:241-242`：直接使用原始值，不做 +60  
  → 例如配置 120，实际是 120 秒

⚠️ 两套机制的超时阈值**不一致**。`_check_timeout` 比 `no_voice_close_connect` 多等 60 秒。

### 1.3 保活/心跳机制

```
pingMessageHandler.py:27-28 —— enable_websocket_ping 开关检查
pingMessageHandler.py:35-40 —— 处理 PING → 发送 PONG + 刷新 last_activity_time
```

**现状：**
- 协议层支持 `{"type": "ping"}` → `{"type": "pong"}` 应用层心跳
- 但 `enable_websocket_ping: false` 默认关闭
- 关闭状态下，PING 消息会被**静默忽略**（第 29-30 行）
- **没有服务端主动 PING 机制**——服务端不发送 PING 帧，完全依赖客户端发 PING 后服务端回复 PONG
- `websockets` 库默认 `ping_interval=20`（秒级自动心跳）在服务器端的 `.serve()` 调用中没有显式设置，使用库默认值

**结论：** 当前依赖的是「客户端任意活动（包括音频）刷新 `last_activity_time`」的隐式保活，而不是主动心跳。

---

## 二、World 引用位置

### 2.1 全部引用清单

| 文件 | 行号 | 引用方式 | 具体标识 |
|------|------|----------|----------|
| `core/connection.py` | 48 | `from core.world import World` | **World** 类 |
| `core/connection.py` | 49 | `from core.character import Character` | **Character** 类 |
| `core/connection.py` | 52 | `from core.scene_dispatcher import SceneDispatcher` | **SceneDispatcher** 类 |
| `core/connection.py` | 213 | `from core.llm_adapter import LLMAdapter`（函数内导入） | **LLMAdapter** 类 |
| `core/connection.py` | 149 | `self.world = None` | 成员变量 |
| `core/connection.py` | 153 | `self.scene_dispatcher = None` | 成员变量 |
| `core/connection.py` | 208-250 | `_init_world()` 方法 | 创建 World + Character 实例 |
| `core/connection.py` | 252-289 | `_init_scene_dispatcher()` 方法 | 创建 SceneDispatcher 实例 |
| `core/connection.py` | 428-431 | `handle_connection()` 中调用两个初始化 | 初始化调用 |
| `core/connection.py` | 577-584 | `process_with_world()` 方法 | 调用 `self.world.process()` |
| `core/connection.py` | 590-602 | `process_with_scene()` 方法 | 调用 `self.scene_dispatcher.process()` |
| `core/handle/receiveAudioHandle.py` | 17 | `from core.world import World` | **World** 类（未使用——只导入但无直接调用） |
| `core/handle/receiveAudioHandle.py` | 18 | `from core.character import Character` | **Character** 类（未使用——只导入但无直接调用） |
| `core/handle/receiveAudioHandle.py` | 191 | `hasattr(conn, 'scene_dispatcher')` | 调用 `conn.process_with_scene()` |
| `core/handle/receiveAudioHandle.py` | 213-222 | `hasattr(conn, 'world')` → `conn.world.process()` | **World** 实例使用（Fallback 路径） |
| `core/handle/receiveAudioHandle.py` | 94-141 | `_dispatch_world_results()` | World 调度结果分发 |
| `core/scene_dispatcher.py` | 11 | `from core.world import World` | **World** 类 |
| `core/scene_dispatcher.py` | 12 | `from core.llm_adapter import LLMAdapter` | **LLMAdapter** 类 |
| `core/scene_dispatcher.py` | 68 | `from core.character import Character`（函数内导入） | **Character** 类 |
| `core/scene_dispatcher.py` | 21-29 | `__init__` 内部创建 `self.world = World(...)` | 内部实例 |
| `core/scene_dispatcher.py` | 111 | `self.world.process(user_input)` | 调用 |
| `core/world.py` | 9 | `from .character import Character` | 自引用 |

### 2.2 World + SceneDispatcher 共存的文件

| 文件 | World 使用方式 | SceneDispatcher 使用方式 |
|------|---------------|-------------------------|
| `core/connection.py` | `_init_world()` + `process_with_world()` + `_dispatch_world_results()` | `_init_scene_dispatcher()` + `process_with_scene()` |
| `core/handle/receiveAudioHandle.py` | `conn.world.process()`（Fallback 优先级 2） | `conn.process_with_scene()`（优先级 1） |
| `core/scene_dispatcher.py` | 内部持有 `self.world` 实例 | 自身就是 SceneDispatcher |

### 2.3 引用示意图

```
connection.py
 ├── import: World, Character
 ├── import: SceneDispatcher, ChatScene
 ├── import: LLMAdapter (inside _init_world)
 ├── self.world = None
 ├── self.scene_dispatcher = None
 ├── _init_world()          → World + Character
 ├── _init_scene_dispatcher() → SceneDispatcher (内部又建了一个 World!)
 ├── process_with_world()
 └── process_with_scene()

receiveAudioHandle.py
 ├── import: World, Character (未使用, 仅入口)
 ├── startToChat():
 │   ├── [P1] scene_dispatcher → process_with_scene()
 │   ├── [P2] world → conn.world.process()
 │   └── [P3] 原始 LLM 流程
 └── _dispatch_world_results()

scene_dispatcher.py
 ├── import: World, LLMAdapter
 ├── import: Character (inside register_characters)
 ├── self.world = World(…)  ← 内部新建 World 实例
 └── self.world.process()
```

### 2.4 关键发现

1. **SceneDispatcher 构造函数有 Bug**  
   `connection.py:264` 传入 `connection_handler=self`，但 `SceneDispatcher.__init__` 签名只有 `(llm_instance, device_manager=None, redis_manager=None)`，**不接受 `connection_handler` 参数**。  
   → 运行到该路径会抛出 `TypeError: __init__() got an unexpected keyword argument 'connection_handler'`  
   → 但 `scene_dispatcher.py:191` 又直接使用了 `self.connection_handler`  
   → 推测 `connection_handler` 是作为属性在初始化后被赋值，或者代码尚未完整集成

2. **World 与 SceneDispatcher 是重复的调度体系**  
   SceneDispatcher 内部也创建了一个 `World` 实例（`scene_dispatcher.py:29`），同时 `connection.py` 也独立创建了一个 `World` 实例（`connection.py:216`）。**系统中同时存在两个 World 实例**，一个挂接在 `conn.world`，一个藏在 `conn.scene_dispatcher.world`。

3. **`receiveAudioHandle.py` 的 import 是僵尸代码**  
   第 17-18 行导入了 `World` 和 `Character`，但在该文件中**从未直接使用它们**——所有调用都是通过 `conn.world.process()` 或 `conn.process_with_scene()` 间接完成。

4. **优先级链已清晰**  
   `receiveAudioHandle.py:startToChat()` 中存在三级 Fallback：  
   **SceneDispatcher → World → 原始 LLM**，说明 SceneDispatcher 是新的主力路径，World 是中间过渡产物。

---

## 三、清理建议

### 3.1 分阶段执行

#### 阶段 A：修复 Bug（可立即并行）

| 任务 | 文件 | 优先级 | 工作量 |
|------|------|--------|--------|
| A1. 修复 SceneDispatcher 构造函数，增加 `connection_handler` 参数 | `scene_dispatcher.py:21` | 🔴 高 | 1 行 |
| A2. 删除 `receiveAudioHandle.py` 中未使用的 `import World, Character` | `receiveAudioHandle.py:17-18` | 🟢 低 | 2 行 |

**A1 修复示例：**
```python
def __init__(self, llm_instance, device_manager=None, redis_manager=None, connection_handler=None):
    ...
    self.connection_handler = connection_handler
```

#### 阶段 B：统一超时机制

| 任务 | 文件 | 优先级 | 工作量 |
|------|------|--------|--------|
| B1. 消除 `+60` 秒硬编码偏差（两处对齐） | `connection.py:194-195`, `receiveAudioHandle.py:241-242` | 🟡 中 | 2 处 |
| B2. 评估是否保留两套超时。建议只保留 `_check_timeout()` 任务，删除 `no_voice_close_connect` 中的超时逻辑 | `connection.py:1783-1812`, `receiveAudioHandle.py:234-258` | 🟡 中 | 需讨论 |

#### 阶段 C：清理冗余调度体系

| 任务 | 文件 | 优先级 | 工作量 |
|------|------|--------|--------|
| C1. 删除 `connection.py` 中 `_init_world()` 及相关方法（`process_with_world`, `_dispatch_world_results`） | `connection.py:208-250`, `577-584`, `292-357` | 🟡 中 | 3 个方法 |
| C2. 删除 `connection.py` 顶层的 `World`/`Character` 导入 | `connection.py:47-49` | 🟢 低 | 3 行 |
| C3. 删除 `receiveAudioHandle.py` 中 World Fallback 路径（`startToChat` 的 Priority 2 分支 + `_dispatch_world_results`） | `receiveAudioHandle.py:210-222`, `94-141` | 🟡 中 | 需确认 SceneDispatcher 已稳定 |
| C4. 删除 `receiveAudioHandle.py` 中 World/Character 导入（Phase A2 已做） | 同上 | 🟢 低 | 已计 |
| C5. 删除 `world.py`、`character.py`、`llm_adapter.py`（如果 SceneDispatcher 不再需要内部 World） | `core/world.py`, `core/character.py`, `core/llm_adapter.py` | 🟠 低 | 需确认 SceneDispatcher 不再依赖 World |

### 3.2 依赖关系图

```
Phase A ──→ Phase B ──→ Phase C
  A1              B1           C1  ← 依赖 B 完成
  A2              B2           C2  ← 依赖 C1
                               C3  ← 依赖 B2 + C1
                               C4  ← 依赖 C3
                               C5  ← 依赖 C3
```

- **A1 和 A2 可并行**，无依赖
- **B1 和 B2 可并行**
- **C 系列必须按顺序**：C1 → C2 → C3 → C4 → C5
- **A 和 B 无依赖**，可并行

### 3.3 风险提示

1. SceneDispatcher 目前收到 P1 优先级但**构造函数有 Bug**——必须先修复 A1 才能启用
2. 删除 World 前需确认 SceneDispatcher 内部是否可以直接处理而不依赖 `world.py`（SceneDispatcher 的 `self.world.process()` 调用在 `scene_dispatcher.py:111`）
3. 心跳机制若启用 PING/PONG，需评估 `enable_websocket_ping: true` 时的客户端兼容性（固件是否需要支持发送 `{"type":"ping"}`）

---

*报告完毕。*
