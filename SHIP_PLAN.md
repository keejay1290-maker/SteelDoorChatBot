# Ship-in-a-day plan

Goal: a working, demonstrable instant-estimate + lead-capture assistant for Steel Door
Company that runs on a host **you control** (not their live Shopify site).

> Positioning: this gives an **instant indicative estimate** and captures the enquiry.
> It is not a binding quote - every door is made to measure and confirmed after a survey.
> This matches their published "Same Day Quote" promise and is honest about bespoke pricing.

## Done
- [x] Real product model: single/double, internal/external/fire-rated/wine-room, hinged/sliding,
      glass (transparent/opaque/reeded), any RAL colour, side panels, oversize, Summer Sale.
- [x] Deterministic quoting engine (LLM never sets prices).
- [x] Chatbot intake (mock by default, DeepSeek pluggable).
- [x] Lead capture: `/api/enquiry` + SQLite store.
- [x] Branded landing UI: USP bar, chat, enquiry form, contact/trust footer.
- [x] Tests + CI + Docker + Makefile.

## To finish for a credible demo (priority order)
1. **Confirm real uplift prices** with Steel Door Company (the only honest fix for accuracy).
2. **Email the enquiry** to sales@steeldoorcompany.co.uk (SMTP) and send the customer a copy.
3. **Wire DeepSeek** (`LLM_PROVIDER=deepseek` + key in `.env`) for natural replies.
4. **Deploy** to a host you control (see below) with HTTPS.
5. **Handles / finishes** (lever, pull, hammered; bronze / RAL) as quote options.
6. **Light analytics**: count estimates vs enquiries (conversion).

## Deployment (host YOU control)
Do not deploy under their domain/branding publicly until they ask. Good options:
- **Fly.io / Render / Railway**: `Dockerfile` is already provided; point the platform at the repo.
- Set env: `LLM_PROVIDER`, `DEEPSEEK_API_KEY`, `ENQUIRY_DB` (use a persistent volume or Postgres).
- Add a real domain + HTTPS; put it behind basic auth if it's just for the interview.

## Before any real/public use
- Replace SQLite with Postgres + backups.
- Add auth + rate limiting on the API.
- GDPR: privacy notice on the form, retention policy, lawful basis for storing leads.
- Get written sign-off from Steel Door Company to use their brand/content.
