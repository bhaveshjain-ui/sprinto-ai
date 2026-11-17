import json
import os

import pytest

from app import db
from app.config import load_config
from app.modules import contacts, delivery, drafting, intent, research, scoring

CFG = load_config()


def F(id, crit, value, status="VERIFIED", conflict=0, snippet="x" * 20):
    return {"id": id, "criterion": crit, "value": value, "status": status, "conflict": conflict, "snippet": snippet}


GOOD = [F(1, "funding_stage", "Series B"), F(2, "saas", "yes"), F(3, "audit_signals", "Hiring GRC lead"),
        F(4, "audit_signals", "SOC 2 in progress"), F(5, "employee_count", "120"),
        F(6, "customers", "enterprise customers incl. Acme"), F(7, "industry", "fintech"), F(8, "cloud", "AWS")]


# ---- scoring ----
def test_full_score_qualified():
    r = scoring.score_facts(GOOD, CFG)
    assert r["score"] == 100 and r["classification"] == "qualified"


def test_unverified_never_positive_and_missing_does_not_reject():
    only = [f for f in GOOD if f["criterion"] in ("funding_stage", "saas")]
    r = scoring.score_facts(only, CFG)
    assert r["score"] == 30 and r["classification"] == "further_investigation"
    assert r["detail"]["cloud"]["state"] == "unverified"


def test_asserted_facts_earn_nothing():
    facts = [dict(f, status="ASSERTED") for f in GOOD]
    r = scoring.score_facts(facts, CFG)
    assert r["score"] == 0


def test_verified_not_saas_rejects():
    facts = [f if f["criterion"] != "saas" else F(2, "saas", "no") for f in GOOD]
    assert scoring.score_facts(facts, CFG)["classification"] == "rejected"


def test_competitor_rejects():
    r = scoring.score_facts(GOOD + [F(9, "competitor", "Vanta")], CFG)
    assert r["classification"] == "rejected" and "Vanta" in r["reason"]


def test_conflict_earns_nothing():
    facts = [dict(f, conflict=1) if f["criterion"] == "employee_count" else f for f in GOOD]
    r = scoring.score_facts(facts, CFG)
    assert r["detail"]["employee_count"]["state"] == "conflict" and r["score"] == 90


def test_verified_wrong_stage_is_negative_not_unverified():
    facts = [F(1, "funding_stage", "Series D")] + GOOD[1:]
    assert scoring.score_facts(facts, CFG)["detail"]["funding_stage"]["state"] == "negative"


def test_bands():
    mid = [f for f in GOOD if f["criterion"] != "cloud" and f["criterion"] != "industry"]
    r = scoring.score_facts(mid, CFG)  # 80 -> qualified
    assert r["classification"] == "qualified"
    low = [f for f in GOOD if f["criterion"] in ("funding_stage", "saas", "audit_signals")]
    assert scoring.score_facts(low, CFG)["score"] == 55
    assert scoring.score_facts(low, CFG)["classification"] == "further_investigation"


# ---- contacts ----
def H(first, pos, conf=95):
    return {"first_name": first, "last_name": "Doe", "position": pos, "value": f"{first}@x.com", "confidence": conf}


def test_contact_priority_by_size():
    cands = [H("Ann", "CISO"), H("Bob", "Co-Founder"), H("Cy", "CTO"), H("Di", "Marketing Manager")]
    assert contacts.rank(cands, 20, 80)[0]["first_name"] == "Bob"
    assert contacts.rank(cands, 100, 80)[0]["first_name"] == "Cy"
    assert contacts.rank(cands, 500, 80)[0]["first_name"] == "Ann"
    assert all(c["first_name"] != "Di" for c in contacts.rank(cands, 20, 80))


def test_contact_confidence_and_name_required():
    assert contacts.rank([H("Ann", "CISO", 50)], 100, 80) == []
    assert contacts.rank([{**H("Ann", "CISO"), "last_name": None}], 100, 80) == []


# ---- drafting validator ----
VER = {1: {"value": "Series B, $25M", "snippet": "Acme raised a $25 million Series B led by Foo"},
       2: {"value": "SOC 2 in progress", "snippet": "Our trust page says SOC 2 Type I in progress"}}
