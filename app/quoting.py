"""Deterministic, auditable quoting engine for Steel Door Company.

Base prices are REAL published 'from' prices from the Shopify product feed.
Dimension scaling and option uplifts are rule-based and fully transparent.
Uplift amounts flagged TODO are estimates until confirmed with the business.

The LLM never sets prices. This engine does, line by line.
"""
from __future__ import annotations

import uuid

from .catalogue import CATALOGUE
from .models import QuoteRequest, QuoteResponse, QuoteLine

# ---------------------------------------------------------------------------
# Pricing table. All GBP inc. installation, exc. VAT.
# Base prices: REAL (Shopify feed, 2026-06-11).
# Uplifts marked TODO: confirm with Steel Door Company before customer use.
# ---------------------------------------------------------------------------
PRICING: dict = {
    # Base 'from' price by door_set (at catalogue baseline dimensions).
    "base": {
        "single": 1700.0,
        "double": 3000.0,
    },

    # Additional cost when door_type changes the product specification.
    # TODO: confirm exact figures with Steel Door Company.
    "door_type_uplift": {
        "internal": 0.0,
        "external": 800.0,     # weatherproofing, external-grade hardware, weatherseal
        "fire_rated": 1700.0,  # fire certification; 1700+1700 = 3400 = published FD30 price
        "wine_room": 600.0,    # humidity-resistant sealing, magnetic close, brush seal
    },

    # Additional cost for non-hinged mechanisms.
    # TODO: confirm exact figures with Steel Door Company.
    "mechanism_uplift": {
        "hinged": 0.0,
        "sliding": 1750.0,    # sliding track & hardware  (4750 - 3000)
        "concertina": 2250.0, # concertina system          (5250 - 3000)
    },

    # Glazing uplifts. TODO: confirm with Steel Door Company.
    "glass_uplift": {
        "clear": 0.0,
        "reeded": 120.0,
        "frosted": 100.0,
        "bespoke": 300.0,
    },

    # Fire-rating certification uplift (applied when explicitly requested ON TOP of base).
    # TODO: confirm with Steel Door Company.
    "fire_rating_uplift": {
        "none": 0.0,
        "FD30": 350.0,
        "FD60": 600.0,
    },

    "ral_colour_uplift": 150.0,   # Any RAL powder coat. TODO: confirm.
    "side_panel_each": 400.0,     # Fixed side panel. TODO: confirm.
    "threshold_uplift": {
        "flush": 0.0,
        "weathered": 80.0,
        "step_over": 0.0,
    },

    # Dimension scaling: charge per m2 of opening ABOVE the product baseline.
    # TODO: confirm rate with Steel Door Company.
    "scaling_per_m2": 260.0,

    # Summer Sale: 10% off, capped at GBP 1,000 (matches published offer).
    "sale_fraction": 0.10,
    "sale_cap": 1000.0,

    "vat_rate": 0.20,
}


def _resolve_catalogue_key(req: QuoteRequest) -> str:
    """Map door_set + door_type + mechanism to the nearest CATALOGUE entry."""
    if req.door_type == "fire_rated":
        return "fire_rated"
    if req.mechanism == "concertina":
        return "concertina"
    if req.mechanism == "sliding":
        return "sliding"
    if req.door_type == "external":
        return "external_patio"
    if req.door_type == "wine_room":
        return "wine_room"
    if req.door_set == "double":
        return "double"
    return "single"


def _area_m2(width_mm: float, height_mm: float) -> float:
    return (width_mm / 1000.0) * (height_mm / 1000.0)


def _quote_reference() -> str:
    return "SDA-" + uuid.uuid4().hex[:8].upper()


def calculate_quote(req: QuoteRequest) -> QuoteResponse:
    """Calculate an itemised, deterministic estimate for a bespoke door."""
    cat_key = _resolve_catalogue_key(req)
    product = CATALOGUE[cat_key]
    lines: list[QuoteLine] = []
    notes: list[str] = []

    # --- Base price ---
    base = PRICING["base"].get(req.door_set, PRICING["base"]["single"])
    lines.append(QuoteLine(label=f"{product['name']} — base (from)", amount=base))

    # --- Door type uplift ---
    type_uplift = PRICING["door_type_uplift"][req.door_type]
    if type_uplift:
        lines.append(QuoteLine(label=f"Door type ({req.door_type.replace('_', ' ')})", amount=type_uplift))

    # --- Mechanism uplift ---
    mech_uplift = PRICING["mechanism_uplift"][req.mechanism]
    if mech_uplift:
        lines.append(QuoteLine(label=f"Mechanism ({req.mechanism})", amount=mech_uplift))

    # --- Dimension scaling above the product's published baseline ---
    baseline_area = _area_m2(product["baseline_w_mm"], product["baseline_h_mm"])
    area = _area_m2(req.width_mm, req.height_mm)
    if area > baseline_area:
        scaling = round((area - baseline_area) * PRICING["scaling_per_m2"], 2)
        lines.append(QuoteLine(label=f"Size uplift ({area:.2f} m² opening)", amount=scaling))

    # --- Glass ---
    glass_uplift = PRICING["glass_uplift"][req.glass]
    if glass_uplift:
        lines.append(QuoteLine(label=f"Glazing — {req.glass}", amount=glass_uplift))

    # --- Explicit fire rating (on top of base fire_rated type cost) ---
    fire_uplift = PRICING["fire_rating_uplift"][req.fire_rating]
    if fire_uplift:
        lines.append(QuoteLine(label=f"Fire rating certification ({req.fire_rating})", amount=fire_uplift))

    # --- RAL colour ---
    if req.ral_colour:
        lines.append(QuoteLine(label=f"Custom RAL colour ({req.ral_colour})", amount=PRICING["ral_colour_uplift"]))

    # --- Side panels ---
    if req.side_panels:
        panel_cost = round(PRICING["side_panel_each"] * req.side_panels, 2)
        lines.append(QuoteLine(label=f"Fixed side panels ×{req.side_panels}", amount=panel_cost))

    # --- Threshold ---
    threshold_uplift = PRICING["threshold_uplift"].get(req.threshold, 0.0)
    if threshold_uplift:
        lines.append(QuoteLine(label=f"Threshold ({req.threshold.replace('_', ' ')})", amount=threshold_uplift))

    # --- Totals ---
    unit_price = round(sum(ln.amount for ln in lines), 2)
    gross = round(unit_price * req.quantity, 2)

    raw_discount = gross * PRICING["sale_fraction"]
    sale_discount = round(min(raw_discount, PRICING["sale_cap"]), 2)
    if sale_discount:
        notes.append(
            f"Summer Sale applied: {int(PRICING['sale_fraction'] * 100)}% off "
            f"(capped at GBP {PRICING['sale_cap']:.0f})."
        )

    subtotal = round(gross - sale_discount, 2)
    vat = round(subtotal * PRICING["vat_rate"], 2)
    total = round(subtotal + vat, 2)

    notes.append(
        "Base 'from' prices are published by Steel Door Company. Size scaling and option "
        "uplifts are estimates for this demo — confirmed only after a free site survey."
    )
    notes.append("Delivery and installation priced separately after survey.")

    return QuoteResponse(
        reference=_quote_reference(),
        product_name=product["name"],
        lines=lines,
        unit_price=unit_price,
        quantity=req.quantity,
        subtotal=subtotal,
        sale_discount=sale_discount,
        vat=vat,
        total=total,
        lead_time=product["lead_time"],
        image_url=product.get("image_url"),
        notes=notes,
    )
