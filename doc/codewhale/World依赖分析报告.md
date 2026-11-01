# World 依赖分析报告

> 侦察时间：2026-07-19
> 侦察范围：`xiaozhi-server/` 目录下全部 `.py` 文件
> 核心文件：`core/world.py`, `core/scene_dispatcher.py`, `core/connection.py`, `core/character.py`, `core/llm_adapter.py`, `core/handle/receiveAudioHandle.py`

---

## 1. 核心发现总览

| 问题 | 结论 |
|------|------|
| SceneDispatcher 的**活跃代码**是否调用 `self.world.process()`？ | **否** — 活跃 `process()`（第94-153行）直接调用 `self.llm_adapter()`，不依赖 World |
| SceneDispatcher 中是否存在**死代码**调用 `self.world.process()`？ | **是** — 第170行之后的第二个 `process()` 方法（死代码）调用 `self.world.process()` |
| World 是否被其他模块直接调用？ | **完全死路** — `_init_world()` 在第426行被注释，`self.world` 始终为 None |
| Character 是否被 SceneDispatcher 活跃依赖？ | **否** — 仅在死代码 `register_characters()` 中使用 |
| LLMAdapter 是否被 SceneDispatcher 依赖？ | **是** — SceneDispatcher 实时路径直接依赖 `self.llm_adapter` |

---

## 2. 所有调用 `self.world.process()` 的位置

### 2.1 `core/scene_dispatcher.py` — 第176行（死代码）

```python
# 第170-223行：重复的 process() 方法（死代码，不可达）
def process(self, user_input: str, device_id: str) -> Dict[str, Any]:
    ...
    try:
        raw_results = self.world.process(user_input)   # ← 第176行
        ...
```

**说明：** `scene_dispatcher.py` 文件中存在**两个** `process()` 方法。第一个（第94行）是活跃路径；第二个（第170行）是残留的死代码，且依赖 `self.world`，但 `self.world` 在 `__init__` 中从未被赋值，调用必报 `AttributeError`。

### 2.2 `core/connection.py` — 第581行（不可达）

```python
# 第576-582行：process_with_world()
def process_with_world(self, text: str) -> list:
    if not self.world:          # self.world 始终为 None
        return []
    results = self.world.process(text)  # ← 第581行
    return results
```

**说明：** `_init_world()` 在第426行被**注释**，`self.world` 永远为 `None`，此路径不可达。

### 2.3 `core/handle/receiveAudioHandle.py` — 第216行（不可达）

```python
# 第213-222行：Priority 2 — World fallback
if hasattr(conn, 'world') and conn.world:         # conn.world 是 None
    results = conn.world.process(actual_text)     # ← 第216行
```

**说明：** 接收音频处理中作为 SceneDispatcher 的 Fallback。但由于 `_init_world()` 被注释，`conn.world is None`，此分支永远跳过，直接走到第227行的原始 LLM 流程。

---

## 3. 所有导入 World 的位置

| 文件 | 行号 | 语句 | 状态 |
|------|------|------|------|
| `core/scene_dispatcher.py` | 11 | `from core.world import World` | **死导入** — 仅在死代码中引用 `self.world` |
| `core/connection.py` | 48 | `from core.world import World` | **死导入** — `_init_world()` 被注释 |
| `core/handle/receiveAudioHandle.py` | 17 | `from core.world import World` | **死导入** — 仅在不可达分支中引用 `conn.world` |

### World 的全部引用点

