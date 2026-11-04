"""Stage 4: ICP score out of 100 from VERIFIED, non-conflicting facts only.
Per criterion the state is: positive | negative (verified bad) | unverified | conflict.
Missing data never counts as a positive and never auto-rejects on its own."""
import json
import re

from app import db


def _num(value: str) -> int | None:
    m = re.search(r"\d[\d,]*", value or "")
    return int(m.group().replace(",", "")) if m else None


def _eval(crit: str, vals: list[str], cfg: dict) -> tuple[float | None, str]:
    """Returns (fraction of weight earned, or None for verified-negative, explanation)."""
    sc = cfg["scoring"]
    text = " | ".join(vals).lower()
    if crit == "funding_stage":
        letters = re.findall(r"series\s+([a-z])", text)
        if any(l in "abc" for l in letters):
            return 1.0, "verified Series A-C"
        if letters or "seed" in text:
            return None, "verified stage outside Series A-C"
        return 0.0, "stage value not interpretable (treated as unverified)"
    if crit == "saas":
        if text.startswith("yes") or "saas" in text:
            return 1.0, "verified SaaS"
        if text.startswith("no"):
            return None, "verified NOT SaaS"
        return 0.0, "value not interpretable"
    if crit == "audit_signals":
        return (1.0, f"{len(vals)} verified audit signals") if len(vals) >= 2 else (0.6, "1 verified audit signal")
    if crit == "employee_count":
        n = _num(vals[0])
        if n is None:
            return 0.0, "no number in value"
        lo, hi = sc["employee_full"]
        if lo <= n <= hi:
            return 1.0, f"{n} employees (ideal band)"
        if any(a <= n <= b for a, b in sc["employee_half"]):
            return 0.5, f"{n} employees (acceptable band)"
        return None, f"{n} employees (outside target size)"
    if crit == "customers":
        if any(k in text for k in sc["enterprise_keywords"]):
            return 1.0, "verified enterprise customers"
        return 0.5, "verified customers, enterprise relevance not shown"
    if crit == "industry":
        if any(k in text for k in sc["relevant_industries"]):
            return 1.0, "relevant industry"
        return 0.5, "industry verified, relevance unclear"
    if crit == "cloud":
        if re.search(r"aws|amazon web|gcp|google cloud|azure", text):
            return 1.0, "AWS/GCP/Azure"
        return 0.5, "other cloud provider"
    return 0.0, ""


def score_facts(facts: list[dict], cfg: dict) -> dict:
    sc = cfg["scoring"]
    detail, total, potential = {}, 0.0, 0.0
    hard_stop = None
    for crit, weight in sc["weights"].items():
        mine = [f for f in facts if f["criterion"] == crit]
        ver = [f for f in mine if f["status"] == "VERIFIED"]
        if any(f["conflict"] for f in ver):
            detail[crit] = {"state": "conflict", "points": 0, "max": weight, "evidence": [f["id"] for f in ver],
                            "explanation": "verified sources disagree; earns nothing until resolved"}
            potential += weight
        elif not ver:
            why = "; ".join(sorted({f["status"] for f in mine})) or "no data"
            detail[crit] = {"state": "unverified", "points": 0, "max": weight, "evidence": [],
                            "explanation": f"UNVERIFIED ({why}); not counted as positive or negative"}
            potential += weight
        else:
            frac, why = _eval(crit, [f["value"] for f in ver], cfg)
            ev = [f["id"] for f in ver]
            if frac is None:
                detail[crit] = {"state": "negative", "points": 0, "max": weight, "evidence": ev, "explanation": why}
                if crit == "saas":
                    hard_stop = "verified not SaaS"
            else:
                pts = round(weight * frac, 1)
                detail[crit] = {"state": "positive" if frac > 0 else "unverified", "points": pts, "max": weight,
                                "evidence": ev, "explanation": why}
                total += pts
                if frac == 0:
                    potential += weight
    comp = [f for f in facts if f["criterion"] == "competitor" and f["status"] == "VERIFIED"]
    if comp:
        hard_stop = f"already uses a competitor: {comp[0]['value']}"
        detail["competitor"] = {"state": "negative", "points": 0, "max": 0, "evidence": [comp[0]["id"]],
                                "explanation": hard_stop}
    total = round(total, 1)
    if hard_stop:
        cls, reason = "rejected", hard_stop
    elif total >= sc["qualified_min"]:
        cls, reason = "qualified", f"score {total} >= {sc['qualified_min']}"
    elif total >= sc["investigate_min"]:
        cls, reason = "further_investigation", f"score {total} in {sc['investigate_min']}-{sc['qualified_min'] - 1}"
    elif total + potential >= sc["investigate_min"]:
        cls, reason = "further_investigation", (
            f"score {total} below {sc['investigate_min']} but {round(potential)} points are UNVERIFIED, "
            "so missing data alone does not reject")
    else:
        cls, reason = "rejected", f"score {total}; even full unverified points could not reach {sc['investigate_min']}"
    return {"score": total, "classification": cls, "reason": reason, "detail": detail,
            "unverified_points": round(potential, 1)}


def run_company(conn, cfg, company_id: int) -> dict:
    facts = [dict(r) for r in conn.execute("SELECT * FROM facts WHERE company_id=?", (company_id,))]
    res = score_facts(facts, cfg)
    status = {"qualified": "qualified", "further_investigation": "further_investigation", "rejected": "stopped"}[
        res["classification"]]
    conn.execute("UPDATE companies SET score=?, classification=?, score_detail=?, status=?, stage='score',"
                 " stop_reason=? WHERE id=?",
                 (res["score"], res["classification"], json.dumps(res), status,
                  res["reason"] if res["classification"] == "rejected" else None, company_id))
    db.log_decision(conn, company_id, "score", res["classification"], res["reason"])
    conn.commit()
    return res
