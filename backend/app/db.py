import json
import os
import re
import sqlite3
from pathlib import Path

from app.config import ROOT

SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
  namespace TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (namespace, key)
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS icp_reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT, report TEXT NOT NULL, sources TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS companies (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  domain TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  origin TEXT NOT NULL DEFAULT 'auto',        -- auto | manual
  status TEXT NOT NULL DEFAULT 'discovered',
    -- discovered|shortlisted|researched|qualified|further_investigation|rejected|stopped|lead|drafted
  stage TEXT NOT NULL DEFAULT 'discover',
  stop_reason TEXT,
  discover_sources TEXT NOT NULL DEFAULT '[]',
  triage TEXT,                                 -- json: rough industry/stage from shortlist triage
  shortlist_score REAL,
  score REAL, classification TEXT, score_detail TEXT,
  priority TEXT, intent TEXT,                  -- json
  researched_at TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS facts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  company_id INTEGER NOT NULL REFERENCES companies(id),
  criterion TEXT NOT NULL, value TEXT, source_url TEXT, snippet TEXT,
  origin TEXT,                 -- grounding | scraper
  status TEXT NOT NULL,        -- VERIFIED | ASSERTED | STALE | NOT_FOUND
  status_reason TEXT, page_date TEXT, retrieved_at TEXT,
  attempt INTEGER, method TEXT,
  conflict INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS facts_company ON facts(company_id);

CREATE TABLE IF NOT EXISTS research_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  company_id INTEGER NOT NULL, criterion TEXT NOT NULL, attempt INTEGER NOT NULL,
  method TEXT NOT NULL, outcome TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  company_id INTEGER NOT NULL, stage TEXT NOT NULL, decision TEXT NOT NULL, detail TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS contacts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  company_id INTEGER NOT NULL, first_name TEXT, last_name TEXT, email TEXT, position TEXT,
  confidence INTEGER, verification TEXT, source TEXT,
  selected INTEGER NOT NULL DEFAULT 0, reasoning TEXT
);

CREATE TABLE IF NOT EXISTS drafts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  company_id INTEGER NOT NULL, contact_id INTEGER NOT NULL,
  subject TEXT NOT NULL, body TEXT NOT NULL, fact_ids TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'pending',     -- pending|approved|rejected|sent|failed
  approved_hash TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')), updated_at TEXT
);

