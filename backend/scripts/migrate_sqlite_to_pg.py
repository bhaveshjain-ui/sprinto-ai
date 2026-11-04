"""One-time copy of backend/sprinto.db into Postgres (Neon). Usage:
    DATABASE_URL=postgresql://... python backend/scripts/migrate_sqlite_to_pg.py
Safe to re-run: existing rows (same id) are skipped. The response cache is not copied."""
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import db  # noqa: E402
from app.config import ROOT, load_config  # noqa: E402

TABLES = ["companies", "facts", "research_log", "decisions", "contacts", "drafts", "sends", "icp_reports"]

load_config()
if not os.environ.get("DATABASE_URL"):
    sys.exit("Set DATABASE_URL to your Neon connection string first.")
src = sqlite3.connect(ROOT / load_config()["db_path"])
src.row_factory = sqlite3.Row
pg = db.connect()  # creates the tables if needed
for t in TABLES:
    rows = src.execute(f"SELECT * FROM {t}").fetchall()
    for r in rows:
        cols = r.keys()
        pg.execute(f"INSERT OR IGNORE INTO {t} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", tuple(r))
    if rows:
        pg.execute(f"SELECT setval(pg_get_serial_sequence('{t}','id'), (SELECT MAX(id) FROM {t}))")
    print(f"{t}: {len(rows)} rows")
for r in src.execute("SELECT key, value FROM settings").fetchall():
    pg.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (r["key"], r["value"]))
print("done")
