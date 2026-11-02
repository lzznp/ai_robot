# 02 · DSH / SDK 口径（**会过期**，读前先核版本）

> 口径：包 **`0.1.0-rc.8`**；Python SDK **`deepseek-harness-sdk==0.1.5rc1`** + **`deepseek-harness-runtime-bin==0.1.5rc1`**（2026-09）
> ⚠️ **这份一定会过期。** 每条都标了来源：
> 【实测】＝本项目真跑过的；【文档】＝从包的 README 读到的（**未跑通验证**）；【未验证】＝只是推断。
> **换版本先重核**，别拿旧口径当事实。本文件尽量只写"**怎么查**"，写死的东西一定会带偏新对话。

---

## 一、怎么向一个新对话解释 DSH（三层，从下往上）

1. **harness 本体** ＝ 你正在用的这套对话系统：一棵**插件树** + 一个入口（CLI / GUI / 无头）。
2. **SDK** ＝ 让**别的程序**去调用 harness 的接口。**有两条路**（别只知道 Python 那条）：
   - **Python SDK**：`deepseek_harness.DeepSeekHarness`，配一个**单文件可执行运行时**（≈229 MB exe，自带 node）。
   - **stdio JSON-RPC（语言无关）**：按换行分隔的 JSON-RPC，走 stdin/stdout；**stdout 只承载协议帧，诊断走 stderr**。
     启动参数实测是 **`<exe> --profile <name> [--patch <file>]…`**（见 §五）。
     ⚠️ 本文原先记的"启动需要一个 `cordis.yml`（取 `$DSH_CORDIS_CONFIG`，或位置参数 `argv[2]`）"——**与实测不符，已作废**。
     ⇒ **任何语言都能当客户端**（Go / C# / Node 都行），**不限于 Python**。【实测，见 §五】
3. **插件树 ＝ 能力边界。** 有一个现成的「**不含执行器、不含 UI 的 agent 主干**」组合包，它挂载：LLM 服务、session、system-prompt、tools 注册表、skill、agent、goal、jobs、invariants、**agent-loop**。
   **可替换的留在外面**：LLM 适配器、shell 执行器、skill 提供方、**入口**。【文档】

**"人机协同"是现成件，不用自己发明**：用户批准 / 反问 / 权限预设 / 计划模式 / 沙箱策略 / ask-user 工具。【文档】
**关键判据**：**关掉插件 ＝ 不挂载 ＝ 调用被拒** ⇒ **能力由设计决定，不由技术决定。**
（例：不给浏览器自动化工具 ⇒ 模型连"能这么干"都不知道。这是**实测过的**做法，不是理论。）

---

## 二、Python SDK 最小调用（【实测】本项目）

```python
from deepseek_harness import DeepSeekHarness

with DeepSeekHarness(env=env, max_tokens=16384, profile="sdk",
                     dsh_home=MY_DSH_HOME, patches=(persona_patch,),
                     cwd=WORKDIR, provider="deepseek-official") as h:
    result = h.run(prompt, session_id=f"{base}-{action}-{int(time.time())}")
    print(result.final_response, result.finish_reason)
```

- 装：`pip install -r requirements.txt`（就两行：SDK + runtime-bin）。
- **Windows 原生可用**，不需要 WSL/Mac。【实测】

---

## 三、坑（每条都是实测换来的）

| # | 坑 | 为什么 / 怎么办 |
|---|---|---|
| 1 | **单文件运行时首跑要自解压** | 自解压到 `%USERPROFILE%\.cache\pkg\<hash>` ⇒ **该目录必须可写**；`initialize` 超时给足（我们给 **180s**） |
| 2 | **session id 不能跨进程复用** | 同 id 第二次报 `session "X" already exists` ⇒ **每轮新 id** |
| 3 | **锁版本，别追新** | 一次被动升级把底座带崩（旧 `cordis` / `session_root` 调用作废）⇒ 运行环境 pip 锁死，**与主机 DSH 本体解耦** |
| 4 | **`dsh_home` 用项目自带的** | 别碰 `~/.dsh`（隔离；换机器可复现） |
| 5 | **不赌会话记忆** | agent **无跨 run 记忆**；上轮的结论不注入它就真看不到 ⇒ **每轮注入"状态卡"** + 盘上文件续上下文 |
| 6 | **长跑要专门设计** | 一轮 run 结束＝进程结束。跨过回合边界的长任务（我们 70 分钟的采集）会被连带收掉、**轨迹全丢** ⇒ 台账"**开始就落盘**"才活得下来 |
| 7 | **别走"LLM 生成代码 → 直接执行"** | 没有工具面、没有权限边界、出错难回滚。正确形状：**LLM 出结构化意图（JSON/参数）→ 本地代码执行** |
| 8 | **意图路由是最难的一层** | 关键词路由会误判；更坑的是：路由判成某动作后，任务书只带 job、**不带用户原话** ⇒ 用户的话丢了，它连**反问**的机会都没有 |
| 9 | **诚实边界要写进提示词** | 写"你手里的工具清单＝你的真实能力；清单里没有的就是做不到" ⇒ 它才会如实说，而不是编 |
| 10 | **每轮固定开销** | 首轮前缀 ≈**7,430 token**；工具面 ≈**6,481 token/轮**。**能关的工具都关** |