ALLOWED = {"acme", "dana", "doe"}


def mk(**over):
    d = {"subject": "Acme's Series B and SOC 2", "sentences": [
        {"kind": "trigger", "text": "Congrats on the $25 million Series B.", "fact_ids": [1]},
        {"kind": "pressure", "text": "Your trust page shows SOC 2 Type I in progress, which enterprise buyers check.", "fact_ids": [2]},
        {"kind": "offer", "text": "Sprinto automates evidence collection for SOC 2.", "fact_ids": []},
        {"kind": "ask", "text": "Open to a 15 minute chat?", "fact_ids": []}]}
    d.update(over)
    return d


def test_valid_draft_passes():
    assert drafting.validate(mk(), VER, CFG, ALLOWED) == []


def test_uncited_number_fails():
    d = mk()
    d["sentences"][0]["text"] = "Congrats on the $40 million Series B."
    assert any("40" in e for e in drafting.validate(d, VER, CFG, ALLOWED))


def test_unverified_fact_id_fails():
    d = mk()
    d["sentences"][0]["fact_ids"] = [99]
    assert drafting.validate(d, VER, CFG, ALLOWED)


def test_factual_sentence_needs_citation():
    d = mk()
    d["sentences"][1]["fact_ids"] = []
    assert any("cites no VERIFIED" in e for e in drafting.validate(d, VER, CFG, ALLOWED))


def test_invented_name_fails():
    d = mk()
    d["sentences"][0]["text"] = "Congrats on the $25 million Series B led by Zorgon."
    assert any("zorgon" in e for e in drafting.validate(d, VER, CFG, ALLOWED))


def test_length_limits():
    d = mk(subject="one two three four five six seven eight nine")
    assert any("subject" in e for e in drafting.validate(d, VER, CFG, ALLOWED))
    d = mk()
    d["sentences"][2]["text"] = " ".join(["Sprinto helps"] * 70)
    assert any("words" in e for e in drafting.validate(d, VER, CFG, ALLOWED))


def test_no_trigger_fails():
    d = mk()
    d["sentences"] = d["sentences"][1:]
    assert any("trigger" in e for e in drafting.validate(d, VER, CFG, ALLOWED))


# ---- delivery ----
@pytest.fixture
def c(tmp_path, monkeypatch):
    monkeypatch.setenv("MY_EMAIL", "me@example.com")
    monkeypatch.setenv("SENDER_EMAIL", "onboarding@resend.dev")
    conn = db.connect(tmp_path / "t.db")
    conn.execute("INSERT INTO companies (id, domain, name) VALUES (1,'acme.com','Acme')")
    conn.execute("INSERT INTO facts (company_id, criterion, value, snippet, status) VALUES "
                 "(1,'funding_stage','Series B, $25M','Acme raised a $25 million Series B','VERIFIED')")
    conn.execute("INSERT INTO contacts (id, company_id, first_name, last_name, email, position, selected)"
                 " VALUES (1,1,'Dana','Doe','dana@acme.com','CTO',1)")
    conn.execute("INSERT INTO drafts (id, company_id, contact_id, subject, body) VALUES (1,1,1,'Hello','Hi Dana, body')")
    conn.commit()
    return conn


class Sender:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def __call__(self, payload):
        self.calls.append(payload)
        if self.fail:
            raise RuntimeError("resend down")
        return "rid_1"


def test_send_refuses_unapproved(c):
    s = Sender()
    with pytest.raises(delivery.DeliveryError):
        delivery.send(c, 1, s)
    assert s.calls == []


def test_send_refuses_rejected(c):
    delivery.reject(c, 1)
    with pytest.raises(delivery.DeliveryError):
        delivery.send(c, 1, Sender())


def test_send_goes_only_to_my_email_and_logs(c):
    delivery.approve(c, 1)
    s = Sender()
    r = delivery.send(c, 1, s)
    assert r["status"] == "sent" and s.calls[0]["to"] == ["me@example.com"]
    assert "Dana" in s.calls[0]["text"]
    assert "dana@acme.com" not in s.calls[0]["to"]
    row = c.execute("SELECT * FROM sends").fetchone()
    assert row["resend_id"] == "rid_1" and row["status"] == "sent"


