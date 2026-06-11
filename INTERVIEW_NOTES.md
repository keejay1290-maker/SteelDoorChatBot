# Interview Notes — Steel Door Company AI Integration

Prepared for the AI Software Developer (Systems Integration) interview.
Use these as talking points, not a script.

---

## What this demo shows

- AI-assisted quoting assistant with a deterministic pricing engine.
- Design principle: LLM handles conversation, the engine handles every number — no hallucinated prices.
- Pluggable LLM (mock / Groq / DeepSeek). Works zero-config with the mock provider.
- Real prices from their Shopify product feed (steeldoorcompany.co.uk/products.json).
- Real product images scraped from their site via Playwright.
- Full lead capture, quote persistence to SQLite, conversation history.
- 36 passing tests. FastAPI + Pydantic + SQLite. Dockerised.

---

## Price discrepancies — raise at interview

| Product       | Homepage "from" | Shopify products.json | This demo  |
|---------------|-----------------|-----------------------|------------|
| Single door   | £1,500          | £1,700                | £1,700     |
| Double doors  | £2,800          | £3,000                | £3,000     |
| Double baseline height | listed as 980mm on products.json | real door = ~1980mm | corrected to 1980mm |

Talking point: "I noticed the homepage shows £1,500 for a single door but the Shopify product feed says £1,700. Which is current? For any quoting tool there needs to be one source of truth — ideally a live pricing API or admin-editable pricing table, not hardcoded values in two places."

---

## Security observations on steeldoorcompany.co.uk

1. No HSTS header — `Strict-Transport-Security` not set on the Shopify store. HTTP requests aren't force-upgraded at CDN level. Configure in Shopify admin > Online Store > Preferences.

2. No Content Security Policy — `Content-Security-Policy` header absent. Shopify injects many third-party scripts; a CSP limits XSS blast radius.

3. No rate limiting on API endpoints (this demo) — before any public exposure, `/api/chat` and `/api/quote` need rate limiting (slowapi / Redis). Unprotected, a bot can spam the LLM and burn API credits in minutes.

4. Customer PII in SQLite — fine for demo. Production needs Postgres with encrypted backups, row-level access control, and a GDPR retention + deletion policy. The enquiry form collects name/email/phone/postcode — all personal data requiring a lawful basis and a privacy notice.

5. No CSRF protection on the enquiry form — `/api/enquiry` accepts JSON from any origin. Needs a CORS allowlist and SameSite cookie policy before production.

6. LLM API key management — local .env is correct. On Railway/Fly.io, inject as encrypted environment secrets; never commit keys. The .gitignore is set correctly but confirm CI pipelines don't echo env vars in logs.

7. No authentication on `/api/catalogue` — publicly exposes all pricing data. Acceptable if that's the intent. If not, add bearer token auth.

---

## Missing features worth proposing

### Quick wins (under a day each)

1. Email the quote — branded PDF to the customer + notification to sales@steeldoorcompany.co.uk via SMTP or SendGrid when a lead is captured. ~50 lines.

2. Quote PDF generation — ReportLab or WeasyPrint. A printable A4 quote with Steel Door Company branding. Practically useful, impressive in a demo.

3. Quote reference lookup — GET /api/quote/{reference} so sales staff can retrieve any past estimate. Quotes are persisted to DB but not yet retrievable via API.

4. Input clarification loop — when the bot can't extract a required field (size, type), ask one specific follow-up question instead of using defaults. Would improve quote accuracy meaningfully.

### Medium (1-3 days each)

5. RAG on product specs — embed PDFs of fire-rating certificates, installation guides, and building-regulation references into a vector store (Chroma or Pinecone). Let the chatbot answer "does this door meet FD60 for an escape corridor?" with cited sources. This is the highest-value AI integration for a compliance-sensitive product.

6. Structured LLM extraction — replace the regex extractor with an LLM function-call returning a validated QuoteRequest JSON, keeping regex as fallback. More robust for unusual phrasing and multi-item orders.

7. Image-based product suggestion — customer uploads a photo of their opening; a vision model (Claude or GPT-4o) suggests suitable door types and finishes; human confirms before quoting.

8. Architect drawing / PDF schedule extraction — parse uploaded PDF specifications or tender documents to auto-populate door schedules. OCR + structured extraction, flag low-confidence fields for human review.

### Strategic

9. CRM / ERP push — when a lead qualifies, push the quote and customer record to their CRM (HubSpot, Salesforce) or bespoke ERP. Needs auth, idempotency keys, retries, and an audit log.

10. Multi-channel intake — same engine via WhatsApp (Twilio), website widget, and email parsing. The FastAPI backend is already channel-agnostic.

11. Admin pricing UI — staff-editable pricing table with versioning and audit history, so prices can be updated without a code deploy.

12. Observability — LLM cost tracking, request/latency metrics (Prometheus + Grafana or LangSmith), structured JSON logging, alerting on error rate spikes.

---

## Architecture talking points

Why deterministic pricing?
Fire-rated, compliance-sensitive products. A hallucinated price that is too low creates a commercial dispute; too high loses the sale. The LLM never produces numbers — the pricing engine does, line by line, and every line is auditable.

Why FastAPI over Django/Flask?
Pydantic models give automatic request validation and OpenAPI docs at /docs, catching bad input at the API boundary before it reaches the pricing engine. Async-ready for streaming LLM responses (a near-term upgrade).

Why pluggable LLM?
Groq (free tier) for dev and demo. DeepSeek for cost-sensitive production. Claude for highest quality. Same interface, swapped via environment variable. No vendor lock-in.

Conversation history (added in this build)
The chat API now passes the last 10 turns of conversation to the LLM so it can reference earlier context ("you mentioned RAL 9005 earlier"). Mock provider ignores history; real providers use it for multi-step clarification.

Playwright image scraper (added in this build)
scripts/scrape_images.py fetches real product images from steeldoorcompany.co.uk and serves them from the FastAPI static directory. The chat UI shows the matching door photo alongside every quote. Good demo of automated asset pipeline and system integration.

---

## Things to confirm with Steel Door Company

- Current published prices (homepage vs Shopify discrepancy)
- Glass uplift amounts (currently estimated)
- External weatherproofing and mechanism uplift amounts (currently estimated)
- Side panel price (currently £400 estimated)
- Whether FD60 double-leaf doors are offered (products.json only lists up to FD30 / E30)
- Wine room door availability and real pricing
- GDPR lawful basis for storing enquiry data
- Permission to use their brand, logo, and product images

---

## Run the demo

    cd steeldoorai-demo-main
    .venv\Scripts\activate
    uvicorn app.main:app --reload
    # open http://localhost:8000

To enable a real LLM (better natural language responses):

    # In .env:
    LLM_PROVIDER=groq
    GROQ_API_KEY=gsk_...    # free at console.groq.com/keys

To re-scrape product images from the live site:

    python scripts/scrape_images.py
