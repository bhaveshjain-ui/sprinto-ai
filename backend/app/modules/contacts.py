"""Stage 6: Hunter.io domain search + email verifier. Never invents a person or an address."""
import re

import httpx

from app import cache, db
from app.config import env

TIERS = {
    "founder": r"founder|co-?founder|\bceo\b|chief executive",
    "cto": r"\bcto\b|chief technology|head of engineering|vp.{0,3}engineering",
    "ciso": r"\bciso\b|chief information security|chief security",
    "head_infosec": r"head of (information )?security|(director|vp).{0,15}security|infosec|information security",
    "head_compliance": r"head of compliance|compliance (manager|lead|officer|director)|(director|vp).{0,15}compliance",
    "grc": r"\bgrc\b|governance|risk",
}
SPEC_ORDER = ["founder", "cto", "ciso", "head_infosec", "head_compliance", "grc"]


def order_for_size(employees: int | None) -> list[str]:
    if employees is None or employees < 50:
        return SPEC_ORDER
    if employees <= 200:
        return ["cto", "ciso", "head_infosec", "founder", "head_compliance", "grc"]
    return ["ciso", "head_infosec", "head_compliance", "grc", "cto", "founder"]


def tier_of(position: str | None) -> str | None:
    p = (position or "").lower()
    for t in SPEC_ORDER:
        if re.search(TIERS[t], p):
            return t
    return None


def rank(candidates: list[dict], employees: int | None, min_conf: int) -> list[dict]:
    """Keep named, titled, well-scored people in relevant tiers; best-first for this company size."""
    order = order_for_size(employees)
    out = []
    for c in candidates:
        t = tier_of(c.get("position"))
        if not (t and c.get("first_name") and c.get("last_name") and c.get("value")):
            continue
        if (c.get("confidence") or 0) < min_conf:
            continue
        out.append({**c, "tier": t, "rank": order.index(t)})
    out.sort(key=lambda c: (c["rank"], -(c.get("confidence") or 0)))
    return out


def _get(conn, path: str, params: dict):
    key = cache.make_key(path, str(sorted(params.items())))

    def do():
        r = httpx.get(f"https://api.hunter.io/v2/{path}", params={**params, "api_key": env("HUNTER_API_KEY")},
                      timeout=30)
        if r.status_code == 429:
            raise RuntimeError("Hunter rate limit hit; try again later")
        if r.status_code >= 400:  # never include the URL: it carries the API key
            raise RuntimeError(f"Hunter {path} failed ({r.status_code}): {r.text[:200]}")
        return r.json()

    return cache.get_or_set(conn, "hunter", key, do, ttl_days=30)


def domain_search(conn, domain: str) -> list[dict]:
    data = _get(conn, "domain-search", {"domain": domain, "limit": 10})
    return data.get("data", {}).get("emails", [])


def verify_email(conn, email: str) -> str:
    data = _get(conn, "email-verifier", {"email": email})
    return data.get("data", {}).get("status", "unknown")


def employee_count(conn, company_id: int) -> int | None:
    r = conn.execute("SELECT value FROM facts WHERE company_id=? AND criterion='employee_count' AND status='VERIFIED'"
                     " AND conflict=0 LIMIT 1", (company_id,)).fetchone()
    m = re.search(r"\d[\d,]*", r["value"]) if r else None
    return int(m.group().replace(",", "")) if m else None


def run_company(conn, cfg, company, search=domain_search, verifier=verify_email) -> dict | None:
    cid = company["id"]
    emps = employee_count(conn, cid)
    ranked = rank(search(conn, company["domain"]), emps, cfg["contacts"]["min_confidence"])
    conn.execute("DELETE FROM contacts WHERE company_id=?", (cid,))
    chosen = None
    for c in ranked:
        status = verifier(conn, c["value"])
        picked = chosen is None and status == "valid"
        reasoning = (f"{c['position']} matches tier '{c['tier']}' (rank {c['rank'] + 1} for "
                     f"{'unknown' if emps is None else emps} employees); Hunter confidence {c.get('confidence')}; "
                     f"email verifier: {status}")
        conn.execute(
            "INSERT INTO contacts (company_id, first_name, last_name, email, position, confidence, verification,"
            " source, selected, reasoning) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (cid, c["first_name"], c["last_name"], c["value"], c["position"], c.get("confidence"), status,
             "hunter.io domain-search", int(picked), reasoning))
        if picked:
            chosen = c
    conn.commit()
    if not chosen:
        db.stop(conn, cid, "contact", "no relevant contact with valid email and confidence >= "
                f"{cfg['contacts']['min_confidence']}")
        return None
    db.log_decision(conn, cid, "contact", "selected", f"{chosen['first_name']} {chosen['last_name']}")
    return chosen
