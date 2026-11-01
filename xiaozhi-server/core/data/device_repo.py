"""
设备数据访问层
提供设备的 CRUD 操作
"""

import json
from typing import List, Optional, Dict, Any
from datetime import datetime
from .database import get_db_cursor


class DeviceRepo:
    """设备数据仓库"""

    @staticmethod
    def get_all() -> List[Dict[str, Any]]:
        """获取所有设备"""
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT id, alias, device_type, ip, online, last_seen, created_at
                FROM devices
                ORDER BY alias
            """)
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def get_by_id(device_id: str) -> Optional[Dict[str, Any]]:
        """根据ID获取设备"""
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT id, alias, device_type, ip, online, last_seen, created_at
                FROM devices
                WHERE id = ?
            """, (device_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    def get_online() -> List[Dict[str, Any]]:
        """获取所有在线设备"""
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT id, alias, device_type, ip, online, last_seen, created_at
                FROM devices
                WHERE online = 1
                ORDER BY alias
            """)
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def create(device_id: str, alias: str, device_type: str = "unknown", ip: str = "") -> bool:
        """创建设备"""
        with get_db_cursor() as cursor:
            cursor.execute("""
                INSERT INTO devices (id, alias, device_type, ip, online, last_seen)
                VALUES (?, ?, ?, ?, 0, NULL)
            """, (device_id, alias, device_type, ip))
            return True

    @staticmethod
    def update(device_id: str, alias: str = None, device_type: str = None, ip: str = None) -> bool:
        """更新设备信息"""
        updates = []
        params = []
        if alias is not None:
            updates.append("alias = ?")
            params.append(alias)
        if device_type is not None:
            updates.append("device_type = ?")
            params.append(device_type)
        if ip is not None:
            updates.append("ip = ?")
            params.append(ip)

        if not updates:
            return True

        params.append(device_id)
        with get_db_cursor() as cursor:
            cursor.execute(f"""
                UPDATE devices
                SET {', '.join(updates)}
                WHERE id = ?
            """, params)
            return cursor.rowcount > 0

    @staticmethod
    def set_online(device_id: str, online: bool = True) -> bool:
        """设置设备在线状态"""
        with get_db_cursor() as cursor:
            cursor.execute("""
                UPDATE devices
                SET online = ?, last_seen = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (1 if online else 0, device_id))
            return cursor.rowcount > 0

    @staticmethod
    def delete(device_id: str) -> bool:
        """删除设备（级联删除能力和场景角色配置）"""
        with get_db_cursor() as cursor:
            cursor.execute("DELETE FROM devices WHERE id = ?", (device_id,))
            return cursor.rowcount > 0

    @staticmethod
    def exists(device_id: str) -> bool:
        """检查设备是否存在"""
        with get_db_cursor() as cursor:
            cursor.execute("SELECT 1 FROM devices WHERE id = ?", (device_id,))
            return cursor.fetchone() is not None