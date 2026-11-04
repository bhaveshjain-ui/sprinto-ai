"""Stage 5: buying intent, priority and two evidence-backed pain points (verified facts only)."""
import json

from app import db, llm

SIGNAL_TYPES = {"recent_funding", "enterprise_expansion", "compliance_requirements",
                "security_hiring", "audit_preparation", "international_expansion"}


def verified_facts(conn, company_id: int) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM facts WHERE company_id=? AND status='VERIFIED' AND conflict=0", (company_id,))]


def facts_block(facts: list[dict]) -> str:
    return "\n".join(f"{f['id']} | {f['criterion']} | {f['value']} | {f['snippet']}" for f in facts)


def validate(res, valid_ids: set[int], cfg) -> tuple[list, list, list[str]]:
    errs = []
    signals = []
    for s in res.get("signals", []) if isinstance(res, dict) else []:
        ids = [i for i in s.get("fact_ids", []) if i in valid_ids]
        if s.get("type") in SIGNAL_TYPES and ids:
            signals.append({"type": s["type"], "fact_ids": ids})
    seen = set()
    signals = [s for s in signals if not (s["type"] in seen or seen.add(s["type"]))]
    pains = []
    for p in res.get("pain_points", []) if isinstance(res, dict) else []:
        ids = [i for i in p.get("evidence_fact_ids", []) if i in valid_ids]
        if p.get("pain") and ids:
            pains.append({"pain": p["pain"], "evidence_fact_ids": ids, "interpretation": p.get("interpretation", "")})
    if len(pains) < 2:
        errs.append("fewer than two pain points with verified evidence")
    return signals, pains[:2], errs


def run_company(conn, cfg, company) -> dict:
    facts = verified_facts(conn, company["id"])
    res, _ = llm.generate(conn, cfg, "intent", grounded=False, name=company["name"], facts=facts_block(facts))
    signals, pains, errs = validate(res, {f["id"] for f in facts}, cfg)
    n = len(signals)
    ic = cfg["intent"]
    priority = "High" if n >= ic["high_min_signals"] else "Medium" if n >= ic["medium_min_signals"] else "Low"
    intent = {"signals": signals, "pain_points": pains, "priority": priority, "errors": errs}
    conn.execute("UPDATE companies SET intent=?, priority=? WHERE id=?", (json.dumps(intent), priority, company["id"]))
    if priority == "Low" or errs:
        db.stop(conn, company["id"], "intent", f"priority {priority}" + (f"; {'; '.join(errs)}" if errs else ""))
    else:
        conn.execute("UPDATE companies SET status='lead', stage='intent' WHERE id=?", (company["id"],))
        db.log_decision(conn, company["id"], "intent", priority, f"{n} verified signals")
        conn.commit()
    return intent
