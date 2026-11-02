# 机器人文档（实物资料）

这里只放**我们自己的、别的仓库里没有的**实物资料。代码不在这里（代码在 `esp32-firmware/`、`xiaozhi-server/`）。

## 已入库

| 文件 | 是什么 | 用途 |
|---|---|---|
| `moss/20251208-BOM及组装材料清单.xlsx` | MOSS 的 **PCB BOM 清单 + 组装材料清单**（含 `与原版对比情况` 列：一致 / 数量不同 / 新增） | 补焊、换件、对料；和 `工作文档/MOSS-硬件台账.md` 的引脚真相表互补 |
| `moss/FlyingProbeTesting.json` | MOSS 的**飞针测试坐标**（单位 mil，含每个元件的 X/Y/角度/层） | 代工/返修时给测试机用；也能反查某个元件在板上的位置 |

> 这两份是**实物事实**，和台账号一样属于"不用再翻别处"的资料。改硬件后记得同步更新。

## 故意没有入库（第三方代码）

| 目录（本地有） | 是什么 | 为什么不入库 |
|---|---|---|
| `dooi-robot-esp32p4-opensource-master/` | **DooiRobot 官方开源工程**（MIT License，© 2025 深圳新智未来科技），约 10 MB / 1154 文件，含 `docs/`（blufi、mcp-protocol、websocket、custom-board 等） | 第三方代码不重复入库、也不改它；要参考直接取上游仓库即可 |
| `dooirobot/` | 从上面那份里摘出来的**板级 app 文件副本**（`app_motor.c` / `app_servo.c` / `app_led.c` / `app_mcp_tool.cc` …），3.7 MB 里 3.4 MB 是 LVGL 字体，和我们本地副本只有 2 处中文注释差异 | 同上。**我们自己的 Doly 板级代码在 `esp32-firmware/main/boards/doly/`** |

⚠️ 别把这两个目录 `git add -f` 进来 —— 一是体积，二是许可证与归属会含糊。
如果确实需要长期引用上游，正确做法是**记下上游版本/commit**，而不是把源码搬进来。