CREATE TABLE IF NOT EXISTS sends (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  draft_id INTEGER NOT NULL, to_email TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL,
  status TEXT NOT NULL,                       -- sending|sent|failed|dry_run
  resend_id TEXT, error TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS one_live_send ON sends(draft_id) WHERE status IN ('sending','sent');
"""


_INITIALISED: set[str] = set()

NOW_PG = "to_char(now() at time zone 'utc', 'YYYY-MM-DD HH24:MI:SS')"
ID_TABLES = {"companies", "facts", "research_log", "decisions", "contacts", "drafts", "sends", "icp_reports"}

try:  # Postgres (Neon) is optional: SQLite remains the local default
    import psycopg

    IntegrityErrors: tuple = (sqlite3.IntegrityError, psycopg.errors.IntegrityError)
except ImportError:  # pragma: no cover
    psycopg = None
    IntegrityErrors = (sqlite3.IntegrityError,)


def pg_schema() -> str:
    return (SCHEMA.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
            .replace("DEFAULT (datetime('now'))", f"DEFAULT ({NOW_PG})")
            .replace(" REAL", " DOUBLE PRECISION"))


def translate(sql: str, has_params: bool) -> tuple[str, bool]:
    """Rewrite this app's SQLite-flavoured SQL for Postgres. Returns (sql, wants_returning_id)."""
    s = sql.strip().rstrip(";")
    if s.upper() == "BEGIN IMMEDIATE":
        return "BEGIN", False
    s = re.sub(r"datetime\('now',\s*\?\)", f"to_char((now() at time zone 'utc') + ?::interval, 'YYYY-MM-DD HH24:MI:SS')", s)
    s = s.replace("datetime('now')", NOW_PG)
    mode = None
    m = re.match(r"INSERT OR (IGNORE|REPLACE) INTO", s, re.I)
    if m:
        mode = m.group(1).upper()
        s = "INSERT INTO" + s[m.end():]
    if has_params:
        s = s.replace("%", "%%")
    s = s.replace("?", "%s")
    is_insert = s.upper().startswith("INSERT")
    table = (re.match(r"INSERT INTO\s+(\w+)", s, re.I) or [None, ""])[1].lower() if is_insert else ""
    if mode == "IGNORE":
        s += " ON CONFLICT DO NOTHING"
    elif mode == "REPLACE":
        if table == "cache":
            s += " ON CONFLICT (namespace, key) DO UPDATE SET value=EXCLUDED.value, created_at=EXCLUDED.created_at"
        elif table == "settings":
            s += " ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value"
    ret = is_insert and table in ID_TABLES and "RETURNING" not in s.upper()
    if ret:
        s += " RETURNING id"
    return s, ret


class Row(dict):
    """Row that supports row["name"], row[0] and dict(row), like sqlite3.Row."""

    def __getitem__(self, k):
        return list(self.values())[k] if isinstance(k, int) else super().__getitem__(k)


def _row_factory(cursor):
    names = [c.name for c in cursor.description or []]
    return lambda values: Row(zip(names, values))


class PgCursor:
    def __init__(self, cur, returning: bool):
        self._cur = cur
        self.lastrowid = None
        if returning:
            row = cur.fetchone() if cur.description else None
            self.lastrowid = row["id"] if row else None

    @property
    def rowcount(self):
        return self._cur.rowcount

    def fetchone(self):
        return self._cur.fetchone() if self._cur.description else None

    def fetchall(self):
        return self._cur.fetchall() if self._cur.description else []

    def __iter__(self):
        return iter(self.fetchall())


class PgConn:
    """sqlite3-style connection over psycopg (autocommit; explicit transactions via BEGIN IMMEDIATE)."""

    def __init__(self, url: str):
        self.raw = psycopg.connect(url, autocommit=True, prepare_threshold=None, row_factory=_row_factory)

    def execute(self, sql: str, params=()):
        s, ret = translate(sql, bool(params))
        cur = self.raw.cursor()
        cur.execute(s, list(params) if params else None)
        if s == "BEGIN":
            cur.execute("LOCK TABLE sends IN SHARE ROW EXCLUSIVE MODE")
        return PgCursor(cur, ret)

    def _in_txn(self) -> bool:
        return self.raw.info.transaction_status != psycopg.pq.TransactionStatus.IDLE

    def commit(self):
        if self._in_txn():
            self.raw.execute("COMMIT")

    def rollback(self):
        if self._in_txn():
            self.raw.execute("ROLLBACK")

    def close(self):
        try:
            self.raw.close()
        except Exception:
            pass

    def __del__(self):
        self.close()


def _pg_url() -> str | None:
    return os.environ.get("DATABASE_URL", "").strip() or None


def connect(path: str | Path | None = None):
    if path is None:
        from app.config import load_config

        cfg = load_config()
        url = _pg_url()
        if url:
            conn = PgConn(url)
            if "pg" not in _INITIALISED and not os.environ.get("VERCEL"):
                try:
                    conn.raw.execute(pg_schema())
                except Exception:
                    pass  # another process created the tables first
                _INITIALISED.add("pg")
            return conn
        path = ROOT / cfg["db_path"]
    conn = sqlite3.connect(path, timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=60000")
    key = str(path)
    if key not in _INITIALISED:  # schema setup needs a write lock; do it once per process, not per connection
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        _INITIALISED.add(key)
    return conn


def log_decision(conn, company_id: int, stage: str, decision: str, detail=None) -> None:
    conn.execute(
        "INSERT INTO decisions (company_id, stage, decision, detail) VALUES (?,?,?,?)",
        (company_id, stage, decision, json.dumps(detail) if not isinstance(detail, str) else detail),
    )


def stop(conn, company_id: int, stage: str, reason: str, status: str = "stopped") -> None:
    """A company that fails a gate stops there, with the reason saved."""
    conn.execute("UPDATE companies SET status=?, stage=?, stop_reason=? WHERE id=?",
                 (status, stage, reason, company_id))
    log_decision(conn, company_id, stage, status, reason)
    conn.commit()


def get_setting(conn, key: str, default: str) -> str:
    r = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r["value"] if r else default


def set_setting(conn, key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, value))
    conn.commit()
