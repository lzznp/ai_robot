"""
设备能力数据访问层
提供设备能力的 CRUD 操作
"""

import json
from typing import List, Optional, Dict, Any
from datetime import datetime
from .database import get_db_cursor


class CapabilityRepo:
    """设备能力数据仓库"""

    @staticmethod
    def get_by_device(device_id: str, only_visible: bool = False) -> List[Dict[str, Any]]:
        """获取设备的所有能力"""
        with get_db_cursor() as cursor:
            sql = """
                SELECT id, device_id, name, description, capability_type,
                       command, params_schema, tags, llm_visible, sort_order,
                       created_at, updated_at
                FROM device_capabilities
                WHERE device_id = ?
            """
            params = [device_id]
            if only_visible:
                sql += " AND llm_visible = 1"
            sql += " ORDER BY sort_order, name"
            cursor.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def get_by_id(cap_id: str) -> Optional[Dict[str, Any]]:
        """根据ID获取能力"""
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT id, device_id, name, description, capability_type,
                       command, params_schema, tags, llm_visible, sort_order,
                       created_at, updated_at
                FROM device_capabilities
                WHERE id = ?
            """, (cap_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    def create(
        cap_id: str,
        device_id: str,
        name: str,
        command: Dict,
        description: str = "",
        capability_type: str = "atomic",
        params_schema: Dict = None,
        tags: List[str] = None,
        llm_visible: bool = True,
        sort_order: int = 0
    ) -> bool:
        """创建能力"""
        with get_db_cursor() as cursor:
            cursor.execute("""
                INSERT INTO device_capabilities
                (id, device_id, name, description, capability_type,
                 command, params_schema, tags, llm_visible, sort_order)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                cap_id, device_id, name, description, capability_type,
                json.dumps(command),
                json.dumps(params_schema) if params_schema else None,
                json.dumps(tags) if tags else None,
                1 if llm_visible else 0,
                sort_order
            ))
            return True

    @staticmethod
    def update(
        cap_id: str,
        name: str = None,
        description: str = None,
        command: Dict = None,
        params_schema: Dict = None,
        tags: List[str] = None,
        llm_visible: bool = None,
        sort_order: int = None
    ) -> bool:
        """更新能力"""
        updates = []
        params = []

        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if command is not None:
            updates.append("command = ?")
            params.append(json.dumps(command))
        if params_schema is not None:
            updates.append("params_schema = ?")
            params.append(json.dumps(params_schema))
        if tags is not None:
            updates.append("tags = ?")
            params.append(json.dumps(tags))
        if llm_visible is not None:
            updates.append("llm_visible = ?")
            params.append(1 if llm_visible else 0)
        if sort_order is not None:
            updates.append("sort_order = ?")
            params.append(sort_order)

        if not updates:
            return True

        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(cap_id)

        with get_db_cursor() as cursor:
            cursor.execute(f"""
                UPDATE device_capabilities
                SET {', '.join(updates)}
                WHERE id = ?
            """, params)
            return cursor.rowcount > 0

    @staticmethod
    def delete(cap_id: str) -> bool:
        """删除能力"""
        with get_db_cursor() as cursor:
            cursor.execute("DELETE FROM device_capabilities WHERE id = ?", (cap_id,))
            return cursor.rowcount > 0

    @staticmethod
    def delete_by_device(device_id: str) -> bool:
        """删除设备的所有能力"""
        with get_db_cursor() as cursor:
            cursor.execute("DELETE FROM device_capabilities WHERE device_id = ?", (device_id,))
            return True

    @staticmethod
    def get_by_ids(cap_ids: List[str]) -> List[Dict[str, Any]]:
        """批量获取能力"""
        if not cap_ids:
            return []
        placeholders = ",".join("?" * len(cap_ids))
        with get_db_cursor() as cursor:
            cursor.execute(f"""
                SELECT id, device_id, name, description, capability_type,
                       command, params_schema, tags, llm_visible, sort_order,
                       created_at, updated_at
                FROM device_capabilities
                WHERE id IN ({placeholders})
                ORDER BY sort_order, name
            """, cap_ids)
            return [dict(row) for row in cursor.fetchall()]