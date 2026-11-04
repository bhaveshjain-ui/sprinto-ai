"""Stage 8-9: review actions and Resend delivery. Nothing is sent without APPROVE on that exact draft."""
import sqlite3

from app import db
from app.config import env
from app.modules import drafting, intent as intent_mod


class DeliveryError(Exception):
    pass


def _draft(conn, draft_id: int):
    d = conn.execute("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone()
    if not d:
        raise DeliveryError("draft not found")
    return d


def edit(conn, cfg, draft_id: int, subject: str, body: str) -> list[str]:
    """Edit re-validates; any edit resets the draft to pending (approval is voided)."""
    d = _draft(conn, draft_id)
    if d["status"] == "sent":
        raise DeliveryError("already sent")
    company = conn.execute("SELECT * FROM companies WHERE id=?", (d["company_id"],)).fetchone()
    contact = conn.execute("SELECT * FROM contacts WHERE id=?", (d["contact_id"],)).fetchone()
    verified = {f["id"]: f for f in intent_mod.verified_facts(conn, d["company_id"])}
    errs = drafting.validate_text(subject, body, verified, cfg, drafting.allowed_names_for(company, contact))
    if errs:
        return errs
    conn.execute("UPDATE drafts SET subject=?, body=?, status='pending', approved_hash=NULL, updated_at=datetime('now')"
                 " WHERE id=?", (subject.strip(), body, draft_id))
    conn.commit()
    return []


def approve(conn, draft_id: int) -> None:
    d = _draft(conn, draft_id)
    if d["status"] in ("sent", "rejected"):
        raise DeliveryError(f"cannot approve a {d['status']} draft")
    conn.execute("UPDATE drafts SET status='approved', approved_hash=?, updated_at=datetime('now') WHERE id=?",
                 (drafting.draft_hash(d["subject"], d["body"]), draft_id))
    conn.commit()


def reject(conn, draft_id: int) -> None:
    d = _draft(conn, draft_id)
    if d["status"] == "sent":
        raise DeliveryError("already sent")
    conn.execute("UPDATE drafts SET status='rejected', approved_hash=NULL, updated_at=datetime('now') WHERE id=?",
                 (draft_id,))
    conn.commit()


def _resend_send(payload: dict) -> str:
    import resend

    resend.api_key = env("RESEND_API_KEY")
    res = resend.Emails.send(payload)
    return res["id"] if isinstance(res, dict) else res.id


def send(conn, draft_id: int, sender=_resend_send) -> dict:
    """Re-checks status and content hash in the DB, blocks duplicates, always sends to MY_EMAIL."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        d = _draft(conn, draft_id)
        if d["status"] == "sent":
            raise DeliveryError("already sent")
        if d["status"] != "approved":
            raise DeliveryError(f"draft is '{d['status']}', not approved")
        if d["approved_hash"] != drafting.draft_hash(d["subject"], d["body"]):
            raise DeliveryError("content changed since approval; approve again")
        dry = db.get_setting(conn, "dry_run", "false") == "true"
        to = env("MY_EMAIL")  # the only recipient, ever; the prospect appears only in the body
        contact = conn.execute("SELECT * FROM contacts WHERE id=?", (d["contact_id"],)).fetchone()
        if dry:
            conn.execute("INSERT INTO sends (draft_id, to_email, subject, body, status) VALUES (?,?,?,?, 'dry_run')",
                         (draft_id, to, d["subject"], d["body"]))
            conn.commit()
            return {"status": "dry_run", "to": to}
        cur = conn.execute("INSERT INTO sends (draft_id, to_email, subject, body, status) VALUES (?,?,?,?, 'sending')",
                           (draft_id, to, d["subject"], d["body"]))  # unique index blocks a second live send
        send_id = cur.lastrowid
        conn.commit()
    except db.IntegrityErrors:
        conn.rollback()
        raise DeliveryError("a send for this draft is already in progress or done")
    except Exception:
        conn.rollback()
        raise
    note = f"[Prospect preview: {contact['first_name']} {contact['last_name']} <{contact['email']}> - sent to you only]\n\n"
    try:
        rid = sender({"from": env("SENDER_EMAIL", "onboarding@resend.dev"), "to": [to],
                      "subject": d["subject"], "text": note + d["body"]})
    except Exception as e:  # API failure: record it, leave the draft approved so a human can retry
        conn.execute("UPDATE sends SET status='failed', error=? WHERE id=?", (str(e)[:500], send_id))
        conn.commit()
        return {"status": "failed", "error": str(e)}
    conn.execute("UPDATE sends SET status='sent', resend_id=? WHERE id=?", (rid, send_id))
    conn.execute("UPDATE drafts SET status='sent', updated_at=datetime('now') WHERE id=?", (draft_id,))
    conn.commit()
    return {"status": "sent", "resend_id": rid, "to": to}
