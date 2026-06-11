# AI Roadmap & Recommendations

Talking points for proposing how AI can move a steel / security / fire door business forward. Ordered roughly by effort-to-value.

> All ideas assume real product, pricing, and compliance data is supplied by the business. Nothing here invents fire ratings or prices.

## 1. AI-assisted quoting + chatbot (this demo)

- Natural-language intake that drives a **deterministic** quoting engine.
- Key principle: **the LLM handles conversation, the engine handles numbers.** Avoids hallucinated prices, essential in a compliance-sensitive trade.
- Next steps: real price list, account-specific pricing, save/email quote, human handoff.

## 2. RAG support assistant

- Retrieval-augmented chatbot grounded in product specs, fire-rating certificates, installation guides, and building-regulation references.
- Answers "does this door meet FD60 for an escape route?" with **cited sources**, not guesses.

## 3. Document & spec extraction

- Parse architect drawings, PDF schedules, and tender documents to auto-populate orders and quotes.
- OCR + structured extraction; flag low-confidence fields for human review.

## 4. CRM / ERP integration

- Push qualified leads and quotes into the existing CRM/ERP automatically.
- Classify and route enquiries (new build vs repair, B2B vs B2C, region).
- Integration concerns: auth, rate limits, idempotency, retries, audit logging.

## 5. Image-based product suggestion

- Customer uploads a photo of an opening; suggest suitable door types/finishes.
- Vision model first pass, human confirms before quoting.

## 6. Operational & data quality

- Quote-evaluation harness against known-good cases.
- Monitoring for drift, latency, cost; cache common queries.
- GDPR: data minimisation, retention policy, human in the loop for customer-facing output.

## Engineering principles demonstrated

- Deterministic core logic, AI at the edges.
- Pluggable LLM provider (mock by default so the demo always runs).
- Tests + CI from day one.
- Clear separation of models, business logic, orchestration, and UI.
