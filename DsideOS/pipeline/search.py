"""
Web search via DuckDuckGo HTML endpoint (no API key, no CAPTCHA, no JS needed).
Falls back to Bing headless if DDG returns no results for a query.

Usage:
    python search.py "Uttarakhand Patwari capital question"
    from search import search_for_answer, SearchResult
"""

import asyncio
import re
import sys
import urllib.parse
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright


PRIORITY_DOMAINS = [
    "testbook.com",
    "drishtiias.com",
    "theexampillar.com",
    "studyfry.com",
    "kafaltree.com",
    "adda247.com",
    "gktoday.in",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


@dataclass
class SearchResult:
    url: str
    title: str
    snippet: str
    domain: str
    priority: int  # lower = higher priority; len(PRIORITY_DOMAINS) = unknown domain


def _domain_priority(url: str) -> int:
    for i, domain in enumerate(PRIORITY_DOMAINS):
        if domain in url:
            return i
    return len(PRIORITY_DOMAINS)


def _extract_domain(url: str) -> str:
    return re.sub(r"https?://(www\.)?", "", url).split("/")[0]


async def _search_ddg(query: str, num_results: int = 10) -> list[SearchResult]:
    """
    DuckDuckGo HTML search — static page, no JS, no CAPTCHA.
    Uses /html/ endpoint which returns plain HTML results.
    """
    encoded = urllib.parse.quote_plus(query)
    url = f"https://html.duckduckgo.com/html/?q={encoded}"

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=25) as client:
        try:
            response = await client.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query, "b": "", "kl": "in-en"},
                headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
        except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError):
            return []  # caller will trigger Bing fallback

    soup = BeautifulSoup(response.text, "html.parser")
    results = []

    for result in soup.select(".result"):
        link_el = result.select_one(".result__a")
        snippet_el = result.select_one(".result__snippet")
        if not link_el:
            continue

        href = link_el.get("href", "")
        # DDG wraps URLs in a redirect — extract the actual URL
        if "uddg=" in href:
            parsed = urllib.parse.urlparse(href)
            params = urllib.parse.parse_qs(parsed.query)
            href = params.get("uddg", [href])[0]
            href = urllib.parse.unquote(href)

        if not href.startswith("http"):
            continue

        title = link_el.get_text(strip=True)
        snippet = snippet_el.get_text(strip=True) if snippet_el else ""

        results.append(
            SearchResult(
                url=href,
                title=title,
                snippet=snippet,
                domain=_extract_domain(href),
                priority=_domain_priority(href),
            )
        )

        if len(results) >= num_results:
            break

    return results


async def _search_bing_headless(query: str, num_results: int = 10) -> list[SearchResult]:
    """
    Bing headless fallback via Playwright. Much less aggressive than Google.
    Only used when DDG returns nothing.
    """
    encoded = urllib.parse.quote_plus(query)
    url = f"https://www.bing.com/search?q={encoded}&count={num_results}"

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = await browser.new_context(
            user_agent=HEADERS["User-Agent"],
            viewport={"width": 1280, "height": 800},
            locale="en-IN",
        )
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=25000)
        except Exception:
            pass  # may timeout on redirect — still try to get content
        await asyncio.sleep(3.0)
        try:
            html = await page.content()
        except Exception:
            await browser.close()
            return []
        await browser.close()

    soup = BeautifulSoup(html, "html.parser")
    results = []

    for item in soup.select("li.b_algo"):
        link_el = item.select_one("h2 a")
        snippet_el = item.select_one(".b_caption p, .b_algoSlug")
        if not link_el:
            continue

        href = link_el.get("href", "")
        # Decode Bing tracking redirects (/ck/a?...&u=a1<base64url>...)
        if "/ck/a?" in href or href.startswith("/"):
            parsed = urllib.parse.urlparse(href)
            params = urllib.parse.parse_qs(parsed.query)
            u_vals = params.get("u", [])
            if u_vals:
                raw = u_vals[0]
                # strip leading "a1" marker Bing prepends
                if raw.startswith("a1"):
                    raw = raw[2:]
                try:
                    import base64
                    href = base64.urlsafe_b64decode(raw + "==").decode("utf-8", errors="ignore")
                except Exception:
                    href = urllib.parse.unquote(raw)
        if not href.startswith("http"):
            continue

        title = link_el.get_text(strip=True)
        snippet = snippet_el.get_text(strip=True) if snippet_el else ""

        results.append(
            SearchResult(
                url=href,
                title=title,
                snippet=snippet,
                domain=_extract_domain(href),
                priority=_domain_priority(href),
            )
        )

        if len(results) >= num_results:
            break

    return results


async def search_web(query: str, num_results: int = 10) -> list[SearchResult]:
    """
    Search: DDG first, Bing headless fallback if no results.
    Results sorted: priority domains first, then by search rank within same tier.
    """
    results = await _search_ddg(query, num_results)

    if not results:
        print(f"  [DDG returned 0 results, trying Bing...]")
        results = await _search_bing_headless(query, num_results)

    # Stable sort: priority domain first, preserves original rank within same priority
    indexed = list(enumerate(results))
    indexed.sort(key=lambda x: (x[1].priority, x[0]))
    return [r for _, r in indexed]


async def search_for_answer(question_text: str) -> list[SearchResult]:
    """
    Convenience wrapper for exam question lookup.
    Pass 1: scoped to testbook.com.
    Pass 2: broad across all priority sites.
    """
    # Pass 1: testbook-scoped
    results = await search_web(f"site:testbook.com {question_text}", num_results=5)
    priority_hits = [r for r in results if r.priority < len(PRIORITY_DOMAINS)]

    if priority_hits:
        return priority_hits

    # Pass 2: broad
    results = await search_web(
        f"{question_text} testbook drishtiias exam GK",
        num_results=10,
    )
    return results


if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Uttarakhand Patwari capital Dehradun GK"

    async def main():
        print(f"Searching: {query}\n")
        results = await search_web(query, num_results=10)
        if not results:
            print("No results found.")
            return
        for i, r in enumerate(results, 1):
            marker = "*" if r.priority < len(PRIORITY_DOMAINS) else " "
            print(f"{marker}{i}. [{r.domain}] {r.title}")
            print(f"    {r.url}")
            if r.snippet:
                print(f"    {r.snippet[:120]}")
            print()

    asyncio.run(main())
