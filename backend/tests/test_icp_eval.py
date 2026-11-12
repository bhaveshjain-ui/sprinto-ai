"""Tests of the ICP eval itself: a good report passes every case, and each deliberate defect is caught by the right case."""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "evals"))
import run_icp_eval as ev  # noqa: E402


def results_for(report, sources=None):
    return {r["id"]: r for r in ev.run_cases(report, ev.GOOD_SOURCES if sources is None else sources)}


def broken(mutate):
    r = copy.deepcopy(ev.GOOD_REPORT)
    mutate(r)
    return r


def test_cases_have_the_four_parts_and_valid_severity():
    for c in ev.load_cases():
        for part in ("input", "expected_behaviour", "assertion", "severity"):
            assert c.get(part), (c["id"], part)
        assert c["severity"] in ("critical", "major", "minor")
        assert c["check"] in ev.CHECKS, c["id"]
    ids = [c["id"] for c in ev.load_cases()]
    assert len(ids) == len(set(ids))


def test_good_report_passes_every_case():
    res = results_for(ev.GOOD_REPORT)
    failed = {k: v["detail"] for k, v in res.items() if not v["passed"]}
    assert not failed, failed


def _scrub(report, words):
    """Remove every mention of the given words from all text in the report, in place."""
    import json

    raw = json.dumps(report)
    for w in words:
        raw = raw.replace(w, "")
    report.clear()
    report.update(json.loads(raw))


# (defect, expected failing case id)
DEFECTS = [
    ("missing summary", lambda r: r.update(summary=""), "ICP-01"),
    ("summary one sentence", lambda r: r.update(summary="Series A SaaS compliance."), "ICP-02"),
    ("only two industries", lambda r: r.update(industries=r["industries"][:2]), "ICP-03"),
    ("series C missing", lambda r: r.update(funding_stages="Series A and Series B companies are the sweet spot."), "ICP-04"),
    ("no ISO 27001 anywhere", lambda r: _scrub(r, ["ISO/IEC 27001", "ISO 27001", "27001"]), "ICP-05"),
    ("no enterprise signals", lambda r: r.update(enterprise_expansion_signals=["Opening a new office"]), "ICP-06"),
    ("triggers unrelated to customers/audits", lambda r: r.update(compliance_triggers=["New logo", "Rebrand"]), "ICP-07"),
    ("signals not verifiable", lambda r: r.update(buying_signals=[{"signal": "Good vibes", "why_it_matters": "Mood"}] * 3), "ICP-08"),
    ("invented statistic", lambda r: r.update(summary=r["summary"] + " 73% of such firms fail their first audit."), "ICP-10"),
    ("stale year", lambda r: r.update(summary=r["summary"] + " This began in 2019."), "ICP-11"),
    ("too few queries", lambda r: r.update(search_queries=["SOC 2 saas", "ISO 27001 saas"]), "ICP-12"),
    ("duplicate queries", lambda r: r.update(search_queries=["Series A SOC 2 SaaS"] * 4), "ICP-12"),
]


@pytest.mark.parametrize("name,mutate,case_id", DEFECTS, ids=[d[0] for d in DEFECTS])
def test_each_defect_is_caught(name, mutate, case_id):
    res = results_for(broken(mutate))
    assert not res[case_id]["passed"], f"{case_id} should fail for: {name}"


def test_sources_defects_are_caught():
    assert not results_for(ev.GOOD_REPORT, [])["ICP-09"]["passed"]
    assert not results_for(ev.GOOD_REPORT, ["https://a.com/x", "https://a.com/y", "https://a.com/z"])["ICP-09"]["passed"]  # one host
    only_redirects = ["https://vertexaisearch.cloud.google.com/grounding-api-redirect/%d" % i for i in range(5)]
    assert not results_for(ev.GOOD_REPORT, only_redirects)["ICP-09"]["passed"]


def test_missing_report_fails_report_cases_but_not_offline_cases():
    res = {r["id"]: r for r in ev.run_cases(None, [])}
    assert not res["ICP-01"]["passed"] and "no ICP report" in res["ICP-01"]["detail"]
    assert all(res[i]["passed"] for i in ("ICP-14", "ICP-15", "ICP-16", "ICP-17", "ICP-18"))


def test_stage_validation_rejects_bad_shapes():
    from app.modules import icp

    assert icp.validate(ev.GOOD_REPORT) == []
    assert icp.validate("text") and icp.validate({}) and icp.validate(None)
    assert any("industries" in e for e in icp.validate({**ev.GOOD_REPORT, "industries": ["not an object"]}))