| 文件 | 行号 | 代码 | 状态 |
|------|------|------|------|
| `connection.py` | 149 | `self.world = None` | 初始化（无用） |
| `connection.py` | 217 | `self.world = World(llm_client=adapter)` | **不可达**（_init_world() 被注释） |
| `connection.py` | 245 | `self.world.add_character(char)` | 同上 |
| `connection.py` | 247 | `self.world.set_default("瓦力")` | 同上 |
| `connection.py` | 248 | `len(self.world.characters)` | 同上 |
| `connection.py` | 251 | `self.world = None` | 异常处理（无用） |
| `connection.py` | 578 | `if not self.world:` | 始终 True |
| `connection.py` | 581 | `self.world.process(text)` | 不可达 |
| `scene_dispatcher.py` | 74 | `self.world.add_character(char)` | 死代码，self.world 未初始化 |
| `scene_dispatcher.py` | 77 | `self.world.set_default(...)` | 死代码 |
| `scene_dispatcher.py` | 176 | `self.world.process(user_input)` | 死代码，不可达 |
| `receiveAudioHandle.py` | 216 | `conn.world.process(actual_text)` | 不可达 |

---

## 4. 所有导入 Character 的位置

| 文件 | 行号 | 语句 | 状态 |
|------|------|------|------|
| `core/world.py` | 9 | `from .character import Character` | **存活** — World 内部使用 Character 类 |
| `core/scene_dispatcher.py` | 65 | `from core.character import Character` | **死代码** — 仅在 `register_characters()` 中，该方法依赖未初始化的 `self.world` |
| `core/connection.py` | 49 | `from core.character import Character` | **死导入** — 仅在 `_init_world()` 中，该方法被注释 |
| `core/handle/receiveAudioHandle.py` | 18 | `from core.character import Character` | **死导入** — 导入后从未使用（仅 `World` 和 `_dispatch_world_results` 使用） |

### Character 依赖树

```
World ──→ Character (直接 import, 存活)
SceneDispatcher ──→ Character (死代码)
ConnectionHandler ──→ Character (死代码)
receiveAudioHandle ──→ Character (死导入)
```

**关键结论：** 如果完全移除 World，Character 的唯一存活使用者是 World 自身。移除 World 后，Character 连同 world.py 都可以一起废弃。

---

## 5. 所有导入 LLMAdapter 的位置

| 文件 | 行号 | 语句 | 状态 |
|------|------|------|------|
| `core/scene_dispatcher.py` | 12 | `from core.llm_adapter import LLMAdapter` | **存活** — 第29行 `self.llm_adapter = LLMAdapter(llm_instance)`，活跃使用 |
| `core/scene_dispatcher.py` | 29-31 | `self.llm_adapter = LLMAdapter(llm_instance)` | **存活**（但代码重复写了两次，有一行多余） |
| `core/connection.py` | 214 | `from core.llm_adapter import LLMAdapter` | **死导入** — 仅在 `_init_world()` 中，该方法被注释 |

**关键结论：** LLMAdapter 是 SceneDispatcher 的**活跃依赖**。SceneDispatcher 不使用 World，但直接使用 LLMAdapter。移除 World 不影响 LLMAdapter。

---

## 6. SceneDispatcher 的实时路径分析

`scene_dispatcher.py` 当前活跃的处理路径（第94-153行）：

```
process(user_input, device_id)
  ├── 1. 识别目标角色（从 _role_device_map 匹配）
  ├── 2. 获取目标设备 ID
  ├── 3. 构建 system prompt
  ├── 4. 调用 self.llm_adapter(messages) ← 直接调 LLM，不经过 World
  ├── 5. 生成 actions [{"type": "tts", "text": ..., "target": ..., "role": ...}]
  └── 6. 返回 {"actions": ..., "response": ..., "raw_results": []}
```

**无需 World，SceneDispatcher 已具备完整的用户输入处理能力。**

### 死代码清单（可删除）

| 在 `scene_dispatcher.py` 中 | 原因 |
|---|---|
| 第1-12行 `from core.world import World` | 导入从未初始化的类 |
| 第64-79行 `register_characters()` | 依赖 `self.world`（未初始化） |
| 第170-223行 第二个 `process()` 方法 | 重复方法，不可达 |
| 第225-418行 四个重复的 `dispatch_actions()` | 重复方法/空逻辑块，只有最后一个有效 |
| 第29-31行 重复的 `self.llm_adapter = ...` | 同一行写了两次 |

