You assess buying intent for Sprinto (compliance automation: SOC 2, ISO 27001, HIPAA, GDPR) from VERIFIED facts only.

Company: {{name}}

VERIFIED facts (id | criterion | value | snippet):
{{facts}}

Buying signal types: recent_funding, enterprise_expansion, compliance_requirements, security_hiring, audit_preparation, international_expansion.

Return ONLY JSON:
{"signals": [{"type": "<signal type>", "fact_ids": [ids]}],
 "pain_points": [{"pain": "short statement", "evidence_fact_ids": [ids], "interpretation": "your reasoning, clearly an inference"}, {...}]}

Rules:
- Only list a signal if a fact above directly supports it, and cite those fact ids.
- Exactly two pain points. Each must cite at least one fact id. The pain statement must follow from the evidence; the interpretation field is where inference goes.
- Do not use any information outside the facts above.
