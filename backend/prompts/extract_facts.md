Extract facts about the company {{name}} ({{domain}}) from the page texts below.
Today is {{today}}.

Only extract these criteria:
{{criteria}}

Criterion definitions:
- funding_stage: latest funding round and amount.
- saas: "yes" or "no" - does the company sell subscription software?
- audit_signals: the company's compliance STATUS. Begin the value with exactly one tag: "CERTIFIED: " if they already hold a certification or attestation (SOC 2, ISO 27001, HIPAA...), "IN PROGRESS: " if they are preparing for one (trust page says in progress, readiness work, planned first audit), or "HIRING: " for security/compliance/GRC job posts. Always report certification evidence if it exists: already-certified companies are NOT targets, so this matters as much as finding a need.
- employee_count: a number of employees.
- customers: customer count and/or named enterprise customers.
- industry: short phrase.
- cloud: AWS, GCP or Azure.
- competitor: a compliance-automation tool in use (Vanta, Drata, Secureframe, Thoropass, etc.).

Return ONLY a JSON array. Each item:
{"criterion": "...", "value": "short factual value", "source_url": "the URL of the page the snippet came from", "snippet": "..."}

Rules:
- snippet MUST be copied verbatim from that page's text, 15+ characters.
- source_url MUST be exactly one of the page URLs below.
- Any number in value must also appear in snippet.
- Omit anything the pages do not state. Never guess.

PAGES:
{{pages}}
