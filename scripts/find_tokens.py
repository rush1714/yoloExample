import sqlite3
from pathlib import Path

db_paths = list(Path.home().glob(".codex/**/*.sqlite*")) + list(Path.home().glob(".codex/**/*.db*"))
for p in db_paths:
    if p.is_file() and not p.name.endswith(('-shm', '-wal')):
        try:
            conn = sqlite3.connect(p)
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [r[0] for r in cur.fetchall()]
            for t in tables:
                try:
                    cur.execute(f"SELECT * FROM {t} LIMIT 50;")
                    rows = cur.fetchall()
                    for r in rows:
                        s = str(r)
                        if "qwennote" in s or "bearer" in s.lower() or "token" in s.lower() and len(s) < 500:
                            print(f"Found in {p.name} [{t}]: {s[:300]}")
                except Exception:
                    pass
            conn.close()
        except Exception:
            pass
