"""Fill employee_count / cloud / industry gaps from Hunter company enrichment for already-researched companies,
then re-score. Companies that already have drafts or reached contact/intent keep their status (drafts are never touched);
companies still waiting at the score stage continue through the pipeline if they now qualify.

    python backend/scripts/fill_gaps.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402
from app.config import load_config  # noqa: E402
from app.modules import flow, research, scoring  # noqa: E402

cfg = load_config()
conn = db.connect()
rows = conn.execute("SELECT * FROM companies WHERE researched_at IS NOT NULL AND classification IN ('further_investigation','qualified')"
                    " ORDER BY score DESC").fetchall()
print(f"{len(rows)} scored companies to check")
for co in rows:
    cid = co["id"]
    before = (co["score"], co["classification"])
    filled = research.hunter_enrich(conn, cfg, co)
    if not filled:
        continue
    facts = [dict(r) for r in conn.execute("SELECT * FROM facts WHERE company_id=?", (cid,))]
    res = scoring.score_facts(facts, cfg)
    if co["status"] == "further_investigation":  # still waiting at the score stage: continue the pipeline if it now qualifies
        out = flow.process_company(conn, cfg, cid)
        after = conn.execute("SELECT score, classification, status, stop_reason FROM companies WHERE id=?", (cid,)).fetchone()
        note = f"pipeline -> status={after['status']} {after['stop_reason'] or ''}"
    else:  # drafted / lead / stopped later: refresh the score only, never the status or drafts
        conn.execute("UPDATE companies SET score=?, classification=?, score_detail=? WHERE id=?",
                     (res["score"], res["classification"], json.dumps(res), cid))
        conn.commit()
        note = f"score refreshed, status kept ({co['status']})"
    now = conn.execute("SELECT score, classification FROM companies WHERE id=?", (cid,)).fetchone()
    print(f"{co['name'][:22]:22} filled {','.join(filled):28} {before[0]} {before[1]} -> {now['score']} {now['classification']}  | {note}", flush=True)
print("done")
