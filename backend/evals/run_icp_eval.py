"""Run the ICP-stage eval (cases in icp_cases.yaml).

    python backend/evals/run_icp_eval.py             # check the latest stored ICP report (no API call)
    python backend/evals/run_icp_eval.py --live      # regenerate the report with Gemini first (1 grounded call)
    python backend/evals/run_icp_eval.py --strict    # also fail the run on major-severity failures

Exit code 1 if any critical case fails (or any major case with --strict). A human-readable
report with the four parts (input / expected behaviour / assertion / severity) is written to
backend/evals/results/icp_eval_report.md.
"""
import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import db, llm  # noqa: E402
from app.modules import icp  # noqa: E402

CASES_FILE = Path(__file__).with_name("icp_cases.yaml")
RESULTS_DIR = Path(__file__).with_name("results")

# A complete, valid report used by the offline round-trip cases and by the eval's own tests.
GOOD_REPORT = {
    "summary": "Sprinto sells to fast-scaling B2B SaaS companies at Series A to Series C that must pass SOC 2 or ISO 27001 audits "
               "to close enterprise deals. They handle sensitive customer data and face security questionnaires from buyers.",
    "industries": [
        {"name": "Fintech SaaS", "why": "Handles payments and banking data, so buyers and regulators demand audit reports."},
        {"name": "Healthtech SaaS", "why": "Processes patient data under HIPAA, which makes SOC 2 and ISO 27001 a sales requirement."},
        {"name": "Developer tools SaaS", "why": "Enterprise engineering buyers send long security reviews before any contract."},
    ],
    "funding_stages": "Series A, B and C companies are moving from founder-led sales to enterprise accounts where audit reports are mandatory.",
    "buying_signals": [
        {"signal": "First hire of a security or GRC role", "why_it_matters": "Shows compliance work has become a priority."},
        {"signal": "Recent growth-round funding announcement", "why_it_matters": "Budget and pressure to land larger customers."},
        {"signal": "Public trust centre or security page launched", "why_it_matters": "They are preparing to show certifications."},
    ],
    "compliance_triggers": ["Enterprise customers requesting SOC 2 reports before signing", "Upcoming audit deadlines with manual evidence collection"],
    "enterprise_expansion_signals": ["Hiring enterprise sales leaders", "Launching an enterprise plan with SSO and audit logs"],
    "search_queries": ['"Series A" SaaS "SOC 2"', '"Series B" SaaS ISO 27001 compliance', 'SaaS "launches enterprise" plan funding',
                       'hiring "GRC Manager" SaaS', '"trust center" SaaS announces'],
}
GOOD_SOURCES = ["https://sprinto.com/blog/soc-2-for-startups/", "https://www.techcrunch.com/2026/series-b-security/",
                "https://www.vanta.com/resources/soc-2-timeline", "https://news.ycombinator.com/item?id=1"]


