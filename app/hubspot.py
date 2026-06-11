"""HubSpot CRM integration — push qualified leads to Contact + Deal.

Env vars (all optional — graceful no-op if absent):
  HUBSPOT_ACCESS_TOKEN    — private app token (required to send anything)
  HUBSPOT_PIPELINE_ID     — pipeline ID for the deal (default: "default")
  HUBSPOT_PIPELINE_STAGE  — stage ID for new deals (default: "appointmentscheduled")
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .session import ConversationSession

logger = logging.getLogger(__name__)

_HS_BASE = "https://api.hubapi.com/crm/v3/objects"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['HUBSPOT_ACCESS_TOKEN']}",
        "Content-Type": "application/json",
    }


def _post(url: str, payload: dict) -> dict:
    import httpx
    resp = httpx.post(url, headers=_headers(), json=payload, timeout=15.0)
    if resp.status_code == 429:
        import time
        time.sleep(2)
        resp = httpx.post(url, headers=_headers(), json=payload, timeout=15.0)
    resp.raise_for_status()
    return resp.json()


def push_to_hubspot(s: "ConversationSession", quote_total: Optional[float] = None) -> bool:
    """Create/update HubSpot Contact and associated Deal for a qualified lead.

    Returns True on success, False (with logged warning) on any error.
    No-ops silently if HUBSPOT_ACCESS_TOKEN is not set.
    """
    token = os.environ.get("HUBSPOT_ACCESS_TOKEN", "")
    if not token:
        return False

    pipeline = os.environ.get("HUBSPOT_PIPELINE_ID", "default")
    stage = os.environ.get("HUBSPOT_PIPELINE_STAGE", "appointmentscheduled")

    try:
        # 1. Upsert Contact by email
        contact_props: dict = {}
        if s.email:
            contact_props["email"] = s.email
        if s.name:
            parts = s.name.strip().split(" ", 1)
            contact_props["firstname"] = parts[0]
            if len(parts) > 1:
                contact_props["lastname"] = parts[1]
        if s.phone:
            contact_props["phone"] = s.phone
        if s.postcode:
            contact_props["zip"] = s.postcode

        contact_id: Optional[str] = None
        if contact_props.get("email"):
            # Try create; fall back to search-by-email on conflict (409)
            import httpx
            resp = httpx.post(
                f"{_HS_BASE}/contacts",
                headers=_headers(),
                json={"properties": contact_props},
                timeout=15.0,
            )
            if resp.status_code == 409:
                # Already exists — fetch by email
                search_resp = httpx.post(
                    "https://api.hubapi.com/crm/v3/objects/contacts/search",
                    headers=_headers(),
                    json={
                        "filterGroups": [{"filters": [{
                            "propertyName": "email",
                            "operator": "EQ",
                            "value": s.email,
                        }]}]
                    },
                    timeout=15.0,
                )
                search_resp.raise_for_status()
                results = search_resp.json().get("results", [])
                if results:
                    contact_id = results[0]["id"]
                    # Patch existing contact with latest details
                    httpx.patch(
                        f"{_HS_BASE}/contacts/{contact_id}",
                        headers=_headers(),
                        json={"properties": contact_props},
                        timeout=15.0,
                    )
            else:
                resp.raise_for_status()
                contact_id = resp.json()["id"]

        # 2. Build deal name and properties
        door_label = (s.door_set or "door").title()
        if s.door_type:
            door_label += f" ({s.door_type.replace('_', ' ')})"
        deal_name = f"{s.name or s.email or 'Lead'} — {door_label}"

        deal_props: dict = {
            "dealname": deal_name,
            "pipeline": pipeline,
            "dealstage": stage,
        }
        if quote_total is not None:
            deal_props["amount"] = str(round(quote_total, 2))
        if s.postcode:
            deal_props["description"] = f"Postcode: {s.postcode}"
        if s.door_type:
            deal_props["description"] = (
                deal_props.get("description", "")
                + f"\nDoor type: {s.door_type.replace('_', ' ')}"
            ).strip()
        if s.mechanism:
            deal_props["description"] = (
                deal_props.get("description", "")
                + f"\nMechanism: {s.mechanism}"
            ).strip()
        if s.routing:
            deal_props["description"] = (
                deal_props.get("description", "")
                + f"\nRouting: {s.routing}"
            ).strip()

        deal_data = _post(f"{_HS_BASE}/deals", {"properties": deal_props})
        deal_id = deal_data["id"]

        # 3. Associate deal with contact (if we have one)
        if contact_id and deal_id:
            import httpx
            httpx.put(
                f"https://api.hubapi.com/crm/v3/objects/deals/{deal_id}"
                f"/associations/contacts/{contact_id}/deal_to_contact",
                headers=_headers(),
                timeout=15.0,
            )

        logger.info(
            "HubSpot OK: contact=%s deal=%s score=%s name=%s",
            contact_id, deal_id, s.readiness_score, s.name,
        )
        return True

    except Exception as exc:
        logger.error("HubSpot push FAILED: %s", exc, exc_info=True)
        return False
