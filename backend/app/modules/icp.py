import json

from app import llm


def run(conn, cfg) -> dict:
    """Stage 0: dynamic ICP report via grounded Gemini. Stored with its grounding sources."""
    report, sources = llm.generate(conn, cfg, "icp_report", grounded=True)
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
