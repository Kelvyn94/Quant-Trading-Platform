import sqlite3
import os

DB = os.path.join(os.path.dirname(__file__), 'trading.db')
if not os.path.exists(DB):
    raise SystemExit(f"DB not found at {DB}")

conn = sqlite3.connect(DB)
cur = conn.cursor()
tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]

for t in tables:
    try:
        cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{t}_date ON {t}(date);")
        print(f"Created index idx_{t}_date")
    except Exception as e:
        print(f"Failed to create index on {t}: {e}")

conn.commit()
conn.close()