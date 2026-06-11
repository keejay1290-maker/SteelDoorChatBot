"""Tests for the deterministic quoting engine (Steel Door Company model)."""
from app.catalogue import CATALOGUE
from app.models import QuoteRequest
from app.quoting import PRICING, calculate_quote, _area_m2


def test_area_m2():
    assert _area_m2(1000, 2000) == 2.0


def test_quote_has_reference():
    q = calculate_quote(QuoteRequest(door_set="single"))
    assert q.reference.startswith("SDA-")
    assert len(q.reference) == 12


def test_single_base_price():
    """At baseline dimensions, unit price == published 'from' price."""
    cat = CATALOGUE["single"]
    req = QuoteRequest(
        door_set="single",
        width_mm=cat["baseline_w_mm"],
        height_mm=cat["baseline_h_mm"],
    )
    q = calculate_quote(req)
    assert q.unit_price == PRICING["base"]["single"]  # £1,700


def test_double_base_price():
    """At baseline dimensions, unit price == published 'from' price."""
    cat = CATALOGUE["double"]
    req = QuoteRequest(
        door_set="double",
        width_mm=cat["baseline_w_mm"],
        height_mm=cat["baseline_h_mm"],
    )
    q = calculate_quote(req)
    assert q.unit_price == PRICING["base"]["double"]  # £3,000


def test_fire_rated_base_price():
    """fire_rated type hits the fire_rated base + uplift = published FD30 price."""
    cat = CATALOGUE["fire_rated"]
    req = QuoteRequest(
        door_set="single",
        door_type="fire_rated",
        width_mm=cat["baseline_w_mm"],
        height_mm=cat["baseline_h_mm"],
    )
    q = calculate_quote(req)
    expected = (
        PRICING["base"]["single"]
        + PRICING["door_type_uplift"]["fire_rated"]
    )
    # 1700 + 1700 = 3400 — matches real published fire door price
    assert q.unit_price == round(expected, 2)


def test_uplifts_accumulate():
    """All selected options stack additively on the base."""
    cat = CATALOGUE["double"]
    req = QuoteRequest(
        door_set="double",
        door_type="external",
        mechanism="sliding",
        glass="reeded",
        ral_colour="RAL 9005",
        side_panels=2,
        width_mm=cat["baseline_w_mm"],
        height_mm=cat["baseline_h_mm"],
    )
    q = calculate_quote(req)
    expected = (
        PRICING["base"]["double"]
        + PRICING["door_type_uplift"]["external"]
        + PRICING["mechanism_uplift"]["sliding"]
        + PRICING["glass_uplift"]["reeded"]
        + PRICING["ral_colour_uplift"]
        + PRICING["side_panel_each"] * 2
    )
    assert q.unit_price == round(expected, 2)


def test_summer_sale_capped():
    """On a large order, the 10% discount cannot exceed GBP 1,000."""
    req = QuoteRequest(
        door_set="double",
        quantity=10,
        width_mm=CATALOGUE["double"]["baseline_w_mm"],
        height_mm=CATALOGUE["double"]["baseline_h_mm"],
    )
    q = calculate_quote(req)
    assert q.sale_discount == PRICING["sale_cap"]


def test_vat_and_total_consistent():
    req = QuoteRequest(
        door_set="single",
        width_mm=CATALOGUE["single"]["baseline_w_mm"],
        height_mm=CATALOGUE["single"]["baseline_h_mm"],
    )
    q = calculate_quote(req)
    assert q.vat == round(q.subtotal * 0.20, 2)
    assert q.total == round(q.subtotal + q.vat, 2)


def test_oversize_uplift_applied():
    """An oversized door costs more than the baseline."""
    small = calculate_quote(QuoteRequest(
        door_set="single",
        width_mm=CATALOGUE["single"]["baseline_w_mm"],
        height_mm=CATALOGUE["single"]["baseline_h_mm"],
    ))
    large = calculate_quote(QuoteRequest(
        door_set="single",
        width_mm=1000,
        height_mm=3000,
    ))
    assert large.unit_price > small.unit_price


def test_wine_room_door():
    """Wine room type resolves to wine_room product and applies the uplift."""
    req = QuoteRequest(door_set="single", door_type="wine_room")
    q = calculate_quote(req)
    assert "Wine" in q.product_name
    assert q.unit_price > PRICING["base"]["single"]


def test_concertina_mechanism():
    """Concertina mechanism applies the concertina uplift."""
    req = QuoteRequest(
        door_set="double",
        mechanism="concertina",
        width_mm=CATALOGUE["double"]["baseline_w_mm"],
        height_mm=CATALOGUE["double"]["baseline_h_mm"],
    )
    q = calculate_quote(req)
    expected = PRICING["base"]["double"] + PRICING["mechanism_uplift"]["concertina"]
    assert q.unit_price == round(expected, 2)


def test_image_url_present():
    """Every product in the catalogue should have an image_url."""
    req = QuoteRequest(door_set="single")
    q = calculate_quote(req)
    assert q.image_url is not None


def test_lead_time_present():
    req = QuoteRequest(door_set="double")
    q = calculate_quote(req)
    assert q.lead_time
