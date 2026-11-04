"""Stage 7: draft emails with a code validator. Every factual claim must trace to VERIFIED facts."""
import hashlib
import json
import re

from app import db, llm
from app.config import env
from app.modules import intent as intent_mod
from app.verify import norm, numbers

KINDS = ["trigger", "pressure", "offer", "ask"]
FACTUAL = {"trigger", "pressure"}
SMALL_OK = {str(n) for n in range(1, 61)}  # "15 minutes" etc. only allowed in non-factual sentences
ALWAYS_NUM_OK = {"2", "27001"}             # SOC 2, ISO 27001


def words(s: str) -> int:
    return len(s.split())


def draft_hash(subject: str, body: str) -> str:
    return hashlib.sha256(f"{subject}\n{body}".encode("utf-8")).hexdigest()


def _names(text: str, skip_first: bool = True) -> set[str]:
    toks = re.findall(r"\b[A-Z][A-Za-z0-9]+\b", text)
    first = re.match(r"\W*([A-Za-z0-9]+)", text)
    if skip_first and first and toks and toks[0] == first.group(1):
        toks = toks[1:]
    return {t.lower() for t in toks}


def validate(draft, verified: dict[int, dict], cfg, allowed_names: set[str]) -> list[str]:
    dc = cfg["drafting"]
    errs = []
    if not isinstance(draft, dict) or not isinstance(draft.get("sentences"), list):
        return ["output is not {subject, sentences}"]
    subject = (draft.get("subject") or "").strip()
    sents = draft["sentences"]
    if not subject or words(subject) > dc["max_subject_words"]:
        errs.append(f"subject must be 1-{dc['max_subject_words']} words")
    kinds = [s.get("kind") for s in sents]
    if "trigger" not in kinds:
        errs.append("no trigger sentence")
    if kinds != sorted(kinds, key=lambda k: KINDS.index(k) if k in KINDS else 99) or any(k not in KINDS for k in kinds):
        errs.append("sentence kinds must be trigger, pressure, offer, ask in order")
    body = " ".join(s.get("text", "") for s in sents)
    if words(body) >= dc["max_words"]:
        errs.append(f"body is {words(body)} words; must be under {dc['max_words']}")
    allowed = {a.lower() for a in dc["allowed_terms"]} | allowed_names
    for i, s in enumerate(sents):
        text, kind = s.get("text", ""), s.get("kind")
        ids = [x for x in s.get("fact_ids", []) if isinstance(x, int)]
        bad = [x for x in ids if x not in verified]
        if bad:
            errs.append(f"sentence {i + 1} cites non-VERIFIED fact ids {bad}")
        if kind in FACTUAL and not [x for x in ids if x in verified]:
            errs.append(f"sentence {i + 1} ({kind}) cites no VERIFIED fact")
        fact_text = " ".join(f"{verified[x]['value']} {verified[x]['snippet']}" for x in ids if x in verified)
        fact_norm = norm(fact_text)
        fact_nums = numbers(fact_text)
        for n in numbers(text):
            if n in ALWAYS_NUM_OK or (kind not in FACTUAL and n in SMALL_OK):
                continue
            if n not in fact_nums:
                errs.append(f"sentence {i + 1}: number {n} not in cited facts")
        for nm in _names(text):
            if nm in allowed or nm in fact_norm.split() or nm in fact_norm:
                continue
            if kind in FACTUAL or True:
                errs.append(f"sentence {i + 1}: name '{nm}' not in cited facts")
    return errs


def validate_text(subject: str, body: str, verified: dict[int, dict], cfg, allowed_names: set[str]) -> list[str]:
    """For human edits: no sentence-level citations, so numbers/names may come from any VERIFIED fact."""
    dc = cfg["drafting"]
    errs = []
    if not subject.strip() or words(subject) > dc["max_subject_words"]:
        errs.append(f"subject must be 1-{dc['max_subject_words']} words")
    core = body.split("\n\n--")[0]
    if words(core) >= dc["max_words"] + 25:  # greeting/sign-off allowance
        errs.append("body too long")
    all_text = " ".join(f"{f['value']} {f['snippet']}" for f in verified.values())
    nums, low = numbers(all_text), norm(all_text)
    allowed = {a.lower() for a in dc["allowed_terms"]} | allowed_names
    for n in numbers(core) - ALWAYS_NUM_OK - nums - SMALL_OK:
        errs.append(f"number {n} not in any VERIFIED fact")
    for line in core.splitlines():
        for nm in _names(line):
            if nm not in allowed and nm not in low:
                errs.append(f"name '{nm}' not in any VERIFIED fact")
    return sorted(set(errs))


def footer() -> str:
    sender = env("SENDER_NAME", "")
    who = f"{sender}, Sprinto" if sender else "The Sprinto team"
    return f"\n\n--\n{who}\n{env('SENDER_EMAIL', 'onboarding@resend.dev')}\nNot relevant? Reply STOP and I won't email again."


def allowed_names_for(company, contact) -> set[str]:
    names = {contact["first_name"].lower(), contact["last_name"].lower(), env("SENDER_NAME", "team").lower()}
    names |= {t.lower() for t in re.findall(r"[A-Za-z0-9]+", company["name"])}
    names |= {company["domain"].split(".")[0].lower()}
    return names


def run_company(conn, cfg, company, contact) -> int | None:
    cid = company["id"]
    vf = intent_mod.verified_facts(conn, cid)
    verified = {f["id"]: f for f in vf}
    intent = json.loads(company["intent"] or "{}")
    if not intent.get("signals"):
        db.stop(conn, cid, "draft", "no verified why-now trigger; not drafting")
        return None
    allowed = allowed_names_for(company, contact)
    prev, draft = "", None
    for attempt in range(cfg["drafting"]["max_retries"] + 1):
        draft, _ = llm.generate(
            conn, cfg, "draft", grounded=False, sender_name=env("SENDER_NAME", "the Sprinto team"),
            contact_first=contact["first_name"], contact_position=contact["position"], company=company["name"],
            facts=intent_mod.facts_block(vf), signals=json.dumps(intent["signals"]),
            pains=json.dumps(intent["pain_points"]), previous_errors=prev)
        errs = validate(draft, verified, cfg, allowed)
        if not errs:
            break
        prev = "\nYour previous attempt failed validation. Fix these:\n- " + "\n- ".join(errs)
        # force a fresh generation: the previous-errors text changes the cache key
    else:
        db.stop(conn, cid, "draft", "draft failed validation after retries: " + "; ".join(errs))
        return None
    body = f"Hi {contact['first_name']},\n\n" + " ".join(s["text"].strip() for s in draft["sentences"]) + footer()
    cited = sorted({i for s in draft["sentences"] for i in s.get("fact_ids", []) if i in verified})
    conn.execute("DELETE FROM drafts WHERE company_id=? AND status IN ('pending','rejected')", (cid,))
    cur = conn.execute("INSERT INTO drafts (company_id, contact_id, subject, body, fact_ids) VALUES (?,?,?,?,?)",
                       (cid, contact["id"], draft["subject"].strip(), body, json.dumps(cited)))
    conn.execute("UPDATE companies SET status='drafted', stage='draft' WHERE id=?", (cid,))
    db.log_decision(conn, cid, "draft", "drafted", f"draft {cur.lastrowid}")
    conn.commit()
    return cur.lastrowid
