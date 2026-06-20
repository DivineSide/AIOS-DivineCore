"""
Scrapes a page and returns clean answer-relevant text.
Handles JS-heavy pages via Playwright. Falls back to lightweight fetch where possible.

Usage:
    python scrape.py https://testbook.com/...
    from scrape import scrape_page
"""

import asyncio
import re
import sys

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# Lightweight domains — don't need JS rendering
STATIC_DOMAINS = [
    "drishtiias.com",
    "theexampillar.com",
    "kafaltree.com",
    "gktoday.in",
    "studyfry.com",
]

# Selectors to remove from all pages (nav, ads, footer noise)
NOISE_SELECTORS = [
    "header", "footer", "nav", "aside",
    ".advertisement", ".ads", ".ad-container",
    ".sidebar", ".related-posts", ".comments",
    "script", "style", "noscript",
    "[class*='cookie']", "[class*='popup']", "[class*='modal']",
    "[class*='newsletter']", "[class*='subscribe']",
]

# Max characters of page text to return — enough for any answer, small enough to stay cheap
MAX_TEXT_CHARS = 8000


def _is_static_domain(url: str) -> bool:
    return any(d in url for d in STATIC_DOMAINS)


def _clean_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    for selector in NOISE_SELECTORS:
        for el in soup.select(selector):
            el.decompose()

    # Get text, collapse whitespace
    text = soup.get_text(separator="\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()[:MAX_TEXT_CHARS]


async def _fetch_static(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept-Language": "en-IN,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=15) as client:
        response = await client.get(url)
        response.raise_for_status()
        return _clean_html(response.text)


async def _fetch_js(url: str) -> str:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        page = await context.new_page()

        # Block images/fonts/media — faster page load, same text content
        await page.route(
            "**/*",
            lambda route: route.abort()
            if route.request.resource_type in ("image", "media", "font", "stylesheet")
            else route.continue_(),
        )

        await page.goto(url, wait_until="domcontentloaded", timeout=60000)

        # Wait briefly for any lazy-loaded content
        await asyncio.sleep(1.5)

        html = await page.content()
        await browser.close()

    return _clean_html(html)


async def scrape_page(url: str) -> str:
    """
    Fetch and clean a page. Uses lightweight httpx for static sites, Playwright for JS-heavy ones.
    Returns clean text (max 8k chars).
    """
    try:
        if _is_static_domain(url):
            return await _fetch_static(url)
        else:
            return await _fetch_js(url)
    except Exception as e:
        # If lightweight fails, retry with full JS rendering
        if _is_static_domain(url):
            try:
                return await _fetch_js(url)
            except Exception:
                pass
        raise RuntimeError(f"Failed to scrape {url}: {e}") from e


if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    url = sys.argv[1] if len(sys.argv) > 1 else "https://testbook.com"

    async def main():
        print(f"Scraping: {url}\n{'='*60}\n")
        text = await scrape_page(url)
        print(text[:3000])
        print(f"\n[...{len(text)} total chars]")

    asyncio.run(main())