def test_no_duplicate_send(c):
    delivery.approve(c, 1)
    s = Sender()
    delivery.send(c, 1, s)
    with pytest.raises(delivery.DeliveryError):
        delivery.send(c, 1, s)
    assert len(s.calls) == 1


def test_failed_send_recorded_and_retryable(c):
    delivery.approve(c, 1)
    assert delivery.send(c, 1, Sender(fail=True))["status"] == "failed"
    assert c.execute("SELECT status FROM drafts").fetchone()[0] == "approved"
    assert delivery.send(c, 1, Sender())["status"] == "sent"


def test_edit_resets_approval(c):
    delivery.approve(c, 1)
    assert delivery.edit(c, CFG, 1, "Hello again", "Hi Dana, Acme raised a $25 million Series B") == []
    d = c.execute("SELECT * FROM drafts").fetchone()
    assert d["status"] == "pending" and d["approved_hash"] is None
    with pytest.raises(delivery.DeliveryError):
        delivery.send(c, 1, Sender())


def test_edit_revalidates(c):
    errs = delivery.edit(c, CFG, 1, "Hello", "Hi Dana, you raised $99 million")
    assert errs and c.execute("SELECT body FROM drafts").fetchone()[0] == "Hi Dana, body"


def test_content_change_after_approval_blocks_send(c):
    delivery.approve(c, 1)
    c.execute("UPDATE drafts SET body='tampered' WHERE id=1")
    c.commit()
    with pytest.raises(delivery.DeliveryError):
        delivery.send(c, 1, Sender())


def test_dry_run_does_not_call_resend(c):
    db.set_setting(c, "dry_run", "true")
    delivery.approve(c, 1)
    s = Sender()
    assert delivery.send(c, 1, s)["status"] == "dry_run" and s.calls == []
    db.set_setting(c, "dry_run", "false")
    assert delivery.send(c, 1, s)["status"] == "sent"


# ---- research ladder: never more than 4 attempts per criterion ----
def test_research_attempt_limit(c, monkeypatch):
    calls = []

    def fake_generate(conn, cfg, prompt, grounded=False, **v):
        calls.append(prompt)
        return [], set()

    monkeypatch.setattr(research.llm, "generate", fake_generate)
    monkeypatch.setattr(research, "hunter_enrich", lambda *a, **k: [])
    monkeypatch.setattr(research.scrape, "fetch", lambda conn, u: None)
    co = c.execute("SELECT * FROM companies WHERE id=1").fetchone()
    research.run_company(c, CFG, co)
    attempts = c.execute("SELECT criterion, MAX(attempt) m FROM research_log GROUP BY criterion").fetchall()
    assert all(a["m"] <= 4 for a in attempts) and len(attempts) >= 7
    assert calls.count("research_facts") == 1 and calls.count("research_followup") == 2
    nf = c.execute("SELECT COUNT(*) FROM facts WHERE status='NOT_FOUND'").fetchone()[0]
    assert nf == 8  # all criteria UNVERIFIED, none guessed


def test_research_stops_when_verified(c, monkeypatch):
    def fake_generate(conn, cfg, prompt, grounded=False, **v):
        return [], set()

    monkeypatch.setattr(research.llm, "generate", fake_generate)
    monkeypatch.setattr(research, "hunter_enrich", lambda *a, **k: [])
    monkeypatch.setattr(research.scrape, "fetch", lambda conn, u: None)
    monkeypatch.setattr(research, "_verified", lambda conn, cid: set(research.CRITERIA))
    co = c.execute("SELECT * FROM companies WHERE id=1").fetchone()
    research.run_company(c, CFG, co)
    assert c.execute("SELECT COUNT(*) FROM research_log").fetchone()[0] == 0


def test_prompt_loader_accepts_name_variable():
    from app import llm
    assert "Acme" in llm.load_prompt("research_facts", name="Acme", domain="acme.com", criteria="saas")


