"""把 Doly 的 MAC 注册进 SceneDispatcher 的角色-设备映射。

SceneDispatcher 的映射不是硬编码，是 connection.py:_init_scene_dispatcher() 从
SQLite 的 template_role_configs（当前激活场景）读出来的：
    role_device_map[r['role_name']] = r['device_id']
所以"注册进 SceneDispatcher" = 在激活场景里加一行角色配置。

幂等：已存在同 role_name 或同 device_id 就只更新 device_id/role_name，不重复插。
"""
import sqlite3, os, io, sys

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                  "xiaozhi-server", "data", "ai_robot.db")

DOLY_MAC = "58:e6:c5:11:e8:60"
ROLE_NAME = "Doly"
VOICE = "zh-CN-XiaoxiaoNeural"

log = []
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row

active = con.execute(
    "SELECT id, name FROM scene_templates WHERE is_active = 1 LIMIT 1").fetchone()
if not active:
    print("NO_ACTIVE_SCENE")
    sys.exit(1)
tid, tname = active["id"], active["name"]
log.append("激活场景: %s (%s)" % (tid, tname))

before = [dict(r) for r in con.execute(
    "SELECT role_name, device_id, sort_order FROM template_role_configs "
    "WHERE template_id = ? ORDER BY sort_order", (tid,))]
log.append("改前映射: %s" % [(r["role_name"], r["device_id"]) for r in before])

existing = con.execute(
    "SELECT id FROM template_role_configs WHERE template_id = ? AND (role_name = ? OR device_id = ?)",
    (tid, ROLE_NAME, DOLY_MAC)).fetchone()

if existing:
    con.execute("UPDATE template_role_configs SET device_id = ?, role_name = ?, is_active = 1, "
                "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (DOLY_MAC, ROLE_NAME, existing["id"]))
    log.append("已存在，更新: %s" % existing["id"])
else:
    cur = con.execute(
        "SELECT COALESCE(MAX(sort_order), -1) + 1 AS n FROM template_role_configs WHERE template_id = ?",
        (tid,)).fetchone()
    new_id = "role_%s_doly" % tid
    con.execute(
        "INSERT INTO template_role_configs (id, template_id, device_id, role_name, personality, "
        "voice_style, enabled_capability_ids, custom_data, sort_order, is_active) "
        "VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, 1)",
        (new_id, tid, DOLY_MAC, ROLE_NAME, "活泼", VOICE, cur["n"]))
    log.append("新插入: %s (sort_order=%s)" % (new_id, cur["n"]))

con.commit()

after = [dict(r) for r in con.execute(
    "SELECT role_name, device_id, sort_order FROM template_role_configs "
    "WHERE template_id = ? ORDER BY sort_order", (tid,))]
log.append("改后映射: %s" % [(r["role_name"], r["device_id"]) for r in after])
con.close()

path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_register_doly_result.txt")
with open(path, "w", encoding="utf-8") as f:
    f.write("\n".join(log) + "\n")
print("written:", path)
