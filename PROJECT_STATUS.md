小智多机器人调度项目 - 进展记录
最后更新：2026-07-03
维护方式：每次完成一个里程碑后手动更新

一、项目目标
基于小智固件 + 小智后台（xiaozhi-server）改造，实现多机器人智能调度系统。

核心架构：

ESP32 = 纯执行终端（播报语音、执行动作、显示表情）

后台服务器 = 大脑（LLM 调度 + 场景管理）

通信协议：WebSocket

机器人清单：

名称	硬件	角色定位	固件状态
Doly	小车，舵机+电机+双圆屏	活泼前台	✅ 表情系统已完成
瓦力	小车，舵机+电机+小屏幕	憨厚老好人	✅ 运动系统已完成
MOSS	悬挂式，水平/垂直电机+小屏幕	高冷总裁	⏳ 待适配
二、固件状态
✅ Doly（双目屏）— 已完成
功能	状态	说明
双屏驱动	✅	GC9A01 双屏正常显示
LVGL 表情系统	✅	21种表情 + Q弹动画 + 自动眨眼
表情与 WiFi 共存	✅	已解决（定时器改为100ms + 全局单例）
表情切换	✅	{"type":"llm","emotion":"happy"} 正常响应
自测试模式	✅	上电自动循环播放表情（已验证）
WiFi/WebSocket	✅	正常连接后台
✅ 瓦力（小车）— 已完成
功能	状态	说明
电机控制	✅	TC118S 驱动，前进/后退/左转/右转/停止
舵机控制	✅	PWM 驱动，0-180° 控制
运动控制	✅	motor_control.cpp / servo_control.cpp
自测试模式	✅	上电自动循环做动作（已验证）
WiFi/WebSocket	✅	正常连接后台
MCP 初始化	✅	已修复 camera_ 空指针问题
action 指令处理	✅	application.cc 已添加 action 分支
⏳ MOSS（悬挂）— 待适配
功能	状态	说明
固件移植	⏳	需要根据板子开发者提供的 .h 文件适配
水平/垂直电机	⏳	待验证
三、后台状态
✅ 已实现
功能	状态	说明
xiaozhi-server 运行	✅	DeepSeek API 正常
WebSocket 服务	✅	ws://192.168.199.106:8000/xiaozhi/v1/
设备注册	✅	收到 hello 消息，设备在线
World 多角色调度	✅	@瓦力 @Doly 识别和分发
直通指令路由	✅	_route_message 支持 llm / action 透传
⚠️ 待完善
问题	状态	说明
超时断开	⚠️	3 分钟无活动会自动关闭连接
场景插件	❌	未实现（设计文档中定义）
多角色编排	❌	未实现（LLM 编排剧情）
四、固件支持的消息类型
消息类型	格式	用途
TTS	{"type":"tts","state":"sentence_start","text":"..."}	语音播报
STT	{"type":"stt","text":"..."}	语音识别文本
LLM	{"type":"llm","emotion":"happy"}	表情切换（Doly）
ACTION	{"type":"action","action":"move_forward"}	运动控制（瓦力）
MCP	{"type":"mcp",...}	MCP 协议（透传）
五、下一步工作（按优先级排序）
优先级 1：屏蔽麦克风（让机器人“只执行”）
在 menuconfig 中禁用 VAD/ASR

修改 application.cc 屏蔽唤醒词检测

确保机器人不主动“听”，只响应指令

优先级 2：实现“导演台”控制面板
完善 admin_mic.py 作为导演台

添加设备选择、指令下发、状态显示

或改用 Streamlit 搭建 Web 控制面板

优先级 3：实现后台场景插件
实现基础闲聊场景（无角色路由）

实现多角色路由（@瓦力 / @Doly）

实现场景配置（从配置文件加载）

优先级 4：MOSS 适配
根据板子开发者提供的 .h 文件适配固件

验证硬件（屏幕、电机、舵机）

编译测试

优先级 5：心跳机制
在固件中添加 ping 消息

后台响应 pong

超时断开自动重连

六、代码关键位置
文件	作用
固件	
main/application.cc	消息处理主入口（OnIncomingJson）
main/protocols/websocket_protocol.cc	WebSocket 连接管理
main/boards/waveshare-s3-dualeye-lcd-1.28/	Doly 适配（表情系统）
main/boards/lingkong-s3-moc-cam-1.54tft/	瓦力适配（运动系统）
后台	
xiaozhi-server/core/connection.py	WebSocket 连接管理
xiaozhi-server/core/world.py	世界调度器
xiaozhi-server/core/character.py	角色系统
GUI	
admin_mic.py	临时导演台
七、关键问题（已解决）
问题	解决方案
表情系统卡初始化	注释掉 lv_obj_clean()，保留原有 UI
表情与 WiFi 冲突	定时器改为 100ms + 全局单例
表情切换不生效	初始化 s_emoji_mutex 互斥量
MCP 解析崩溃	camera_ = nullptr 修复野指针
运动控制	新增 motor_control.cpp / servo_control.cpp
八、当前状态（2026-07-03）
功能	状态	说明
Doly 表情系统	✅	已完成，自测试验证通过
瓦力运动系统	✅	已完成，自测试验证通过
表情下发	✅	{"type":"llm","emotion":"happy"} 正常
动作下发	✅	{"type":"action","action":"move_forward"} 正常
语音播报	✅	正常
后台直通路由	✅	llm / action 透传正常
麦克风屏蔽	⏳	待处理
场景插件	⏳	待实现
MOSS 适配	⏳	待开始