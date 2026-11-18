"""The compliance rubric: already-compliant companies are low priority; companies that still need compliance are the target."""
import json

import pytest

from app import db
from app.config import load_config
from app.modules import compliance, intent, scoring

CFG = load_config()


def A(id, value, snippet="", status="VERIFIED", conflict=0):
    return {"id": id, "criterion": "audit_signals", "value": value, "snippet": snippet, "status": status, "conflict": conflict}


# ---- classifier, on real evidence strings from the research ----
@pytest.mark.parametrize("value,snippet", [
    ("SOC 2 Type II certified", "Discern is SOC 2 Type II certified. Audited annually"),
    ("ISO 27001 certified", "Respond.io is ISO 27001 certified"),
    ("SOC 1 and SOC 2 Type 2 attestations", "Kaiko holds SOC 1 and SOC 2 Type 2 attestations from a Big Four audit firm"),
    ("SOC 2 Type II, ISO 27001", "Yes. Finout is SOC 2 Type II, ISO 27001, and GDPR compliant."),
    ("SOC 2 Type II", "The platform holds SOC 2 Type II, table stakes for regulated-industry buyers."),
])
def test_certified(value, snippet):
    assert compliance.classify([A(1, value, snippet)])["status"] == "certified"


@pytest.mark.parametrize("value,snippet", [
    ("SOC 2 preparation", "Harden the platform with network policies, workload identity, secrets, and audit logging"),
    ("Compliance Manager", "Compliance Manager EU/UK - Remote. View role: Compliance Manager"),
    ("Hiring Head of Security to oversee SOC 2 and security/compliance programs", "You've owned security programs such as SOC 2"),
    ("Security Engineer job opening to advance SOC 2 compliance readiness", "Lead incident response and advance compliance readiness (e.g., SOC 2)"),
])
def test_in_progress_is_the_target(value, snippet):
    assert compliance.classify([A(1, value, snippet)])["status"] == "in_progress"


def test_holding_a_certification_beats_hiring():
    res = compliance.classify([A(1, "Security Engineer job opening to advance SOC 2 compliance readiness", "advance SOC 2 readiness"),
                               A(2, "SOC 2 Type II and ISO 27001 certified", "Single-tenant architecture. SOC 2 Type II and ISO 27001 certified.")])
    assert res["status"] == "certified" and {"SOC 2", "ISO 27001"} <= set(res["frameworks"])


def test_certified_in_one_framework_is_still_compliant_even_if_working_on_another():
    res = compliance.classify([A(1, "SOC 2 certified, ISO 27001 in progress", "Stuut is SOC 2 certified and GDPR compliant, with ISO 27001 in progress")])
    assert res["status"] == "certified"


def test_unclear_and_unverified_evidence_is_unknown_never_assumed():
    assert compliance.classify([A(1, "SOC 2 compliance", "Technical Operations Lead")])["status"] == "unknown"
    assert compliance.classify([])["status"] == "unknown"
    # ASSERTED / conflicting facts never count, in either direction
    assert compliance.classify([A(1, "SOC 2 Type II certified", "certified", status="ASSERTED")])["status"] == "unknown"
    assert compliance.classify([A(1, "SOC 2 Type II certified", "certified", conflict=1)])["status"] == "unknown"


# ---- scoring: certified earns nothing, a real need earns the audit points ----
def F(id, crit, value, status="VERIFIED"):
    return {"id": id, "criterion": crit, "value": value, "status": status, "conflict": 0, "snippet": "x" * 20}


BASE = [F(1, "funding_stage", "Series B"), F(2, "saas", "yes"), F(5, "employee_count", "120"),
        F(6, "customers", "enterprise customers incl. Acme"), F(7, "industry", "fintech"), F(8, "cloud", "AWS")]


def test_certified_company_loses_the_audit_points_and_says_why():
    r = scoring.score_facts(BASE + [A(3, "SOC 2 Type II certified", "Acme is SOC 2 Type II certified")], CFG)
    d = r["detail"]["audit_signals"]
    assert d["state"] == "negative" and d["points"] == 0 and "ALREADY COMPLIANT" in d["explanation"]
    assert r["compliance"]["status"] == "certified"
    assert r["score"] == 75.0  # funding 15 + saas 15 + employees 10 + customers 15 + industry 10 + cloud 10; audit earns 0


