Extract facts about the company {{name}} ({{domain}}) from the page texts below.
Today is {{today}}.

Only extract these criteria:
{{criteria}}

Criterion definitions:
- funding_stage: latest funding round and amount.
- saas: "yes" or "no" - does the company sell subscription software?
- audit_signals: security/compliance job posts (GRC, security engineer, compliance manager), or a trust/security page stating SOC 2 / ISO 27001 status.
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
