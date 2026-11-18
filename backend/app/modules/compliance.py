"""Compliance status of a prospect, derived from its VERIFIED audit_signals facts only.

Sprinto sells to companies that still NEED compliance. So:
  certified    -> already holds SOC 2 / ISO 27001 / HIPAA etc.   => not a target (low priority)
  in_progress  -> preparing for an audit, or hiring to build the programme => the target
  unknown      -> verified mentions we cannot read as either way, or no audit evidence at all
Precedence: certified > in_progress > unknown (holding a certification wins, even if they are also hiring).
A job posting that merely mentions a framework is hiring evidence, never proof of certification.
"""
import re

FRAMEWORKS = [
    ("SOC 2", r"soc\s?2"), ("SOC 1", r"soc\s?1"), ("ISO 27001", r"iso(?:/iec)?\s?27001"), ("ISO 27701", r"27701"),
    ("ISO 42001", r"42001"), ("HIPAA", r"hipaa"), ("GDPR", r"gdpr"), ("PCI DSS", r"pci[\s-]?dss"),
]

# the text says they HOLD it
CERT = re.compile(r"\b(certified|certifications?|attestations?|attested|compliant|audited|holds?|maintains?|"
                  r"type\s?(?:ii|2)\b|achiev(?:ed|ing)|passed)\b", re.I)
# the text is a job posting (a framework named there is a duty, not a credential)
JOB = re.compile(r"\b(job (?:opening|posting)|hiring|apply|view role|you(?:'ll| will)|you've|responsibilities|your role|"
                 r"what you|we're looking|join (?:us|our))\b", re.I)
# explicit "working toward it"
PREP = re.compile(r"\b(in progress|preparing|preparation|pursuing|working (?:toward|towards|on)|readiness|ready for|"
                  r"planning|planned|undergoing|underway|seeking|roadmap|upcoming|first audit|prepare)\b", re.I)
# a role that exists to build/own compliance
ROLE = re.compile(r"\b(grc|compliance (?:manager|analyst|lead|officer|specialist)|head of (?:security|compliance|information security)|"
                  r"security (?:engineer|lead|manager)|ciso|infosec|information security)\b", re.I)


def _frameworks(text: str) -> list[str]:
    return [name for name, rx in FRAMEWORKS if re.search(rx, text, re.I)]


def classify(audit_facts: list[dict]) -> dict:
    """audit_facts: facts for the audit_signals criterion (any status; only VERIFIED, non-conflicting ones count)."""
    cert, prog, strong_prog, hiring = [], [], [], []
    for f in audit_facts:
        if f.get("status") != "VERIFIED" or f.get("conflict"):
            continue
        text = f"{f.get('value') or ''} {f.get('snippet') or ''}"
        is_job = bool(JOB.search(text)) or (bool(ROLE.search(f.get("value") or "")) and not CERT.search(f.get("value") or ""))
        if CERT.search(text) and not is_job:
            cert.append(f)
        elif PREP.search(text):
            prog.append(f)
            strong_prog.append(f)
        elif is_job or ROLE.search(text):
            prog.append(f)
            hiring.append(f)
    if cert:
        fw = sorted({x for f in cert for x in _frameworks(f"{f.get('value') or ''} {f.get('snippet') or ''}")})
        also = " (also working on more)" if prog else ""
        return {"status": "certified", "frameworks": fw, "evidence": [f["id"] for f in cert],
                "reason": f"already holds {', '.join(fw) or 'a compliance certification'}{also}"}
    if prog:
        fw = sorted({x for f in prog for x in _frameworks(f"{f.get('value') or ''} {f.get('snippet') or ''}")})
        return {"status": "in_progress", "frameworks": fw, "evidence": [f["id"] for f in prog], "strong": bool(strong_prog),
                "reason": "preparing for compliance" if strong_prog else "hiring to build a security/compliance programme"}
    seen = [f for f in audit_facts if f.get("status") == "VERIFIED" and not f.get("conflict")]
    return {"status": "unknown", "frameworks": [], "evidence": [f["id"] for f in seen],
            "reason": "verified audit mentions are unclear" if seen else "no audit evidence verified"}


def label(status: str) -> str:
    return {"certified": "Already compliant", "in_progress": "Seeking compliance", "unknown": "Unknown"}.get(status, status)