# ----------------------------------------------------------------------------- helpers
def flat(obj) -> str:
    """All strings in a report, joined (for keyword checks)."""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        return " ".join(flat(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return " ".join(flat(v) for v in obj)
    return ""


def low(obj) -> str:
    return flat(obj).lower()


def nonempty_str(x) -> bool:
    return isinstance(x, str) and bool(x.strip())


def temp_db():
    d = tempfile.TemporaryDirectory()
    return d, db.connect(Path(d.name) / "eval.db")


def count_reports(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM icp_reports").fetchone()[0]


# ----------------------------------------------------------------------------- report checks
# each check(ctx) -> (passed: bool, detail: str); ctx = {report, sources, case}
def c_schema(ctx):
    r = ctx["report"]
    if not isinstance(r, dict):
        return False, "report is not an object"
    problems = []
    if not nonempty_str(r.get("summary")):
        problems.append("summary empty")
    if not nonempty_str(r.get("funding_stages")):
        problems.append("funding_stages empty")
    for k in ("industries", "buying_signals", "compliance_triggers", "enterprise_expansion_signals", "search_queries"):
        if not isinstance(r.get(k), list) or not r[k]:
            problems.append(f"{k} missing/empty")
    for i in r.get("industries") or []:
        if not (isinstance(i, dict) and nonempty_str(i.get("name")) and nonempty_str(i.get("why"))):
            problems.append("industry entry missing name/why")
            break
    for s in r.get("buying_signals") or []:
        if not (isinstance(s, dict) and nonempty_str(s.get("signal")) and nonempty_str(s.get("why_it_matters"))):
            problems.append("buying signal missing signal/why_it_matters")
            break
    for k in ("compliance_triggers", "enterprise_expansion_signals", "search_queries"):
        if any(not nonempty_str(x) for x in r.get(k) or []):
            problems.append(f"{k} has a non-string entry")
    return (not problems), ("all 7 fields valid" if not problems else "; ".join(problems))


def c_summary_quality(ctx):
    s = (ctx["report"].get("summary") or "").strip()
    n = len([x for x in re.split(r"(?<=[.!?])\s+", s) if x])
    t = s.lower()
    ok = 2 <= n <= 6 and "saas" in t and any(k in t for k in ("soc 2", "iso 27001", "27001", "compliance"))
    return ok, f"{n} sentences; saas={'saas' in t}; framework/compliance mentioned={any(k in t for k in ('soc 2', 'iso 27001', '27001', 'compliance'))}"


def c_industries(ctx):
    inds = ctx["report"].get("industries") or []
    names = {(i.get("name") or "").strip().casefold() for i in inds if isinstance(i, dict)}
    short = [i.get("name") for i in inds if len((i.get("why") or "")) < 40]
    ok = len(inds) >= 3 and len(names) == len(inds) and not short
    return ok, f"{len(inds)} industries, {len(names)} distinct, {len(short)} with a too-short reason"


def c_funding_stages(ctx):
    t = low(ctx["report"].get("funding_stages") or "")
    letters = set()
    for m in re.finditer(r"series\s+([a-c](?:\s*(?:,|and|&|to|-|–|/|or)\s*(?:series\s+)?[a-c])*)", t):
        grp = m.group(1)
        letters |= set(re.findall(r"\b[a-c]\b", grp))
        if re.search(r"\bto\b|-|–", grp) and {"a", "c"} <= letters:
            letters.add("b")
    return {"a", "b", "c"} <= letters, f"stages found: {sorted(x.upper() for x in letters) or 'none'}"


def c_audit_frameworks(ctx):
    t = low(ctx["report"])
    soc, iso = ("soc 2" in t or "soc2" in t), "27001" in t
    return soc and iso, f"SOC 2={soc}, ISO 27001={iso}"


def c_enterprise_signals(ctx):
    items = ctx["report"].get("enterprise_expansion_signals") or []
    hit = [x for x in items if any(k in x.lower() for k in ("enterprise", "upmarket", "up-market", "fortune", "large"))]
    return len(items) >= 2 and bool(hit), f"{len(items)} signals, {len(hit)} mention enterprise/upmarket"


def c_compliance_triggers(ctx):
    items = ctx["report"].get("compliance_triggers") or []
    hit = [x for x in items if any(k in x.lower() for k in ("customer", "client", "buyer", "questionnaire", "audit", "regulat", "procurement"))]
    return len(items) >= 2 and bool(hit), f"{len(items)} triggers, {len(hit)} tied to customers/audits/regulation"


def c_buying_signals(ctx):
    sigs = [s for s in ctx["report"].get("buying_signals") or [] if isinstance(s, dict) and nonempty_str(s.get("signal")) and nonempty_str(s.get("why_it_matters"))]
    hit = [s for s in sigs if any(k in s["signal"].lower() for k in ("hir", "role", "grc", "funding", "raise", "round"))]
    return len(sigs) >= 3 and bool(hit), f"{len(sigs)} complete signals, {len(hit)} about hiring/funding"


def c_sources(ctx):
    src = ctx["sources"] or []
    real = [u for u in src if "vertexaisearch" not in u]
    hosts = {urlparse(u).netloc.lower().removeprefix("www.") for u in real}
    http = all(u.startswith(("http://", "https://")) for u in src)
    ok = len(src) >= 3 and len(hosts) >= 3 and http and bool(real)
    return ok, f"{len(src)} sources, {len(real)} direct, {len(hosts)} distinct hosts, all http(s)={http}"


def c_no_statistics(ctx):
    found = re.findall(r"\d+(?:\.\d+)?\s?%|\$\s?\d[\d,.]*|\d+\s?percent", flat(ctx["report"]))
    return not found, "none" if not found else f"found: {found[:5]}"


def c_no_stale_years(ctx):
    stale = sorted({y for y in re.findall(r"\b(19\d\d|20\d\d)\b", flat(ctx["report"])) if int(y) < 2024})
    return not stale, "none" if not stale else f"found: {stale}"


def c_search_queries(ctx):
    q = ctx["report"].get("search_queries") or []
    short = [x for x in q if len(x.split()) < 3]
    dup = len({x.strip().lower() for x in q}) != len(q)
    rel = any(k in x.lower() for x in q for k in ("soc 2", "iso", "compliance", "series"))
    ok = 3 <= len(q) <= 5 and not short and not dup and rel
    return ok, f"{len(q)} queries, {len(short)} too short, duplicates={dup}, relevant={rel}"


def c_summary_text(ctx):
    d, conn = temp_db()
    try:
        conn.execute("INSERT INTO icp_reports (report, sources) VALUES (?,?)", (json.dumps(ctx["report"]), json.dumps(ctx["sources"])))
        conn.commit()
        s = icp.summary_text(conn)
    finally:
        conn.close()
        d.cleanup()
    ok = s == ctx["report"].get("summary") and 20 <= len(s) <= 1500
    return ok, f"{len(s)} chars; equals report summary={s == ctx['report'].get('summary')}"


# ----------------------------------------------------------------------------- offline checks
def _run_with_stub(generate):
    """Run icp.run against an empty temp DB with llm.generate replaced; returns (error or None, rows stored, conn_closed)."""
    d, conn = temp_db()
    orig = icp.llm.generate
    icp.llm.generate = generate
    err = None
    try:
        try:
            icp.run(conn, {"model": "stub"})
        except Exception as e:  # noqa: BLE001
            err = e
        return err, count_reports(conn), conn, d
    finally:
        icp.llm.generate = orig


def o_parse_fenced(ctx):
    fx = ctx["case"]["fixture"]
    try:
        got = llm.parse_json(fx["reply"])
    except Exception as e:  # noqa: BLE001
        return False, f"parse failed: {e}"
    ok = isinstance(got, dict) and got.get("summary") == fx["summary"]
    return ok, "parsed" if ok else f"unexpected result: {str(got)[:80]}"


def o_reject_non_json(ctx):
    reply = ctx["case"]["fixture"]["reply"]
    err, rows, conn, d = _run_with_stub(lambda *a, **k: (llm.parse_json(reply), set()))
    conn.close(); d.cleanup()
    ok = isinstance(err, ValueError) and rows == 0
    return ok, f"raised={type(err).__name__ if err else None}, rows stored={rows}"


def o_reject_skeletal(ctx):
    report = ctx["case"]["fixture"]["report"]
    err, rows, conn, d = _run_with_stub(lambda *a, **k: (report, set()))
    conn.close(); d.cleanup()
    ok = isinstance(err, ValueError) and rows == 0 and all(k in str(err) for k in ("industries", "buying_signals", "search_queries"))
    return ok, f"raised={type(err).__name__ if err else None}, rows stored={rows}" + ("" if ok else f", message={str(err)[:80]}")


def o_persist_roundtrip(ctx):
    err, rows, conn, d = _run_with_stub(lambda *a, **k: (json.loads(json.dumps(GOOD_REPORT)), set(GOOD_SOURCES)))
    try:
        cur = icp.latest(conn)
    finally:
        conn.close(); d.cleanup()
    ok = err is None and rows == 1 and cur and cur["report"] == GOOD_REPORT and cur["sources"] == sorted(GOOD_SOURCES)
    return bool(ok), f"error={err}, rows={rows}, roundtrip equal={bool(cur and cur['report'] == GOOD_REPORT)}"


def o_fallback_summary(ctx):
    d, conn = temp_db()
    try:
        s = icp.summary_text(conn)
    finally:
        conn.close(); d.cleanup()
    return nonempty_str(s) and "saas" in s.lower(), f"{len(s)} chars: {s[:60]}"


CHECKS = {
    "schema": c_schema, "summary_quality": c_summary_quality, "industries": c_industries, "funding_stages": c_funding_stages,
    "audit_frameworks": c_audit_frameworks, "enterprise_signals": c_enterprise_signals, "compliance_triggers": c_compliance_triggers,
    "buying_signals": c_buying_signals, "sources": c_sources, "no_statistics": c_no_statistics, "no_stale_years": c_no_stale_years,
    "search_queries": c_search_queries, "summary_text": c_summary_text,
    "parse_fenced": o_parse_fenced, "reject_non_json": o_reject_non_json, "reject_skeletal": o_reject_skeletal,
    "persist_roundtrip": o_persist_roundtrip, "fallback_summary": o_fallback_summary,
}


# ----------------------------------------------------------------------------- runner
def load_cases() -> list[dict]:
    return yaml.safe_load(CASES_FILE.read_text(encoding="utf-8"))["cases"]


def run_cases(report, sources, cases=None) -> list[dict]:
    results = []
    for case in cases or load_cases():
        ctx = {"report": report or {}, "sources": sources or [], "case": case}
        if case["kind"] == "report" and report is None:
            ok, detail = False, "no ICP report available to evaluate"
        else:
            try:
                ok, detail = CHECKS[case["check"]](ctx)
            except Exception as e:  # noqa: BLE001  a crashing check is a failing check
                ok, detail = False, f"check crashed: {type(e).__name__}: {e}"
        results.append({**{k: case[k] for k in ("id", "name", "kind", "severity", "input", "expected_behaviour", "assertion")},
                        "passed": bool(ok), "detail": detail})
    return results


def write_report(results, source_note: str) -> Path:
    RESULTS_DIR.mkdir(exist_ok=True)
    esc = lambda s: str(s).replace("|", "\\|").replace("\n", " ")  # noqa: E731
    lines = ["# ICP eval results", "", f"Evaluated: {source_note}", ""]
    lines += ["| ID | Input | Expected behaviour | Assertion | Severity | Result | Detail |", "|---|---|---|---|---|---|---|"]
    for r in results:
        lines.append(f"| {r['id']} | {esc(r['input'])} | {esc(r['expected_behaviour'])} | {esc(r['assertion'])} | {r['severity']} | "
                     f"{'PASS' if r['passed'] else 'FAIL'} | {esc(r['detail'])} |")
    path = RESULTS_DIR / "icp_eval_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="regenerate the ICP report with Gemini before evaluating")
    ap.add_argument("--strict", action="store_true", help="fail on major-severity failures too")
    args = ap.parse_args()

    from app.config import load_config

    cfg = load_config()
    conn = db.connect()
    if args.live:
        icp.run(conn, cfg)
    cur = icp.latest(conn)
    report, sources = (cur["report"], cur["sources"]) if cur else (None, [])
    note = ("freshly generated (live)" if args.live else "latest stored report") + (f", created {cur['created_at']}" if cur else ", NONE FOUND")

    results = run_cases(report, sources)
    for r in results:
        print(f"{r['id']}  {r['severity']:<8} {'PASS' if r['passed'] else 'FAIL'}  {r['name']}" + ("" if r["passed"] else f"\n        -> {r['detail']}"))
    fails = [r for r in results if not r["passed"]]
    by = {s: len([r for r in fails if r["severity"] == s]) for s in ("critical", "major", "minor")}
    print(f"\n{len(results) - len(fails)}/{len(results)} passed. Failures: critical={by['critical']} major={by['major']} minor={by['minor']}")
    print("report:", write_report(results, note))
    return 1 if by["critical"] or (args.strict and by["major"]) else 0


if __name__ == "__main__":
    sys.exit(main())
