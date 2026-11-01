import os
import sys
import copy
import json
import re
import uuid
import time
import queue
import asyncio
import threading
import traceback
import subprocess
import websockets

from core.utils.util import (
    extract_json_from_string,
    check_vad_update,
    check_asr_update,
    filter_sensitive_info,
)
from typing import Dict, Any
from collections import deque
from core.utils.modules_initialize import (
    initialize_modules,
    initialize_tts,
    initialize_asr,
)
from core.handle.reportHandle import report, enqueue_tool_report
from core.providers.tts.default import DefaultTTS
from concurrent.futures import ThreadPoolExecutor
from core.utils.dialogue import Message, Dialogue
from core.providers.asr.dto.dto import InterfaceType
from core.handle.textHandle import handleTextMessage
from core.providers.tools.unified_tool_handler import UnifiedToolHandler
from plugins_func.loadplugins import auto_import_modules
from plugins_func.register import Action, ActionResponse
from core.auth import AuthenticationError
from config.config_loader import get_private_config_from_api
from core.providers.tts.dto.dto import ContentType, TTSMessageDTO, SentenceType
from config.logger import setup_logging, build_module_string, create_connection_logger
from config.manage_api_client import DeviceNotFoundException, DeviceBindException, generate_and_save_chat_title
from core.utils.prompt_manager import PromptManager
from core.utils.voiceprint_provider import VoiceprintProvider
from core.utils.util import get_system_error_response
from core.utils import textUtils

# ========== SceneDispatcher ==========
from core.scene_dispatcher import SceneDispatcher
from scenes.chat import ChatScene

TAG = __name__

auto_import_modules("plugins_func.functions")


class TTSException(RuntimeError):
    pass


# direct_answer 虚拟工具定义
DIRECT_ANSWER_TOOL = {
    "type": "function",
    "function": {
        "name": "direct_answer",
        "description": "当用户的请求不匹配其他任何工具时，可用此选项直接回复。将回复内容写在response参数里。",
        "parameters": {
            "type": "object",
            "properties": {
                "response": {
                    "type": "string",
                    "description": "你回复用户的完整内容",
                },
            },
            "required": ["response"],
        },
    },
}


