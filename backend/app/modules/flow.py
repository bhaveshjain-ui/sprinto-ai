"""Orchestrates stages per company. Every gate stops the company with a saved reason."""
import json
from datetime import datetime, timedelta, timezone

from app import db
from app.modules import contacts, discovery, drafting, icp, intent, research, scoring


def _row(conn, cid):
    return conn.execute("SELECT * FROM companies WHERE id=?", (cid,)).fetchone()


def _stale(row, cfg) -> bool:
    if not row["researched_at"]:
        return True
    t = datetime.fromisoformat(row["researched_at"])
    return datetime.now(timezone.utc) - t > timedelta(days=cfg["refresh_days"])


def process_company(conn, cfg, cid: int, force: bool = False) -> dict:
    c = _row(conn, cid)
    if force or _stale(c, cfg) or c["status"] in ("discovered", "shortlisted"):
        research.run_company(conn, cfg, c)
    c = _row(conn, cid)
    res = scoring.run_company(conn, cfg, cid)
    proceed = res["classification"] == "qualified" or (
        res["classification"] == "further_investigation" and res["score"] >= cfg["scoring"]["proceed_min"])
    if not proceed:
        return {"stopped_at": "score", "classification": res["classification"], "reason": res["reason"]}
    c = _row(conn, cid)
    it = intent.run_company(conn, cfg, c)
    c = _row(conn, cid)
    if c["status"] != "lead":
        return {"stopped_at": "intent", "reason": c["stop_reason"]}
    contact = contacts.run_company(conn, cfg, c)
    c = _row(conn, cid)
    if not contact:
        return {"stopped_at": "contact", "reason": c["stop_reason"]}
    sel = conn.execute("SELECT * FROM contacts WHERE company_id=? AND selected=1", (cid,)).fetchone()
    did = drafting.run_company(conn, cfg, c, sel)
    c = _row(conn, cid)
    if not did:
        return {"stopped_at": "draft", "reason": c["stop_reason"]}
    return {"draft_id": did}


def autonomous(conn, cfg, progress=lambda m: None) -> None:
    progress("ICP report")
    icp.run(conn, cfg)
    progress("discovering companies")
    discovery.discover(conn, cfg)
    progress("shortlisting")
    discovery.shortlist(conn, cfg)
    for r in conn.execute("SELECT id, name FROM companies WHERE status='shortlisted'").fetchall():
        progress(f"processing {r['name']}")
        try:
            process_company(conn, cfg, r["id"])
        except Exception as e:  # one company's failure must not kill the batch
            db.log_decision(conn, r["id"], "error", "failed", str(e)[:300])
            conn.commit()
    progress("done")
