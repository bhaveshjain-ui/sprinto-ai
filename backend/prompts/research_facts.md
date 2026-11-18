You are researching one company for Sprinto (compliance automation). Use Google Search. Today is {{today}}.

Company: {{name}} ({{domain}})

Find facts for these criteria, only those you can support with a source:
{{criteria}}

Criterion definitions:
- funding_stage: latest funding round, e.g. "Series B, $30M, March 2026".
- saas: "yes" or "no" - does the company sell subscription software?
- audit_signals: the company's compliance STATUS. Begin the value with exactly one tag: "CERTIFIED: " if they already hold a certification or attestation (SOC 2, ISO 27001, HIPAA...), "IN PROGRESS: " if they are preparing for one (trust page says in progress, readiness work, planned first audit), or "HIRING: " for security/compliance/GRC job posts. Always report certification evidence if it exists: already-certified companies are NOT targets, so this matters as much as finding a need.
- employee_count: a number of employees.
- customers: customer count and/or named enterprise customers.
- industry: short phrase.
- cloud: AWS, GCP or Azure (as stated by the company or a job post).
- competitor: name of a compliance-automation tool the company uses or is certified through (Vanta, Drata, Secureframe, Thoropass, etc.).

Return ONLY a JSON array of facts (several per criterion allowed):
{"criterion": "...", "value": "short factual value", "source_url": "https://...", "snippet": "..."}

Rules:
- Make sure the source is about THIS company ({{name}}, {{domain}}) and not a similarly named one.
- snippet MUST be copied verbatim from the source page, 15+ characters.
- source_url MUST be a page you actually found through search. Never invent a URL.
- Any number in value must also appear in snippet. Never use industry averages.
- Omit any criterion you cannot support. Never guess.
