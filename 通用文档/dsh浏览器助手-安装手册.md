# DSH 浏览器助手（dsh-browser）安装手册 · 给另一台机器上的你

> **用途**：这是一份"照做就行"的安装/修复手册，写给**另一台机器上的 agent**（同一个 DSH）。
> **来源**：2026-10-09 那场对话（工作区 `D:\study\wails`，会话「基础版开工前衔接确认」）的实测结果。
> **性质**：不是官方文档，是"在这台机器上跑通了的一条路"。凡是**路径、端口、版本号**，都要在你的机器上先核一遍（第 2 节），别照抄。
>
> 一句话结论：**这个插件不能靠"填 git 地址"装，也不能直接装仓库根目录** —— 必须先把源码 `pnpm install` + `build` 出产物，然后把路径指到**桥包那一层**装进 GUI，再手动在浏览器扩展侧边栏里填一次桥地址。
>
> ★★★ **顺序不能颠倒，而且中间有四步只能人工做**（agent 代不了，别让它替你做）：
> **① 人工：GUI 里装插件（本地包形式） → ② 人工：重启整个 GUI → ③ 人工：浏览器加载扩展 → ④ 人工：改插件设置、填桥地址 → ⑤ 让 agent 验收**。
> 跳任何一步，症状都是同一句“连不上”，很容易被误判成装坏了。
> **本手册里任何绝对路径都只是“当时那台机”的值**，包括安装根（作者机 `D:\tools\deepseek-harness`、另一台机 `D:\tools\harness`）——一律照第 2 节现查，**别照抄**。

---

## 1. 结构速览：这套东西由 4 个部件组成

| # | 部件 | 是什么 | 落在哪 |
|---|---|---|---|
| 1 | **桥包**（DSH 插件） | `@yuxianglin/dsh-bridge-browser`，packages/browser/bridge-browser，宿主侧代码，提供 `browser_*` 工具 | 本地源码目录 → `~/.dsh/profiles/<GUI 用的 profile>/package.json` 里注册 |
| 2 | **浏览器扩展** | MV3 侧边栏 + service worker，UI 在侧栏，负责"看页面/点页面" | 浏览器 `chrome://extensions` / `edge://extensions` 加载**未打包**扩展，指向源码目录的 `dist` |
| 3 | **桥端点** | 桥挂在 DSH 宿主自己的 HTTP 端口上，走 `/ext/bridge`（WS） | 和 GUI 同端口，**不额外占端口** |
| 4 | **token** | 非回环连接才需要 | `~/.dsh/ext-bridge-token`；回环 + `chrome-extension://` 来源**免 token** |

**最容易误判的一点**：部件 1 装好 ≠ 能用了。部件 2 的扩展没加载、或部件 3 的地址没手填，工具一调只会报 `no browser extension is connected to the bridge` / `bridge-closed`。

---

## 2. 动手前：先在你自己的机器上读四个事实

**不要照抄我这边（作者机）的路径和端口。** 这四条命令把变量取出来：

```powershell
# ⓪ DSH 安装根（本机实际位置）—— ★ 这是变量，不是常量，后面处处要用它拼 pnpm 路径
$DSHROOT = Split-Path (Get-Process 'DeepSeek Harness' | Select-Object -First 1).Path
$DSHROOT
# 作者机当时是 D:\tools\deepseek-harness；另一台机（2026-10-17 实测）是 D:\tools\harness

# ① GUI 用的是哪个 profile、runtime 在哪 → 看正在跑的 Harness 进程命令行
Get-CimInstance Win32_Process -Filter "Name like '%DeepSeek Harness%'" |
  ForEach-Object { "PID {0}`n{1}" -f $_.ProcessId, $_.CommandLine }

# ② GUI 宿主监听哪个端口（桥就挂在这个端口上，扩展要填的地址用它）
$pids = (Get-CimInstance Win32_Process -Filter "Name like '%DeepSeek Harness%'").ProcessId
Get-NetTCPConnection -State Listen |
  Where-Object { $pids -contains $_.OwningProcess } |
  ForEach-Object { "127.0.0.1:$($_.LocalPort)  PID $($_.OwningProcess)" }