def test_postgres_translation():
    t, ret = db.translate("INSERT OR IGNORE INTO companies (domain, name) VALUES (?,?)", True)
    assert t.endswith("ON CONFLICT DO NOTHING RETURNING id") and "%s" in t and ret
    t, _ = db.translate("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", True)
    assert "ON CONFLICT (key) DO UPDATE" in t
    t, _ = db.translate("UPDATE drafts SET updated_at=datetime('now') WHERE id=?", True)
    assert "datetime" not in t and "to_char(now()" in t
    assert db.translate("BEGIN IMMEDIATE", False)[0] == "BEGIN"
    t, _ = db.translate("SELECT 1 FROM cache WHERE created_at >= datetime('now', ?)", True)
    assert "%s::interval" in t
    assert "BIGSERIAL" in db.pg_schema() and "AUTOINCREMENT" not in db.pg_schema()


# ---- Hunter company-enrichment gap fill ----
ENRICH = {"data": {"indexedAt": "2026-11-16", "metrics": {"employeesCount": 140, "employees": "51-250"},
                   "tech": ["react-js", "amazon-web-services"], "tags": ["software", "recruiting software", "ai", "x"]}}


def _enrich(c, monkeypatch, payload=ENRICH):
    from app.modules import contacts

    monkeypatch.setenv("HUNTER_API_KEY", "test-key")
    monkeypatch.setattr(contacts, "_get", lambda conn, path, params: payload)
    return research.hunter_enrich(c, CFG, c.execute("SELECT * FROM companies WHERE id=1").fetchone())


def test_hunter_enrich_fills_only_what_the_record_supports(c, monkeypatch):
    filled = _enrich(c, monkeypatch)
    assert set(filled) == {"employee_count", "cloud", "industry"}
    rows = {r["criterion"]: r for r in c.execute("SELECT * FROM facts WHERE method='hunter_enrichment'")}
    assert rows["employee_count"]["value"].startswith("140 employees") and rows["employee_count"]["status"] == "VERIFIED"
    assert rows["cloud"]["value"] == "AWS" and "amazon-web-services" in rows["cloud"]["snippet"]
    assert rows["industry"]["value"] == "software, recruiting software, ai"
    assert all(r["origin"] == "hunter_api" and r["attempt"] == 5 and r["page_date"] == "2026-11-16" for r in rows.values())
    assert "domain=acme.com" in rows["cloud"]["source_url"] and "api_key" not in rows["cloud"]["source_url"]


def test_hunter_enrich_never_guesses(c, monkeypatch):
    # no headcount, no cloud tech, no tags -> nothing is invented
    assert _enrich(c, monkeypatch, {"data": {"metrics": {}, "tech": ["react-js"], "tags": []}}) == []
    assert c.execute("SELECT COUNT(*) FROM facts WHERE method='hunter_enrichment'").fetchone()[0] == 0


def test_hunter_enrich_skips_already_verified_and_missing_key(c, monkeypatch):
    c.execute("INSERT INTO facts (company_id, criterion, value, status) VALUES (1,'employee_count','120','VERIFIED')")
    c.execute("INSERT INTO facts (company_id, criterion, value, status) VALUES (1,'cloud','GCP','VERIFIED')")
    c.execute("INSERT INTO facts (company_id, criterion, value, status) VALUES (1,'industry','fintech','VERIFIED')")
    c.commit()
    assert _enrich(c, monkeypatch) == []
    monkeypatch.delenv("HUNTER_API_KEY")
    from app.modules import contacts

    monkeypatch.setattr(contacts, "_get", lambda *a, **k: pytest.fail("must not call Hunter without a key"))
    assert research.hunter_enrich(c, CFG, c.execute("SELECT * FROM companies WHERE id=1").fetchone()) == []


def test_hunter_enrich_survives_api_failure(c, monkeypatch):
    from app.modules import contacts

    monkeypatch.setenv("HUNTER_API_KEY", "test-key")

    def boom(*a, **k):
        raise RuntimeError("Hunter companies/find failed (404)")

    monkeypatch.setattr(contacts, "_get", boom)
    assert research.hunter_enrich(c, CFG, c.execute("SELECT * FROM companies WHERE id=1").fetchone()) == []


def test_employee_range_scores_as_midpoint():
    assert scoring._num("51-250") == 150 and scoring._num("11 - 50") == 30
    assert scoring._num("140 employees (Hunter estimate, range 51-250)") == 140