def test_company_that_needs_compliance_earns_full_audit_points():
    r = scoring.score_facts(BASE + [A(3, "SOC 2 in progress", "Acme is preparing for its first SOC 2 audit")], CFG)
    assert r["detail"]["audit_signals"]["points"] == 25 and r["score"] == 100 and r["classification"] == "qualified"
    assert r["compliance"]["status"] == "in_progress"


def test_hiring_only_evidence_earns_partial_points_and_two_hires_earn_full():
    one = scoring.score_facts(BASE + [A(3, "Compliance Manager", "Compliance Manager. View role")], CFG)
    two = scoring.score_facts(BASE + [A(3, "Compliance Manager", "Compliance Manager. View role"),
                                      A(4, "Security Engineer", "Security Engineer. Apply now")], CFG)
    assert one["detail"]["audit_signals"]["points"] == 15 and two["detail"]["audit_signals"]["points"] == 25


def test_certified_is_worse_than_unknown_which_is_not_penalised():
    certified = scoring.score_facts(BASE + [A(3, "SOC 2 Type II", "holds SOC 2 Type II")], CFG)
    unknown = scoring.score_facts(BASE, CFG)  # no audit evidence at all
    assert unknown["detail"]["audit_signals"]["state"] == "unverified"
    assert unknown["unverified_points"] >= 25 and certified["unverified_points"] < unknown["unverified_points"]


# ---- priority ----
@pytest.mark.parametrize("n,cls,comp,expected", [
    (4, "qualified", "certified", "Low"),            # already compliant: always low, however strong the rest
    (4, "qualified", "in_progress", "High"),
    (3, "qualified", "unknown", "High"),
    (2, "qualified", "in_progress", "High"),         # actively seeking compliance promotes a qualified Medium
    (2, "qualified", "unknown", "Medium"),
    (4, "further_investigation", "in_progress", "Medium"),  # High needs a qualified score
    (4, "further_investigation", "unknown", "Medium"),
    (1, "qualified", "in_progress", "Low"),          # too little evidence
    (0, "qualified", "unknown", "Low"),
])
def test_priority_rubric(n, cls, comp, expected):
    assert intent.decide_priority(n, cls, comp, CFG)[0] == expected


def test_certified_company_is_stopped_without_spending_an_ai_call(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    detail = scoring.score_facts(BASE + [A(3, "SOC 2 Type II certified", "Acme is SOC 2 Type II certified")], CFG)
    conn.execute("INSERT INTO companies (id, domain, name, status, classification, score_detail) VALUES (1,'acme.com','Acme','qualified','qualified',?)",
                 (json.dumps(detail),))
    conn.commit()
    monkeypatch.setattr(intent.llm, "generate", lambda *a, **k: pytest.fail("no AI call for an already-compliant company"))
    out = intent.run_company(conn, CFG, conn.execute("SELECT * FROM companies WHERE id=1").fetchone())
    row = conn.execute("SELECT status, stage, priority, stop_reason FROM companies WHERE id=1").fetchone()
    assert out["priority"] == "Low" and row["status"] == "stopped" and row["priority"] == "Low"
    assert "already compliant" in row["stop_reason"]


def test_only_real_compliance_vendors_count_as_a_competitor():
    ok = BASE + [A(3, "SOC 2 in progress", "preparing for its first SOC 2 audit")]
    assert scoring.score_facts(ok + [F(9, "competitor", "Vanta")], CFG)["classification"] == "rejected"
    assert scoring.score_facts(ok + [F(9, "competitor", "Drata (SOC 2 automation)")], CFG)["classification"] == "rejected"
    noise = scoring.score_facts(ok + [F(9, "competitor", "ouwba")], CFG)  # not a compliance vendor: ignored
    assert noise["classification"] == "qualified" and "competitor" not in noise["detail"]
