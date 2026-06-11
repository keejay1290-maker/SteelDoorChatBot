"""Product catalogue for Steel Door Company.

Base prices, baseline sizes, and lead times taken from the public Shopify product feed
(steeldoorcompany.co.uk/products.json), verified 2026-06-11.
Baseline heights corrected to real-world door heights (products.json listed 980mm for
double which is clearly a data error; door openings are 1980-2100mm).

image_url: local static path served by this API after the Playwright scraper runs.
Falls back to None if the scraper hasn't been run yet.
"""
from __future__ import annotations

CATALOGUE: dict[str, dict] = {
    "single": {
        "name": "Single Steel Door",
        "description": "Made-to-measure single steel door. Ultra-slim 20mm sightlines, "
                       "fully bespoke in any RAL colour. Hinged or pivot, inward or outward.",
        "base_price": 1700.0,
        "baseline_w_mm": 750,
        "baseline_h_mm": 1980,
        "max_w_mm": 1000,
        "max_h_mm": 3000,
        "lead_time": "6-8 weeks from final approval",
        "image_url": "/static/images/single_door.jpg",
        "product_url": "https://steeldoorcompany.co.uk/products/single-steel-door",
    },
    "double": {
        "name": "Double Steel Doors",
        "description": "Made-to-measure double steel doors — perfect for kitchen-diner extensions, "
                       "room dividers and garden access. Up to 1000mm per leaf.",
        "base_price": 3000.0,
        "baseline_w_mm": 1400,
        "baseline_h_mm": 1980,
        "max_w_mm": 2000,
        "max_h_mm": 3000,
        "lead_time": "6-8 weeks from final approval",
        "image_url": "/static/images/double_door.jpg",
        "product_url": "https://steeldoorcompany.co.uk/products/double-steel-doors",
    },
    "fire_rated": {
        "name": "Fire Rated Steel Door (FD30/FD60)",
        "description": "Jansen Economy 50 system. CE/UKCA marked to EN 1634 and BS 476. "
                       "Sound insulation up to Rw 35 dB. Internal partitions, lobbies, "
                       "stairwells, corridors.",
        "base_price": 3400.0,
        "baseline_w_mm": 1170,
        "baseline_h_mm": 2000,
        "max_w_mm": 2000,
        "max_h_mm": 3000,
        "lead_time": "survey-dependent; typically 8-10 weeks",
        "image_url": "/static/images/fire_rated_door.jpg",
        "product_url": "https://steeldoorcompany.co.uk/products/fire-rated-double-steel-doors-made-to-measure",
    },
    "sliding": {
        "name": "Sliding Steel Door",
        "description": "Space-saving made-to-measure sliding door. Single slide, double slide, "
                       "or pocket configurations. Ultra-slim sightlines, smooth gliding operation.",
        "base_price": 4750.0,
        "baseline_w_mm": 2400,
        "baseline_h_mm": 2000,
        "max_w_mm": 1600,
        "max_h_mm": 2500,
        "lead_time": "8-10 weeks from final approval",
        "image_url": "/static/images/sliding_door.jpg",
        "product_url": "https://steeldoorcompany.co.uk/products/sliding-door",
    },
    "concertina": {
        "name": "Concertina Sliding Door",
        "description": "Multi-panel folding concertina door for wide openings. "
                       "Maximum glass exposure, smooth fold-back operation.",
        "base_price": 5250.0,
        "baseline_w_mm": 2550,
        "baseline_h_mm": 2000,
        "max_w_mm": 1600,
        "max_h_mm": 2500,
        "lead_time": "8-10 weeks from final approval",
        "image_url": "/static/images/concertina_door.jpg",
        "product_url": "https://steeldoorcompany.co.uk/products/concertina-sliding-door",
    },
    "external_patio": {
        "name": "External Steel Patio Doors",
        "description": "100% steel external doors. 70mm profile depth, thermally broken. "
                       "Thermal performance up to 2.2 W/(m²K). Sound reduction to 46 dB. "
                       "CE/UKCA to EN 14351-1.",
        "base_price": 5000.0,
        "baseline_w_mm": 2000,
        "baseline_h_mm": 2100,
        "max_w_mm": 3000,
        "max_h_mm": 3000,
        "lead_time": "survey-dependent",
        "image_url": "/static/images/external_patio_door.jpg",
        "product_url": "https://steeldoorcompany.co.uk/products/external-steel-patio-doors",
    },
    "wine_room": {
        "name": "Wine Room Steel Door",
        "description": "Climate-controlled wine room specialist door. Humidity-resistant sealing, "
                       "specialist magnetic hardware, continuous brush seal. Maintains 55-65% "
                       "relative humidity and 10-15°C temperature.",
        "base_price": 2300.0,
        "baseline_w_mm": 750,
        "baseline_h_mm": 1980,
        "max_w_mm": 1000,
        "max_h_mm": 2400,
        "lead_time": "8-10 weeks from final approval",
        "image_url": "/static/images/wine_room_door.jpg",
        "product_url": "https://steeldoorcompany.co.uk",
    },
}

PRODUCT_KEYS = tuple(CATALOGUE.keys())
