"""Fact verification, done in code and never by the model.

A fact is VERIFIED only if:
  1. its URL came from Gemini's grounding metadata or our own scraper,
  2. the page fetches and contains the snippet,
  3. the value's numbers are backed by the snippet, and
  4. the page date is inside the recency window for that criterion
     (window None = no date needed, for static first-party facts).
Otherwise it is ASSERTED (unsupported) or STALE (supported but old/undated).
"""
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from typing import Callable
from urllib.parse import urlparse

VERIFIED = "VERIFIED"
ASSERTED = "ASSERTED"
STALE = "STALE"
NOT_FOUND = "NOT_FOUND"

_TRANSLATE = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"',
                            "–": "-", "—": "-", " ": " "})


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).translate(_TRANSLATE).casefold()
    s = s.strip().strip(".… ")
    return re.sub(r"\s+", " ", s)


def alnum(s: str) -> str:
    """Letters and digits only: ignores quotes, dashes, markdown and spacing, but every word must still match."""
    return re.sub(r"[^a-z0-9]", "", norm(s))


def norm_url(u: str) -> str:
    p = urlparse(u.strip())
    host = p.netloc.lower().removeprefix("www.")
    return f"{host}{p.path.rstrip('/')}" + (f"?{p.query}" if p.query else "")


def numbers(s: str) -> set[str]:
    return {m.replace(",", "") for m in re.findall(r"\d[\d,]*(?:\.\d+)?", s)}


def months_between(earlier: date, later: date) -> float:
    return (later - earlier).days / 30.44


@dataclass
class Result:
    status: str
    reason: str
    page_date: date | None = None


def verify_fact(
    fact: dict,
    allowed_urls: set[str],
    fetch: Callable[[str], object | None],
    today: date,
    recency_months: dict,
    min_snippet_chars: int = 15,
) -> Result:
    """`fetch(url)` returns an object with .text, .raw_text, .date or None."""
    value, url, snippet = fact.get("value"), fact.get("source_url"), fact.get("snippet")
    if value in (None, "", "NOT_FOUND"):
        return Result(NOT_FOUND, "no value")
    if not url or not snippet:
        return Result(ASSERTED, "missing source_url or snippet")
    if len(norm(snippet)) < min_snippet_chars:
        return Result(ASSERTED, "snippet too short to check")

    if norm_url(url) not in {norm_url(u) for u in allowed_urls}:
        return Result(ASSERTED, "url not from grounding metadata or scraper")

    page = fetch(url)
    if page is None:
        return Result(ASSERTED, "page did not fetch")
    want = norm(snippet)
    want_a = alnum(snippet)
    if (want not in norm(page.text) and want not in norm(page.raw_text)
            and want_a not in alnum(page.text) and want_a not in alnum(page.raw_text)):
        return Result(ASSERTED, "snippet not found on page")

    missing = {n for n in numbers(str(value)) if n not in numbers(snippet)}
    if missing:
        return Result(ASSERTED, f"value numbers not in snippet: {sorted(missing)}")

    window = recency_months.get(fact["criterion"])
    if window is None:
        return Result(VERIFIED, "snippet found; no date required", page.date)
    if page.date is None:
        return Result(STALE, "page has no date", None)
    age = months_between(page.date, today)
    if age > window or age < -1:
        return Result(STALE, f"page dated {page.date} outside {window}-month window", page.date)
    return Result(VERIFIED, f"snippet found; page dated {page.date}", page.date)