---

## 四、怎么现查（换版本后照这个核）

| 想查什么 | 怎么查 |
|---|---|
| 装了哪些 DSH 包 | 看运行时的包树里的 `@deepseek-ai/` 目录（Node 侧即 `node_modules/@deepseek-ai/`） |
| **某个包到底能干什么** | ⭐ **每个包自带中英双语 README**（`README.md` / `README.zh.md`）——**最快最准，优先读它，别猜** |
| 版本号 | 各包 `package.json` 的 `version`；Python 侧看 `requirements.txt` 锁的版本 |
| 协议细节 | 读 `dsh-sdk-protocol` 的 README（传输 + 请求/结果/通知类型） |
| agent 主干有哪些件 | 读 `dsh-agent-spine-demo` 的 README（它列出了完整插件树与组合顺序） |
| ⚠️ **不要做** | 不要凭记忆回答"SDK 支持 X 吗" —— 去读那个包的 README；**查不到就说查不到** |

（本工作区里这些包在 `参考代码\bestagent\.dsh-staging\node_modules\@deepseek-ai\`；⚠️ 这个路径属于某次快照，换工作区会变，**以包名为准**。）

---

## 五、Go 客户端实测形状（2026-09-28 补；**实物在盘上**）

**实物（两处，同源）**

- **产品里**：`别的项目源码用于参考\cankao\go项目参考\xiaolie\internal\dshruntime\` —— `client.go` **614 行、纯 Go 标准库、零第三方依赖**
- **最早的原型**：`别的项目源码用于参考\cankao\go项目参考\test\` —— 它的 `README.md` 是这套东西**最完整的实测记录**（Go 代码 2026-09-25 已搬进产品，旧副本按"搬家即搬家"删掉）

### 5.1 结论：**底座是同一个 ⇒ 本文其余口径在 Go 路线上全部适用**

`DSH_HOME` 必须显式给（原话：运行时**故意**不会回退到 `~/.dsh`）、**`patches` 机制一样**（`--patch <file>`）、运行时 exe 要带 **`-rg.exe` 伴随程序**（缺了直接报错）。
⇒ **`04` 判据、以及 patch 那两个坑（整行替换 / row id 静默失效）在 Go 这边同样适用，不用重学。**

### 5.2 协议形状（实测）

| 项 | 内容 |
|---|---|
| 启动 argv | `<exe> --profile <name> [--patch <file>]…` |
| 通道 | stdio、newline-delimited JSON-RPC 2.0、三根管道；`DSH_HOME` 走环境变量 |
| 客户端→运行时 | **只有 3 个**：`initialize` / `session/prompt` / `shutdown` |
| 运行时→客户端 | 4 个通知：`session.event` / `session.status` / `subagent.started` / `subagent.finished` |
| `initialize` | `{cwd, provider, model, reasoningEffort?, maxTokens?}` |
| `session/prompt` | `{sessionId, contentBlocks}` → `{messageId}`（**只是入队回执，不代表答完**） |
| 错误码 | 坏帧忽略；无处理器 `-32601`；处理器失败 `-32603` |
| **没有的** | **没有版本协商**；**没有 `cancel` / `session-close`**（只能杀进程放弃一个回合） |

实测数据（本机 win-x64，runtime `0.1.5rc1`）：起子进程 **0.02–0.22 s**；`initialize` 握手 **1.40 s**；真实 LLM 往返 **2.71 s / 17 条通知 / `kind=completed`**。

### 5.3 ★ 会话复用：**同一进程内复用同一个 `sessionId` ＝ 续聊成立（已实测）**

同一个客户端进程、同一个 `sessionId` 连发 3 回合：

| 回合 | 问 | 答 |
|---|---|---|
| R1 | 请记住一个词：苹果。只回复 OK | `OK` |
| R2 | 我刚才让你记住的是什么词？ | **`苹果`** |
| R3 | 再记住：深圳。把两个词用中文逗号连起来 | **`苹果，深圳`** |

⇒ **R2 记得 R1、R3 记得前两轮**；`sessionId` **由客户端指定、运行时照用**。

⚠️ **措辞要准**：这是**同一运行时进程内**复用。**换个进程再用同一个 id 会报 `already exists`**（协议里没有"打开已有会话"这个操作）。

**★ 2026-10-03 晚把机制钉死了（实测，别再用"协议没这个操作"含糊过去）**：运行时会话是**落盘持久化**的 ——
`<DSH_HOME>\sessions\<工程目录编码>\<sessionId>\session.v3.jsonl.zstd`（**多帧** zstd，逐帧解才读得全）。
而 `session/prompt` 是**建会话**语义：新运行时进程起来后**从盘上把同名会话捡回来**，再发就被
`json-rpc -32603: session "…" already exists` 挡死 —— **连重试都进不去**。

⇒ **产品口径（必须照做）**：一个运行时进程内复用同一条串；**只要重开了运行时（或重开了壳），就必须换新串名**。
串名建议 = `时间戳 ＋ 随机后缀`（只有时间的话，同一秒起两个壳会撞）。
反例（本项目 10-03 晚踩的）：壳的重试只重开运行时、**沿用旧串** ⇒ 用户在界面上**重发多少次都没用**。
（壳侧修复＋两条判据：`insole\app.go` 的 `bumpSessionToken()`、`projects_test.go` 的
`TestSessionTokenRotatesOnRetry` / `TestSessionTokenDiffersAcrossBoots`。）

⚠️ **但产品最后还是选了"每轮新会话"**（`xiaolie\app_chat.go:27-40`，2026-09-25 夜）：①**上下文要有上限**（会话堆积没有上限）②消掉 id 撞名。
⇒ **"能用"不等于"该用"**——取舍见 `04` 判据 8。

### 5.4 运行时自带审批 / 沙箱（**闸门是现成件**）

第一个回合的头三条事件就是它自报的：

```
seq0  permission/preset   {"preset":"workspace-write"}
seq1  sandbox/mode        {"mode":"workspace-write"}
seq2  approval/policy     {"policy":"ask"}
```

⚠️ 但**协议里没有"运行时反过来问客户端要批准"的通路**（官方 README 原话：server→client requests 是 **dead capability**，Python SDK 的 responder 面留给**未来的**审批流）
⇒ **闸门不要建在协议层**，用它自带的那套。

### 5.5 分发代价（"以后给别人用"必须提前知道）

| 项 | 数值 |
|---|---|
| 运行时 exe ＋ `-rg.exe` | **234.6 MB**（必须随 app 一起发） |
| 隔离 home（首次自动生成） | ≈ **140 MB / 每个用户** |
| **合计** | **≈ 380 MB** |

两种形状：①**发文件夹**（简单透明）②嵌进 app、启动时释放到 `%LOCALAPPDATA%`（好看，但"**未签名 exe 自释放**"正是**会被杀软拦**的形状）。

### 5.6 两个"不核就会错"的口径

- ⚠️ **§一 那条 `cordis.yml / argv[2]` 与实测不符，已在本文作废**；实测是 `--profile` / `--patch`。
- ⚠️ **"首次启动自解压到 `%USERPROFILE%\.cache\pkg\<hash>`"这条待核**：Go 侧实测是**不释放到磁盘**（`--version` 返回 `0.1.5-rc.1`，**0.8 s**，从 exe 内建虚拟文件系统直接跑）。
  **两条口径至少有一条过期 ⇒ 换版本时以实跑为准。**

### 5.7 顺带：人家怎么核版本兼容性（**方法可抄**）

他们把 `0.1.5-alpha.2` 与 `0.1.7-rc.1` 的**同名文件逐个比 hash**，发现只有 `sdk-runtime/.../__init__.py` 不同（新版加了 Office sidecar 校验，与我们要用的无关）⇒ **判定"Go 客户端在 0.1.7-rc.1 上照样成立"**。
⇒ 这正是 `03-新机器与新工作区起步.md` §一 那条「**用 hash 比对，别只看时间戳**」的实例。

---

## 六、变更记录

| 日期 | 改了什么 | 为什么 |
|---|---|---|
| 2026-09-23 | v1 建立 | 口径：包 0.1.0-rc.8 / SDK 0.1.5rc1；补上"stdio JSON-RPC 语言无关"这条（原先只记了 Python 一条路） |
| 2026-09-28 | 新增 §五（**Go 客户端实测形状**）；**作废 §一 里 `cordis.yml / argv[2]` 那条口径** | 起因：盘上两处 Go 实物（`xiaolie\internal\dshruntime\client.go` ＋ 最早原型 `test\README.md`）。补入：协议只有 **3 请求 4 通知**、**同进程内复用 `sessionId` 续聊已实测成立**、运行时自带审批沙箱、**分发代价 ≈380 MB**、`--version` **不落盘**（与"首次自解压"那条冲突、待核） |
| **2026-10-03C** | **§5.3 把 `already exists` 的机制钉死**：会话**落盘持久化**（`<DSH_HOME>\sessions\…\<sessionId>\session.v3.jsonl.zstd`，多帧）＋ `session/prompt` 是**建会话**语义 ⇒ 新进程会把同名会话从盘上捡回来再拒。**产品口径：只要重开了运行时/壳，就必须换新串名**（时间戳＋随机） | 起因：真实对话里 `TRANSPORT` 一次后**重试全部失败**，用户在界面上重发多少次都没用 —— 真身是壳的退避重试"重开运行时但沿用旧串"。已修（`insole\app.go` `bumpSessionToken()` ＋ 两条测试），并顺手把"读会话日志"的方法写进项目 C 报告 §3.7 |
