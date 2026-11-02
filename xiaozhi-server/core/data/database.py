"""
数据库连接管理模块
提供统一的 SQLite 连接获取和关闭
支持多线程（Streamlit 环境）
"""

import sqlite3
import os
import threading
from contextlib import contextmanager
from typing import Generator

# 数据库文件路径（相对于项目根目录）
DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data",
    "ai_robot.db"
)


class Database:
    """数据库连接管理（支持多线程）"""

    def __init__(self):
        self._local = threading.local()

    def get_connection(self) -> sqlite3.Connection:
        """获取当前线程的数据库连接"""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            # 确保目录存在
            os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
            self._local.conn = sqlite3.connect(
                DB_PATH,
                check_same_thread=False  # 允许跨线程使用（每个线程独立连接）
            )
            self._local.conn.row_factory = sqlite3.Row
            # 启用外键约束
            self._local.conn.execute("PRAGMA foreign_keys = ON")
        return self._local.conn

    def close(self):
        """关闭当前线程的数据库连接"""
        if hasattr(self._local, 'conn') and self._local.conn:
            self._local.conn.close()
            self._local.conn = None


# 全局数据库实例
db = Database()


@contextmanager
def get_db_connection() -> Generator[sqlite3.Connection, None, None]:
    """上下文管理器：自动获取和关闭连接"""
    conn = db.get_connection()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        # 不关闭连接，由线程本地管理
        pass


@contextmanager
def get_db_cursor() -> Generator[sqlite3.Cursor, None, None]:
    """上下文管理器：获取游标，自动提交"""
    conn = db.get_connection()
    cursor = conn.cursor()
    try:
        yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


def _migrate() -> None:
    """在导入时补齐新增列（幂等）。

    2026-11-01：devices 加 hw_json —— 存**这台设备此刻的实物现状**
      {"lamp_pins": [7], "notes": ["灯组1 目前只接了 1 颗"]}
    与 core/actions.py 的 KNOWN_BOARDS 分工：
      KNOWN_BOARDS = 固件/设计事实（跟 config.h 一起 review）
      hw_json      = 这台机器的实物备注与覆盖（会变，页面上可改）
    ⚠️ 不在页面里随便塞引脚“新事实”：hw_json 只是**覆盖/补充**，界面上会标出“本机”。
    """
    try:
        with get_db_cursor() as cursor:
            cols = {row[1] for row in cursor.execute("PRAGMA table_info(devices)")}
            if cols and "hw_json" not in cols:
                cursor.execute("ALTER TABLE devices ADD COLUMN hw_json TEXT")
    except sqlite3.Error:
        # 数据库还没建表时不管；真正用到时 repo 会报错，不在这里吞掉信息
        pass


_migrate()