# ③ 该 profile 里现在注册了哪些 bundle
Get-Content "$env:USERPROFILE\.dsh\profiles\<你的 profile>\package.json" -Raw
```

**判据**：
- 第 ⓪ 步拿到的 `$DSHROOT` 要**写在手边**：pnpm 就在 `$DSHROOT\resources\runtime\pnpm\bin\pnpm.cjs`。**不要**把任何安装根写死进命令里。
- 第 ① 步命令行里出现 `profiles\desktop` ⇒ GUI 用的是 `desktop` profile（**这是关键**：官方安装器 `scripts/install.ps1` 把 profile 写死成 `web`，所以官方一行安装器在 GUI 版上一定装错地方）。
- 第 ② 步拿到的端口，记下来，后面要填进扩展。**作者机与另一台机都是 19387**；扩展的自动探测表只有 `3080 / 3081 / 3090 / 14389 / 43189`，端口若不在这张表里 ⇒ **必须手填**。
- 第 ③ 步若 `dsh.profile.bundles` 里没有 `@yuxianglin/dsh-bridge-browser` ⇒ 桥没挂上。

顺手核一下桥端点（现在是 404 属正常，因为还没装）：

```powershell
curl.exe -s -o NUL -w "%{http_code}`n" "http://127.0.0.1:<端口>/ext/bridge-config"
# 404 / 页面 HTML ⇒ 桥没挂上
# 200 + {"wsUrl":"ws://127.0.0.1:<端口>/ext/bridge"} ⇒ 桥已就绪
```

---

## 3. 处理源码（这一步就是"解压后你处理了"里的"处理"）

### 3.1 拿到源码并放到固定位置

GitHub 下 zip 解压（推荐，比 clone 干净）：

```
https://github.com/Lum1104/dsh-browser
```

作者机放的是 `D:\tools\dsh-browser-main`（zip 解压出来自带 `-main` 后缀）。**放在哪都行，路径后面要用。**

> ⚠️ 先确认位置：**仓库根**（`name: "dsh-browser"`）**不能**当插件装，能装的是它下面那层 `packages/browser/bridge-browser`。目录别搞混。

### 3.2 装依赖 —— 用 Harness 自带的 pnpm 内核

`pnpm.ps1` 在 Windows 上常被执行策略挡住，直接用 node 跑 `.cjs`：

```powershell
$pnpm = "$DSHROOT\resources\runtime\pnpm\bin\pnpm.cjs"          # $DSHROOT 来自第 2 节 ⓪，现查不要照抄
node $pnpm --version                                            # 作者机与另一台机都是 11.7.0

cd <源码根，例如 D:\tools\dsh-browser-main>
node $pnpm install --store-dir "<源码根>\.pnpm-store" --reporter=append-only
```

- 仓库自带 `.npmrc` 指向 **npm 官方源**；`pnpm-workspace.yaml` 里已列好 `esbuild / koffi / node-pty / protobufjs` 等构建脚本白名单，不需要额外放行。
- 装完大约 **690+ 个包**，全部依赖应解析到宿主同一版本（作者机：全部 `0.2.0-rc.2`）。
- **`node_modules` 和 `.pnpm-store` 要留着**，那是构建要用的，别当垃圾清。

### 3.3 构建桥包 + 构建扩展（两次 build，缺一不可）

```powershell
# 桥（宿主侧）：产出 lib/，插件入口 main 指着 lib/index.js
node $pnpm --filter @yuxianglin/dsh-bridge-browser run build

# 扩展（浏览器侧）：产出 extensions\dsh-browser\dist\
node $pnpm --filter dsh-browser-extension run build
```

> **最容易漏的就是第二次 build。** 我上一轮只 build 了桥，结果插件装好了、扩展目录里却**没有 `dist`**，浏览器根本加载不了。zip 里**不带任何编译产物**。

### 3.4 核产物

```powershell
# 桥产物
Get-ChildItem "<源码根>\packages\browser\bridge-browser\lib" -Recurse -File |
  ForEach-Object { "{0,10}  {1}" -f $_.Length, $_.Name }
# 作者机：index.js 87.9KB、protocol.js、invariant.js、client.js、types\**

# 扩展产物（manifest.json 必须在 dist 根！）
Get-ChildItem "<源码根>\extensions\dsh-browser\dist" |
  ForEach-Object { "{0,10}  {1}" -f $_.Length, $_.Name }
