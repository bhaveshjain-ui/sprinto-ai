import json

from app import llm


REQUIRED_LISTS = ("industries", "buying_signals", "compliance_triggers", "enterprise_expansion_signals", "search_queries")


def validate(report) -> list[str]:
    """Hard contract only: a report the pipeline can safely build on. Coverage/quality is checked by evals/."""
    if not isinstance(report, dict):
        return ["report is not a JSON object"]
    errs = []
    for k in ("summary", "funding_stages"):
        if not isinstance(report.get(k), str) or not report[k].strip():
            errs.append(f"{k} is empty")
    for k in REQUIRED_LISTS:
        v = report.get(k)
        if not isinstance(v, list) or not v:
            errs.append(f"{k} is empty")
        elif k in ("industries", "buying_signals") and not all(isinstance(x, dict) for x in v):
            errs.append(f"{k} entries must be objects")
        elif k not in ("industries", "buying_signals") and not all(isinstance(x, str) and x.strip() for x in v):
            errs.append(f"{k} entries must be non-empty strings")
    return errs


def run(conn, cfg) -> dict:
    """Stage 0: dynamic ICP report via grounded Gemini. Stored with its grounding sources.
    A report that fails validate() is rejected and never stored, so discovery cannot run on it."""
    report, sources = llm.generate(conn, cfg, "icp_report", grounded=True)
    errs = validate(report)
    if errs:
        raise ValueError("ICP report rejected, not stored: " + "; ".join(errs))
    conn.execute("INSERT INTO icp_reports (report, sources) VALUES (?,?)",
                 (json.dumps(report), json.dumps(sorted(sources))))
    conn.commit()
    return report


def latest(conn) -> dict | None:
    r = conn.execute("SELECT * FROM icp_reports ORDER BY id DESC LIMIT 1").fetchone()
    if not r:
        return None
    return {"report": json.loads(r["report"]), "sources": json.loads(r["sources"]), "created_at": r["created_at"]}


def summary_text(conn) -> str:
    cur = latest(conn)
    if not cur:
        return "SaaS companies at Series A-C preparing for SOC 2 / ISO 27001 or expanding to enterprise customers."
    rep = cur["report"]
    return rep.get("summary") or json.dumps(rep)[:1500]
