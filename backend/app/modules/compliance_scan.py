"""Establish a company's real compliance status from ITS OWN pages, in code (no AI guesswork).

Two steps, both only ever producing facts that are verbatim sentences on a page we fetched:
  1. recheck_first_party: certification claims the research found on the company's own site but could not
     verify (page undated -> STALE, text mismatch -> ASSERTED). A certification claim on a live first-party page is
     current as of the day we fetched it, so the 6-month window that suits job posts does not apply to it.
  2. scan: read the company's security / trust / compliance pages directly. Sentences naming SOC 2 / ISO 27001 /
     HIPAA... become CERTIFIED / IN PROGRESS facts. If real trust pages were read and claim nothing, record
     NONE FOUND (evidence of absence on those pages, clearly not proof). If we could not read them, record nothing,
     so the status stays UNKNOWN instead of being guessed.
"""
import re
from datetime import date, datetime, timezone
from urllib.parse import urlparse

from app import scrape, verify
from app.modules import compliance

PATHS = ["/security", "/trust", "/trust-center", "/compliance", "/security-and-compliance", "/legal/security", "/company/security", "/"]
SUBDOMAINS = ["trust", "security"]
FW = re.compile(r"soc\s?[12]\b|iso(?:/iec)?\s?27001|27701|42001|hipaa|gdpr|pci[\s-]?dss", re.I)
TRUST_PATH = re.compile(r"trust|security|compliance|legal", re.I)
FIRST_PERSON = re.compile(r"\b(we|we're|we've|our|us)\b", re.I)
MIN_TRUST_TEXT = 400  # a trust page with less readable text than this is probably script-rendered: do not conclude anything from it


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def is_first_party(url: str | None, domain: str) -> bool:
    host = (urlparse(url or "").netloc or "").lower().removeprefix("www.")
    return host == domain or host.endswith("." + domain)


def _sentences(text: str) -> list[str]:
    out = []
    for s in re.split(r"(?<=[.!?])\s+|\n+", text or ""):
        s = re.sub(r"\s+", " ", s).strip()
        if 12 <= len(s) <= 300:
            out.append(s)
    return out


def _claim(sentence: str):
    """('certified'|'in_progress', frameworks) for a sentence that states a compliance position, else None."""
    fw = compliance._frameworks(sentence)
    if not fw:
        return None
    if compliance.JOB.search(sentence):
        return None
    if compliance.CERT.search(sentence) and not compliance.PREP.search(sentence):
        return "certified", fw
    if compliance.PREP.search(sentence):
        return "in_progress", fw
    return None


def recheck_first_party(conn, cfg, company) -> int:
    """Re-verify unverified certification claims that sit on the company's own pages. Returns how many became VERIFIED."""
    fixed = 0
    rows = conn.execute("SELECT * FROM facts WHERE company_id=? AND criterion='audit_signals' AND status IN ('STALE','ASSERTED')",
                        (company["id"],)).fetchall()
    windows = {**cfg["recency_months"], "audit_signals": None}  # certification claims on a live first-party page are current
    for f in rows:
        if not is_first_party(f["source_url"], company["domain"]):
            continue
        fact = dict(f)
        if compliance.classify([dict(fact, status="VERIFIED")])["status"] != "certified":
            continue  # only certification claims get the exemption; hiring signals keep their recency window
        res = verify.verify_fact(fact, {f["source_url"]}, lambda u: scrape.fetch(conn, u), date.today(), windows,
                                 cfg["research"]["min_snippet_chars"])
        if res.status == verify.VERIFIED:
            conn.execute("UPDATE facts SET status='VERIFIED', status_reason=?, page_date=?, method=COALESCE(method,'compliance_recheck') WHERE id=?",
                         ("first-party page, live when fetched: a certification claim on the company's own site is current",
                          res.page_date.isoformat() if res.page_date else None, f["id"]))
            fixed += 1
    conn.commit()
    return fixed


def _candidate_urls(conn, domain: str) -> list[str]:
    urls = [f"https://{domain}{p}" for p in PATHS] + [f"https://{s}.{domain}" for s in SUBDOMAINS]
    home = scrape.fetch(conn, f"https://{domain}/")
    if home:  # follow the site's own footer links to trust/security pages
        for link in scrape.links(home):
            if is_first_party(link, domain) and TRUST_PATH.search(urlparse(link).path or "") and link not in urls and len(urls) < 14:
                urls.append(link.split("#")[0])
    seen, out = set(), []
    for u in urls:
        if u.rstrip("/") not in seen:
            seen.add(u.rstrip("/"))
            out.append(u)
    return out


