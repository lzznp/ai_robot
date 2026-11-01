# 小智多机器人调度（ai_robot）

基于**小智固件 + 小智后台（xiaozhi-server）**改造的多机器人智能调度项目。
目标架构：ESP32 是纯执行终端（播报、动作、表情），后台是大脑（LLM 调度 + 场景管理），走 WebSocket。

当前三台机器人的状态见 `PROJECT_STATUS.md`（最后更新 2026-07-03）：
Doly（双圆屏小车）、瓦力（小车）固件已完成，MOSS（悬挂式）待适配。

## 目录

| 目录 | 是什么 |
|---|---|
| `esp32-firmware/` | 固件（在其上改造了 Doly/瓦力的电机舵机、LVGL 21 种表情、双屏驱动） |
| `xiaozhi-server/` | 后台（LLM 调度、场景管理、MCP 工具） |
| `xiaozhi-server/data/roles.yaml`、`scenes/*.yaml` | **多机器人角色与场景设定**（本项目的核心设计） |
| `dooirobot/` | 机器人的辅助代码（字体、IMU 配置等） |
| `doc/`、`docs/` | 侦察报告、接线图、开发记录 |
| `moss/`、`tools/` | 零散工具与实验 |
| `PROJECT_STATUS.md` | 项目进展（人工维护，每个里程碑更新） |
| `GEMINI.md` | 智能体交互规范（中文、先方案后动手） |

## 这个仓库里**故意没有**什么（`.gitignore` 里挡着）

| 没入库 | 为什么 | 怎么恢复 |
|---|---|---|
| `xiaozhi-server/models/`（含 `SenseVoiceSmall/model.pt`，892 MB） | GitHub 单文件上限 100 MB，且模型可重新下载 | 按 xiaozhi-server 官方文档下载模型到 `models/` |
| `xiaozhi-server/data/.config.yaml` | **里面是真凭据**：约 50 处 API key / MQTT 签名密钥 / 各类 token，其中确有可用真 key | `cp xiaozhi-server/config.yaml xiaozhi-server/data/.config.yaml`，再填自己的 key |
| `xiaozhi-server/data/*.db` | 运行期数据库（设备注册、会话记录），二进制且一直变 | 首次运行自动生成 |
| `xiaozhi-server/tmp/`、`**/*.log` | 日志 | 可再生 |
| `esp32-firmware/build/`、`.pio/` | 编译产物 | 重新编译 |
| `*-old/`（`esp32-firmware-old`、`xiaozhi-server-old`）、`准备废弃/` | 旧版本与废弃目录，留在本地 | 见本地磁盘 |
| `.deepseek/` | DSH 智能体的运行期状态，跟本项目无关 | — |

⚠️ **配置里的密钥要单独保管**。`.config.yaml` 不进版本库是有意的，别图省事把它加回来。

## 另一台电脑上怎么接着做（重要）

这个仓库是用**本机 2026-07 的副本**建的初始提交，最新代码在那台开发机上。
在那台机器上**不要 `git init` 一个新仓库**——那样会和这份历史分叉。正确做法：

```powershell
# 1) 先克隆这个仓库（得到一个带历史的空壳）
git clone git@github.com:lzznp/ai_robot.git D:\study\ai_robot_gh

# 2) 把那边项目目录里"该入库的东西"覆盖进克隆目录
#    （直接整目录拷贝也行，.gitignore 会把模型/编译产物/日志挡掉；别拷 .git* 和 data/.config.yaml）

# 3) 在那份克隆里提交并推
cd D:\study\ai_robot_gh
git add -A
git commit -m "同步开发机上的最新进展（YYYY-MM-DD）"
git push
```

那台机器也需要一把自己的 SSH key（`ssh-keygen -t ed25519`，公钥加到
<https://github.com/settings/keys>），因为第一把钥匙只装在这台笔记本上。

## 历史

- `2026-11-02` 初始提交：从本机 7 月副本整理入库（1685 个文件，排除了模型/凭据/编译产物/旧版本）。
