#!/usr/bin/env python3
"""
数据库初始化脚本
创建 ai_robot.db 的所有表结构和默认数据

使用方法:
    python scripts/init_db.py

表结构:
    1. devices              - 设备表
    2. device_capabilities  - 设备能力表
    3. scene_templates      - 场景模板表
    4. template_role_configs - 场景角色配置表
"""

import sqlite3
import json
import os
from datetime import datetime

# 数据库路径
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ai_robot.db")


def create_tables(conn):
    """创建所有表"""
    cursor = conn.cursor()

    # 1. 设备表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            id TEXT PRIMARY KEY,
            alias TEXT,
            device_type TEXT,
            ip TEXT,
            online BOOLEAN DEFAULT 0,
            last_seen DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 2. 设备能力表（能力直接属于设备，无全局能力库）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS device_capabilities (
            id TEXT PRIMARY KEY,
            device_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            capability_type TEXT DEFAULT 'atomic',
            command JSON NOT NULL,
            params_schema JSON,
            tags JSON,
            llm_visible BOOLEAN DEFAULT 1,
            sort_order INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
        )
    """)

    # 3. 场景模板表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scene_templates (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            category TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 4. 场景角色配置表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS template_role_configs (
            id TEXT PRIMARY KEY,
            template_id TEXT NOT NULL,
            device_id TEXT NOT NULL,
            role_name TEXT NOT NULL,
            personality TEXT,
            voice_style TEXT,
            enabled_capability_ids JSON,
            custom_data JSON,
            sort_order INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (template_id) REFERENCES scene_templates(id) ON DELETE CASCADE,
            FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
        )
    """)

    # 创建索引
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cap_device_id ON device_capabilities(device_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_role_template_id ON template_role_configs(template_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_role_device_id ON template_role_configs(device_id)")

    conn.commit()
    print("✅ 所有表创建完成")


def insert_default_data(conn):
    """插入默认数据"""
    cursor = conn.cursor()

    # ----- 3.1 默认设备 -----
    devices = [
        ("moss", "MOSS", "desktop", "192.168.1.101", 0, None),
        ("doly", "Doly", "mobile", "192.168.1.102", 0, None),
        ("walle", "瓦力", "mobile", "192.168.1.103", 0, None),
    ]
    cursor.executemany("""
        INSERT OR IGNORE INTO devices (id, alias, device_type, ip, online, last_seen)
        VALUES (?, ?, ?, ?, ?, ?)
    """, devices)

    # ----- 3.2 默认能力（基于固件支持的原子指令）-----
    capabilities = []

    # MOSS 的能力
    moss_caps = [
        ("cap_moss_tts", "moss", "说话", "TTS语音播报", "atomic", json.dumps({"type": "tts", "text": "{{text}}"}),
         json.dumps({"text": {"type": "string", "description": "要播报的文本"}}), json.dumps(["speech"]), 1, 0),

        ("cap_moss_emotion", "moss", "表情", "显示表情", "atomic", json.dumps({"type": "llm", "emotion": "{{emotion}}"}),
         json.dumps({"emotion": {"type": "string", "enum": ["happy", "sad", "angry", "neutral"]}}), json.dumps(["emotion"]), 1, 1),

        ("cap_moss_wave", "moss", "挥手", "舵机挥手动作", "atomic", json.dumps({"type": "action", "action": "wave"}),
         None, json.dumps(["action"]), 1, 2),

        ("cap_moss_servo", "moss", "云台转动", "舵机转动到指定角度", "atomic",
         json.dumps({"type": "action", "action": "servo", "params": {"angle": "{{angle}}"}}),
         json.dumps({"angle": {"type": "int", "min": 0, "max": 180, "description": "目标角度0-180"}}),
         json.dumps(["servo"]), 1, 3),
    ]
    capabilities.extend(moss_caps)

    # Doly 的能力
    doly_caps = [
        ("cap_doly_tts", "doly", "说话", "TTS语音播报", "atomic", json.dumps({"type": "tts", "text": "{{text}}"}),
         json.dumps({"text": {"type": "string", "description": "要播报的文本"}}), json.dumps(["speech"]), 1, 0),

        ("cap_doly_emotion", "doly", "表情", "显示表情", "atomic", json.dumps({"type": "llm", "emotion": "{{emotion}}"}),
         json.dumps({"emotion": {"type": "string", "enum": ["happy", "sad", "angry", "neutral"]}}), json.dumps(["emotion"]), 1, 1),

        ("cap_doly_forward", "doly", "前进", "向前移动", "atomic", json.dumps({"type": "action", "action": "move_forward"}),
         None, json.dumps(["wheel"]), 1, 2),

        ("cap_doly_backward", "doly", "后退", "向后移动", "atomic", json.dumps({"type": "action", "action": "move_backward"}),
         None, json.dumps(["wheel"]), 1, 3),

        ("cap_doly_left", "doly", "左转", "向左转弯", "atomic", json.dumps({"type": "action", "action": "turn_left"}),
         None, json.dumps(["wheel"]), 1, 4),

        ("cap_doly_right", "doly", "右转", "向右转弯", "atomic", json.dumps({"type": "action", "action": "turn_right"}),
         None, json.dumps(["wheel"]), 1, 5),

        ("cap_doly_stop", "doly", "停止", "停止所有运动", "atomic", json.dumps({"type": "action", "action": "stop"}),
         None, json.dumps(["wheel"]), 1, 6),

        ("cap_doly_wave", "doly", "挥手", "舵机挥手动作", "atomic", json.dumps({"type": "action", "action": "wave"}),
         None, json.dumps(["action"]), 1, 7),
    ]
    capabilities.extend(doly_caps)

    # 瓦力的能力
    walle_caps = [
        ("cap_walle_tts", "walle", "说话", "TTS语音播报", "atomic", json.dumps({"type": "tts", "text": "{{text}}"}),
         json.dumps({"text": {"type": "string", "description": "要播报的文本"}}), json.dumps(["speech"]), 1, 0),

        ("cap_walle_emotion", "walle", "表情", "显示表情", "atomic", json.dumps({"type": "llm", "emotion": "{{emotion}}"}),
         json.dumps({"emotion": {"type": "string", "enum": ["happy", "sad", "angry", "neutral"]}}), json.dumps(["emotion"]), 1, 1),

        ("cap_walle_forward", "walle", "前进", "向前移动", "atomic", json.dumps({"type": "action", "action": "move_forward"}),
         None, json.dumps(["wheel"]), 1, 2),

        ("cap_walle_backward", "walle", "后退", "向后移动", "atomic", json.dumps({"type": "action", "action": "move_backward"}),
         None, json.dumps(["wheel"]), 1, 3),

        ("cap_walle_left", "walle", "左转", "向左转弯", "atomic", json.dumps({"type": "action", "action": "turn_left"}),
         None, json.dumps(["wheel"]), 1, 4),

        ("cap_walle_right", "walle", "右转", "向右转弯", "atomic", json.dumps({"type": "action", "action": "turn_right"}),
         None, json.dumps(["wheel"]), 1, 5),

        ("cap_walle_stop", "walle", "停止", "停止所有运动", "atomic", json.dumps({"type": "action", "action": "stop"}),
         None, json.dumps(["wheel"]), 1, 6),

        ("cap_walle_wave", "walle", "挥手", "舵机挥手动作", "atomic", json.dumps({"type": "action", "action": "wave"}),
         None, json.dumps(["action"]), 1, 7),
    ]
    capabilities.extend(walle_caps)

    cursor.executemany("""
        INSERT OR IGNORE INTO device_capabilities
        (id, device_id, name, description, capability_type, command, params_schema, tags, llm_visible, sort_order)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, capabilities)

    # ----- 3.3 默认场景模板（闲聊场景）-----
    scenes = [
        ("scene_chat", "闲聊", "默认闲聊场景", "chat"),
    ]
    cursor.executemany("""
        INSERT OR IGNORE INTO scene_templates (id, name, description, category)
        VALUES (?, ?, ?, ?)
    """, scenes)

    # ----- 3.4 场景角色配置（闲聊场景启用3个设备）-----
    role_configs = [
        ("role_chat_moss", "scene_chat", "moss", "MOSS", "高冷理性、说话简洁、略带傲娇", "zh-CN-YunxiNeural",
         json.dumps(["cap_moss_tts", "cap_moss_emotion", "cap_moss_wave"]), None, 0),

        ("role_chat_doly", "scene_chat", "doly", "Doly", "活泼可爱、话多、喜欢卖萌", "zh-CN-XiaoxiaoNeural",
         json.dumps(["cap_doly_tts", "cap_doly_forward", "cap_doly_wave", "cap_doly_emotion"]), None, 1),

        ("role_chat_walle", "scene_chat", "walle", "瓦力", "憨厚老实、说话慢、真诚", "zh-CN-YunyangNeural",
         json.dumps(["cap_walle_tts", "cap_walle_forward", "cap_walle_wave", "cap_walle_emotion"]), None, 2),
    ]
    cursor.executemany("""
        INSERT OR IGNORE INTO template_role_configs
        (id, template_id, device_id, role_name, personality, voice_style, enabled_capability_ids, custom_data, sort_order)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, role_configs)

    conn.commit()
    print("✅ 默认数据插入完成")
    print(f"   - {len(devices)} 个设备")
    print(f"   - {len(capabilities)} 个能力")
    print(f"   - {len(scenes)} 个场景模板")
    print(f"   - {len(role_configs)} 个角色配置")


def main():
    """主函数"""
    # 确保 data 目录存在
    data_dir = os.path.dirname(DB_PATH)
    os.makedirs(data_dir, exist_ok=True)

    print(f"📁 数据库路径: {DB_PATH}")

    # 检查是否已存在
    if os.path.exists(DB_PATH):
        response = input("⚠️ 数据库已存在，是否覆盖？(y/N): ")
        if response.lower() != 'y':
            print("❌ 操作已取消")
            return
        os.remove(DB_PATH)
        print("🗑️ 旧数据库已删除")

    # 连接数据库
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        create_tables(conn)
        insert_default_data(conn)
        print(f"\n✅ 数据库初始化完成: {DB_PATH}")
    except Exception as e:
        print(f"❌ 初始化失败: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()