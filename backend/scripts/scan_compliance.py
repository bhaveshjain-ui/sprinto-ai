"""Settle the compliance status of already-researched companies from their own pages.

    python backend/scripts/scan_compliance.py            # every scored company that is not already known to be compliant
    python backend/scripts/scan_compliance.py Ema Duvo   # only these

Then run apply_compliance_rubric.py to re-score, re-prioritise and set aside any lead found to be already compliant.
"""
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402
from app.config import load_config  # noqa: E402
from app.modules import compliance, compliance_scan  # noqa: E402

cfg = load_config()
names = sys.argv[1:]
boot = db.connect()
rows = boot.execute("SELECT id, name FROM companies WHERE classification IS NOT NULL ORDER BY score DESC").fetchall()
targets = [(r["id"], r["name"]) for r in rows if not names or r["name"] in names]


def status_of(conn, cid):
    facts = [dict(r) for r in conn.execute("SELECT * FROM facts WHERE company_id=? AND criterion='audit_signals'", (cid,))]
    return compliance.classify(facts)


def one(item):
    cid, name = item
    conn = db.connect()
    try:
        co = conn.execute("SELECT * FROM companies WHERE id=?", (cid,)).fetchone()
        before = status_of(conn, cid)["status"]
        summary = compliance_scan.run(conn, cfg, co)
        after = status_of(conn, cid)
        ev = conn.execute("SELECT value, snippet, source_url FROM facts WHERE company_id=? AND method='compliance_scan' LIMIT 1", (cid,)).fetchone()
        line = f"{name[:20]:20} {before:11} -> {after['status']:11} rechecked={summary.get('rechecked_verified', 0)} pages={summary.get('pages_read', '-')} trust={summary.get('trust_pages', '-')}"
        if ev:
            line += f" | {(ev['value'] or '')[:60]}"
        print(line, flush=True)
        return name, before, after["status"]
    except Exception as e:  # noqa: BLE001
        print(f"{name[:20]:20} ERROR {type(e).__name__}: {str(e)[:80]}", flush=True)
        return name, "?", "error"
    finally:
        conn.close()


with ThreadPoolExecutor(max_workers=4) as ex:
    results = list(ex.map(one, targets))
tally = {}
for _, _, after in results:
    tally[after] = tally.get(after, 0) + 1
print("\nstatus after scan:", tally)
