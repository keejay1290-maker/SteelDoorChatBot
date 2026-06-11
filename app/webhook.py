"""Outbound CRM webhook — fires a JSON POST to WEBHOOK_URL when a session qualifies.

All env vars optional; if WEBHOOK_URL is not set, calls are silently no-ops.

Required env var:
    WEBHOOK_URL  — full URL to POST to (e.g. a HubSpot, Zapier, or Make.com endpoint)

Optional:
    WEBHOOK_SECRET  — if set, added as X-Webhook-Secret header for receiver verification
"""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)


def fire_webhook(payload: dict) -> bool:
    """POST payload as JSON to WEBHOOK_URL. Returns True on 2xx, False on error/not-configured."""
    url = os.environ.get("WEBHOOK_URL", "").strip()
    if not url:
        return False

    headers: dict[str, str] = {"Content-Type": "application/json"}
    secret = os.environ.get("WEBHOOK_SECRET", "").strip()
    if secret:
        headers["X-Webhook-Secret"] = secret

    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=10.0)
        resp.raise_for_status()
        logger.info("Webhook fired to %s — %s", url, resp.status_code)
        return True
    except Exception as exc:
        logger.warning("Webhook failed: %s", exc)
        return False
