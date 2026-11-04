"""Stages 1-2: discover candidates with grounded search, triage, verify official domains, shortlist."""
import json
import re

from app import db, llm, scrape
from app.modules import icp
from app.verify import norm

BATCH = 10


def clean_domain(d) -> str | None:
    if not d or not isinstance(d, str):
        return None
    d = d.strip().lower().removeprefix("https://").removeprefix("http://").removeprefix("www.")
    d = d.split("/")[0].split("?")[0]
    return d if re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", d) else None


def _name_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def add_manual(conn, domain: str, name: str | None = None) -> int | None:
    d = clean_domain(domain)
    if not d:
        return None
    conn.execute(
        "INSERT OR IGNORE INTO companies (domain, name, origin, status, stage) VALUES (?,?,'manual','shortlisted','shortlist')",
        (d, name or d.split(".")[0].title()))
    conn.commit()
    return conn.execute("SELECT id FROM companies WHERE domain=?", (d,)).fetchone()["id"]


def discover(conn, cfg) -> int:
    target = cfg["discover"]["candidates"]
    focuses = cfg["discover"]["focuses"]
    per_focus = -(-target // len(focuses)) + 3
    icp_text = icp.summary_text(conn)
    added = 0
    for focus in focuses:
        rows = conn.execute("SELECT domain, name FROM companies").fetchall()
        if len(rows) >= target:
            break
        known_names = {_name_key(r["name"]) for r in rows}
        items, _ = llm.generate(conn, cfg, "discover", grounded=True, focus=focus, count=per_focus,
                                icp=icp_text, exclude=", ".join(r["domain"] for r in rows) or "none")
        for it in items if isinstance(items, list) else []:
            domain = clean_domain(it.get("domain"))
            if not domain or not it.get("name") or _name_key(it["name"]) in known_names:
                continue
            src = {"trigger": it.get("trigger"), "url": it.get("source_url"), "focus": focus}
            cur = conn.execute(
                "INSERT OR IGNORE INTO companies (domain, name, discover_sources, triage) VALUES (?,?,?,?)",
                (domain, it["name"], json.dumps([src]),
                 json.dumps({"industry": it.get("industry"), "funding_stage": it.get("funding_stage")})))
            if cur.rowcount:
                known_names.add(_name_key(it["name"]))
                added += 1
            else:  # same domain seen again: keep both sources
                r = conn.execute("SELECT id, discover_sources FROM companies WHERE domain=?", (domain,)).fetchone()
                conn.execute("UPDATE companies SET discover_sources=? WHERE id=?",
                             (json.dumps(json.loads(r["discover_sources"]) + [src]), r["id"]))
        conn.commit()
    return added


def _keywords(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{6,}", (text or "").lower())} - {"company", "platform", "software", "series",
            "funding", "raised", "announced", "automate", "automates", "financial", "services", "solutions"}


def domain_verified(conn, domain: str, name: str, sources: list | None = None, triage: dict | None = None):
    """The domain must load, mention the company, and match the company we discovered
    (the discovery article links/mentions the domain, or the site matches the described business)."""
    page = scrape.fetch(conn, f"https://{domain}")
    if page is None:
        return False, "official site did not load (or robots.txt disallows)"
    hay = norm(page.text + " " + page.raw_text[:5000])
    if norm(name) not in hay and domain.split(".")[0] not in hay:
        return False, "site does not mention the company name"
    if not sources:  # manual input: the user vouches for the domain
        return True, "site loads and mentions the company"
    for s in sources:
        art = scrape.fetch(conn, s["url"]) if s.get("url") else None
        if art and domain in (art.html or "").lower():
            return True, "discovery article references this domain"
    want = _keywords(" ".join(str(s.get("trigger") or "") for s in sources) + " " + str((triage or {}).get("industry") or ""))
    if want & _keywords(page.text + " " + page.raw_text[:8000]):
        return True, "site content matches the described business"
    return False, "site does not match the business described in discovery (possible name clash)"


def shortlist(conn, cfg) -> tuple[int, int]:
    sc = cfg["shortlist"]
    rows = conn.execute("SELECT * FROM companies WHERE status='discovered' AND origin='auto'").fetchall()
    scored = []
    for i in range(0, len(rows), BATCH):
        batch = rows[i:i + BATCH]
        listing = "\n".join(f"- {r['name']} ({r['domain']})" for r in batch)
        items, _ = llm.generate(conn, cfg, "shortlist", grounded=True, companies=listing)
        by_domain = {str(x.get("domain", "")).lower(): x for x in items if isinstance(x, dict)}
        for r in batch:
            x = by_domain.get(r["domain"])
            if x is None:
                db.stop(conn, r["id"], "shortlist", "no triage result returned")
            elif x.get("is_saas") is False:
                db.stop(conn, r["id"], "shortlist", "not SaaS (triage)")
            elif x.get("funding_stage") and x["funding_stage"] not in sc["allowed_stages"]:
                db.stop(conn, r["id"], "shortlist", f"stage {x['funding_stage']} outside Series A-C (triage)")
            else:
                conn.execute("UPDATE companies SET triage=? WHERE id=?", (json.dumps(x), r["id"]))
                scored.append((float(x.get("fit") or 0), r))
    scored.sort(key=lambda t: -t[0])
    kept = 0
    for fit, r in scored:
        if kept >= sc["keep_max"]:
            db.stop(conn, r["id"], "shortlist", f"ranked below top {sc['keep_max']} (fit {fit:g})")
            continue
        ok, why = domain_verified(conn, r["domain"], r["name"], json.loads(r["discover_sources"]), json.loads(r["triage"] or "{}"))
        if not ok:
            db.stop(conn, r["id"], "shortlist", f"official domain not verifiable: {why}")
            continue
        conn.execute("UPDATE companies SET status='shortlisted', stage='shortlist', shortlist_score=? WHERE id=?",
                     (fit, r["id"]))
        db.log_decision(conn, r["id"], "shortlist", "shortlisted", f"fit {fit:g}; domain: {why}")
        kept += 1
    conn.commit()
    return kept, len(rows) - kept
