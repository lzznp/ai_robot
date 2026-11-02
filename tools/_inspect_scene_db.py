import sqlite3, os, io

db = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                  "xiaozhi-server", "data", "ai_robot.db")
out = io.StringIO()
out.write("DB: %s\n" % db)
con = sqlite3.connect(db)
con.row_factory = sqlite3.Row

tables = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
out.write("TABLES: %s\n" % tables)

for t in ("scene_templates", "template_role_configs", "devices"):
    if t not in tables:
        continue
    out.write("\n=== %s ===\n" % t)
    for r in con.execute("select * from %s" % t):
        out.write(repr(dict(r)) + "\n")

path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_scene_db_dump.txt")
with open(path, "w", encoding="utf-8") as f:
    f.write(out.getvalue())
print("written:", path)
