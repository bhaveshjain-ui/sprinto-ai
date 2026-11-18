"""Apply the compliance rubric to companies that are already researched:
  - re-score from their stored facts (audit signals now mean "needs compliance", not "has it")
  - already-compliant companies become Low priority, are stopped, and their PENDING drafts are rejected
  - other companies get their priority recomputed with the new rule
Every change is logged in the decisions table (stage 'rubric') with the previous values, so it can be reversed.

    python backend/scripts/apply_compliance_rubric.py --dry-run     # show what would change
    python backend/scripts/apply_compliance_rubric.py               # apply it
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402
from app.config import load_config  # noqa: E402
from app.modules import intent, scoring  # noqa: E402

dry = "--dry-run" in sys.argv
cfg = load_config()
conn = db.connect()
rows = conn.execute("SELECT * FROM companies WHERE classification IS NOT NULL ORDER BY score DESC").fetchall()
out, rejected_total = [], 0
for co in rows:
    cid = co["id"]
    facts = [dict(r) for r in conn.execute("SELECT * FROM facts WHERE company_id=?", (cid,))]
    res = scoring.score_facts(facts, cfg)
    comp = res["compliance"]
    old = {"score": co["score"], "classification": co["classification"], "priority": co["priority"],
           "status": co["status"], "stage": co["stage"], "stop_reason": co["stop_reason"]}
    new = dict(old, score=res["score"], classification=res["classification"])
    n_signals = len((json.loads(co["intent"] or "{}")).get("signals") or [])
    hard_rejected = res["classification"] == "rejected"  # e.g. already uses a competitor: keep its status and reason
    action = ""
    if comp["status"] == "certified":
        new["priority"] = "Low"
        if not hard_rejected:
            new.update(status="stopped", stage="intent", stop_reason=f"priority Low: already compliant ({', '.join(comp['frameworks']) or 'certified'})")
            action = "stopped: already compliant"
    elif co["intent"]:
        new["priority"], _ = intent.decide_priority(n_signals, res["classification"], comp["status"], cfg)
    drafts = [d for d in conn.execute("SELECT id, status FROM drafts WHERE company_id=? AND status IN ('pending','approved')", (cid,))]
    to_reject = [d["id"] for d in drafts] if (comp["status"] == "certified" and not hard_rejected) else []
    rejected_total += len(to_reject)
    out.append((co["name"], comp["status"], old, new, action, to_reject))
    if dry:
        continue
    conn.execute("UPDATE companies SET score=?, classification=?, score_detail=?, priority=?, status=?, stage=?, stop_reason=? WHERE id=?",
                 (new["score"], new["classification"], json.dumps(res), new["priority"], new["status"], new["stage"], new["stop_reason"], cid))
    for did in to_reject:
        conn.execute("UPDATE drafts SET status='rejected', approved_hash=NULL, updated_at=datetime('now') WHERE id=?", (did,))
    db.log_decision(conn, cid, "rubric", "compliance-rubric-v2",
                    json.dumps({"previous": old, "new": new, "compliance": comp["status"], "auto_rejected_draft_ids": to_reject}))
    conn.commit()

print(f"{'DRY RUN - nothing changed' if dry else 'APPLIED'}: {len(rows)} companies\n")
print(f"{'company':20} {'compliance':12} {'score':>13} {'class':>11}  {'priority':>13}  note")
for name, st, old, new, action, rej in out:
    print(f"{name[:20]:20} {st:12} {str(old['score']):>5} -> {str(new['score']):>5} {str(new['classification'])[:11]:>11}  "
          f"{str(old['priority']):>6} -> {str(new['priority']):>6}  {action}{' | rejected drafts '+str(rej) if rej else ''}")
tally = {}
for _, st, *_ in out:
    tally[st] = tally.get(st, 0) + 1
print("\ncompliance status:", tally, "| pending drafts rejected:", rejected_total)
print("TARGETS (High/Medium, not compliant):", [(n, new["priority"]) for n, st, o, new, a, r in out if st != "certified" and new["priority"] in ("High", "Medium")])
