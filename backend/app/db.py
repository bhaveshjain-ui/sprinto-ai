import json
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


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    if path is None:
        from app.config import load_config

        path = ROOT / load_config()["db_path"]
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
