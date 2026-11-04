from datetime import date
from types import SimpleNamespace

from app import verify

TODAY = date(2026, 11, 3)
WINDOWS = {"funding_stage": 18, "audit_signals": 6, "saas": None}
URL = "https://news.example.com/acme-raises"
TEXT = "Acme raised a $25 million Series B led by Foo Capital. Acme is hiring a Head of GRC."


def page(text=TEXT, d=date(2026, 8, 1)):
    return SimpleNamespace(text=text, raw_text=text, date=d)


def check(fact, allowed=(URL,), pg=page(), windows=WINDOWS):
    base = {"criterion": "funding_stage", "value": "Series B", "source_url": URL,
            "snippet": "Acme raised a $25 million Series B"}
    base.update(fact)
    return verify.verify_fact(base, set(allowed), lambda u: pg, TODAY, windows)


def test_verified():
    r = check({})
    assert r.status == verify.VERIFIED and r.page_date == date(2026, 8, 1)


def test_url_not_from_grounding_is_asserted():
    assert check({}, allowed=("https://other.com/x",)).status == verify.ASSERTED


def test_url_match_ignores_www_and_trailing_slash():
    assert check({"source_url": "https://www.news.example.com/acme-raises/"}).status == verify.VERIFIED


def test_page_not_fetching_is_asserted():
    assert check({}, pg=None).status == verify.ASSERTED


def test_snippet_not_on_page_is_asserted():
    assert check({"snippet": "Acme raised a $90 million Series B"}).status == verify.ASSERTED


def test_snippet_match_is_whitespace_and_quote_tolerant():
    pg = page("Acme   raised\na $25 million Series B — big news")
    assert check({}, pg=pg).status == verify.VERIFIED


def test_old_page_is_stale():
    assert check({}, pg=page(d=date(2024, 1, 1))).status == verify.STALE


def test_undated_page_is_stale_when_window_applies():
    assert check({}, pg=page(d=None)).status == verify.STALE


def test_undated_page_ok_when_no_window():
    f = {"criterion": "saas", "value": "yes", "snippet": "Acme is hiring a Head of GRC"}
    assert check(f, pg=page(d=None)).status == verify.VERIFIED


def test_window_edges():
    # 18 months before 2026-11-03 is ~2025-05-03
    assert check({}, pg=page(d=date(2025, 6, 1))).status == verify.VERIFIED
    assert check({}, pg=page(d=date(2025, 4, 1))).status == verify.STALE


def test_audit_signal_uses_shorter_window():
    f = {"criterion": "audit_signals", "value": "Hiring Head of GRC",
         "snippet": "Acme is hiring a Head of GRC"}
    assert check(f, pg=page(d=date(2026, 7, 1))).status == verify.VERIFIED
    assert check(f, pg=page(d=date(2026, 1, 1))).status == verify.STALE


def test_number_in_value_must_be_in_snippet():
    assert check({"value": "Series B, $40M"}).status == verify.ASSERTED
    assert check({"value": "Series B, $25M"}).status == verify.VERIFIED


def test_missing_value_is_not_found():
    assert check({"value": None}).status == verify.NOT_FOUND


def test_missing_snippet_or_url_is_asserted():
    assert check({"snippet": None}).status == verify.ASSERTED
    assert check({"source_url": None}).status == verify.ASSERTED


def test_short_snippet_is_asserted():
    assert check({"snippet": "Series B"}).status == verify.ASSERTED


def test_future_dated_page_is_not_verified():
    assert check({}, pg=page(d=date(2027, 6, 1))).status == verify.STALE


def test_snippet_match_ignores_punctuation_and_markdown():
    pg = page("Acme raised **a $25 million** Series B — led by Foo Capital.")
    assert check({"snippet": "Acme raised a $25 million Series B, led by Foo Capital"}, pg=pg).status == verify.VERIFIED


def test_snippet_with_different_words_still_fails():
    assert check({"snippet": "Acme raised a $25 million Series C round"}).status == verify.ASSERTED
