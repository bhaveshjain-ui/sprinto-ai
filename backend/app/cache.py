import hashlib
import json
import sqlite3
from typing import Callable

DEFAULT_TTL_DAYS = 7


def make_key(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def get_or_set(conn: sqlite3.Connection, namespace: str, key: str, fn: Callable[[], object],
               ttl_days: int | None = DEFAULT_TTL_DAYS):
    """Cached JSON value for (namespace, key); entries older than ttl_days are refetched."""
    row = conn.execute(
        "SELECT value, created_at >= datetime('now', ?) AS fresh FROM cache WHERE namespace=? AND key=?",
        (f"-{ttl_days or 36500} days", namespace, key),
    ).fetchone()
    if row is not None and row["fresh"]:
        return json.loads(row["value"])
    value = fn()
    conn.execute(
        "INSERT OR REPLACE INTO cache (namespace, key, value, created_at) VALUES (?,?,?,datetime('now'))",
        (namespace, key, json.dumps(value)),
    )
    conn.commit()
    return value
