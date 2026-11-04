Write a short, natural cold email from {{sender_name}} at Sprinto to {{contact_first}} ({{contact_position}}) at {{company}}.

Sprinto automates compliance (SOC 2, ISO 27001, HIPAA, GDPR) so SaaS teams get audit-ready faster without spreadsheets and manual evidence collection.

VERIFIED facts about {{company}} (id | value | snippet):
{{facts}}

Why-now signals: {{signals}}
Pain points (evidence-based): {{pains}}

Return ONLY JSON:
{"subject": "...", "sentences": [{"kind": "trigger|pressure|offer|ask", "text": "...", "fact_ids": [ids]}]}

Structure, in this order, 4-5 sentences total:
1. trigger: a specific hook from a verified fact (why now). Cite fact ids.
2. pressure: why that creates audit/compliance pressure for them. Cite fact ids.
3. offer: what Sprinto does about it (no fact ids needed, no invented claims or stats).
4. ask: one soft call to action, e.g. a short chat. 

Hard rules:
- Body under 110 words; subject at most 7 words, no clickbait.
- Do NOT write a greeting or signature; code adds them.
- Every number and every proper name in trigger/pressure sentences must appear in the cited facts.
- Never mention anything not in the facts. No exaggerated claims, no "I noticed" fluff, no placeholders.
{{previous_errors}}
