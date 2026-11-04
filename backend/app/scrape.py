"""Polite page fetching: robots.txt, caching, text and date extraction."""
import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
import trafilatura

from app import cache

UA = "SprintoOutboundBot/0.1"
MAX_HTML = 2_000_000


@dataclass
class Page:
    url: str
    final_url: str
    text: str          # trafilatura main-content text
    raw_text: str      # tag-stripped full text (fallback for matching)
    html: str
    date: date | None


def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": UA}, timeout=15, follow_redirects=True)


def robots_allowed(conn: sqlite3.Connection, url: str) -> bool:
    p = urlparse(url)
    robots_url = f"{p.scheme}://{p.netloc}/robots.txt"

    def fetch_robots():
        try:
            with _client() as c:
                r = c.get(robots_url)
            return {"status": r.status_code, "body": r.text[:200_000] if r.status_code == 200 else ""}
        except httpx.HTTPError:
            return {"status": 0, "body": ""}

    res = cache.get_or_set(conn, "robots", robots_url, fetch_robots)
    if res["status"] != 200:
        return True  # no robots.txt (or unreachable): nothing forbids us
    rp = RobotFileParser()
    rp.parse(res["body"].splitlines())
    return rp.can_fetch(UA, url)


def _strip_tags(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    return re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", html))


def _find_date(html: str) -> date | None:
    try:
        from htmldate import find_date

        s = find_date(html, extensive_search=True, original_date=True)
    except Exception:
        return None
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def fetch(conn: sqlite3.Connection, url: str) -> Page | None:
    """Fetch a page (cached, robots-respecting). None if disallowed, unreachable or non-200."""
    if urlparse(url).scheme not in ("http", "https"):
        return None

    def do():
        # Resolving an arbitrary redirect is a fetch too, so check robots on the requested URL.
        if not robots_allowed(conn, url):
            return {"ok": False, "reason": "robots"}
        try:
            with _client() as c:
                r = c.get(url)
        except httpx.HTTPError as e:
            return {"ok": False, "reason": f"error:{type(e).__name__}"}
        ctype = r.headers.get("content-type", "")
        if r.status_code != 200 or "html" not in ctype and "text" not in ctype:
            return {"ok": False, "reason": f"status:{r.status_code}"}
        try:
            html = r.content.decode("utf-8")  # most sites; r.text can guess wrong and garble symbols like the euro sign
        except UnicodeDecodeError:
            html = r.text
        return {"ok": True, "final_url": str(r.url), "html": html[:MAX_HTML]}

    res = cache.get_or_set(conn, "page", url, do)
    if not res["ok"]:
        return None
    html = res["html"]
    text = trafilatura.extract(html, favor_recall=True) or ""
    return Page(
        url=url,
        final_url=res["final_url"],
        text=text,
        raw_text=_strip_tags(html),
        html=html,
        date=_find_date(html),
    )


def resolve(conn: sqlite3.Connection, url: str) -> str:
    """Follow redirects (Gemini grounding URIs are redirectors) and return the final URL."""
    from urllib.parse import urljoin

    def do():
        cur = url
        # Only unwrap Google's redirector; the real target is fetched later via fetch(),
        # which checks robots.txt.
        for _ in range(5):
            if "vertexaisearch.cloud.google.com" not in urlparse(cur).netloc:
                break
            try:
                with httpx.Client(headers={"User-Agent": UA}, timeout=15) as c:
                    r = c.get(cur)
            except httpx.HTTPError:
                break
            loc = r.headers.get("location")
            if r.status_code in (301, 302, 303, 307, 308) and loc:
                cur = urljoin(cur, loc)
            else:
                break
        return cur

    return cache.get_or_set(conn, "resolve", url, do)


def links(page: Page) -> list[str]:
    from urllib.parse import urljoin

    out = []
    for m in re.finditer(r'href=["\']([^"\']+)["\']', page.html):
        out.append(urljoin(page.final_url, m.group(1)))
    return out
