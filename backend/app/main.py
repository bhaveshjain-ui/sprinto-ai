import json
import os
import threading
import time

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import db
from app.config import has_env, load_config
from app.modules import delivery, discovery, flow, icp

app = FastAPI(title="Sprinto AI")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])

CFG = load_config()
JOBS: dict[str, dict] = {}


def conn():
    return db.connect_cached()


def rows(c, sql, *a):
    return [dict(r) for r in c.execute(sql, a)]


def start_job(name: str, fn):
    """Run fn(conn, progress) in a thread; one job of each name at a time."""
    if os.environ.get("VERCEL"):
        raise HTTPException(501, "Research jobs run on your own machine (serverless functions time out). "
                                 "Run the app locally against the same database, then review and send here.")
    if JOBS.get(name, {}).get("running"):
        raise HTTPException(409, f"{name} already running")
    JOBS[name] = {"running": True, "message": "starting", "error": None, "cancel": False}

    def run():
        c = db.connect()
        try:
            fn(c, lambda m: JOBS[name].update(message=m))
        except Exception as e:
            JOBS[name]["error"] = str(e)[:400]
        finally:
            JOBS[name]["running"] = False
            c.close()

    threading.Thread(target=run, daemon=True).start()
    return JOBS[name]


@app.post("/api/jobs/{name}/stop")
def stop_job(name: str):
    """Ask a running batch to stop after the companies currently in flight; finished work is kept."""
    if name in JOBS and JOBS[name].get("running"):
        JOBS[name]["cancel"] = True
        JOBS[name]["message"] = "stopping after current companies"
    return JOBS.get(name, {})


@app.get("/api/jobs")
def jobs():
    return JOBS


@app.get("/api/overview")
def overview():
    c = conn()
    return dict(c.execute("""SELECT
      (SELECT COUNT(*) FROM companies) AS discovered,
      (SELECT COUNT(*) FROM companies WHERE researched_at IS NOT NULL) AS researched,
      (SELECT COUNT(*) FROM companies WHERE status='stopped' AND stage IN ('discover','shortlist')) AS filtered_out,
      (SELECT COUNT(*) FROM companies WHERE status IN ('shortlisted','researched') AND classification IS NULL) AS in_queue,
      (SELECT COUNT(*) FROM companies WHERE classification='qualified') AS qualified,
      (SELECT COUNT(*) FROM companies WHERE classification='further_investigation') AS further_investigation,
      (SELECT COUNT(*) FROM companies WHERE classification='rejected') AS rejected,
      (SELECT COUNT(*) FROM companies WHERE priority='High' AND status IN ('lead','drafted')) AS high_priority,
      (SELECT COUNT(*) FROM drafts WHERE status IN ('pending','approved')) AS pending_approvals,
      (SELECT COUNT(*) FROM sends WHERE status='sent') AS sent""").fetchone())


@app.get("/api/settings")
def settings():
    c = conn()
    return {
        "dry_run": db.get_setting(c, "dry_run", "false") == "true",
        "integrations": {k: has_env(k) for k in ("GEMINI_API_KEY", "HUNTER_API_KEY",
                                                 "RESEND_API_KEY", "SENDER_EMAIL", "MY_EMAIL")},
        "cloud": bool(os.environ.get("VERCEL")),
        "local_only": ["GEMINI_API_KEY", "HUNTER_API_KEY"],
        "recipient": os.environ.get("MY_EMAIL", ""),
        "recipient_hint": "All emails go to MY_EMAIL only.",
    }


class DryRun(BaseModel):
    dry_run: bool


@app.put("/api/settings/dry_run")
def set_dry_run(body: DryRun):
    db.set_setting(conn(), "dry_run", "true" if body.dry_run else "false")
    return {"dry_run": body.dry_run}


