# Build: Sprinto Outbound Pipeline (Python CLI)

Sprinto automates compliance (SOC 2, ISO 27001, HIPAA, GDPR) for SaaS companies.
Build a pipeline that finds ICP-fit companies, qualifies them, finds a contact,
drafts an email, and sends only after my approval. Plan first, then build.

## Stack
Python, google-genai (Gemini + Google Search grounding), httpx + trafilatura
(scraping), Hunter.io API, resend SDK, SQLite, typer CLI.
Keys in .env: GEMINI_API_KEY, HUNTER_API_KEY, RESEND_API_KEY, SENDER_EMAIL.
ICP weights, thresholds, and limits go in config.yaml.

## Hard rules
1. Only VERIFIED facts may appear in emails.
2. Nothing is sent without my APPROVE on that exact draft. Send is dry-run by default.
3. Missing data = NOT_FOUND. Never guess.
4. A company that fails a gate stops there, with the reason saved.

## Verification (done in code, not by the model)
Gemini returns facts as {criterion, value, source_url, snippet}.
A fact is VERIFIED only if:
- the URL came from Gemini's grounding metadata or our scraper,
- the page fetches and contains the snippet, and
- the page has a date within the recency window (funding 18 mo, hiring 6 mo,
  news 12 mo).
Otherwise label it ASSERTED or STALE. Only VERIFIED facts count anywhere.

## Stages
1. **Discover**: Gemini news search for Series A–C SaaS companies with recent
   funding, enterprise wins, or SOC 2 / ISO prep. Get 40 candidates.
2. **Shortlist**: quick check (SaaS, stage, industry). Keep the best 10–20.
3. **Research**: Gemini first; for gaps, scrape homepage, /about, /careers
   (plus ATS pages), /security or /trust. Criteria:
   - funding stage
   - SaaS (must-have)
   - audit signals (compliance or security job posts, trust page status)
   - employee count
   - customers (count and enterprise logos)
   - industry
   - cloud (AWS / GCP / Azure)
   - competitor in use (Vanta, Drata, Secureframe, etc.)
4. **ICP gate**: score in code from VERIFIED facts only.
   - Pass if score ≥ threshold AND audit signals are VERIFIED.
   - Stop if not SaaS, already certified with a competitor, or fewer than
     3 VERIFIED facts.
5. **Qualify**: Gemini sees only VERIFIED facts. It returns:
   - a "why now" trigger (as a fact id),
   - a persona by size (<50: CEO/CTO; 50–200: CTO/VP Eng; 200+: CISO/GRC), and
   - QUALIFIED / LOW_PRIORITY / NOT_QUALIFIED.
6. **Contact**: Hunter domain-search for the persona, then email-verifier.
   Keep only "valid" with confidence ≥ 80. Never guess email addresses.
7. **Draft**: Gemini returns {subject, sentences: [{text, fact_ids}]}.
   The email has three parts: the trigger, why it creates audit pressure,
   and what Sprinto does, then a soft ask. Limits: under 120 words,
   subject under 8 words.
   The code validator checks that:
   - every factual sentence cites VERIFIED fact ids, and
   - every number or name in the body appears in a cited fact.
   Regenerate up to 2 times on failure. If there's no trigger, don't draft.
   Code adds the footer: sender address and an unsubscribe line.
8. **Review**: `pipeline review` shows company, score, contact, email, and
   sources. Options: approve / edit (re-validates) / reject.
   An edit after approval resets the draft to pending.
9. **Send**: `pipeline send --live` sends APPROVED drafts only, after
   re-checking status in the DB. Respect the daily limit and log the Resend id.

## Also
- Cache all API responses.
- Respect robots.txt.
- Keep Gemini prompts in prompts/*.md.
- Add tests for verification, the ICP gate, the email validator, and send
  refusing unapproved drafts.
- `pipeline run` runs stages 1–7.
- `pipeline report` shows counts and stop reasons.

After stage 3 works, run it on 2 real companies and show me the facts table
before continuing.