### 文件粗糙度评级

`scene_dispatcher.py`（418行）中有大量重复的死代码，文件质量**极差** — 三个 `dispatch_actions` 方法完全重复，只有最后一个（从第363行开始）是唯一完整的版本。

---

## 7. 清理建议

### 阶段一：立即清理 scene_dispatcher.py（不改变行为）

```
1. 删除死导入：from core.world import World          (第11行)
2. 删除重复赋值：self.llm_adapter = ... 的重复行      (第30或31行，保留一行)
3. 删除死方法：register_characters()                  (第63-79行)
4. 删除第二个 process() 方法                          (第170-223行)
5. 删除前三个重复的 dispatch_actions() 方法            (第225-362行，保留第363行之后的版本)
```

**风险：** 无。这些全部是死代码或重复代码。

### 阶段二：清理引用 World 的导入（可选，推荐）

```
6. connection.py：删除 import World, Character        (第48-49行)
7. connection.py：删除 self.world = None               (第149行)
8. connection.py：删除 self.pending_responses = []      (第150行)
9. connection.py：删除 _init_world() 整个方法           (第210-251行)
10. connection.py：删除 set_pending_responses()         (第584-586行)
11. connection.py：删除 process_with_world()            (第576-582行)
12. connection.py：删除 _dispatch_world_results()       (第289-378行)
13. connection.py：删除 _send_tts_to_device()           (第357-365行)
14. connection.py：删除 _send_emotion_to_device()       (第367-377行)
```

**注意：** 第426行已有 `# self._init_world()` 注释标记，无需额外操作。

### 阶段三：清理 receiveAudioHandle.py

```
15. receiveAudioHandle.py：删除 import World, Character (第17-18行)
16. receiveAudioHandle.py：删除 _dispatch_world_results() (第94-141行)
17. receiveAudioHandle.py：删除 Priority 2 World 调度路径 (第210-222行)
```

**注意：** 删除后，`startToChat()` 中 SceneDispatcher 失败时直接 Fallback 到原有 LLM 流程（Priority 3，第227行），行为不变。

### 阶段四：清理 World 和 Character 文件（风险项）

```
18. 确认再无任何 import → 删除 core/world.py
19. 确认再无任何 import → 删除 core/character.py
20. 确认 LLMAdapter 不再引用 Character 概念（注释中提到）→ 更新注释
```

**风险：** 需要确认 `xiaozhi-server-old/` 以及任何测试文件是否引用 world.py/character.py。建议先做前三个阶段，确认运行正常后再做阶段四。

### 推荐执行顺序

```
第1步：scene_dispatcher.py 清理（死代码 + 重复代码）
     ↓ 测试：启动服务器，验证基本对话正常
第2步：connection.py 清理（World 相关）
     ↓ 测试：启动服务器，验证基本对话正常
第3步：receiveAudioHandle.py 清理（World 相关）
     ↓ 测试：发送音频，验证对话正常
第4步：删除 world.py 和 character.py
     ↓ 测试：完整功能回归测试
```

---

## 8. 总结

| 组件 | 状态 | 建议 |
|------|------|------|
| **World** (`core/world.py`) | 完全死路 — `_init_world()` 被注释，没有任何活跃调用 | **可安全删除** |
| **Character** (`core/character.py`) | 唯一存活使用者是 World 自身 | 随 World 一起删除 |
| **LLMAdapter** (`core/llm_adapter.py`) | SceneDispatcher 活跃依赖 | **保留** |
| **SceneDispatcher** (`core/scene_dispatcher.py`) | 活跃代码不依赖 World，含大量死代码 | **清理死代码** |

**一句话结论：** World 和 Character 在当前代码库中是彻底的死代码。SceneDispatcher 已经通过 `self.llm_adapter` 独立处理用户输入，无需 World 过渡。建议分四个阶段安全移除整个 World + Character 子系统。
