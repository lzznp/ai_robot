"""
场景数据访问层
提供场景模板和角色配置的 CRUD 操作
"""

import json
from typing import List, Optional, Dict, Any
from datetime import datetime
from .database import get_db_cursor


class SceneRepo:
    """场景模板数据仓库"""

    @staticmethod
    def get_all() -> List[Dict[str, Any]]:
        """获取所有场景模板"""
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT id, name, description, category, created_at, updated_at
                FROM scene_templates
                ORDER BY name
            """)
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def get_by_id(template_id: str) -> Optional[Dict[str, Any]]:
        """根据ID获取场景模板"""
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT id, name, description, category, created_at, updated_at
                FROM scene_templates
                WHERE id = ?
            """, (template_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    def create(template_id: str, name: str, description: str = "", category: str = "chat") -> bool:
        """创建场景模板"""
        with get_db_cursor() as cursor:
            cursor.execute("""
                INSERT INTO scene_templates (id, name, description, category)
                VALUES (?, ?, ?, ?)
            """, (template_id, name, description, category))
            return True

    @staticmethod
    def update(
        template_id: str,
        name: str = None,
        description: str = None,
        category: str = None
    ) -> bool:
        """更新场景模板"""
        updates = []
        params = []
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if category is not None:
            updates.append("category = ?")
            params.append(category)

        if not updates:
            return True

        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(template_id)

        with get_db_cursor() as cursor:
            cursor.execute(f"""
                UPDATE scene_templates
                SET {', '.join(updates)}
                WHERE id = ?
            """, params)
            return cursor.rowcount > 0

    @staticmethod
    def delete(template_id: str) -> bool:
        """删除场景模板（级联删除角色配置）"""
        with get_db_cursor() as cursor:
            cursor.execute("DELETE FROM scene_templates WHERE id = ?", (template_id,))
            return cursor.rowcount > 0

    @staticmethod
    def set_active(scene_id: str) -> bool:
        """将指定场景设为激活，其他场景取消激活"""
        with get_db_cursor() as cursor:
            cursor.execute("UPDATE scene_templates SET is_active = 0")
            cursor.execute("UPDATE scene_templates SET is_active = 1 WHERE id = ?", (scene_id,))
            return True


    @staticmethod
    def get_active_scene() -> Optional[Dict[str, Any]]:
        """获取当前激活的场景"""
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT id, name, description, category, is_active
                FROM scene_templates WHERE is_active = 1 LIMIT 1
            """)
            row = cursor.fetchone()
            return dict(row) if row else None


class RoleConfigRepo:
    """场景角色配置数据仓库"""

    @staticmethod
    def get_by_template(template_id: str) -> List[Dict[str, Any]]:
        """获取场景的所有角色配置"""
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT id, template_id, device_id, role_name, personality,
                       voice_style, enabled_capability_ids, custom_data,
                       sort_order, is_active, created_at, updated_at
                FROM template_role_configs
                WHERE template_id = ?
                ORDER BY sort_order
            """, (template_id,))
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def get_by_id(config_id: str) -> Optional[Dict[str, Any]]:
        """根据ID获取角色配置"""
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT id, template_id, device_id, role_name, personality,
                       voice_style, enabled_capability_ids, custom_data,
                       sort_order, is_active, created_at, updated_at
                FROM template_role_configs
                WHERE id = ?
            """, (config_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    def create(
        config_id: str,
        template_id: str,
        device_id: str,
        role_name: str,
        personality: str = "",
        voice_style: str = "",
        enabled_capability_ids: List[str] = None,
        custom_data: Dict = None,
        sort_order: int = 0,
        is_active: bool = True
    ) -> bool:
        """创建角色配置"""
        with get_db_cursor() as cursor:
            cursor.execute("""
                INSERT INTO template_role_configs
                (id, template_id, device_id, role_name, personality, voice_style,
                 enabled_capability_ids, custom_data, sort_order, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                config_id, template_id, device_id, role_name, personality, voice_style,
                json.dumps(enabled_capability_ids) if enabled_capability_ids else None,
                json.dumps(custom_data) if custom_data else None,
                sort_order,
                1 if is_active else 0
            ))
            return True

    @staticmethod
    def update(
        config_id: str,
        role_name: str = None,
        personality: str = None,
        voice_style: str = None,
        enabled_capability_ids: List[str] = None,
        custom_data: Dict = None,
        sort_order: int = None,
        is_active: bool = None
    ) -> bool:
        """更新角色配置"""
        updates = []
        params = []

        if role_name is not None:
            updates.append("role_name = ?")
            params.append(role_name)
        if personality is not None:
            updates.append("personality = ?")
            params.append(personality)
        if voice_style is not None:
            updates.append("voice_style = ?")
            params.append(voice_style)
        if enabled_capability_ids is not None:
            updates.append("enabled_capability_ids = ?")
            params.append(json.dumps(enabled_capability_ids))
        if custom_data is not None:
            updates.append("custom_data = ?")
            params.append(json.dumps(custom_data))
        if sort_order is not None:
            updates.append("sort_order = ?")
            params.append(sort_order)
        if is_active is not None:
            updates.append("is_active = ?")
            params.append(1 if is_active else 0)

        if not updates:
            return True

        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(config_id)

        with get_db_cursor() as cursor:
            cursor.execute(f"""
                UPDATE template_role_configs
                SET {', '.join(updates)}
                WHERE id = ?
            """, params)
            return cursor.rowcount > 0

    @staticmethod
    def delete(config_id: str) -> bool:
        """删除角色配置"""
        with get_db_cursor() as cursor:
            cursor.execute("DELETE FROM template_role_configs WHERE id = ?", (config_id,))
            return cursor.rowcount > 0

    @staticmethod
    def delete_by_template(template_id: str) -> bool:
        """删除场景的所有角色配置"""
        with get_db_cursor() as cursor:
            cursor.execute("DELETE FROM template_role_configs WHERE template_id = ?", (template_id,))
            return True

    @staticmethod
    def get_enabled_capabilities(config_id: str) -> List[str]:
        """获取角色启用的能力ID列表"""
        config = RoleConfigRepo.get_by_id(config_id)
        if not config:
            return []
        return json.loads(config.get("enabled_capability_ids", "[]")) or []