# 作者机：manifest.json(v0.1.4)、background.js 177.7KB、content.js 22.5KB、
#         panel\index.html、panel\assets\index.js 424KB、assets\icons\*、_locales\{en,zh_CN,zh_TW}
```

`dist` 是自包含的，能直接当未打包扩展加载。

### 3.5 特殊情形：老版本源码（桥 v0.0.4 及更早）才需要改 peer

- 新版（**v0.0.7**）的 `peerDependencies` 已经写成宿主实际版本（作者机 `0.2.0-rc.2`），**不用改任何源码**。
- 老版（v0.0.4）把 13 条 `@deepseek-ai/*` 的 peer 全写死 `^0.1.2-rc.1`，不含 0.2.x ⇒ 安装/加载会被版本判定拦下。那时要把 `packages/browser/bridge-browser/package.json` 里这些 `^0.1.2-rc.1` 放宽为 `*`。
  - 放宽是**有依据**的：桥运行时真正调用的只有 `defineTool`（dsh-tools）、`createUserMessage`（dsh-llm）、`dshHomePath`（dsh-home-paths）、`z`（schemastery），这四个在 0.2.0 里都在；`ToolDefinition / ToolRunContext / WebRoute / WebUpgradeRoute` 全是 `import type`，编译后一行不剩。

---

## 4. ★ 人工步骤一：在 GUI 里装插件（本地包形式，不需要手改 profile 的 json）

> ⚠️ **这一步必须由人来做，agent 不要代做。**
> 原因不是权限：**手改 `~/.dsh/profiles/<profile>/package.json` 会被 GUI 自己重写覆盖**（2026-10-17 实测：agent 手写进去的注册，在 GUI 用本地包形式装成功后，被它按自己的格式整份重写了）。
> 所以**让人在 GUI 里点**，注册才归 GUI 管，以后升级/卸载才不会打架。
> agent 在这一步的正确姿势：**把该填的路径算好、念给人听，然后等**。

GUI 的插件管理器明确支持**本地绝对路径**、包名、git 地址、压缩包，装完可「立即启用」，且 profile 变更**跨会话持久化**。所以走 GUI 就行，别去手改 `package.json`。

> 用户实测：**在 GUI 里填 git 地址装不上**（上游没跟上宿主版本）；填仓库根目录会报
> `这个包没有声明组合包，无法作为插件安装：dsh-browser declares no dsh.bundle`。
> ★ **看到这句就只说明一件事：你选的那层不是桥包。** 报错里点名的名字就是那层包的 `name`（仓库根是 `dsh-browser`）；换成 `packages\browser\bridge-browser` 就行。**不要**把这句话误读成“GUI 装不了、得手改 json”。

**操作**：

1. ★ **由你本人操作**：GUI → **设置 → 插件 → 添加插件**（选「本地包」/本地绝对路径那一项，**不是** git 地址）
2. 填**桥包那一层**的绝对路径（不是仓库根）：
   ```
   <源码根>\packages\browser\bridge-browser
   ```
   例：`D:\tools\dsh-browser-main\packages\browser\bridge-browser`
3. 安装完点 **立即启用**
4. **重启整个 GUI**（不是"重载插件"）—— 然后才去装扩展（第 5 节）、才去改插件设置填地址（第 6 节）

> **为什么必须重启整个程序**：桥是**宿主代码**，跑在宿主进程里；"重载插件"只对改了 `extension\` 的扩展生效。

**验收（这一步过了，GUI 那半就对了）**：

```powershell
curl.exe -s "http://127.0.0.1:<端口>/ext/bridge-config"
# 期望：{"wsUrl":"ws://127.0.0.1:<端口>/ext/bridge"}

Get-Content "$env:USERPROFILE\.dsh\profiles\<profile>\package.json" -Raw
# 期望：dependencies 里有 "@yuxianglin/dsh-bridge-browser": "link:<源码根路径>/packages/browser/bridge-browser"
#       dsh.profile.bundles 里含 "@yuxianglin/dsh-bridge-browser"
```

---

## 5. ★ 人工步骤二/三：重启 GUI，然后加载扩展（顺序别倒）

**先确认第 4 节的插件已经「立即启用」并且整个 GUI 重启过了**（`curl http://127.0.0.1:<端口>/ext/bridge-config` 返回 200 之后再往下）。**扩展先装、插件后装**的顺序会让人白折腾一轮：扩展装了也连不上，还容易误判成扩展坏了。

1. 开 `edge://extensions`（Chrome 就是 `chrome://extensions`）
2. 打开 **开发人员模式**
3. 点 **「加载解压缩的扩展」**
4. 选到 **`dist` 这一层**：
   ```
   <源码根>\extensions\dsh-browser\dist
   ```
5. 如果之前装过旧版（比如 `C:\deepseek\dsh-browser\extensions\dsh-browser\dist`），**先移除旧的再加载新的**，否则加载的是内存里那份旧产物。

---

## 6. ★ 人工步骤四：改插件设置、手填桥地址（唯一需要人工配置的一步）

> 顺序：**扩展加载完之后再来改这一项**。地址填错/没填的症状，和“插件没装”一模一样（都是连不上），所以先保证第 4、5 节都过了。

1. 点浏览器工具栏的 DeepSeek 图标 → 打开侧边栏
2. 进设置，把桥地址填成：
   ```
   ws://127.0.0.1:<端口>/ext/bridge
   ```
   例：`ws://127.0.0.1:19387/ext/bridge`
3. **只填地址，token 空着**

**为什么必须手填**：扩展自动探测的端口表是 `3080 / 3081 / 3090 / 14389 / 43189`（`extensions/dsh-browser/src/background/index.ts` 里的 `DISCOVERY_PORTS`）。GUI 版宿主端口（作者机 19387）不在表里，不手填就永远探不到。

**为什么不用 token**：桥的校验规则是「**回环地址 + `chrome-extension://` 来源 ⇒ 免 token**」（`packages/browser/bridge-browser/src/server.ts`，约 294–310 行）。Edge/Chrome 的扩展正好是 `chrome-extension://`，所以回环免签。

4. 侧边栏显示**已连接**即可。

---

## 7. 全链路验收（四层，逐层都验，别跳）

| 层 | 怎么验 | 通过的样子 |
|---|---|---|
| 桥（宿主） | `curl http://127.0.0.1:<端口>/ext/bridge-config` | 200 + `{"wsUrl":...}` |
| 注册 | 读 `profiles\<profile>\package.json` | dependencies 有 link、bundles 里有它 |
| 扩展 | 浏览器扩展页里那条是"已加载"、路径指向新 `dist` | 无报错、manifest 版本是新构建的 |
| **端到端** | 让 agent 调 `browser_list_tabs` | 能列出标签页（而不是 `no browser extension is connected to the bridge`） |

**最后一步才是"真通了"**：`browser_list_tabs` 能返回标签页列表 ⇒ 桥、扩展、连接三者都成立。
注意列表里的 `controlled` 字段：全部 `false` 表示扩展连上了、但**还没有页面被交给助手**；用户真正发话/或在侧栏绑定之后才会变 true。

---

## 8. 坑清单（都是实测踩过的）

| # | 坑 | 正确做法 |
|---|---|---|
| 1 | 用官方 `scripts/install.ps1` 一行装 | ❌ 它把 profile 写死 `web`；GUI 版用 `desktop` ⇒ 桥永远挂不上 |
| 2 | GUI 里填 **git 地址** | ❌ 上游版本没跟上宿主；走本地路径 |
| 3 | GUI 里填 **仓库根路径** | ❌ 报 `declares no dsh.bundle`；填 `packages/browser/bridge-browser` |
| 4 | 只 build 桥、忘了 build 扩展 | ❌ 扩展目录无 `dist`，浏览器加载不了 |
| 5 | 装完插件只"重载插件" | ❌ 桥是宿主代码，要**重启整个 GUI** |
| 6 | 侧边栏不填地址，等它自动发现 | ❌ 探测表不含 GUI 端口，必须手填 |
| 7 | 用 `pnpm` / `pnpm.ps1` | ❌ 常被执行策略挡；用 `node <harness>\resources\runtime\pnpm\bin\pnpm.cjs` |
| 8 | 按 `Test-Path` / `Get-ChildItem` 判断 `app.asar` 里的东西 | ❌ asar 是归档不是目录，磁盘 API 会骗你；要读就 `ELECTRON_RUN_AS_NODE=1` + `DeepSeek Harness.exe` 跑脚本 |
| 9 | 把 `node_modules` / `.pnpm-store` 当垃圾删 | ❌ 那是 build 依赖，删了要重装 |
| 10 | 扩展升了、桥没升（或反过来） | ⚠️ 两者版本要配套；升级后**两边都重建**，且扩展要去扩展页"重新加载" |

---

## 9. 一键抄写块（变量现查，别把路径写死）

```powershell
# ===== 变量（★ 全部现查，不要把任何绝对路径抄进脚本）=====
$SRC      = "D:\tools\dsh-browser-main"                                  # 源码根（解压出来的那层；本机实测就是这个位置）
$DSHROOT  = Split-Path (Get-Process 'DeepSeek Harness' | Select-Object -First 1).Path
                                                                        # 安装根：作者机 D:\tools\deepseek-harness、另一台机 D:\tools\harness
$PNPM     = "$DSHROOT\resources\runtime\pnpm\bin\pnpm.cjs"
$PORT     = 19387                                                       # ← 用第 2 节 ② 查出来的端口（两台机实测都是 19387）

# ===== 1) 装依赖 =====
cd $SRC
node $PNPM install --store-dir "$SRC\.pnpm-store" --reporter=append-only

# ===== 2) 建桥产物 =====
node $PNPM --filter @yuxianglin/dsh-bridge-browser run build

# ===== 3) 建扩展产物 =====
node $PNPM --filter dsh-browser-extension run build

# ===== 4) 核产物 =====
Get-ChildItem "$SRC\packages\browser\bridge-browser\lib" -Recurse -File | Select-Object Length,Name
Get-ChildItem "$SRC\extensions\dsh-browser\dist" | Select-Object Length,Name

# ===== 5) 核桥端点（★ 必须等人工做完 A 并重启 GUI 之后再跑）=====
curl.exe -s "http://127.0.0.1:$PORT/ext/bridge-config"

# ===== ★★ 下面四步只能人工做，顺序不能颠倒（agent 只负责把路径念给人听）=====
#  A. 人工｜GUI → 设置 → 插件 → 添加插件（**本地包**形式）→ 填：
#        "$SRC\packages\browser\bridge-browser"      ← ★ 是桥包这一层，不是仓库根！
#     → 点「立即启用」
#     ⚠️ 报 `dsh-browser declares no dsh.bundle` = 选错层了，换上面那个路径重来
#     ⚠️ agent 不要替人改 profile 的 json：GUI 会整份重写覆盖
#  B. 人工｜**完全退出 GUI 再重新打开**（不是"重载插件"）→ 回来跑第 5) 步，应返回 200
#  C. 人工｜edge://extensions → 开发人员模式 → 加载解压缩的扩展 → 选：
#        "$SRC\extensions\dsh-browser\dist"          ← ★ 是 dist 这一层
#     ⚠️ 若以前加载过旧版扩展，先移除旧的再加新的
#  D. 人工｜改插件设置 → 桥地址手填： ws://127.0.0.1:$PORT/ext/bridge    （token 留空）
# ===== 最后：让 agent 调 browser_list_tabs 验收 =====
```

---

## 10. 本次事实台账（作者机，仅供对照，别当常量）

| 项 | 值 |
|---|---|
| 会话 | `D:\study\wails` ·「基础版开工前衔接确认」· 2026-10-09 |
| DSH 安装位置 | `D:\tools\deepseek-harness`（GUI 版，运行时 **0.2.0-rc.2**） |
| 旧位置 | `C:\deepseek\deepseek-harness`（老网页版，运行时 0.1.5-alpha.2） |
| profile | `desktop`（GUI 用）/ `web`（老网页版用，已停用） |
| 宿主端口 | **19387** |
| 源码 | `D:\tools\dsh-browser-main`（GitHub zip，桥 **v0.0.7**、扩展 **v0.1.4**） |
| 旧源码 | `C:\deepseek\dsh-browser`（git clone，桥 v0.0.4、扩展 v0.1.3，**没删，是孤儿**） |
| 桥产物 | `packages\browser\bridge-browser\lib\index.js` 87.9 KB 等 |
| 扩展产物 | `extensions\dsh-browser\dist\`（manifest v0.1.4 + background.js 177.7KB + content.js 22.5KB + panel 424KB） |
| token | `~\.dsh\ext-bridge-token`（回环连接用不上） |
| 工具链 | node v24.13.0 / pnpm 11.7.0（Harness 自带 pnpm.cjs） |
| 上游 | https://github.com/Lum1104/dsh-browser ，MIT，作者 Yuxiang Lin |

### 10.1 另一台机实测（2026-10-17，Windows / 用户本机）

| 项 | 值（**同样只是那台机的值**） |
|---|---|
| DSH 安装根 | **`D:\tools\harness`**（与作者机的 `D:\tools\deepseek-harness` **不同**，所以路径一律现查） |
| pnpm 路径 | `D:\tools\harness\resources\runtime\pnpm\bin\pnpm.cjs` |
| 运行时 / node / pnpm | `0.2.0-rc.2` / node **24.20.0** / pnpm **11.7.0**（与桥的 peer 声明一致，**源码一行没改**） |
| profile / 端口 | `desktop` / **19387**（与作者机相同） |
| 源码 | `D:\tools\dsh-browser-main`，桥 **0.0.7**、扩展 **0.1.4** |
| 装依赖 | `pnpm install` **4 分 31 秒**，全部 `@deepseek-ai/*` 解析到 `0.2.0-rc.2` |
| 旧扩展残留 | **`C:\deepseek\dsh-browser\extensions\dsh-browser\dist` 还在**——加载新扩展前要先移除旧的 |
| 装完的现象 | `GET /ext/bridge-config` → `200 {"wsUrl":"ws://127.0.0.1:19387/ext/bridge"}`；`browser_list_tabs` 能列出标签页 ⇒ 三层全通 |
| 一个只有实操才知道的细节 | 扩展的**每个动作都要人在侧栏点“允许”**；超时未点会报 `The browser approval request for "browser_xxx" timed out before the user responded.`（不是坏了） |


---

## 11. 给"另一台机器的你"的两句话

1. **先读事实再动手**：**安装根**、`profile` 名、端口、运行时版本、源码版本，这五个变量每台机都可能不同。手册里的 `D:\tools\harness`、`19387`、`desktop`、`0.2.0-rc.2` 都只是“某台机”的值。
2. **验收以工具为准**：`browser_list_tabs` 能列标签页，才算装好了；`/ext/bridge-config` 返回 JSON 只证明桥活着，不证明浏览器那头连着。
3. **四步人工不能省、顺序不能倒**：GUI 装插件（本地包）→ 重启整个 GUI → 加载扩展 → 改插件设置填桥地址。**agent 只负责把路径念给人听，不要替人改 profile。**

---

## 12. 更正记录（2026-10-17，第二台机装通之后追补）

> 规矩同项目其它文档：**不抹旧结论，改了就追加并说明为什么改。**

| # | 原来写的 | 改成 | 为什么改 |
|---|---|---|---|
| 1 | 安装根写死 `D:\tools\deepseek-harness` | **一律现查** `$DSHROOT = Split-Path (Get-Process 'DeepSeek Harness').Path`，脚本里不再出现绝对路径 | 这台机的安装根是 `D:\tools\harness`，与作者机**不同**。手册里写死路径，下一个人一定照抄错 |
| 2 | 只说“GUI 那半归人做”，没给顺序 | **四步人工、顺序写死**：GUI 装插件 → 重启 GUI → 加载扩展 → 改插件设置填地址 | 实测过一次顺序反了（先折腾扩展），症状只有一句“连不上”，白绕一圈 |
| 3 | 隐含“GUI 装不上就手改 json” | ★ **明确禁止 agent 手改 profile 的 json**：GUI 会整份重写覆盖 | 实测：agent 手写的 `link:` 注册，在 GUI 用本地包形式装成功后**被整份覆盖**。既然会被覆盖，手改就是白干且制造“我装过了”的假象 |
| 4 | — | ★ 加一条误判警示：报 `declares no dsh.bundle` **只说明选错了层** | 我这次把它误读成“GUI 这条路不可信”，于是抢着手改——**错的是我的判断，不是 GUI**。看到这句就换 `packages\browser\bridge-browser` 重来 |
| 5 | — | 加“扩展每个动作要人点允许” | 不写这条，agent 会以为 `timed out before the user responded` 是装坏了；实际是安全设计 |
| 6 | — | 第 5/6 节加了前置顺序说明 | 同上，都是为了不再把“顺序问题”误判成“装坏了” |

