"""Stage 3: research ladder. Max 4 attempts per missing data point, in this order:
 1 Google Search (grounded)   2 official website scrape   3 credible news/announcements   4 one targeted retry
Stops for a criterion as soon as it has a VERIFIED fact."""
import json
from datetime import date, datetime, timezone

from app import llm, scrape, verify
from app.config import ALL_CRITERIA, CRITERIA, EXTRA_CRITERIA
from app.verify import norm

SINGLE_VALUED = ("funding_stage", "employee_count", "saas")

ATTEMPT_3 = ("Look ONLY at credible news articles, press releases, announcements and industry reports "
             "(TechCrunch, company blog, press wires, analyst reports). Ignore the company's own site.")
ATTEMPT_4 = ("Final targeted attempt: use alternative keywords and different sources than the obvious ones "
             "(e.g. job boards, LinkedIn company posts, Crunchbase/PitchBook summaries, conference talks, "
             "customer case studies, trust.{domain}).")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _entity_ok(conn, company, url: str) -> bool:
    """The page must actually be about this company (name or domain on the page)."""
    page = scrape.fetch(conn, url)
    if page is None:
        return False
    hay = norm(page.text + " " + page.raw_text[:20000])
    return norm(company["name"]) in hay or company["domain"].split(".")[0] in hay


def _check(conn, cfg, company, facts, allowed, origin, attempt, method) -> None:
    rc = cfg["research"]
    for f in facts if isinstance(facts, list) else []:
        if not isinstance(f, dict) or f.get("criterion") not in ALL_CRITERIA:
            continue
        res = verify.verify_fact(f, allowed, lambda u: scrape.fetch(conn, u), date.today(),
                                 cfg["recency_months"], rc["min_snippet_chars"])
        status, reason = res.status, res.reason
        same_site = company["domain"] in (f.get("source_url") or "")
        if status == verify.VERIFIED and not same_site and not _entity_ok(conn, company, f["source_url"]):
            status, reason = verify.ASSERTED, "page does not mention this company (wrong-entity risk)"
        conn.execute(
            "INSERT INTO facts (company_id, criterion, value, source_url, snippet, origin, status,"
            " status_reason, page_date, retrieved_at, attempt, method) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (company["id"], f["criterion"], f.get("value"), f.get("source_url"), f.get("snippet"), origin,
             status, reason, res.page_date.isoformat() if res.page_date else None, _now(), attempt, method))
    conn.commit()


def _verified(conn, cid) -> set[str]:
    return {r["criterion"] for r in conn.execute(
        "SELECT DISTINCT criterion FROM facts WHERE company_id=? AND status='VERIFIED'", (cid,))}


def _scrape_pages(conn, cfg, domain):
    rc = cfg["research"]
    pages = {}
    for path in rc["scrape_paths"]:
        p = scrape.fetch(conn, f"https://{domain}{path}")
        if p:
            pages[p.url] = p
    ats = []
    for u, p in list(pages.items()):
        if "career" in u or "jobs" in u:
            for link in scrape.links(p):
                if any(h in link for h in rc["ats_hosts"]) and link not in ats:
                    ats.append(link)
    for link in ats[: rc["max_ats_pages"]]:
        p = scrape.fetch(conn, link)
        if p:
            pages[p.url] = p
    return pages


def _flag_conflicts(conn, cid) -> None:
    for crit in SINGLE_VALUED:
        rows = conn.execute("SELECT id, value FROM facts WHERE company_id=? AND criterion=? AND status='VERIFIED'",
                            (cid, crit)).fetchall()
        if len({norm(r["value"]) for r in rows}) > 1:
            conn.execute(f"UPDATE facts SET conflict=1, status_reason='CONFLICT: verified sources disagree' "
                         f"WHERE id IN ({','.join(str(r['id']) for r in rows)})")
    conn.commit()


def run_company(conn, cfg, company) -> dict:
    cid = company["id"]
    conn.execute("DELETE FROM facts WHERE company_id=?", (cid,))
    conn.execute("DELETE FROM research_log WHERE company_id=?", (cid,))
    conn.commit()  # release the write lock before the slow Gemini calls so parallel workers aren't blocked
    max_attempts = cfg["research"]["max_attempts"]
    name, domain = company["name"], company["domain"]
    gaps = list(ALL_CRITERIA)

    def log(attempt, method, targets):
        done = _verified(conn, cid)
        for c in targets:
            conn.execute("INSERT INTO research_log (company_id, criterion, attempt, method, outcome) VALUES (?,?,?,?,?)",
                         (cid, c, attempt, method, "verified" if c in done else "not_verified"))

    for attempt in range(1, max_attempts + 1):
        gaps = [c for c in CRITERIA if c not in _verified(conn, cid)]
        if not gaps:
            break
        targets = gaps + (EXTRA_CRITERIA if attempt == 1 else [])
        if attempt == 1:
            method = "google_search"
            facts, grounding = llm.generate(conn, cfg, "research_facts", grounded=True,
                                            name=name, domain=domain, criteria=", ".join(targets))
            _check(conn, cfg, company, facts, grounding, "grounding", attempt, method)
        elif attempt == 2:
            method = "official_site"
            pages = _scrape_pages(conn, cfg, domain)
            if pages:
                mx = cfg["research"]["max_chars_per_page"]
                blob = "\n\n".join(f"URL: {u}\n{(p.text or p.raw_text)[:mx]}" for u, p in pages.items())
                facts, _ = llm.generate(conn, cfg, "extract_facts", grounded=False, name=name, domain=domain,
                                        criteria=", ".join(gaps), pages=blob)
                _check(conn, cfg, company, facts, set(pages), "scraper", attempt, method)
        else:
            method = "news_search" if attempt == 3 else "targeted_retry"
            instruction = (ATTEMPT_3 if attempt == 3 else ATTEMPT_4).replace("{domain}", domain)
            facts, grounding = llm.generate(conn, cfg, "research_followup", grounded=True, name=name,
                                            domain=domain, criteria=", ".join(gaps), instruction=instruction)
            _check(conn, cfg, company, facts, grounding, "grounding", attempt, method)
        log(attempt, method, targets)

    if cfg["research"].get("hunter_enrichment", True):
        hunter_enrich(conn, cfg, company)
    _flag_conflicts(conn, cid)
    have = {r["criterion"] for r in conn.execute("SELECT criterion FROM facts WHERE company_id=?", (cid,))}
    for c in ALL_CRITERIA:
        if c not in have:
            conn.execute("INSERT INTO facts (company_id, criterion, status, status_reason, retrieved_at)"
                         " VALUES (?,?,'NOT_FOUND','UNVERIFIED: nothing found after all attempts',?)", (cid, c, _now()))
    conn.execute("UPDATE companies SET status='researched', stage='research', researched_at=? WHERE id=?",
                 (_now(), cid))
    conn.commit()
    return {r["status"]: r["n"] for r in conn.execute(
        "SELECT status, COUNT(*) n FROM facts WHERE company_id=? GROUP BY status", (cid,))}


