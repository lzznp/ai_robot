# 小智多机器人调度（ai_robot）

基于**小智固件 + 小智后台（xiaozhi-server）**改造的多机器人智能调度项目 —— 目标是做一台"AI 剧场"：
**ESP32 是纯执行终端**（说话、亮灯、动电机、拍照），**后台是大脑**（LLM 调度 + 能力库 + 场景），两者走 WebSocket。

> **当前状态（2026-11-01）**：MOSS 的灯 / 屏 / 摄像头 / **两个步进电机**已全部打通，可由后台指令驱动；
> 后台已建立**动作词汇表**（单一真相源）与**能力库页面**。机器人侧的表情/电机仍在逐台补齐。
>
> **开工先读** → [`工作文档/后台框架·一页纸_20261101.md`](工作文档/后台框架·一页纸_20261101.md)
> 其中 **§9「当前基线」** 写明了：板上固件是什么、哪些已实测、哪些没验、下一步做什么。
> 硬件真相看三份台账：`工作文档/MOSS-硬件台账.md`、`月球车-硬件台账.md`、`瓦力-硬件台账.md`。

## 设计原则（已拍板，别再翻案）

1. **固件不写语义**：固件只认芯片级/引脚级动作（`gpio` / `pwm` / `ws2812` / `stepper` / `camera`），
   不写"前进""亮红灯""呼吸"这类语义 —— 语义属于后台能力库。
2. **后台只认硬件事实**：后台不需要懂引脚电路，只按词汇表拼 JSON 发 `/api/command`。
3. **动作词汇表是唯一真相源**：`xiaozhi-server/core/actions.py`（字段 + 串口判据 + 各板支持矩阵）。
   固件新增动作 ⇒ 先改词汇表，再写代码。

## 目录

| 目录 | 是什么 |
|---|---|
| `esp32-firmware/` | 固件（多板：`moss_550w`、`lingkong-s3-moc-cam-1.54tft`、`wali`、`doly` 等；含 `stepper`/`ws2812`/`camera` 芯片级动作） |
| `xiaozhi-server/` | 后台（LLM 调度、能力库、场景、MCP 工具） |
| `xiaozhi-server/core/actions.py` | ★ **动作词汇表 + 信封构造 + 已知板硬件资料（KNOWN_BOARDS）** |
| `xiaozhi-server/web_console/` | Streamlit 控制台（设备管理 / 能力库 / 场景编排 / 聊天测试） |
| `pin_scan/` | 瓦力自检固件独立工程 |
| `doc/`、`docs/` | 侦察报告、接线图、开发记录 |
| `tools/`、`moss/`、`dooirobot/` | 零散工具与实验 |
| **`工作文档/`** | ★ 项目记忆：衔接报告、三份硬件台账、后台框架一页纸 |
| **`通用文档/`** | ★ 方法论：协作方法、SDK 口径、板子自检框架、LLM 助手设计判据 |
| `PROJECT_STATUS.md` | 早期项目进展（2026-07-03，已过时，以 `工作文档/` 为准） |
| `GEMINI.md` | 智能体交互规范（中文、先方案后动手） |

## 怎么跑起来（本机）

```powershell
# 后台（8000 websocket / 8003 OTA+视觉 / 8004 指令 API）
#   ⚠️ opus.dll 在 envs\lzluck\Library\bin，app.py 顶部已自动处理 PATH（2026-11-01）
C:\ProgramData\miniconda3\envs\lzluck\python.exe D:\study\jiqiren\ai_robot\xiaozhi-server\app.py

# 控制台（另起一个进程；改了 core/*.py 必须重启它，改 pages/*.py 刷新即可）
cd D:\study\jiqiren\ai_robot\xiaozhi-server\web_console
C:\ProgramData\miniconda3\envs\lzluck\python.exe -m streamlit run app.py

# 固件（MOSS，注意 sdkconfig 不带后缀）
cd D:\study\jiqiren\ai_robot\esp32-firmware
idf.py -B build -DSDKCONFIG=sdkconfig -p COM4 flash
#   本机内存小：先 $env:NINJAFLAGS = "-j1"，否则 cc1plus 会 OOM
```

指令长这样（发给 `POST http://<ip>:8004/api/command`）：

```json
{"device_id":"58:e6:c5:5a:2f:fc",
 "command":{"type":"command","payload":{"actions":[
   {"type":"ws2812","pin":7,"count":1,"rgb":[64,0,0]},
   {"type":"stepper","motor":1,"steps":64,"speed":60}
 ]}}}
```

## 这个仓库里**故意没有**什么（`.gitignore` 里挡着）

| 没入库 | 为什么 | 怎么恢复 |
|---|---|---|
| `xiaozhi-server/models/`（`SenseVoiceSmall/model.pt`，892 MB） | GitHub 单文件上限 100 MB，模型可重新下载 | 按 xiaozhi-server 官方文档下载到 `models/` |
| `xiaozhi-server/data/.config.yaml` | **里面是真凭据**（约 50 处 API key / MQTT 签名密钥 / token） | `cp xiaozhi-server/config.yaml xiaozhi-server/data/.config.yaml`，再填自己的 key |
| `xiaozhi-server/data/*.db` | 运行期数据库（设备登记、能力、场景），二进制且一直变 | 首次运行自动生成 |
| `xiaozhi-server/tmp/`、`**/*.log` | 日志 | 可再生 |
| `esp32-firmware/build*/`、`.pio/` | 编译产物（四个 build 目录合计 1.6 GB） | 重新编译 |
| `firmware_dumps/`、`_archive/` | 固件整片备份与历史存档（共约 165 MB） | 见本地磁盘 |
| `*-old/`、`准备废弃/` | 旧版本与废弃目录 | 见本地磁盘 |
| `.deepseek/`、`.idea/` | 智能体运行期状态 / IDE 配置 | — |

⚠️ **密钥单独保管**：`data/.config.yaml` 不进版本库是有意的。
⚠️ **历史遗留**：初始提交里 `xiaozhi-server/config.yaml` 曾带过一个真 key，
2026-11-01 的提交已把它换成占位符；如该 key 仍在用，**请作废换新**。

## 换机器怎么接着做

本机就是开发机，仓库以 `D:\study\jiqiren\ai_robot` 的内容为准。另一种做法是保留一份克隆：

```powershell
git clone git@github.com:lzznp/ai_robot.git D:\study\ai_robot_gh
# 把开发机项目目录里"该入库的东西"覆盖进去（.gitignore 会挡住模型/产物/日志；
# 别拷 .git、别拷 data/.config.yaml），然后：
cd D:\study\ai_robot_gh
git add -A; git commit -m "同步（YYYY-MM-DD）"; git push
```

**网络前提**：本机到 `github.com:443` 会被间歇性阻断。已配置：
- `~/.ssh/config` 里 `github.com` → `ssh.github.com:443`（SSH 走 443）
- 每台机器一把自己的 key，加到对应仓库的 **Deploy keys（勾 write access）**
  —— 注意 GitHub 规定**一把 deploy key 只能绑一个仓库**。

## 历史

- `2026-11-02` 初始提交：从本机 7 月副本整理入库（1685 个文件，排除了模型/凭据/编译产物/旧版本）。
- `2026-11-01` 同步开发机进展：固件新增 `stepper` 动作；后台加动作词汇表与能力库页面；
  `devices` 表加 `hw_json`（本机备注）；`config.yaml` 的真实 key 换成占位符。
- `2026-11-01` 加入 `工作文档/`（衔接报告 + 三份硬件台账 + 后台框架一页纸）与 `通用文档/`（方法论）。
