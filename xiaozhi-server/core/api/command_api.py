# core/api/command_api.py
"""
指令下发 API - 供 Streamlit 控制台调用
"""

import json
import logging
from aiohttp import web
from core.device_manager import DeviceManager
from core.data import SceneRepo, RoleConfigRepo

routes = web.RouteTableDef()
logger = logging.getLogger(__name__)


@routes.post('/api/command')
async def send_command(request):
    """下发指令到指定设备"""
    try:
        data = await request.json()
        device_id = data.get("device_id")
        command = data.get("command")

        if not device_id:
            return web.json_response({
                "success": False,
                "message": "缺少 device_id 参数"
            }, status=400)

        if not command:
            return web.json_response({
                "success": False,
                "message": "缺少 command 参数"
            }, status=400)

        if not isinstance(command, dict):
            return web.json_response({
                "success": False,
                "message": "command 必须是 JSON 对象"
            }, status=400)

        dm: DeviceManager = request.app.get("device_manager")
        if not dm:
            logger.error("[CommandAPI] DeviceManager 未初始化")
            return web.json_response({
                "success": False,
                "message": "DeviceManager 未初始化"
            }, status=500)

        if not dm.is_online(device_id):
            logger.warning(f"[CommandAPI] 设备 {device_id} 不在线")
            return web.json_response({
                "success": False,
                "message": f"设备 {device_id} 不在线"
            }, status=404)

        logger.info(f"[CommandAPI] 下发指令到 {device_id}: {json.dumps(command, ensure_ascii=False)}")
        success = await dm.send(device_id, command)

        if success:
            return web.json_response({
                "success": True,
                "message": f"指令已下发到 {device_id}",
                "data": {
                    "device_id": device_id,
                    "command": command
                }
            })
        else:
            return web.json_response({
                "success": False,
                "message": f"指令下发失败，请检查设备连接"
            }, status=500)

    except json.JSONDecodeError as e:
        logger.error(f"[CommandAPI] JSON 解析错误: {e}")
        return web.json_response({
            "success": False,
            "message": f"请求体 JSON 格式错误: {str(e)}"
        }, status=400)

    except Exception as e:
        logger.error(f"[CommandAPI] 异常: {e}")
        return web.json_response({
            "success": False,
            "message": f"服务器内部错误: {str(e)}"
        }, status=500)


@routes.get('/api/devices')
async def get_devices(request):
    """获取所有在线设备列表"""
    try:
        dm: DeviceManager = request.app.get("device_manager")
        if not dm:
            return web.json_response({
                "success": False,
                "message": "DeviceManager 未初始化"
            }, status=500)

        devices = []
        for device_id in dm.get_online_devices():
            info = dm.get_device_info(device_id) or {}
            devices.append({
                "device_id": device_id,
                "ip": info.get("ip", "未知"),
                "last_seen": info.get("last_seen", "未知"),
            })

        return web.json_response({
            "success": True,
            "devices": devices
        })

    except Exception as e:
        logger.error(f"[CommandAPI] 获取设备列表异常: {e}")
        return web.json_response({
            "success": False,
            "message": f"服务器内部错误: {str(e)}"
        }, status=500)


@routes.post('/api/scene/switch')
async def switch_scene(request):
    """切换场景"""
    try:
        data = await request.json()
        scene_id = data.get('scene_id')
        if not scene_id:
            return web.json_response({'success': False, 'message': '缺少 scene_id'})

        scene = SceneRepo.get_by_id(scene_id)
        if not scene:
            return web.json_response({'success': False, 'message': '场景不存在'})

        role_configs = RoleConfigRepo.get_by_template(scene_id)

        role_device_map = {}
        for r in role_configs:
            role_device_map[r['role_name']] = r['device_id']

        device_manager = request.app.get('device_manager')
        if device_manager:
            device_manager.current_scene = {
                'id': scene_id,
                'name': scene['name'],
                'role_device_map': role_device_map,
                'role_configs': role_configs
            }
            return web.json_response({'success': True, 'message': f'已切换到场景: {scene["name"]}'})
        else:
            return web.json_response({'success': False, 'message': 'DeviceManager 未初始化'})
    except Exception as e:
        return web.json_response({'success': False, 'message': str(e)})


@routes.post('/api/scene/stop')
async def stop_scene(request):
    """停止当前场景"""
    try:
        device_manager = request.app.get('device_manager')
        if device_manager:
            device_manager.current_scene = None
            return web.json_response({'success': True, 'message': '场景已停止'})
        return web.json_response({'success': False, 'message': 'DeviceManager 未初始化'})
    except Exception as e:
        return web.json_response({'success': False, 'message': str(e)})


@routes.post('/api/text')
async def handle_text(request):
    try:
        data = await request.json()
        device_id = data.get('device_id')
        text = data.get('text')

        if not device_id or not text:
            return web.json_response({'success': False, 'message': '缺少 device_id 或 text'})

        dm: DeviceManager = request.app.get('device_manager')
        if not dm:
            return web.json_response({'success': False, 'message': 'DeviceManager 未初始化'})

        # ★★★ 调试日志 ★★★
        logger.info(f"[DEBUG] device_id: {device_id}")
        logger.info(f"[DEBUG] dm._handlers: {dm._handlers}")
        logger.info(f"[DEBUG] dm._handlers keys: {list(dm._handlers.keys())}")

        handler = dm.get_handler(device_id)
        logger.info(f"[DEBUG] handler: {handler}")

        if not handler:
            return web.json_response({'success': False, 'message': f'设备 {device_id} 不在线或无处理器'})

        # 检查 handler 的方法
        logger.info(f"[DEBUG] handler 方法: {dir(handler)}")

        if hasattr(handler, 'test_scene_dispatcher'):
            result = await handler.test_scene_dispatcher(text)
            return web.json_response(result)
        else:
            return web.json_response({'success': False, 'message': 'test_scene_dispatcher 方法不存在'})

    except Exception as e:
        logger.error(f"[CommandAPI] /api/text 异常: {e}")
        return web.json_response({'success': False, 'message': str(e)})