class ConnectionHandler:
    def __init__(
            self,
            config: Dict[str, Any],
            _vad,
            _asr,
            _llm,
            _memory,
            _intent,
            server=None,
    ):
        self.common_config = config
        self.config = copy.deepcopy(config)
        self.session_id = str(uuid.uuid4())
        self.logger = setup_logging()
        self.server = server

        self.need_bind = False
        self.bind_completed_event = asyncio.Event()
        self.bind_code = None
        self.last_bind_prompt_time = 0
        self.bind_prompt_interval = 60

        self.read_config_from_api = self.config.get("read_config_from_api", False)

        self.websocket: websockets.ServerConnection | None = None
        self.headers = None
        self.device_id = None
        self.client_ip = None
        self.prompt = None
        self.welcome_msg = None
        self.max_output_size = 0
        self.chat_history_conf = 0
        self.audio_format = "opus"
        self.sample_rate = 24000

        self.client_abort = False
        self.client_is_speaking = False
        self.client_listen_mode = "auto"

        self.loop = None
        self.stop_event = threading.Event()
        self.executor = ThreadPoolExecutor(max_workers=5)

        self.report_queue = queue.Queue()
        self.report_thread = None
        self.report_asr_enable = self.read_config_from_api
        self.report_tts_enable = self.read_config_from_api

        self.vad = None
        self.asr = None
        self.tts = None
        self._asr = _asr
        self._vad = _vad
        self.llm = _llm
        self.memory = _memory
        self.intent = _intent

        # ========== SceneDispatcher ==========
        self.scene_dispatcher = None

        self.voiceprint_provider = None

        self.client_audio_buffer = bytearray()
        self.client_have_voice = False
        self.client_voice_window = deque(maxlen=5)
        self.first_activity_time = 0.0
        self.last_activity_time = 0.0
        self.vad_last_voice_time = 0.0
        self.client_voice_stop = False
        self.last_is_voice = False

        self.asr_audio = []
        self.asr_audio_queue = queue.Queue()
        self.current_speaker = None

        self.dialogue = Dialogue()

        self.sentence_id = None
        self.tts_MessageText = ""

        self.iot_descriptors = {}
        self.func_handler = None

        self.cmd_exit = self.config["exit_commands"]

        self.close_after_chat = False
        self.load_function_plugin = False
        self.intent_type = "nointent"

        self.timeout_seconds = 86460
        self.logger.info(
            f"🔍 超时时间配置: close_connection_no_voice_time={self.config.get('close_connection_no_voice_time')}, timeout_seconds={self.timeout_seconds}")

        self.timeout_task = None
        self.features = None
        self.conn_from_mqtt_gateway = False

        self.prompt_manager = PromptManager(self.config, self.logger)

    # ========== 初始化 SceneDispatcher ==========
    def _init_scene_dispatcher(self):
        """初始化场景调度器（从数据库加载配置）"""
        try:
            device_manager = None
            if hasattr(self.server, 'device_manager'):
                device_manager = self.server.device_manager

            self.scene_dispatcher = SceneDispatcher(
                llm_instance=self.llm,
                device_manager=device_manager,
                connection_handler=self
            )

            self.scene_dispatcher.register_scene(ChatScene())

            from core.data import SceneRepo
            active_scene = SceneRepo.get_active_scene()
            if active_scene:
                from core.data import RoleConfigRepo
                role_configs = RoleConfigRepo.get_by_template(active_scene['id'])
                role_device_map = {}
                for r in role_configs:
                    role_device_map[r['role_name']] = r['device_id']
                self.scene_dispatcher.set_role_device_map(role_device_map)
                self.logger.info(f"从数据库加载场景: {active_scene['name']}, 角色映射: {role_device_map}")
            else:
                self.logger.warning("未找到激活的场景")
                self.scene_dispatcher.set_role_device_map({
                    "助手": self.device_id,
                })

        except Exception as e:
            self.logger.error(f"[SceneDispatcher] 初始化失败: {e}")
            self.scene_dispatcher = None

    async def handle_connection(self, ws: websockets.ServerConnection):
        try:
            self.loop = asyncio.get_running_loop()

            self.headers = dict(ws.request.headers)
            real_ip = self.headers.get("x-real-ip") or self.headers.get(
                "x-forwarded-for"
            )
            if real_ip:
                self.client_ip = real_ip.split(",")[0].strip()
            else:
                self.client_ip = ws.remote_address[0]
            self.logger.bind(tag=TAG).info(
                f"{self.client_ip} conn - Headers: {self.headers}"
            )

            self.device_id = self.headers.get("device-id", None)
            self.websocket = ws

            request_path = ws.request.path
            self.conn_from_mqtt_gateway = request_path.endswith("?from=mqtt_gateway")
            if self.conn_from_mqtt_gateway:
                self.logger.bind(tag=TAG).info("连接来自:MQTT网关")

            self.first_activity_time = time.time() * 1000
            self.last_activity_time = time.time() * 1000

            self.timeout_task = asyncio.create_task(self._check_timeout())

            self.welcome_msg = self.config["xiaozhi"]
            self.welcome_msg["session_id"] = self.session_id

            self.sample_rate = self.welcome_msg["audio_params"]["sample_rate"]
            self.logger.bind(tag=TAG).info(f"配置输出音频采样率为: {self.sample_rate}")

            asyncio.create_task(self._background_initialize())

            # ========== 初始化 SceneDispatcher ==========
            self._init_scene_dispatcher()

            try:
                async for message in self.websocket:
                    await self._route_message(message)
            except websockets.exceptions.ConnectionClosed:
                self.logger.bind(tag=TAG).info("客户端断开连接")

        except AuthenticationError as e:
            self.logger.bind(tag=TAG).error(f"Authentication failed: {str(e)}")
            return
        except Exception as e:
            stack_trace = traceback.format_exc()
            self.logger.bind(tag=TAG).error(f"Connection error: {str(e)}-{stack_trace}")
            return
        finally:
            try:
                await self._save_and_close(ws)
            except Exception as final_error:
                self.logger.bind(tag=TAG).error(f"最终清理时出错: {final_error}")
                try:
                    await self.close(ws)
                except Exception as close_error:
                    self.logger.bind(tag=TAG).error(
                        f"强制关闭连接时出错: {close_error}"
                    )

    async def _save_and_close(self, ws):
        """保存记忆并关闭连接"""
        try:
            if self.session_id:
                def generate_title_task():
                    try:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        loop.run_until_complete(
                            generate_and_save_chat_title(self.session_id)
                        )
                    except Exception as e:
                        self.logger.bind(tag=TAG).error(f"生成标题失败: {e}")
                    finally:
                        try:
                            loop.close()
                        except Exception:
                            pass

                threading.Thread(target=generate_title_task, daemon=True).start()

            if self.memory:
                def save_memory_task():
                    try:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        loop.run_until_complete(
                            self.memory.save_memory(
                                self.dialogue.dialogue, self.session_id
                            )
                        )
                    except Exception as e:
                        self.logger.bind(tag=TAG).error(f"保存记忆失败: {e}")
                    finally:
                        try:
                            loop.close()
                        except Exception:
                            pass

                threading.Thread(target=save_memory_task, daemon=True).start()
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"保存记忆失败: {e}")
        finally:
            try:
                await self.close(ws)
            except Exception as close_error:
                self.logger.bind(tag=TAG).error(
                    f"保存记忆后关闭连接失败: {close_error}"
                )

    async def _discard_message_with_bind_prompt(self):
        """丢弃消息并检查是否需要播放绑定提示"""
        current_time = time.time()
        if current_time - self.last_bind_prompt_time >= self.bind_prompt_interval:
            self.last_bind_prompt_time = current_time
            from core.handle.receiveAudioHandle import check_bind_device
            asyncio.create_task(check_bind_device(self))

    async def _route_message(self, message):
        """消息路由 - 增加 llm 直通转发"""
        if not self.bind_completed_event.is_set():
            try:
                await asyncio.wait_for(self.bind_completed_event.wait(), timeout=1)
            except asyncio.TimeoutError:
                await self._discard_message_with_bind_prompt()
                return

        if self.need_bind:
            await self._discard_message_with_bind_prompt()
            return

        # llm 消息直接透传
        if isinstance(message, str):
            try:
                data = json.loads(message)
                if data.get("type") == "llm":
                    target = data.get("target")
                    if target and hasattr(self.server, 'device_manager'):
                        success = await self.server.device_manager.send(target, data)
                        if success:
                            self.logger.info(f"[直通] llm → {target}")
                        else:
                            self.logger.warning(f"[直通] 目标设备 {target} 不在线")
                    else:
                        await self.websocket.send(json.dumps(data))
                        self.logger.info("[直通] llm → 当前设备")
                    return
            except:
                pass

        if isinstance(message, str):
            await handleTextMessage(self, message)
        elif isinstance(message, bytes):
            if self.vad is None or self.asr is None:
                return

            if self.conn_from_mqtt_gateway and len(message) >= 16:
                handled = await self._process_mqtt_audio_message(message)
                if handled:
                    return

            self.asr_audio_queue.put(message)

    # ========== 使用 SceneDispatcher 处理 ==========
    async def process_with_scene(self, text: str) -> dict:
        """使用场景调度器处理用户输入"""
        if not self.scene_dispatcher:
            return {"actions": [], "response": "场景调度器未初始化"}

        result = await self.scene_dispatcher.process(text, self.device_id)

        if hasattr(self.server, 'device_manager') and self.server.device_manager:
            await self.scene_dispatcher.dispatch_actions(result.get("actions", []))

        return result

    # ========== 测试 SceneDispatcher ==========
    async def test_scene_dispatcher(self, text: str):
        """测试 SceneDispatcher 是否正常工作"""
        if not self.scene_dispatcher:
            self.logger.warning("SceneDispatcher 未初始化")
            return {"success": False, "message": "SceneDispatcher 未初始化"}

        self.logger.info(f"[测试] 发送文本到 SceneDispatcher: {text}")

        try:
            result = await self.scene_dispatcher.process(text, self.device_id)
            self.logger.info(f"[测试] SceneDispatcher 返回: {result}")

            if result and result.get("actions"):
                await self.scene_dispatcher.dispatch_actions(result["actions"])
                self.logger.info(f"[测试] 已下发 {len(result['actions'])} 个动作")
            else:
                self.logger.warning("[测试] SceneDispatcher 没有生成动作")

            return {"success": True, "data": result}
        except Exception as e:
            self.logger.error(f"[测试] SceneDispatcher 处理失败: {e}")
            return {"success": False, "message": str(e)}

    async def _process_mqtt_audio_message(self, message):
        """处理来自MQTT网关的音频消息"""
        try:
            timestamp = int.from_bytes(message[8:12], "big")
            audio_length = int.from_bytes(message[12:16], "big")

            if audio_length > 0 and len(message) >= 16 + audio_length:
                audio_data = message[16: 16 + audio_length]
                self._process_websocket_audio(audio_data, timestamp)
                return True
            elif len(message) > 16:
                audio_data = message[16:]
                self.asr_audio_queue.put(audio_data)
                return True
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"解析WebSocket音频包失败: {e}")
        return False

    def _process_websocket_audio(self, audio_data, timestamp):
        """处理WebSocket格式的音频包"""
        if not hasattr(self, "audio_timestamp_buffer"):
            self.audio_timestamp_buffer = {}
            self.last_processed_timestamp = 0
            self.max_timestamp_buffer_size = 20

        if timestamp >= self.last_processed_timestamp:
            self.asr_audio_queue.put(audio_data)
            self.last_processed_timestamp = timestamp

            processed_any = True
            while processed_any:
                processed_any = False
                for ts in sorted(self.audio_timestamp_buffer.keys()):
                    if ts > self.last_processed_timestamp:
                        buffered_audio = self.audio_timestamp_buffer.pop(ts)
                        self.asr_audio_queue.put(buffered_audio)
                        self.last_processed_timestamp = ts
                        processed_any = True
                        break
        else:
            if len(self.audio_timestamp_buffer) < self.max_timestamp_buffer_size:
                self.audio_timestamp_buffer[timestamp] = audio_data
            else:
                self.asr_audio_queue.put(audio_data)

    async def handle_restart(self, message):
        """处理服务器重启请求"""
        try:
            self.logger.bind(tag=TAG).info("收到服务器重启指令，准备执行...")
            await self.websocket.send(
                json.dumps(
                    {
                        "type": "server",
                        "status": "success",
                        "message": "服务器重启中...",
                        "content": {"action": "restart"},
                    }
                )
            )

            def restart_server():
                time.sleep(1)
                self.logger.bind(tag=TAG).info("执行服务器重启...")
                subprocess.Popen(
                    [sys.executable, "app.py"],
                    stdin=sys.stdin,
                    stdout=sys.stdout,
                    stderr=sys.stderr,
                    start_new_session=True,
                )
                os._exit(0)

            threading.Thread(target=restart_server, daemon=True).start()

        except Exception as e:
            self.logger.bind(tag=TAG).error(f"重启失败: {str(e)}")
            await self.websocket.send(
                json.dumps(
                    {
                        "type": "server",
                        "status": "error",
                        "message": f"Restart failed: {str(e)}",
                        "content": {"action": "restart"},
                    }
                )
            )

    def _initialize_components(self):
        try:
            if self.tts is None:
                self.tts = self._initialize_tts()
            asyncio.run_coroutine_threadsafe(
                self.tts.open_audio_channels(self), self.loop
            )
            if self.need_bind:
                self.bind_completed_event.set()
                return
            self.selected_module_str = build_module_string(
                self.config.get("selected_module", {})
            )
            self.logger = create_connection_logger(self.selected_module_str)

            if self.config.get("prompt") is not None:
                user_prompt = self.config["prompt"]
                prompt = self.prompt_manager.get_quick_prompt(user_prompt)
                self.change_system_prompt(prompt)
                self.logger.bind(tag=TAG).info(
                    f"快速初始化组件: prompt成功 {prompt[:50]}..."
                )

            if self.vad is None:
                self.vad = self._vad
            if self.asr is None:
                self.asr = self._initialize_asr()

            self._initialize_voiceprint()
            asyncio.run_coroutine_threadsafe(
                self.asr.open_audio_channels(self), self.loop
            )

            self._initialize_memory()
            self._initialize_intent()
            self._init_report_threads()
            self._init_prompt_enhancement()
            self._inject_tool_call_fewshot()

        except Exception as e:
            self.logger.bind(tag=TAG).error(f"实例化组件失败: {e}")

    def _init_prompt_enhancement(self):
        self.prompt_manager.update_context_info(self, self.client_ip)
        enhanced_prompt = self.prompt_manager.build_enhanced_prompt(
            self.config["prompt"], self.device_id, self.client_ip
        )
        if enhanced_prompt:
            self.change_system_prompt(enhanced_prompt)
            self.logger.bind(tag=TAG).debug("系统提示词已增强更新")

    def _inject_tool_call_fewshot(self):
        """注入工具调用 few-shot 示例"""
        if self.intent_type != "function_call":
            return
        if not hasattr(self, "func_handler") or self.func_handler is None:
            return

        tools = self.func_handler.get_functions()
        if not tools:
            return

        tool_names = {t.get("function", {}).get("name") for t in tools}

        da_tc_id = "fewshot_da_001"
        self.dialogue.put(Message(role="user", content="给我讲个故事吧", is_temporary=True))
        self.dialogue.put(Message(
            role="assistant",
            tool_calls=[{
                "id": da_tc_id,
                "function": {
                    "arguments": '{"response": "好呀，你想听什么类型的呀？童话、冒险还是搞笑的？选一个我给你开讲~"}',
                    "name": "direct_answer"},
                "type": "function", "index": 0,
            }],
            is_temporary=True,
        ))
        self.dialogue.put(Message(
            role="tool", tool_call_id=da_tc_id,
            content="已直接回复", is_temporary=True,
        ))

        if "handle_exit_intent" in tool_names:
            tc_id = "fewshot_exit_001"
            self.dialogue.put(Message(role="user", content="拜拜", is_temporary=True))
            self.dialogue.put(Message(
                role="assistant",
                tool_calls=[{
                    "id": tc_id,
                    "function": {"arguments": '{"say_goodbye": "再见，下次再聊~"}', "name": "handle_exit_intent"},
                    "type": "function", "index": 0,
                }],
                is_temporary=True,
            ))
            self.dialogue.put(Message(
                role="tool", tool_call_id=tc_id,
                content="退出意图已处理", is_temporary=True,
            ))
            self.dialogue.put(Message(
                role="assistant", content="再见，下次再聊~", is_temporary=True,
            ))

        self.logger.bind(tag=TAG).debug("已注入工具调用 few-shot 示例")

    def _init_report_threads(self):
        """初始化ASR和TTS上报线程"""
        if not self.read_config_from_api or self.need_bind:
            return
        if self.chat_history_conf == 0:
            return
        if self.report_thread is None or not self.report_thread.is_alive():
            self.report_thread = threading.Thread(
                target=self._report_worker, daemon=True
            )
            self.report_thread.start()
            self.logger.bind(tag=TAG).info("TTS上报线程已启动")

    def _initialize_tts(self):
        tts = None
        if not self.need_bind:
            tts = initialize_tts(self.config)

        if tts is None:
            tts = DefaultTTS(self.config, delete_audio_file=True)

        return tts

    def _initialize_asr(self):
        if (
                self._asr is not None
                and hasattr(self._asr, "interface_type")
                and self._asr.interface_type == InterfaceType.LOCAL
        ):
            asr = self._asr
        else:
            asr = initialize_asr(self.config)
        return asr

    def _initialize_voiceprint(self):
        try:
            voiceprint_config = self.config.get("voiceprint", {})
            if voiceprint_config:
                voiceprint_provider = VoiceprintProvider(voiceprint_config)
                if voiceprint_provider is not None and voiceprint_provider.enabled:
                    self.voiceprint_provider = voiceprint_provider
                    self.logger.bind(tag=TAG).info("声纹识别功能已在连接时动态启用")
                else:
                    self.logger.bind(tag=TAG).warning("声纹识别功能启用但配置不完整")
            else:
                self.logger.bind(tag=TAG).info("声纹识别功能未启用")
        except Exception as e:
            self.logger.bind(tag=TAG).warning(f"声纹识别初始化失败: {str(e)}")

    async def _background_initialize(self):
        try:
            await self._initialize_private_config_async()
            self.executor.submit(self._initialize_components)
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"后台初始化失败: {e}")

    async def _initialize_private_config_async(self):
        if not self.read_config_from_api:
            self.need_bind = False
            self.bind_completed_event.set()
            return
        try:
            begin_time = time.time()
            private_config = await get_private_config_from_api(
                self.config,
                self.headers.get("device-id"),
                self.headers.get("client-id", self.headers.get("device-id")),
            )
            private_config["delete_audio"] = bool(self.config.get("delete_audio", True))
            self.logger.bind(tag=TAG).info(
                f"{time.time() - begin_time} 秒，异步获取差异化配置成功: {json.dumps(filter_sensitive_info(private_config), ensure_ascii=False)}"
            )
            self.need_bind = False
            self.bind_completed_event.set()
        except DeviceNotFoundException as e:
            self.need_bind = True
            private_config = {}
        except DeviceBindException as e:
            self.need_bind = True
            self.bind_code = e.bind_code
            private_config = {}
        except Exception as e:
            self.need_bind = True
            self.logger.bind(tag=TAG).error(f"异步获取差异化配置失败: {e}")
            private_config = {}

        init_llm, init_tts, init_memory, init_intent = False, False, False, False

        init_vad = check_vad_update(self.common_config, private_config)
        init_asr = check_asr_update(self.common_config, private_config)

        if init_vad:
            self.config["VAD"] = private_config["VAD"]
            self.config["selected_module"]["VAD"] = private_config["selected_module"]["VAD"]
        if init_asr:
            self.config["ASR"] = private_config["ASR"]
            self.config["selected_module"]["ASR"] = private_config["selected_module"]["ASR"]
        if private_config.get("TTS") is not None:
            init_tts = True
            self.config["TTS"] = private_config["TTS"]
            self.config["selected_module"]["TTS"] = private_config["selected_module"]["TTS"]
        if private_config.get("LLM") is not None:
            init_llm = True
            self.config["LLM"] = private_config["LLM"]
            self.config["selected_module"]["LLM"] = private_config["selected_module"]["LLM"]
        if private_config.get("VLLM") is not None:
            self.config["VLLM"] = private_config["VLLM"]
            self.config["selected_module"]["VLLM"] = private_config["selected_module"]["VLLM"]
        if private_config.get("Memory") is not None:
            init_memory = True
            self.config["Memory"] = private_config["Memory"]
            self.config["selected_module"]["Memory"] = private_config["selected_module"]["Memory"]
        if private_config.get("Intent") is not None:
            init_intent = True
            self.config["Intent"] = private_config["Intent"]
            model_intent = private_config.get("selected_module", {}).get("Intent", {})
            self.config["selected_module"]["Intent"] = model_intent
            if model_intent != "Intent_nointent":
                plugin_from_server = private_config.get("plugins", {})
                for plugin, config_str in plugin_from_server.items():
                    plugin_from_server[plugin] = json.loads(config_str)
                self.config["plugins"] = plugin_from_server
                self.config["Intent"][self.config["selected_module"]["Intent"]]["functions"] = plugin_from_server.keys()
        if private_config.get("prompt") is not None:
            self.config["prompt"] = private_config["prompt"]
        if private_config.get("voiceprint") is not None:
            self.config["voiceprint"] = private_config["voiceprint"]
        if private_config.get("summaryMemory") is not None:
            self.config["summaryMemory"] = private_config["summaryMemory"]
        if private_config.get("device_max_output_size") is not None:
            self.max_output_size = int(private_config["device_max_output_size"])
        if private_config.get("chat_history_conf") is not None:
            self.chat_history_conf = int(private_config["chat_history_conf"])
        if private_config.get("mcp_endpoint") is not None:
            self.config["mcp_endpoint"] = private_config["mcp_endpoint"]
        if private_config.get("context_providers") is not None:
            self.config["context_providers"] = private_config["context_providers"]

        if private_config.get("correct_words") is not None:
            select_tts_module = self.config["selected_module"]["TTS"]
            self.config["TTS"][select_tts_module]["correct_words"] = private_config["correct_words"]

        try:
            modules = await self.loop.run_in_executor(
                None,
                initialize_modules,
                self.logger,
                private_config,
                init_vad,
                init_asr,
                init_llm,
                init_tts,
                init_memory,
                init_intent,
            )
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"初始化组件失败: {e}")
            modules = {}
        if modules.get("tts") is not None:
            self.tts = modules["tts"]
        if modules.get("vad") is not None:
            self.vad = modules["vad"]
        if modules.get("asr") is not None:
            self.asr = modules["asr"]
        if modules.get("llm") is not None:
            self.llm = modules["llm"]
        if modules.get("intent") is not None:
            self.intent = modules["intent"]
        if modules.get("memory") is not None:
            self.memory = modules["memory"]

    def _initialize_memory(self):
        if self.memory is None:
            return
        self.memory.init_memory(
            role_id=self.device_id,
            llm=self.llm,
            summary_memory=self.config.get("summaryMemory", None),
            save_to_file=not self.read_config_from_api,
        )

        memory_config = self.config["Memory"]
        memory_type = self.config["Memory"][self.config["selected_module"]["Memory"]]["type"]
        if memory_type == "nomem" or memory_type == "mem_report_only":
            return
        elif memory_type == "mem_local_short":
            memory_llm_name = memory_config[self.config["selected_module"]["Memory"]]["llm"]
            if memory_llm_name and memory_llm_name in self.config["LLM"]:
                from core.utils import llm as llm_utils
                memory_llm_config = self.config["LLM"][memory_llm_name]
                memory_llm_type = memory_llm_config.get("type", memory_llm_name)
                memory_llm = llm_utils.create_instance(memory_llm_type, memory_llm_config)
                self.logger.bind(tag=TAG).info(
                    f"为记忆总结创建了专用LLM: {memory_llm_name}, 类型: {memory_llm_type}"
                )
                self.memory.set_llm(memory_llm)
            else:
                self.memory.set_llm(self.llm)
                self.logger.bind(tag=TAG).info("使用主LLM作为意图识别模型")

    def _initialize_intent(self):
        if self.intent is None:
            return
        self.intent_type = self.config["Intent"][self.config["selected_module"]["Intent"]]["type"]
        if self.intent_type == "function_call" or self.intent_type == "intent_llm":
            self.load_function_plugin = True

        intent_config = self.config["Intent"]
        intent_type = self.config["Intent"][self.config["selected_module"]["Intent"]]["type"]

        if intent_type == "nointent":
            return
        elif intent_type == "intent_llm":
            intent_llm_name = intent_config[self.config["selected_module"]["Intent"]]["llm"]
            if intent_llm_name and intent_llm_name in self.config["LLM"]:
                from core.utils import llm as llm_utils
                intent_llm_config = self.config["LLM"][intent_llm_name]
                intent_llm_type = intent_llm_config.get("type", intent_llm_name)
                intent_llm = llm_utils.create_instance(intent_llm_type, intent_llm_config)
                self.logger.bind(tag=TAG).info(
                    f"为意图识别创建了专用LLM: {intent_llm_name}, 类型: {intent_llm_type}"
                )
                self.intent.set_llm(intent_llm)
            else:
                self.intent.set_llm(self.llm)
                self.logger.bind(tag=TAG).info("使用主LLM作为意图识别模型")

        self.func_handler = UnifiedToolHandler(self)
        if hasattr(self, "loop") and self.loop:
            asyncio.run_coroutine_threadsafe(self.func_handler._initialize(), self.loop)

    def change_system_prompt(self, prompt):
        self.prompt = prompt
        self.dialogue.update_system_message(self.prompt)

    def chat(self, query, depth=0):
        current_sentence_id = None

        if query is not None:
            self.logger.bind(tag=TAG).info(f"大模型收到用户消息: {query}")

        if depth == 0:
            current_sentence_id = str(uuid.uuid4().hex)
            self.sentence_id = current_sentence_id
            self.dialogue.put(Message(role="user", content=query))
            self.tts.tts_text_queue.put(
                TTSMessageDTO(
                    sentence_id=current_sentence_id,
                    sentence_type=SentenceType.FIRST,
                    content_type=ContentType.ACTION,
                )
            )
        else:
            current_sentence_id = self.sentence_id

        MAX_DEPTH = 5
        force_final_answer = False

        if depth >= MAX_DEPTH:
            self.logger.bind(tag=TAG).debug(
                f"已达到最大工具调用深度 {MAX_DEPTH}，将强制基于现有信息回答"
            )
            force_final_answer = True
            self.dialogue.put(
                Message(
                    role="user",
                    content="[系统提示] 已达到最大工具调用次数限制，请你基于目前已经获取的所有信息，直接给出最终答案。不要再尝试调用任何工具。",
                )
            )

        functions = None
        if (
                self.intent_type == "function_call"
                and hasattr(self, "func_handler")
                and not force_final_answer
        ):
            functions = self.func_handler.get_functions()
            if functions is not None and depth == 0:
                functions.append(DIRECT_ANSWER_TOOL)

        response_message = []

        try:
            memory_str = None
            if self.memory is not None and query:
                future = asyncio.run_coroutine_threadsafe(
                    self.memory.query_memory(query), self.loop
                )
                memory_str = future.result()

            if self.intent_type == "function_call" and functions is not None:
                llm_responses = self.llm.response_with_functions(
                    self.session_id,
                    self.dialogue.get_llm_dialogue_with_memory(
                        memory_str, self.config.get("voiceprint", {})
                    ),
                    functions=functions,
                )
            else:
                llm_responses = self.llm.response(
                    self.session_id,
                    self.dialogue.get_llm_dialogue_with_memory(
                        memory_str, self.config.get("voiceprint", {})
                    ),
                )
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"LLM 处理出错 {query}: {e}")
            return None

        tool_call_flag = False
        tool_calls_list = []
        content_arguments = ""
        emotion_flag = True

        try:
            for response in llm_responses:
                if self.client_abort:
                    break
                if self.intent_type == "function_call" and functions is not None:
                    content, tools_call = response
                    if "content" in response:
                        content = response["content"]
                        tools_call = None
                    if content is not None and len(content) > 0:
                        content_arguments += content

                    if not tool_call_flag and content_arguments.startswith("<tool_call>"):
                        tool_call_flag = True

                    if tools_call is not None and len(tools_call) > 0:
                        tool_call_flag = True
                        self._merge_tool_calls(tool_calls_list, tools_call)

                    _DA_STREAM_BUFFER = 5
                    for tc in tool_calls_list:
                        if tc["name"] == "direct_answer" and tc.get("arguments"):
                            da_text = self._extract_direct_answer_response(tc["arguments"])
                            sent_len = tc.get("_da_sent", 0)
                            if da_text and len(da_text) > sent_len:
                                safe_end = max(sent_len, len(da_text) - _DA_STREAM_BUFFER)
                                if safe_end > sent_len:
                                    new_part = da_text[sent_len:safe_end]
                                    new_part = self._clean_response_garbage(new_part)
                                    if new_part:
                                        tc["_da_sent"] = safe_end
                                        self.tts.tts_text_queue.put(
                                            TTSMessageDTO(
                                                sentence_id=current_sentence_id,
                                                sentence_type=SentenceType.MIDDLE,
                                                content_type=ContentType.TEXT,
                                                content_detail=new_part,
                                            )
                                        )
                else:
                    content = response

                if emotion_flag and content is not None and content.strip():
                    if (self.features or {}).get("emoji", True):
                        asyncio.run_coroutine_threadsafe(
                            textUtils.get_emotion(self, content),
                            self.loop,
                        )
                    emotion_flag = False

                if content is not None and len(content) > 0:
                    if not tool_call_flag:
                        response_message.append(content)
                        self.tts.tts_text_queue.put(
                            TTSMessageDTO(
                                sentence_id=current_sentence_id,
                                sentence_type=SentenceType.MIDDLE,
                                content_type=ContentType.TEXT,
                                content_detail=content,
                            )
                        )
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"LLM stream processing error: {e}")
            self.tts.tts_text_queue.put(
                TTSMessageDTO(
                    sentence_id=current_sentence_id,
                    sentence_type=SentenceType.MIDDLE,
                    content_type=ContentType.TEXT,
                    content_detail=get_system_error_response(self.config),
                )
            )
            if depth == 0:
                self.tts.tts_text_queue.put(
                    TTSMessageDTO(
                        sentence_id=current_sentence_id,
                        sentence_type=SentenceType.LAST,
                        content_type=ContentType.ACTION,
                    )
                )
            return

        if tool_call_flag:
            bHasError = False
            if len(tool_calls_list) == 0 and content_arguments:
                a = extract_json_from_string(content_arguments)
                if a is not None:
                    try:
                        content_arguments_json = json.loads(a)
                        tool_calls_list.append({
                            "id": str(uuid.uuid4().hex),
                            "name": content_arguments_json["name"],
                            "arguments": json.dumps(content_arguments_json["arguments"], ensure_ascii=False),
                        })
                    except Exception as e:
                        bHasError = True
                        response_message.append(a)
                else:
                    bHasError = True
                    response_message.append(content_arguments)
                if bHasError:
                    self.logger.bind(tag=TAG).error(f"function call error: {content_arguments}")

            if not bHasError and len(tool_calls_list) > 0:
                direct_answer_calls = [tc for tc in tool_calls_list if tc["name"] == "direct_answer"]
                real_tool_calls = [tc for tc in tool_calls_list if tc["name"] != "direct_answer"]

                if direct_answer_calls:
                    self.logger.bind(tag=TAG).debug("模型选择 direct_answer，流式已播报，写入对话历史")
                    for tc in direct_answer_calls:
                        da_response = self._extract_direct_answer_response(tc.get("arguments", "{}"))
                        if da_response:
                            sent_len = tc.get("_da_sent", 0)
                            remaining = da_response[sent_len:]
                            if remaining:
                                remaining = self._clean_response_garbage(remaining)
                                if remaining:
                                    self.tts.tts_text_queue.put(
                                        TTSMessageDTO(
                                            sentence_id=current_sentence_id,
                                            sentence_type=SentenceType.MIDDLE,
                                            content_type=ContentType.TEXT,
                                            content_detail=remaining,
                                        )
                                    )
                            da_response = self._clean_response_garbage(da_response)
                            self.tts.store_tts_text(current_sentence_id, da_response)
                            self.dialogue.put(Message(role="assistant", content=da_response))

                    if not real_tool_calls:
                        if depth == 0:
                            self.tts.tts_text_queue.put(
                                TTSMessageDTO(
                                    sentence_id=current_sentence_id,
                                    sentence_type=SentenceType.LAST,
                                    content_type=ContentType.ACTION,
                                )
                            )
                        return

                    tool_calls_list = real_tool_calls

            if not bHasError and len(tool_calls_list) > 0:
                self.logger.bind(tag=TAG).debug(f"检测到 {len(tool_calls_list)} 个工具调用")

                streamed_text = ""
                if len(response_message) > 0:
                    streamed_text = "".join(response_message)
                    self.tts.store_tts_text(current_sentence_id, streamed_text)
                    self.dialogue.put(Message(role="assistant", content=streamed_text))
                response_message.clear()

                futures_with_data = []
                for tool_call_data in tool_calls_list:
                    self.logger.bind(tag=TAG).debug(
                        f"function_name={tool_call_data['name']}, function_id={tool_call_data['id']}, function_arguments={tool_call_data['arguments']}"
                    )
                    tool_input = json.loads(tool_call_data.get("arguments") or "{}")
                    enqueue_tool_report(self, tool_call_data['name'], tool_input)

                    future = asyncio.run_coroutine_threadsafe(
                        self.func_handler.handle_llm_function_call(self, tool_call_data),
                        self.loop,
                    )
                    futures_with_data.append((future, tool_call_data, tool_input))

                tool_call_timeout = int(self.config.get("tool_call_timeout", 30))
                tool_results = []

                for future, tool_call_data, tool_input in futures_with_data:
                    try:
                        result = future.result(timeout=tool_call_timeout)
                        tool_results.append((result, tool_call_data))
                        enqueue_tool_report(self, tool_call_data['name'], tool_input,
                                            str(result.result) if result.result else None, report_tool_call=False)
                    except Exception as e:
                        self.logger.bind(tag=TAG).error(
                            f"工具调用超时或异常: {tool_call_data['name']}, 错误: {e}"
                        )
                        tool_results.append((
                            ActionResponse(action=Action.ERROR, result="哎呀，网络遇到点问题，请稍后再试下！"),
                            tool_call_data
                        ))
                        enqueue_tool_report(self, tool_call_data['name'], tool_input, str(e), report_tool_call=False)

                if tool_results:
                    self._handle_function_result(tool_results, depth=depth, streamed_text=streamed_text)

        if len(response_message) > 0:
            text_buff = "".join(response_message)
            self.tts.store_tts_text(current_sentence_id, text_buff)
            self.dialogue.put(Message(role="assistant", content=text_buff))

        if depth == 0:
            self.tts.tts_text_queue.put(
                TTSMessageDTO(
                    sentence_id=current_sentence_id,
                    sentence_type=SentenceType.LAST,
                    content_type=ContentType.ACTION,
                )
            )
            self.logger.bind(tag=TAG).debug(
                lambda: json.dumps(self.dialogue.get_llm_dialogue(), indent=4, ensure_ascii=False)
            )

        return True

    def _handle_function_result(self, tool_results, depth, streamed_text=""):
        need_llm_tools = []
        record_tools = []

        for result, tool_call_data in tool_results:
            if result.action in [Action.RESPONSE, Action.NOTFOUND, Action.ERROR]:
                text = result.response if result.response else result.result
                if streamed_text and text in streamed_text:
                    self.logger.bind(tag=TAG).debug(
                        f"Skipping duplicate TTS for tool {tool_call_data['name']}, already streamed"
                    )
                else:
                    self.tts.tts_one_sentence(self, ContentType.TEXT, content_detail=text)
                    self.tts.store_tts_text(self.sentence_id, text)
                self.dialogue.put(Message(role="assistant", content=text))
            elif result.action == Action.REQLLM:
                need_llm_tools.append((result, tool_call_data))
            elif result.action == Action.RECORD:
                record_tools.append((result, tool_call_data))
            else:
                pass

        if record_tools:
            all_tool_calls = [
                {
                    "id": tool_call_data["id"],
                    "function": {
                        "arguments": "{}" if tool_call_data["arguments"] == "" else tool_call_data["arguments"],
                        "name": tool_call_data["name"],
                    },
                    "type": "function",
                    "index": idx,
                }
                for idx, (_, tool_call_data) in enumerate(record_tools)
            ]
            self.dialogue.put(Message(role="assistant", tool_calls=all_tool_calls))

            for result, tool_call_data in record_tools:
                text = result.result or ""
                self.dialogue.put(
                    Message(
                        role="tool",
                        tool_call_id=str(uuid.uuid4()) if tool_call_data["id"] is None else tool_call_data["id"],
                        content=text,
                    )
                )

            response_parts = []
            for result, _ in record_tools:
                resp = result.response or result.result
                if resp:
                    response_parts.append(resp)
            if response_parts:
                self.dialogue.put(Message(role="assistant", content="，".join(response_parts)))

        if need_llm_tools:
            all_tool_calls = [
                {
                    "id": tool_call_data["id"],
                    "function": {
                        "arguments": "{}" if tool_call_data["arguments"] == "" else tool_call_data["arguments"],
                        "name": tool_call_data["name"],
                    },
                    "type": "function",
                    "index": idx,
                }
                for idx, (_, tool_call_data) in enumerate(need_llm_tools)
            ]
            self.dialogue.put(Message(role="assistant", tool_calls=all_tool_calls))

            for result, tool_call_data in need_llm_tools:
                text = result.result
                if text is not None and len(text) > 0:
                    self.dialogue.put(
                        Message(
                            role="tool",
                            tool_call_id=str(uuid.uuid4()) if tool_call_data["id"] is None else tool_call_data["id"],
                            content=text,
                        )
                    )

            self.chat(None, depth=depth + 1)

    def _report_worker(self):
        while not self.stop_event.is_set():
            try:
                item = self.report_queue.get(timeout=1)
                if item is None:
                    break
                try:
                    if self.executor is None:
                        continue
                    self.executor.submit(self._process_report, *item)
                except Exception as e:
                    self.logger.bind(tag=TAG).error(f"聊天记录上报线程异常: {e}")
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.bind(tag=TAG).error(f"聊天记录上报工作线程异常: {e}")

        self.logger.bind(tag=TAG).info("聊天记录上报线程已退出")

    def _process_report(self, type, text, audio_data, report_time):
        try:
            asyncio.run(report(self, type, text, audio_data, report_time))
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"上报处理异常: {e}")
        finally:
            self.report_queue.task_done()

    def clearSpeakStatus(self):
        self.client_is_speaking = False
        self.logger.bind(tag=TAG).debug(f"清除服务端讲话状态")

    async def close(self, ws=None):
        try:
            if (
                    hasattr(self, "vad")
                    and self.vad
                    and hasattr(self.vad, "release_conn_resources")
            ):
                self.vad.release_conn_resources(self)

            if hasattr(self, "audio_buffer"):
                self.audio_buffer.clear()

            if self.timeout_task and not self.timeout_task.done():
                self.timeout_task.cancel()
                try:
                    await self.timeout_task
                except asyncio.CancelledError:
                    pass
                self.timeout_task = None

            if hasattr(self, "func_handler") and self.func_handler:
                try:
                    await self.func_handler.cleanup()
                except Exception as cleanup_error:
                    self.logger.bind(tag=TAG).error(f"清理工具处理器时出错: {cleanup_error}")

            if self.stop_event:
                self.stop_event.set()

            self.clear_queues()

            try:
                if ws:
                    try:
                        if hasattr(ws, "closed") and not ws.closed:
                            await ws.close()
                        elif hasattr(ws, "state") and ws.state.name != "CLOSED":
                            await ws.close()
                        else:
                            await ws.close()
                    except Exception:
                        pass
                elif self.websocket:
                    try:
                        if hasattr(self.websocket, "closed") and not self.websocket.closed:
                            await self.websocket.close()
                        elif hasattr(self.websocket, "state") and self.websocket.state.name != "CLOSED":
                            await self.websocket.close()
                        else:
                            await self.websocket.close()
                    except Exception:
                        pass
            except Exception as ws_error:
                self.logger.bind(tag=TAG).error(f"关闭WebSocket连接时出错: {ws_error}")

            if self.tts:
                await self.tts.close()
            if self.asr:
                await self.asr.close()

            if self.executor:
                try:
                    self.executor.shutdown(wait=False)
                except Exception as executor_error:
                    self.logger.bind(tag=TAG).error(f"关闭线程池时出错: {executor_error}")
                self.executor = None
            self.logger.bind(tag=TAG).info("连接资源已释放")
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"关闭连接时出错: {e}")
        finally:
            if self.stop_event:
                self.stop_event.set()

    def clear_queues(self):
        if self.tts:
            self.logger.bind(tag=TAG).debug(
                f"开始清理: TTS队列大小={self.tts.tts_text_queue.qsize()}, 音频队列大小={self.tts.tts_audio_queue.qsize()}"
            )

            for q in [
                self.tts.tts_text_queue,
                self.tts.tts_audio_queue,
                self.report_queue,
            ]:
                if not q:
                    continue
                while True:
                    try:
                        q.get_nowait()
                    except queue.Empty:
                        break

            if hasattr(self, "audio_rate_controller") and self.audio_rate_controller:
                self.audio_rate_controller.reset()
                self.logger.bind(tag=TAG).debug("已重置音频流控器")

            self.logger.bind(tag=TAG).debug(
                f"清理结束: TTS队列大小={self.tts.tts_text_queue.qsize()}, 音频队列大小={self.tts.tts_audio_queue.qsize()}"
            )

    def reset_audio_states(self):
        self.client_audio_buffer.clear()
        self.client_have_voice = False
        self.client_voice_stop = False
        self.client_voice_window.clear()
        self.last_is_voice = False
        self.vad_last_voice_time = 0.0
        self.asr_audio.clear()
        self.logger.bind(tag=TAG).debug("All audio states reset.")

    def chat_and_close(self, text):
        try:
            self.chat(text)
            self.close_after_chat = True
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"Chat and close error: {str(e)}")

    async def _check_timeout(self):
        try:
            while not self.stop_event.is_set():
                last_activity_time = self.last_activity_time
                if self.need_bind:
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
                                self.logger.bind(tag=TAG).error(f"超时关闭连接时出错: {close_error}")
                        break
                await asyncio.sleep(10)
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"超时检查任务出错: {e}")
        finally:
            self.logger.bind(tag=TAG).info("超时检查任务已退出")

    @staticmethod
    def _extract_direct_answer_response(arguments_str):
        if not arguments_str:
            return ""
        try:
            data = json.loads(arguments_str)
            if isinstance(data, dict) and "response" in data:
                return data["response"]
        except (json.JSONDecodeError, TypeError):
            pass

        marker = '"response": "'
        idx = arguments_str.find(marker)
        if idx < 0:
            marker = '"response":"'
            idx = arguments_str.find(marker)
        if idx < 0:
            return ""
        start = idx + len(marker)
        raw = arguments_str[start:]
        if raw.endswith('"}'):
            raw = raw[:-2]
        elif raw.endswith('"'):
            raw = raw[:-1]
        raw = raw.replace('\\"', '"').replace('\\n', '\n').replace('\\\\', '\\')
        return raw

    @staticmethod
    def _clean_response_garbage(text):
        if not text:
            return text
        _garbage_chars = frozenset('")\'}）')
        lines = text.split('\n')
        cleaned = []
        for line in lines:
            stripped = line.strip()
            if stripped and len(stripped) <= 8 and all(c in _garbage_chars for c in stripped):
                continue
            cleaned.append(line)
        result = '\n'.join(cleaned)
        result = re.sub(r'["\'}\]]+$', '', result.rstrip()).rstrip()
        return result

    def _merge_tool_calls(self, tool_calls_list, tools_call):
        for tool_call in tools_call:
            tool_index = getattr(tool_call, "index", None)
            if tool_index is None:
                if tool_call.function.name:
                    tool_index = len(tool_calls_list)
                else:
                    tool_index = len(tool_calls_list) - 1 if tool_calls_list else 0

            if tool_index >= len(tool_calls_list):
                tool_calls_list.append({"id": "", "name": "", "arguments": ""})

            if tool_call.id:
                tool_calls_list[tool_index]["id"] = tool_call.id
            if tool_call.function.name:
                tool_calls_list[tool_index]["name"] = tool_call.function.name
            if tool_call.function.arguments:
                tool_calls_list[tool_index]["arguments"] += tool_call.function.arguments