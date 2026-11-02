# 小智多机器人调度

基于小智固件和 xiaozhi-server 的多机器人项目。ESP32 通过 WebSocket 接收指令，执行语音、灯光、电机和摄像头操作；后台负责对话、能力管理和场景编排。

截至 2026-11-01 的开发记录，MOSS 的灯、屏幕、摄像头和两个步进电机已完成后台联调。其他机器人的表情与电机功能仍在逐台补充。具体固件版本与实测范围见[后台框架说明](工作文档/后台框架·一页纸_20261101.md)及[硬件台账](#开发文档)。

## 架构与目录

固件提供 `gpio`、`pwm`、`ws2812`、`stepper`、`camera` 等底层动作。后台能力库把“前进”“呼吸灯”等行为转换为动作序列，再通过 `/api/command` 下发。动作字段和各板支持情况维护在 [core/actions.py](xiaozhi-server/core/actions.py)。

| 路径 | 内容 |
|---|---|
| `esp32-firmware/` | 多板固件，包括 MOSS、月球车和瓦力等配置 |
| `xiaozhi-server/` | 对话服务、动作接口、能力库与场景管理 |
| `xiaozhi-server/web_console/` | Streamlit 控制台 |
| `pin_scan/` | 瓦力引脚自检工程 |
| `tools/`、`moss/`、`dooirobot/` | 调试工具与实验代码 |
| `doc/`、`docs/`、`机器人文档/` | 接线图、硬件资料与开发记录 |
| `工作文档/`、`通用文档/` | 项目进度、硬件台账和开发方法 |

## 本地运行

以下命令在仓库根目录执行，使用已经配置好依赖的 Python 环境。后台依赖以 [requirements.txt](xiaozhi-server/requirements.txt) 为准，控制台另需 Streamlit。Windows 下还需准备 Opus 和 FFmpeg；入口会将当前环境的 `Library\bin` 加入 DLL 搜索路径。

首次运行时复制配置模板，再填写所用模型服务的参数。以下命令会保留已有配置：

```powershell
New-Item -ItemType Directory -Force xiaozhi-server/data | Out-Null
if (-not (Test-Path xiaozhi-server/data/.config.yaml)) {
    Copy-Item xiaozhi-server/config.yaml xiaozhi-server/data/.config.yaml
}
```

按所选语音识别方案下载模型到 `xiaozhi-server/models/`，然后启动后台：

```powershell
cd xiaozhi-server
python app.py
```

默认端口为 WebSocket 8000、OTA/视觉服务 8003、指令 API 8004。WebSocket 和 HTTP 端口可在配置中调整。

另开终端启动控制台：

```powershell
cd xiaozhi-server/web_console
python -m streamlit run app.py
```

修改后台或控制台依赖的 `core/` 模块后重启对应进程。控制台页面代码通常刷新即可加载。

## 固件与指令

编译、烧录前先选择对应板型和串口。以下为 MOSS 的烧录命令示例：

```powershell
cd esp32-firmware
idf.py -B build -DSDKCONFIG=sdkconfig -p COM4 flash
```

内存较少的开发机可以先设置 `$env:NINJAFLAGS = "-j1"`，减少并行编译进程。

指令发送到 `POST http://<server>:8004/api/command`。下面以支持 WS2812 和步进电机的板型为例；设备 ID、引脚和动作参数按实际硬件填写：

```json
{
  "device_id": "<device_id>",
  "command": {
    "type": "command",
    "payload": {
      "actions": [
        {"type": "ws2812", "pin": 7, "count": 1, "rgb": [64, 0, 0]},
        {"type": "stepper", "motor": 1, "steps": 64, "speed": 60}
      ]
    }
  }
}
```

## 开发文档

- [后台框架与当前基线](工作文档/后台框架·一页纸_20261101.md)
- [MOSS 硬件台账](工作文档/MOSS-硬件台账.md)
- [月球车硬件台账](工作文档/月球车-硬件台账.md)
- [瓦力硬件台账](工作文档/瓦力-硬件台账.md)

`PROJECT_STATUS.md` 是早期进度记录，当前状态以 `工作文档/` 为准。

## 本地数据

模型权重、`data/.config.yaml`、运行数据库、日志和固件构建产物由本地环境维护，未纳入版本控制。换机时需单独恢复配置、模型和需要保留的设备/能力/场景数据。

历史提交中的配置曾包含真实 API 密钥，后续已替换为占位符。旧密钥如仍有效，应撤销并更换。