def reverify(conn, cfg, company) -> int:
    """Re-check stored 'snippet not found' facts against the (cached) pages with the current matcher."""
    fixed = 0
    rows = conn.execute("SELECT * FROM facts WHERE company_id=? AND status='ASSERTED' AND status_reason='snippet not found on page'",
                        (company["id"],)).fetchall()
    for f in rows:
        fact = dict(f)
        res = verify.verify_fact(fact, {f["source_url"]}, lambda u: scrape.fetch(conn, u), date.today(),
                                 cfg["recency_months"], cfg["research"]["min_snippet_chars"])
        status, reason = res.status, res.reason
        same_site = company["domain"] in (f["source_url"] or "")
        if status == verify.VERIFIED and not same_site and not _entity_ok(conn, company, f["source_url"]):
            status, reason = verify.ASSERTED, "page does not mention this company (wrong-entity risk)"
        if status != f["status"] or reason != f["status_reason"]:
            conn.execute("UPDATE facts SET status=?, status_reason=?, page_date=? WHERE id=?",
                         (status, reason, res.page_date.isoformat() if res.page_date else None, f["id"]))
            fixed += status == verify.VERIFIED
    _flag_conflicts(conn, company["id"])
    conn.commit()
    return fixed


CLOUD_TECH = {"amazon-web-services": "AWS", "google-cloud": "GCP", "google-cloud-platform": "GCP", "microsoft-azure": "Azure"}


def hunter_enrich(conn, cfg, company) -> list[str]:
    """Fifth, structured method for criteria still unverified after the four searches: Hunter's company-enrichment
    record (employee estimate, tech stack, industry tags). One cheap API call, no scraping. Returns criteria filled."""
    import json

    from app.config import has_env
    from app.modules import contacts

    cid = company["id"]
    if not has_env("HUNTER_API_KEY"):
        return []
    need = [c for c in ("employee_count", "cloud", "industry") if c not in _verified(conn, cid)]
    if not need:
        return []
    try:
        data = contacts._get(conn, "companies/find", {"domain": company["domain"]}).get("data") or {}
    except Exception:  # not found / quota: leave the criteria UNVERIFIED rather than guessing
        return []
    m, tech, tags = data.get("metrics") or {}, data.get("tech") or [], data.get("tags") or []
    indexed = (data.get("indexedAt") or "")[:10] or None
    found = {}
    cnt, rng = m.get("employeesCount"), m.get("employees")
    if cnt:
        found["employee_count"] = (f"{cnt} employees (Hunter estimate, range {rng})", f'"employeesCount": {cnt}, "employees": "{rng}"')
    elif rng:
        found["employee_count"] = (f"{rng} employees (Hunter range)", f'"employees": "{rng}"')
    clouds = [(t, CLOUD_TECH[t]) for t in tech if t in CLOUD_TECH]
    if clouds:
        found["cloud"] = (", ".join(sorted({n for _, n in clouds})), f'"tech": {json.dumps([t for t, _ in clouds])}')
    if tags:
        found["industry"] = (", ".join(tags[:3]), f'"tags": {json.dumps(tags[:3])}')
    filled = []
    src = f"https://api.hunter.io/v2/companies/find?domain={company['domain']}"
    for crit in need:
        if crit not in found:
            continue
        value, snippet = found[crit]
        conn.execute(
            "INSERT INTO facts (company_id, criterion, value, source_url, snippet, origin, status, status_reason,"
            " page_date, retrieved_at, attempt, method) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (cid, crit, value, src, snippet, "hunter_api", "VERIFIED",
             f"Hunter company-enrichment record (structured third-party data, indexed {indexed})", indexed, _now(), 5, "hunter_enrichment"))
        conn.execute("INSERT INTO research_log (company_id, criterion, attempt, method, outcome) VALUES (?,?,?,?,?)",
                     (cid, crit, 5, "hunter_enrichment", "verified"))
        filled.append(crit)
    conn.commit()
    return filled
