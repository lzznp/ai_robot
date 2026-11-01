# WebSocket 连接建立后的处理逻辑分析

> 生成时间：2026-06-22  
> 分析范围：`xiaozhi-server/core/`（WebSocket 服务端）

---

## 目录

1. [WebSocket 连接入口函数](#1-websocket-连接入口函数)
2. [收数据前的校验逻辑](#2-收数据前的校验逻辑)
3. [客户端首条消息格式要求](#3-客户端首条消息格式要求)
4. [超时关闭机制](#4-超时关闭机制)

---

## 1. WebSocket 连接入口函数

连接建立后有两层入口，按调用顺序排列：

### 第 1 层：`WebSocketServer._handle_connection()`

**文件**：`xiaozhi-server/core/websocket_server.py` **第 81 行**

```python
async def _handle_connection(self, websocket: websockets.ServerConnection):
    headers = dict(websocket.request.headers)
    if headers.get("device-id", None) is None:
        # 尝试从 URL 的查询参数中获取 device-id
        from urllib.parse import parse_qs, urlparse
        request_path = websocket.request.path
        if not request_path:
            self.logger.bind(tag=TAG).error("无法获取请求路径")
            await websocket.close()
            return
        parsed_url = urlparse(request_path)
        query_params = parse_qs(parsed_url.query)
        if "device-id" not in query_params:
            await websocket.send("端口正常，如需测试连接，请启动digital-human测试")
            await websocket.close()
            return
        else:
            websocket.request.headers["device-id"] = query_params["device-id"][0]
        ...
    # 先认证，后建立连接
    try:
        await self._handle_auth(websocket)
    except AuthenticationError:
        await websocket.send("认证失败")
        await websocket.close()
        return
    handler = ConnectionHandler(...)
    try:
        await handler.handle_connection(websocket)       # → 第 2 层
    except Exception as e:
        ...
```

这个函数在 WebSocket 握手成功后**立即**被调用。注册于 `websocket_server.py:77`：

```python
async with websockets.serve(
    self._handle_connection, host, port, process_request=self._http_response
):
    await asyncio.Future()
```

### 第 2 层：`ConnectionHandler.handle_connection()`

**文件**：`xiaozhi-server/core/connection.py` **第 193 行**

```python
async def handle_connection(self, ws: websockets.ServerConnection):
    try:
        self.loop = asyncio.get_running_loop()
        self.headers = dict(ws.request.headers)
        ...
        # 启动超时检查任务
        self.timeout_task = asyncio.create_task(self._check_timeout())
        # 在后台初始化配置和组件
        asyncio.create_task(self._background_initialize())
        try:
            async for message in self.websocket:       # ★ 消息循环入口
                await self._route_message(message)
        except websockets.exceptions.ConnectionClosed:
            ...
    finally:
        await self._save_and_close(ws)
```

**消息循环入口**：`connection.py:239-241`，用 `async for` 迭代 WebSocket 消息流。

---

## 2. 收数据前的校验逻辑

在 `async for message in self.websocket` 循环开始之前，有两层校验和初始化。

### 2.1 连接层校验（握手后、`handle_connection()` 前）

`websocket_server.py:81-114`，即在 `handler.handle_connection()` 被调用之前：

| 校验 | 文件:行号 | 逻辑 | 失败后果 |
|------|----------|------|---------|
| **Device-ID 存在性** | `websocket_server.py:83-106` | 先查 headers 中的 `device-id`；若无则从 URL query params 中取 | 取不到则关闭连接（第 91、97 行） |
| **客户端认证** | `websocket_server.py:110-114` | 调用 `_handle_auth()`（第 206-227 行） | 发"认证失败"后关闭连接（第 113 行） |

**`_handle_auth()` 的完整实现**（`websocket_server.py:206-227`）：

```python
async def _handle_auth(self, websocket):
    # 先认证，后建立连接
    if self.auth_enable:
        headers = dict(websocket.request.headers)
        device_id = headers.get("device-id", None)
        client_id = headers.get("client-id", None)
        if self.allowed_devices and device_id in self.allowed_devices:
            # 白名单设备免检
            return
        else:
            token = headers.get("authorization", "")
            if token.startswith("Bearer "):
                token = token[7:]
            else:
                raise AuthenticationError("Missing or invalid Authorization header")
            auth_success = self.auth.verify_token(
                token, client_id=client_id, username=device_id
            )
            if not auth_success:
                raise AuthenticationError("Invalid token")
```

**Token 验证算法**（`core/auth.py:40-58`）：

```
HMAC-SHA256(secret, "{client_id}|{device_id}|{timestamp}")
→ base64url 编码 → "{signature}.{timestamp}"
```

### 2.2 `handle_connection()` 内的预初始化

`connection.py:193-237`，在 `async for message` 循环开始前依次执行：

| 操作 | 行号 | 代码 | 说明 |
|------|------|------|------|
| 记录事件循环 | 196 | `self.loop = asyncio.get_running_loop()` | 供跨线程回调使用 |
| 保存 headers | 199 | `self.headers = dict(ws.request.headers)` | |
| 解析 client IP | 200-206 | `self.client_ip = ...` | 优先级：x-real-ip > x-forwarded-for > remote_address |
| 保存 device_id | 211 | `self.device_id = self.headers.get("device-id", None)` | |
| 检查 MQTT 来源 | 218 | `self.conn_from_mqtt_gateway = request_path.endswith("?from=mqtt_gateway")` | |
| **初始化活动时间戳** | **222-224** | `self.first_activity_time = time.time() * 1000` `self.last_activity_time = time.time() * 1000` | 用于超时计算 |
| **启动超时检查任务** | **227** | `self.timeout_task = asyncio.create_task(self._check_timeout())` | 后台协程，每 10 秒检查 |
| 预配置 welcome 消息 | 229-233 | `self.welcome_msg = self.config["xiaozhi"]; self.welcome_msg["session_id"] = self.session_id` | 加上会话 ID |
| **后台初始化** | **237** | `asyncio.create_task(self._background_initialize())` | 异步获取设备绑定状态 |

### 2.3 消息路由中的绑定校验

每次收到消息时，`_route_message()`（`connection.py:332-365`）先做两道绑定检查：

```python
async def _route_message(self, message):
    """消息路由"""
    # 检查 1：绑定状态尚未确定
    if not self.bind_completed_event.is_set():
        # 等待获取真实状态，最多等 1 秒
        try:
            await asyncio.wait_for(self.bind_completed_event.wait(), timeout=1)
        except asyncio.TimeoutError:
            await self._discard_message_with_bind_prompt()    # 丢弃消息 + 播放绑定提示
            return

    # 检查 2：已确定需要绑定
    if self.need_bind:
        await self._discard_message_with_bind_prompt()        # 丢弃所有消息
        return

    # 绑定检查通过，正常处理
    if isinstance(message, str):
        await handleTextMessage(self, message)
    elif isinstance(message, bytes):
        ...
```

**绑定状态决议**由 `_background_initialize()` → `_initialize_private_config_async()`（`connection.py:670-699`）完成：

```python
async def _initialize_private_config_async(self):
    if not self.read_config_from_api:        # 本地模式：直接放行
        self.need_bind = False
        self.bind_completed_event.set()
        return
    try:
        private_config = await get_private_config_from_api(...)
        self.need_bind = False               # API 返回成功 → 设备已绑定
        self.bind_completed_event.set()
    except DeviceNotFoundException:          # 设备不存在 → 需要绑定
        self.need_bind = True
    except DeviceBindException:              # 设备需绑定验证码
        self.need_bind = True
        self.bind_code = e.bind_code
    except Exception:                        # API 异常 → 保守地要求绑定
        self.need_bind = True
```

---

## 3. 客户端首条消息格式要求

### 3.1 强制要求

**服务器不要求客户端立即发送特定消息。** 没有"先等 welcome"的强制流程。服务器在 `handle_connection()` 执行完毕后即进入消息循环（`connection.py:239-241`），等待任何消息。

### 3.2 协议约定的首条消息

按照协议约定，客户端**应该**发送 `type: "hello"` 消息：

```json
{
  "type": "hello",
  "version": 1,
  "features": {
    "mcp": true
  },
  "transport": "websocket",
  "audio_params": {
    "format": "opus",
    "sample_rate": 16000,
    "channels": 1,
    "frame_duration": 60
  }
}
```

### 3.3 服务器对 hello 的处理

消息经 `textMessageProcessor.py:21-38` 按 `type: "hello"` 路由到 `HelloTextMessageHandler`（`textHandler/helloMessageHandler.py:10-17`），最终调用 `helloHandle.py:42-60` 的 `handleHelloMessage()`：

```python
async def handleHelloMessage(conn, msg_json):
    """处理hello消息"""
    audio_params = msg_json.get("audio_params")
    if audio_params:
        format = audio_params.get("format")
        conn.audio_format = format
        conn.welcome_msg["audio_params"] = audio_params   # 用客户端参数更新服务器配置

    features = msg_json.get("features")
    if features:
        conn.features = features
        if features.get("mcp"):
            conn.mcp_client = MCPClient()
            asyncio.create_task(send_mcp_initialize_message(conn))  # 触发 MCP 握手

    await conn.websocket.send(json.dumps(conn.welcome_msg))         # 回复 welcome
```

服务器回复的 welcome 格式（`connection.py:229-230`，取自 `config.yaml` 的 `xiaozhi` 字段）：

```json
{
  "type": "hello",
  "transport": "websocket",
  "session_id": "xxxxxxxxxxxx",
  "audio_params": {
    "format": "opus",
    "sample_rate": 24000,
    "channels": 1,
    "frame_duration": 60
  }
}
```

### 3.4 如果客户端不发送 hello

不发送 hello 不会导致连接被立即关闭。消息仍会正常进入 `handleTextMessage()`，按 `type` 字段匹配已注册的 7 种处理器类型：

| 消息类型 | 处理器 | 文件 |
|----------|--------|------|
| `hello` | `HelloTextMessageHandler` | `textHandler/helloMessageHandler.py` |
| `abort` | `AbortTextMessageHandler` | `textHandler/abortMessageHandler.py` |
| `listen` | `ListenTextMessageHandler` | `textHandler/listenMessageHandler.py` |
| `iot` | `IotTextMessageHandler` | `textHandler/iotMessageHandler.py` |
| `mcp` | `McpTextMessageHandler` | `textHandler/mcpMessageHandler.py` |
| `server` | `ServerTextMessageHandler` | `textHandler/serverMessageHandler.py` |
| `ping` | `PingMessageHandler` | `textHandler/pingMessageHandler.py` |

如果类型未知，`textMessageProcessor.py:34` 记录日志并跳过。

**关键点**：**仅发送 hello 才能触发 MCP 初始化**（`helloHandle.py:54-58`）。若客户端先发 listen 等消息，虽然不会出错，但 MCP 握手不会自动触发。

### 3.5 完整握手流程

```
Client                              Server
  |                                    |
  |--- WebSocket 握手 (headers) ------>|  device-id, authorization, client-id
  |                                    |-- 校验 Device-ID
  |                                    |-- 校验 Bearer Token (HMAC-SHA256)
  |                                    |-- _background_initialize() → 检查绑定状态
  |                                    |-- _check_timeout() → 启动超时监控
  |                                    |
  |--- {"type":"hello","version":1,  ->|  建议第一条消息
  |     "audio_params":{...},
  |     "features":{"mcp":true}}
  |                                    |-- 更新 audio_params
  |                                    |-- 若 features.mcp=true → MCP 初始化
  |<-- {"type":"hello",              --|  回复 welcome
  |     "session_id":"xxx",
  |     "audio_params":{...}}
  |                                    |
  |--- 正常消息交互开始                |
```

---

## 4. 超时关闭机制

### 4.1 超时参数

**文件**：`connection.py` **第 179-181 行**

```python
self.timeout_seconds = (
    int(self.config.get("close_connection_no_voice_time", 120)) + 60
)
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `close_connection_no_voice_time` | 120 秒 | 来自配置文件，静音超时 |
| + 60 秒 (硬编码) | 60 秒 | 二道防线，在用户配置之上加 1 分钟 |
| **最终超时值** | **180 秒 (3 分钟)** | |

### 4.2 超时检查逻辑

**文件**：`connection.py` **第 1543-1572 行**

```python
async def _check_timeout(self):
    """检查连接超时"""
    try:
        while not self.stop_event.is_set():
            last_activity_time = self.last_activity_time
            if self.need_bind:
                # 绑定模式下，用连接时间而非最后活动时间
                last_activity_time = self.first_activity_time

            if last_activity_time > 0.0:
                current_time = time.time() * 1000
                if current_time - last_activity_time > self.timeout_seconds * 1000:
                    if not self.stop_event.is_set():
                        self.logger.bind(tag=TAG).info("连接超时，准备关闭")
                        self.stop_event.set()
                        try:
                            await self.close(self.websocket)
                        except Exception as close_error:
                            self.logger.bind(tag=TAG).error(
                                f"超时关闭连接时出错: {close_error}"
                            )
                    break
            # 每 10 秒检查一次
            await asyncio.sleep(10)
    except Exception as e:
        self.logger.bind(tag=TAG).error(f"超时检查任务出错: {e}")
    finally:
        self.logger.bind(tag=TAG).info("超时检查任务已退出")
```

### 4.3 时间线总结

| 场景 | 计时起点 | 超时值 | 检查间隔 |
|------|---------|--------|---------|
| **正常模式** (`need_bind=False`) | `last_activity_time`（最后音频活动时间） | 默认 **180 秒** | 10 秒 |
| **需绑定模式** (`need_bind=True`) | `first_activity_time`（连接建立时间） | 默认 **180 秒** | 10 秒 |
| **绑定状态等待超时** | `bind_completed_event.wait()` 开始 | **1 秒** | — |
| **绑定提示间隔** | 上次提示播放时间 | **60 秒** | — |

### 4.4 活动时间戳更新点

`last_activity_time` 在以下位置被更新：

| 场景 | 文件 | 行号 | 代码 |
|------|------|------|------|
| 发音频包前 | `sendAudioHandle.py` | 207 | `conn.last_activity_time = time.time() * 1000` |
| 发音频包时 | `sendAudioHandle.py` | 231 | `conn.last_activity_time = time.time() * 1000` |
| 初始化连接时 | `connection.py` | 224 | `self.last_activity_time = time.time() * 1000` |

**注意**：`_route_message()` 在收到**文本消息**时**不会**更新 `last_activity_time`。所以仅发送文本消息（如 hello 或 ping）不会延长超时。

---

## 附录：关键文件索引

| 功能 | 文件 | 行号 |
|------|------|------|
| WebSocket 服务入口 + Device-ID 提取 | `core/websocket_server.py` | 81-127 |
| 认证实现（_handle_auth） | `core/websocket_server.py` | 206-227 |
| Token 生成与验证 | `core/auth.py` | 1-70 |
| 连接处理器主入口 | `core/connection.py` | 193-264 |
| 超时参数配置 | `core/connection.py` | 179-181 |
| 超时检查任务 | `core/connection.py` | 1543-1572 |
| 消息路由 + 绑定检查 | `core/connection.py` | 332-365 |
| 绑定状态异步决议 | `core/connection.py` | 660-699 |
| 后台初始化入口 | `core/connection.py` | 660-668 |
| Hello 消息处理 | `core/handle/helloHandle.py` | 42-60 |
| 文本消息路由调度 | `core/handle/textMessageProcessor.py` | 21-38 |
| 消息处理器注册表 | `core/handle/textMessageHandlerRegistry.py` | 15-47 |
| 消息类型枚举 | `core/handle/textMessageType.py` | 1-13 |
| 活动时间戳更新（发音频时） | `core/handle/sendAudioHandle.py` | 207, 231 |