@app.post("/api/selftest/{name}")
def selftest(name: str):
    """Cheap live check of each integration."""
    from app.config import env

    if os.environ.get("VERCEL") and name in ("gemini", "hunter"):
        return {"ok": True, "detail": "runs on your own machine, not needed on Vercel"}
    try:
        if name == "gemini":
            from app import llm

            return {"ok": bool(llm._call(CFG["model"], "Reply with the word OK", False, 0)["text"])}
        if name == "hunter":
            import httpx

            r = httpx.get("https://api.hunter.io/v2/account", params={"api_key": env("HUNTER_API_KEY")}, timeout=20)
            return {"ok": r.status_code == 200, "detail": r.json().get("data", {}).get("requests")}
        if name == "resend":
            env("RESEND_API_KEY")  # send-only keys cannot call read endpoints; real check is a send
            return {"ok": True, "detail": "key present (send-only keys can't be probed without sending)"}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:300]}
    raise HTTPException(404)


# --- ICP / discovery -------------------------------------------------------
@app.get("/api/icp")
def get_icp():
    return icp.latest(conn()) or {}


@app.post("/api/icp/run")
def run_icp():
    return start_job("icp", lambda c, p: icp.run(c, CFG))


class Domains(BaseModel):
    domains: list[str]


@app.post("/api/discover")
def run_discover():
    def go(c, p):
        p("ICP report")
        icp.run(c, CFG)
        p("discovering")
        discovery.discover(c, CFG)
        p("shortlisting")
        discovery.shortlist(c, CFG)

    return start_job("discover", go)


@app.post("/api/companies/manual")
def add_manual(body: Domains):
    c = conn()
    ids = [discovery.add_manual(c, d) for d in body.domains]
    return {"added": [i for i in ids if i], "invalid": [d for d, i in zip(body.domains, ids) if not i]}


@app.post("/api/autonomous")
def autonomous():
    return start_job("autonomous", lambda c, p: flow.autonomous(c, CFG, p))


@app.post("/api/companies/process")
def process_all():
    def go(c, p):
        from concurrent.futures import ThreadPoolExecutor

        ids = [(r["id"], r["name"]) for r in c.execute(
            "SELECT id, name FROM companies WHERE status IN ('shortlisted','researched') AND classification IS NULL")]
        done = [0]

        def one(item):
            cid, name = item
            if JOBS["process"].get("cancel"):
                return
            wc = db.connect()
            try:
                for attempt in range(4):  # a lock clash is transient and the work is cached, so retrying is cheap
                    try:
                        flow.process_company(wc, CFG, cid)
                        break
                    except Exception as e:
                        if "locked" in str(e) and attempt < 3:
                            time.sleep(2 + attempt * 3)
                            continue
                        try:  # one company's failure must not stop the batch
                            db.log_decision(wc, cid, "error", "failed", str(e)[:300])
                            wc.commit()
                        except Exception:
                            pass
                        break
            finally:
                wc.close()
                done[0] += 1
                p(f"Researching and scoring queued companies: {done[0]} of {len(ids)} done (latest: {name})")

        with ThreadPoolExecutor(max_workers=4) as ex:
            list(ex.map(one, ids))

    return start_job("process", go)


@app.post("/api/companies/{cid}/process")
def process_one(cid: int, force: bool = True):
    return start_job(f"company-{cid}", lambda c, p: flow.process_company(c, CFG, cid, force=force))


@app.get("/api/companies")
def companies():
    out = rows(conn(), "SELECT id, domain, name, origin, status, stage, stop_reason, score, classification, priority,"
                       " researched_at, score_detail FROM companies ORDER BY COALESCE(score,-1) DESC, id")
    for r in out:  # which criteria are still unverified: tells you what "further investigation" actually needs
        detail = json.loads(r.pop("score_detail") or "{}").get("detail", {})
        r["missing"] = [k for k, v in detail.items() if v.get("state") in ("unverified", "conflict")]
    return out


