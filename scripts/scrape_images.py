"""Playwright scraper — downloads product hero images from steeldoorcompany.co.uk.

Run once before starting the server so the chat UI can show door previews.

Usage:
    python -m pip install playwright
    playwright install chromium
    python scripts/scrape_images.py

Images are saved to app/static/images/ and referenced by catalogue.py.
"""
from __future__ import annotations

import asyncio
import urllib.request
from pathlib import Path

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

IMAGES_DIR = Path(__file__).parent.parent / "app" / "static" / "images"

# product_key -> (Shopify product URL, target filename)
PRODUCT_PAGES = {
    "single":        ("https://steeldoorcompany.co.uk/products/single-steel-door",            "single_door.jpg"),
    "double":        ("https://steeldoorcompany.co.uk/products/double-steel-doors",           "double_door.jpg"),
    "fire_rated":    ("https://steeldoorcompany.co.uk/products/fire-rated-double-steel-doors-made-to-measure", "fire_rated_door.jpg"),
    "sliding":       ("https://steeldoorcompany.co.uk/products/sliding-door",                 "sliding_door.jpg"),
    "concertina":    ("https://steeldoorcompany.co.uk/products/concertina-sliding-door",       "concertina_door.jpg"),
    "external_patio":("https://steeldoorcompany.co.uk/products/external-steel-patio-doors",   "external_patio_door.jpg"),
    "wine_room":     ("https://steeldoorcompany.co.uk/products/double-steel-doors",           "wine_room_door.jpg"),
}

# Fallback CDN images if scraping fails (royalty-free steel door photos)
FALLBACK_IMAGES = {
    "single":         "https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=600",
    "double":         "https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=600",
    "fire_rated":     "https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=600",
    "sliding":        "https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=600",
    "concertina":     "https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=600",
    "external_patio": "https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=600",
    "wine_room":      "https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=600",
}


async def scrape_product_image(page, product_key: str, url: str, filename: str) -> bool:
    """Navigate to a product page and save the first hero/product image."""
    try:
        await page.goto(url, wait_until="networkidle", timeout=15000)

        # Try Shopify product image selectors
        selectors = [
            ".product__media img",
            ".product-single__photo img",
            ".product-image img",
            "[data-product-featured-image]",
            ".featured-image img",
            "img.photo-gallery__photo",
            ".product__photo img",
            "figure img",
        ]

        img_url = None
        for selector in selectors:
            try:
                el = await page.query_selector(selector)
                if el:
                    src = await el.get_attribute("src")
                    if src and not src.startswith("data:"):
                        img_url = src if src.startswith("http") else f"https:{src}"
                        # Request a decent resolution
                        img_url = img_url.split("?")[0] + "?v=1&width=800"
                        break
            except Exception:
                continue

        if not img_url:
            print(f"  [!] {product_key}: no image selector matched, taking screenshot")
            path = IMAGES_DIR / filename
            await page.screenshot(path=str(path), full_page=False)
            return True

        # Download the image
        dest = IMAGES_DIR / filename
        req = urllib.request.Request(img_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            dest.write_bytes(resp.read())
        print(f"  [ok] {product_key}: saved {filename} ({dest.stat().st_size} bytes)")
        return True

    except Exception as exc:
        print(f"  [!] {product_key}: scrape failed — {exc}")
        return False


def download_fallback(product_key: str, filename: str) -> None:
    """Download a placeholder image if scraping fails."""
    url = FALLBACK_IMAGES.get(product_key)
    if not url:
        return
    try:
        dest = IMAGES_DIR / filename
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            dest.write_bytes(resp.read())
        print(f"  [fallback] {product_key}: saved placeholder {filename}")
    except Exception as exc:
        print(f"  [!] {product_key}: fallback download failed — {exc}")


async def main() -> None:
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Saving images to: {IMAGES_DIR}")

    if not PLAYWRIGHT_AVAILABLE:
        print("Playwright not installed. Install with: pip install playwright && playwright install chromium")
        print("Downloading placeholder images instead...")
        for key, (_, filename) in PRODUCT_PAGES.items():
            download_fallback(key, filename)
        return

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_extra_http_headers({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"})

        for key, (url, filename) in PRODUCT_PAGES.items():
            dest = IMAGES_DIR / filename
            if dest.exists() and dest.stat().st_size > 5000:
                print(f"  [skip] {key}: {filename} already exists")
                continue
            print(f"  Scraping {key} from {url} ...")
            ok = await scrape_product_image(page, key, url, filename)
            if not ok:
                download_fallback(key, filename)

        await browser.close()

    print("\nDone. Images available at /static/images/")


if __name__ == "__main__":
    asyncio.run(main())