def scan(conn, cfg, company) -> dict:
    """Read the company's own security/trust pages and record what they say. Returns a summary dict."""
    cid, domain = company["id"], company["domain"]
    conn.execute("DELETE FROM facts WHERE company_id=? AND method='compliance_scan'", (cid,))
    pages = []
    for u in _candidate_urls(conn, domain):
        p = scrape.fetch(conn, u)
        if p and is_first_party(p.final_url, domain):
            pages.append(p)
    claims, trust_pages_read = [], []
    for p in pages:
        trust = bool(TRUST_PATH.search(urlparse(p.final_url).path or "")) or urlparse(p.final_url).netloc.split(".")[0] in SUBDOMAINS
        if trust and len(p.text or p.raw_text or "") >= MIN_TRUST_TEXT:
            trust_pages_read.append(p.final_url)
        for s in _sentences(p.text or p.raw_text or ""):
            c = _claim(s)
            if not c:
                continue
            # on a trust/security page a bare list item ("SOC 2 Type II") is a claim; elsewhere the sentence must be about "us"
            if trust or FIRST_PERSON.search(s) or company["name"].lower() in s.lower():
                claims.append((c[0], c[1], s, p))
    saved = {"certified": 0, "in_progress": 0}
    windows = {**cfg["recency_months"], "audit_signals": None}
    seen = set()
    for kind, fw, sentence, page in sorted(claims, key=lambda c: c[0] != "certified"):
        key = (kind, tuple(fw))
        if key in seen or saved[kind] >= 2:
            continue
        seen.add(key)
        fact = {"criterion": "audit_signals", "value": f"{'CERTIFIED' if kind == 'certified' else 'IN PROGRESS'}: {', '.join(fw)}",
                "source_url": page.final_url, "snippet": sentence}
        res = verify.verify_fact(fact, {page.final_url}, lambda u: scrape.fetch(conn, u), date.today(), windows,
                                 cfg["research"]["min_snippet_chars"])
        if res.status != verify.VERIFIED:
            continue
        conn.execute("INSERT INTO facts (company_id, criterion, value, source_url, snippet, origin, status, status_reason, page_date,"
                     " retrieved_at, attempt, method) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                     (cid, "audit_signals", fact["value"], fact["source_url"], sentence, "scraper", "VERIFIED",
                      "compliance scan of the company's own page (verbatim sentence, live when fetched)",
                      res.page_date.isoformat() if res.page_date else None, _now(), 5, "compliance_scan"))
        saved[kind] += 1
    if not any(saved.values()) and trust_pages_read:
        conn.execute("INSERT INTO facts (company_id, criterion, value, source_url, snippet, origin, status, status_reason, retrieved_at,"
                     " attempt, method) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (cid, "audit_signals", "NONE FOUND: no SOC 2 / ISO 27001 / HIPAA claim on the company's trust pages", trust_pages_read[0],
                      None, "compliance_scan", "VERIFIED",
                      f"read {len(trust_pages_read)} security/trust page(s) and found no certification claims: {', '.join(trust_pages_read[:3])}",
                      _now(), 5, "compliance_scan"))
        saved["none_found"] = 1
    conn.commit()
    return {"pages_read": len(pages), "trust_pages": len(trust_pages_read), **saved}


def run(conn, cfg, company) -> dict:
    """Recheck first-party claims, then scan, but only when the status is not already settled."""
    facts = [dict(r) for r in conn.execute("SELECT * FROM facts WHERE company_id=? AND criterion='audit_signals'", (company["id"],))]
    fixed = recheck_first_party(conn, cfg, company)
    facts = [dict(r) for r in conn.execute("SELECT * FROM facts WHERE company_id=? AND criterion='audit_signals'", (company["id"],))]
    status = compliance.classify(facts)["status"]
    summary = {"rechecked_verified": fixed, "status_before_scan": status}
    if status in ("certified", "none_found"):
        return summary
    summary.update(scan(conn, cfg, company))
    return summary
