"""Compliance scan: status comes from sentences on the company's own pages; nothing is guessed."""
from datetime import date

import pytest

from app import db
from app.config import load_config
from app.modules import compliance, compliance_scan as cs, scoring
from app.scrape import Page

CFG = load_config()
LONG = ("Our platform helps teams plan work, track projects and collaborate across departments with simple dashboards and reports. " * 6)


def page(url, text, d=None):
    return Page(url=url, final_url=url, text=text, raw_text=text, html=text, date=d)


@pytest.fixture
def env(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    conn.execute("INSERT INTO companies (id, domain, name) VALUES (1,'acme.com','Acme')")
    conn.commit()
    return conn, monkeypatch


def serve(monkeypatch, pages: dict):
    monkeypatch.setattr(cs.scrape, "fetch", lambda conn, url: pages.get(url.rstrip("/")) or pages.get(url))


def co(conn):
    return conn.execute("SELECT * FROM companies WHERE id=1").fetchone()


def audit(conn):
    return [dict(r) for r in conn.execute("SELECT * FROM facts WHERE company_id=1 AND criterion='audit_signals'")]


def test_certification_on_the_security_page_is_recorded_verbatim_and_classified(env):
    conn, mp = env
    sentence = "Acme is SOC 2 Type II certified and ISO 27001 certified, audited annually by an independent firm."
    serve(mp, {"https://acme.com/security": page("https://acme.com/security", LONG + sentence)})
    out = cs.scan(conn, CFG, co(conn))
    facts = audit(conn)
    assert out["certified"] == 1 and facts[0]["status"] == "VERIFIED" and facts[0]["value"].startswith("CERTIFIED")
    assert facts[0]["snippet"] == sentence and facts[0]["source_url"] == "https://acme.com/security"
    res = compliance.classify(facts)
    assert res["status"] == "certified" and {"SOC 2", "ISO 27001"} <= set(res["frameworks"])


def test_preparing_for_an_audit_is_in_progress(env):
    conn, mp = env
    serve(mp, {"https://acme.com/trust": page("https://acme.com/trust", LONG + "We are preparing for our first SOC 2 audit this year.")})
    cs.scan(conn, CFG, co(conn))
    assert compliance.classify(audit(conn))["status"] == "in_progress"


def test_trust_pages_that_claim_nothing_give_none_found_not_unknown(env):
    conn, mp = env
    serve(mp, {"https://acme.com/security": page("https://acme.com/security", LONG)})
    out = cs.scan(conn, CFG, co(conn))
    facts = audit(conn)
    assert out["none_found"] == 1 and facts[0]["value"].startswith("NONE FOUND") and facts[0]["snippet"] is None
    res = compliance.classify(facts)
    assert res["status"] == "none_found" and "trust" in res["reason"]


def test_none_found_scores_partial_points_never_full_and_never_negative(env):
    conn, mp = env
    serve(mp, {"https://acme.com/security": page("https://acme.com/security", LONG)})
    cs.scan(conn, CFG, co(conn))
    base = [{"id": 1, "criterion": c, "value": v, "status": "VERIFIED", "conflict": 0, "snippet": "x" * 20}
            for c, v in [("funding_stage", "Series B"), ("saas", "yes"), ("employee_count", "120"), ("customers", "enterprise customers"),
                         ("industry", "fintech"), ("cloud", "AWS")]]
    r = scoring.score_facts(base + audit(conn), CFG)
    d = r["detail"]["audit_signals"]
    assert d["state"] == "positive" and d["points"] == 15 and "NOT CERTIFIED" in d["explanation"] and r["compliance"]["status"] == "none_found"


def test_a_page_we_could_not_read_leaves_the_status_unknown(env):
    conn, mp = env
    serve(mp, {"https://acme.com/security": page("https://acme.com/security", "Loading...")})  # script-rendered: no real text
    out = cs.scan(conn, CFG, co(conn))
    assert out["trust_pages"] == 0 and audit(conn) == [] and compliance.classify(audit(conn))["status"] == "unknown"
    serve(mp, {})  # nothing reachable at all
    assert cs.scan(conn, CFG, co(conn))["pages_read"] == 0 and audit(conn) == []


def test_homepage_marketing_about_other_peoples_compliance_is_ignored(env):
    conn, mp = env
    serve(mp, {"https://acme.com": page("https://acme.com", LONG + "Helping teams get SOC 2 compliant faster than ever before.")})
    cs.scan(conn, CFG, co(conn))
    assert audit(conn) == []  # no trust page read, and the sentence is not about "us"


def test_a_first_person_claim_on_the_homepage_counts(env):
    conn, mp = env
    serve(mp, {"https://acme.com": page("https://acme.com", LONG + "We are SOC 2 Type II certified and take security seriously.")})
    cs.scan(conn, CFG, co(conn))
    assert compliance.classify(audit(conn))["status"] == "certified"


def test_a_hiring_sentence_is_not_a_certification(env):
    conn, mp = env
    serve(mp, {"https://acme.com/security": page("https://acme.com/security", LONG + "We're hiring a GRC lead to build our SOC 2 program.")})
    cs.scan(conn, CFG, co(conn))
    assert compliance.classify(audit(conn))["status"] != "certified"


def test_rescan_replaces_the_old_scan_result(env):
    conn, mp = env
    serve(mp, {"https://acme.com/security": page("https://acme.com/security", LONG)})
    cs.scan(conn, CFG, co(conn))
    serve(mp, {"https://acme.com/security": page("https://acme.com/security", LONG + "Acme is ISO 27001 certified.")})
    cs.scan(conn, CFG, co(conn))
    st = [f["value"] for f in audit(conn)]
    assert len(st) == 1 and st[0].startswith("CERTIFIED") and compliance.classify(audit(conn))["status"] == "certified"


# ---- recheck of claims the research already found but could not verify ----
def stale_fact(conn, url, value, snippet, status="STALE"):
    conn.execute("INSERT INTO facts (company_id, criterion, value, source_url, snippet, origin, status, status_reason) VALUES (1,'audit_signals',?,?,?,?,?, 'page dated 2025-01-01 outside 6-month window')",
                 (value, url, snippet, "grounding", status))
    conn.commit()


def test_stale_first_party_certification_claim_becomes_verified(env):
    conn, mp = env
    snippet = "Acme maintains SOC 2 Type II and ISO 27001 certifications."
    stale_fact(conn, "https://acme.com/security", "SOC 2 Type II, ISO 27001", snippet)
    serve(mp, {"https://acme.com/security": page("https://acme.com/security", LONG + snippet, d=date(2025, 1, 1))})
    assert cs.recheck_first_party(conn, CFG, co(conn)) == 1
    f = audit(conn)[0]
    assert f["status"] == "VERIFIED" and "first-party" in f["status_reason"] and compliance.classify(audit(conn))["status"] == "certified"


def test_recheck_leaves_third_party_and_hiring_claims_alone(env):
    conn, mp = env
    snippet = "Acme maintains SOC 2 Type II certification."
    stale_fact(conn, "https://blog.example.org/acme", "SOC 2 Type II", snippet)                      # third party
    job = "We're hiring a Compliance Manager to own our SOC 2 programme."
    stale_fact(conn, "https://acme.com/careers/compliance-manager", "Compliance Manager", job)       # hiring keeps its window
    serve(mp, {"https://blog.example.org/acme": page("https://blog.example.org/acme", snippet),
               "https://acme.com/careers/compliance-manager": page("https://acme.com/careers/compliance-manager", job)})
    assert cs.recheck_first_party(conn, CFG, co(conn)) == 0
    assert {f["status"] for f in audit(conn)} == {"STALE"}


def test_recheck_does_not_verify_a_claim_that_is_not_on_the_page(env):
    conn, mp = env
    stale_fact(conn, "https://acme.com/security", "SOC 2 Type II", "Acme is SOC 2 Type II certified.", status="ASSERTED")
    serve(mp, {"https://acme.com/security": page("https://acme.com/security", LONG)})
    assert cs.recheck_first_party(conn, CFG, co(conn)) == 0 and audit(conn)[0]["status"] == "ASSERTED"


def test_run_skips_the_scan_when_the_status_is_already_certified(env):
    conn, mp = env
    conn.execute("INSERT INTO facts (company_id, criterion, value, snippet, status) VALUES (1,'audit_signals','SOC 2 Type II certified','Acme is SOC 2 Type II certified','VERIFIED')")
    conn.commit()
    mp.setattr(cs.scrape, "fetch", lambda *a, **k: pytest.fail("no fetching when the status is already settled"))
    assert cs.run(conn, CFG, co(conn))["status_before_scan"] == "certified"