@app.get("/api/companies/{cid}")
def company(cid: int):
    c = conn()
    co = c.execute("SELECT * FROM companies WHERE id=?", (cid,)).fetchone()
    if not co:
        raise HTTPException(404)
    co = dict(co)
    for k in ("discover_sources", "triage", "score_detail", "intent"):
        co[k] = json.loads(co[k]) if co[k] else None
    return {"company": co,
            "facts": rows(c, "SELECT * FROM facts WHERE company_id=? ORDER BY criterion, id", cid),
            "research_log": rows(c, "SELECT * FROM research_log WHERE company_id=? ORDER BY attempt, id", cid),
            "decisions": rows(c, "SELECT * FROM decisions WHERE company_id=? ORDER BY id", cid),
            "contacts": rows(c, "SELECT * FROM contacts WHERE company_id=?", cid),
            "drafts": rows(c, "SELECT * FROM drafts WHERE company_id=?", cid)}


@app.get("/api/leads")
def leads():
    c = conn()
    out = []
    for co in rows(c, "SELECT * FROM companies WHERE status IN ('lead','drafted')"):
        out.append({"id": co["id"], "name": co["name"], "domain": co["domain"], "score": co["score"],
                    "priority": co["priority"], "intent": json.loads(co["intent"] or "{}"),
                    "contacts": rows(c, "SELECT * FROM contacts WHERE company_id=? AND selected=1", co["id"])})
    return out


# --- review & delivery -------------------------------------------------------
def _in(ids) -> str:
    return ",".join(str(int(i)) for i in ids) or "NULL"


@app.get("/api/drafts")
def drafts(status: str | None = None):
    """Few round trips on purpose: batch-load companies, contacts, facts and sends for all drafts."""
    c = conn()
    q = "SELECT * FROM drafts" + (" WHERE status=?" if status else "") + " ORDER BY id DESC"
    ds = rows(c, q, *([status] if status else []))
    if not ds:
        return []
    cos = {r["id"]: r for r in rows(c, f"SELECT * FROM companies WHERE id IN ({_in({d['company_id'] for d in ds})})")}
    cts = {r["id"]: r for r in rows(c, f"SELECT * FROM contacts WHERE id IN ({_in({d['contact_id'] for d in ds})})")}
    fact_ids = {i for d in ds for i in json.loads(d["fact_ids"])}
    facts = {r["id"]: r for r in rows(c, f"SELECT id, criterion, value, source_url, snippet, page_date FROM facts WHERE id IN ({_in(fact_ids)})")}
    sends = rows(c, f"SELECT draft_id, status, resend_id, error, created_at FROM sends WHERE draft_id IN ({_in(d['id'] for d in ds)}) ORDER BY id")
    for d in ds:
        co = cos[d["company_id"]]
        d["company"] = {k: co[k] for k in ("id", "name", "domain", "score", "classification", "priority")}
        d["score_detail"] = json.loads(co["score_detail"] or "{}")
        d["intent"] = json.loads(co["intent"] or "{}")
        d["contact"] = cts[d["contact_id"]]
        d["sources"] = [facts[i] for i in json.loads(d["fact_ids"]) if i in facts]
        d["sends"] = [{k: x[k] for k in ("status", "resend_id", "error", "created_at")} for x in sends if x["draft_id"] == d["id"]]
    return ds


class Edit(BaseModel):
    subject: str
    body: str


def _guard(fn, *a):
    try:
        return fn(*a)
    except delivery.DeliveryError as e:
        raise HTTPException(400, str(e))


@app.put("/api/drafts/{did}")
def edit_draft(did: int, body: Edit):
    errs = _guard(delivery.edit, conn(), CFG, did, body.subject, body.body)
    if errs:
        raise HTTPException(422, {"validation_errors": errs})
    return {"status": "pending"}


@app.post("/api/drafts/{did}/reject")
def reject_draft(did: int):
    _guard(delivery.reject, conn(), did)
    return {"status": "rejected"}


@app.post("/api/drafts/{did}/approve-send")
def approve_send(did: int):
    c = conn()
    _guard(delivery.approve, c, did)
    return _guard(delivery.send, c, did)


@app.get("/api/sent")
def sent():
    return rows(conn(), "SELECT s.*, co.name AS company FROM sends s JOIN drafts d ON d.id=s.draft_id "
                        "JOIN companies co ON co.id=d.company_id ORDER BY s.id DESC")
