You are doing a quick triage of sales prospects for a compliance-automation vendor.
Use Google Search. Today is {{today}}.

For each company below, quickly determine:
- is_saas: true/false/null (sells software as a subscription service)
- funding_stage: "Seed", "Series A", "Series B", "Series C", "Series D+", "Public", "Bootstrapped" or null
- industry: a short phrase or null
- fit: integer 0-10, how likely this is a SaaS company at Series A-C that needs its first SOC 2 / ISO 27001 audit

Companies:
{{companies}}

Return ONLY a JSON array, one item per company, in the same order:
{"domain": "...", "is_saas": true, "funding_stage": "Series B", "industry": "...", "fit": 7}

Use null when unknown. Do not guess. This is a rough triage; full verification happens later.
