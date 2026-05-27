"""
Lead Enrichment Script — US ICPs

Scrapes each lead's website (homepage + About page) to extract
personalization data, then writes signal type (col U) and phrase (col V)
back to the Google Sheet.

Usage:
    python execution/enrich/enrich-leads-us.py --client <client> --icp <icp> --rows 2,3,4
    python execution/enrich/enrich-leads-us.py --client <client> --icp <icp> --all-empty
    python execution/enrich/enrich-leads-us.py --client <client> --icp <icp> --rows 5 --dry-run

Flags:
    --all-empty   Process all rows where column U is empty
    --dry-run     Print results without writing to sheet
    --force       Re-research rows that already have U filled
"""

import argparse
import re
import sys
import time
from datetime import date
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse

import requests
import yaml
from bs4 import BeautifulSoup
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import AuthorizedSession, Request

ROOT = Path(__file__).resolve().parents[2]
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
BASE_URL = "https://sheets.googleapis.com/v4/spreadsheets"
MASTER_TAB = "All Leads"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
FETCH_TIMEOUT = 12
REQUEST_DELAY = 0.8

BOOKING_SIGNALS = [
    "calendly", "zocdoc", "janeapp", "jane.app", "zenoti", "square.site",
    "simplybook", "booksy", "acuityscheduling", "schedulicity",
    "mindbodyonline", "vagaro", "boulevard", "fresha",
    "booker", "phorest", "timely", "treatwell",
]

ABOUT_SLUGS = ["/about", "/about-us", "/our-story", "/who-we-are",
               "/about-our-practice", "/our-practice", "/meet-the-team",
               "/team", "/our-team", "/about-the-team"]

SERVICE_SLUGS = ["/services", "/treatments", "/our-services", "/what-we-do",
                 "/procedures", "/offerings", "/specialties", "/menu"]

BLOG_SLUGS = ["/blog", "/news", "/journal", "/stories", "/updates", "/latest"]

LAUNCH_KEYWORDS = [
    "introducing", "just launched", "now available", "announcing",
    "meet our", "new drop", "just dropped", "new arrival", "launch",
]

LAUNCH_PREFIXES = [
    r"^introducing[\s:]+",
    r"^just launched[\s:]+",
    r"^announcing[\s:]+",
    r"^meet our (new(?:est)? )?",
    r"^now available[\s:]+",
    r"^new drop[\s:]*",
    r"^new!?\s+",
    r"^launch(?:ed)?[\s:]+",
]


# ── Config loaders ─────────────────────────────────────────────────────────────

def load_client_config(client: str) -> dict:
    path = ROOT / "clients" / client / "config.yaml"
    if not path.exists():
        print(f"ERROR: client config not found at {path}")
        sys.exit(1)
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def get_icp_config(client_cfg: dict, icp: str) -> dict:
    for entry in client_cfg.get("icps", []):
        if entry["name"] == icp:
            return entry
    print(f"ERROR: ICP '{icp}' not found in client config.")
    sys.exit(1)


def load_triggers(client: str, icp: str) -> list:
    try:
        path = ROOT / "clients" / client / "triggers" / "trigger-library.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data.get(icp, {}).get("triggers", [])
    except Exception:
        return []


def pick_trigger(triggers: list, row: int) -> str:
    if not triggers:
        return ""
    return triggers[row % len(triggers)]


# ── Google Sheets helpers ──────────────────────────────────────────────────────

def get_session() -> AuthorizedSession:
    creds = Credentials.from_authorized_user_file(ROOT / "token.json", SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        (ROOT / "token.json").write_text(creds.to_json())
    return AuthorizedSession(creds)


def sheets_get(session, sid, range_, retries=3):
    url = f"{BASE_URL}/{sid}/values/{quote(range_, safe='')}"
    for attempt in range(retries):
        try:
            r = session.get(url, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise


def sheets_update(sid, range_, values, retries=3):
    url = f"{BASE_URL}/{sid}/values/{quote(range_, safe='')}?valueInputOption=RAW"
    for attempt in range(retries):
        try:
            session = get_session()
            r = session.put(url, json={"values": values}, timeout=30)
            r.raise_for_status()
            return
        except Exception:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise


def parse_rows_arg(rows_str):
    rows = []
    for part in rows_str.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            rows.extend(range(int(a), int(b) + 1))
        else:
            rows.append(int(part))
    return rows


# ── Web scraping ───────────────────────────────────────────────────────────────

def fetch_page(url: str) -> BeautifulSoup | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=FETCH_TIMEOUT, allow_redirects=True)
        if r.status_code == 200:
            return BeautifulSoup(r.text, "html.parser")
        return None
    except Exception:
        return None


def find_subpage(base_url: str, slugs: list[str]) -> tuple[str | None, BeautifulSoup | None]:
    parsed = urlparse(base_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    for slug in slugs:
        url = base + slug
        soup = fetch_page(url)
        if soup:
            return url, soup
        time.sleep(0.2)
    return None, None


def get_visible_text(soup: BeautifulSoup, max_chars: int = 4000) -> str:
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    return text[:max_chars]


# ── Extraction helpers ─────────────────────────────────────────────────────────

def extract_founding_year(text: str, apollo_year: str = "") -> str | None:
    if apollo_year and re.match(r"^(19|20)\d{2}$", str(apollo_year).strip()):
        return str(apollo_year).strip()
    patterns = [
        r"\bsince\s+(19|20)\d{2}\b",
        r"\best(?:ablished)?\.?\s+(19|20)\d{2}\b",
        r"\bfounded(?:\s+in)?\s+(19|20)\d{2}\b",
        r"\bserving\s+since\s+(19|20)\d{2}\b",
        r"\bin\s+business\s+since\s+(19|20)\d{2}\b",
        r"\bopened\s+in\s+(19|20)\d{2}\b",
        r"\bstarted\s+in\s+(19|20)\d{2}\b",
        r"©\s*(19|20)\d{2}",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            year_m = re.search(r"(19|20)\d{2}", m.group())
            if year_m:
                return year_m.group()
    return None


def extract_tagline(soup: BeautifulSoup, company_name: str = "") -> str | None:
    skip_patterns = ["home", "welcome to", "404", "page not found"]

    def is_generic(text: str) -> bool:
        t = text.lower().strip()
        if company_name and company_name.lower()[:15] in t:
            return True
        if " in " in t and ("," in t):
            return True
        if any(p in t for p in skip_patterns):
            return True
        if len(text.split()) < 3:
            return True
        return False

    h1 = soup.find("h1")
    if h1:
        text = re.sub(r"\s+", " ", h1.get_text(separator=" ", strip=True))
        if 8 < len(text) < 120 and not is_generic(text):
            return text
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        content = meta["content"].strip()
        if 15 < len(content) < 160 and not is_generic(content):
            return content
    h2 = soup.find("h2")
    if h2:
        text = h2.get_text(strip=True)
        if 8 < len(text) < 120 and not is_generic(text):
            return text
    return None


def has_booking_widget(soup: BeautifulSoup, page_text: str) -> bool:
    html_lower = str(soup).lower()
    for signal in BOOKING_SIGNALS:
        if signal in html_lower:
            return True
    for iframe in soup.find_all("iframe"):
        src = (iframe.get("src") or "").lower()
        if any(s in src for s in BOOKING_SIGNALS):
            return True
    booking_phrases = ["book online", "book an appointment", "schedule online",
                       "request appointment", "book now", "schedule now"]
    for phrase in booking_phrases:
        if phrase in page_text.lower():
            for tag in soup.find_all(["a", "button"]):
                if phrase in tag.get_text(strip=True).lower():
                    return True
    return False


def extract_services(soup: BeautifulSoup) -> list:
    skip_words = {
        "home", "about", "contact", "team", "gallery", "blog", "news",
        "faq", "reviews", "testimonials", "careers", "map", "directions",
        "privacy", "terms", "menu", "services", "treatments", "procedures",
        "before", "after", "appointment", "booking", "schedule", "login",
        "patient", "portal", "insurance", "financing", "specials", "offers",
        "shop", "store", "buy", "new", "used", "inventory", "search",
    }
    candidates = []
    for tag in soup.find_all(["a", "li", "h2", "h3", "h4"]):
        text = tag.get_text(strip=True)
        words = text.split()
        if 1 <= len(words) <= 4 and 4 < len(text) < 45:
            if text.lower() not in skip_words and not any(s in text.lower() for s in skip_words):
                candidates.append(text)
    seen = set()
    unique = []
    for c in candidates:
        key = c.lower()
        if key not in seen:
            seen.add(key)
            unique.append(c)
    unique.sort(key=len)
    return unique[:3]


def format_services(services: list) -> str:
    if not services:
        return ""
    if len(services) == 1:
        return services[0]
    if len(services) == 2:
        return f"{services[0]} and {services[1]}"
    return f"{services[0]}, {services[1]}, and {services[2]}"


def extract_social_proof(text: str) -> str | None:
    patterns = [
        r"(?:over|more than)?\s*\d[\d,]+\s+(?:patients|clients|customers|families|homes|vehicles|reviews)",
        r"(?:over|more than)?\s*\d+\s+years?\s+(?:of\s+)?(?:experience|service|serving)",
        r"(?:top|best|award.winning|#1|number one)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return m.group().strip()
    return None


# ── Product launch detection ───────────────────────────────────────────────────

def _clean_launch_text(text: str) -> str:
    result = text.strip()
    for prefix in LAUNCH_PREFIXES:
        result = re.sub(prefix, "", result, flags=re.IGNORECASE).strip()
    result = result.rstrip(".:!").strip()
    return result[:60]


def detect_product_launch(
    homepage_soup: BeautifulSoup | None,
    blog_soup: BeautifulSoup | None,
) -> tuple[bool, str]:
    """Return (found, product_text) if a recent product launch is detected."""
    # Check blog/news headings first — strongest signal
    if blog_soup:
        for heading in blog_soup.find_all(["h1", "h2", "h3"]):
            text = heading.get_text(strip=True)
            if not text or len(text) > 120:
                continue
            if any(kw in text.lower() for kw in LAUNCH_KEYWORDS):
                cleaned = _clean_launch_text(text)
                if len(cleaned) > 3:
                    return True, cleaned

    # Check homepage for launch phrases near product listings
    if homepage_soup:
        homepage_lower = str(homepage_soup).lower()
        homepage_launch_phrases = [
            "new in", "just arrived", "new arrivals", "new drop",
            "just launched", "new collection", "introducing",
        ]
        for phrase in homepage_launch_phrases:
            if phrase in homepage_lower:
                for tag in homepage_soup.find_all(["h1", "h2", "h3", "span", "p"]):
                    tag_text = tag.get_text(strip=True)
                    if phrase in tag_text.lower() and 3 < len(tag_text) < 80:
                        return True, tag_text[:50]

    return False, ""


# ── Signal decision tree ───────────────────────────────────────────────────────
# Detects patterns from website scraping (priority order):
#   new_product_launch   — recent launch detected on blog or homepage
#   active_meta_spender  — Meta/Google ad pixels found on site
#   mature_ad_account    — Brand has been running for 2+ years (founding year found)
#   complex_ad_account   — Broad product range (many list/heading elements)
#   fallback             — No strong signal detected

def determine_signal(
    founding_year: str | None,
    has_booking: bool,
    tagline: str | None,
    social_proof: str | None,
    homepage_text: str,
    homepage_html: str,
    about_text: str,
    triggers: list,
    row: int,
    services: list,
    signal_fallbacks: dict,
    company_name: str = "",
) -> tuple[str, str, str]:
    current_year = date.today().year
    notes_parts = []
    clean_combined = homepage_text + " " + about_text
    name = company_name or "Your brand"

    # ── Detect mature account (founding year) ─────────────────────────────────
    react_year = None
    years_running = None
    if founding_year:
        try:
            years_running = current_year - int(founding_year)
            notes_parts.append(f"Founded {founding_year} ({years_running}yr)")
            react_year = founding_year
        except ValueError:
            pass

    # ── Detect active Meta spender (ad pixels) ────────────────────────────────
    has_meta_ads = any(sig in homepage_html.lower() for sig in [
        "fbq(", "facebook pixel", "connect.facebook.net",
        "gtag(", "googletagmanager", "google-analytics",
    ])
    if has_meta_ads:
        notes_parts.append("Ad pixels detected")

    # ── Detect complex ad account (broad product range) ───────────────────────
    product_count = len(re.findall(r"<li[^>]*>|<h[23][^>]*>", homepage_html, re.IGNORECASE))
    has_complex = product_count > 8
    if has_complex:
        notes_parts.append(f"Broad product range ({product_count} items)")

    trigger = pick_trigger(triggers, row)
    fb_mature = signal_fallbacks.get("reactivation", "an established ad account with likely accumulated issues")

    # Company-specific openers — each phrase becomes {{opener_line}} in the email
    if has_meta_ads:
        phrase = f"{name} is running Meta ads right now."
        return "active_meta_spender (primary)", phrase, " | ".join(notes_parts)

    if has_complex and react_year:
        phrase = f"{name} is running multiple product lines through Meta."
        return "complex_ad_account (fallback)", phrase, " | ".join(notes_parts)

    if react_year and years_running is not None:
        phrase = f"{name} has been running for {years_running} years."
        return "mature_ad_account (primary)", phrase, " | ".join(notes_parts)

    if has_complex:
        phrase = f"{name} is running multiple product lines through Meta."
        return "complex_ad_account (fallback)", phrase, " | ".join(notes_parts)

    notes_parts.append("Final fallback")
    phrase = trigger if trigger else fb_mature
    return "fallback", phrase, " | ".join(notes_parts)


# ── Main research pipeline ─────────────────────────────────────────────────────

def research_lead(website_url: str, apollo_year: str, icp: str, company_name: str,
                  triggers: list, row: int, signal_fallbacks: dict) -> dict:
    fb_mature = signal_fallbacks.get("reactivation", "an established ad account with likely accumulated issues")

    def _fallback(apollo_year: str) -> dict:
        trigger = pick_trigger(triggers, row)
        phrase = trigger if trigger else fb_mature
        note = f"No website — Apollo year {apollo_year}" if apollo_year else "No website — no data"
        return {"signal": "fallback", "phrase": phrase, "notes": note, "pages": []}

    if not website_url or not website_url.startswith("http"):
        return _fallback(apollo_year)

    pages_scraped = []

    time.sleep(REQUEST_DELAY)
    homepage_soup = fetch_page(website_url)
    if not homepage_soup:
        return _fallback(apollo_year)

    pages_scraped.append("homepage")
    homepage_text = get_visible_text(homepage_soup)
    homepage_html = str(homepage_soup)

    time.sleep(REQUEST_DELAY)
    about_url, about_soup = find_subpage(website_url, ABOUT_SLUGS)
    about_text = ""
    if about_soup:
        pages_scraped.append("about")
        about_text = get_visible_text(about_soup)

    time.sleep(REQUEST_DELAY)
    blog_url, blog_soup = find_subpage(website_url, BLOG_SLUGS)
    if blog_soup:
        pages_scraped.append("blog")

    # Product launch is the highest-priority signal — check before all others
    launch_found, launch_text = detect_product_launch(homepage_soup, blog_soup)
    if launch_found and launch_text:
        phrase = f"Saw {company_name} just launched {launch_text}."
        notes = f"Pages: {','.join(pages_scraped)} | Product launch detected: {launch_text[:50]}"
        return {"signal": "new_product_launch (primary)", "phrase": phrase, "notes": notes, "pages": pages_scraped}

    combined_text = homepage_text + " " + about_text
    founding_year = extract_founding_year(combined_text, apollo_year)
    tagline = extract_tagline(homepage_soup, company_name=company_name)
    booking = has_booking_widget(homepage_soup, homepage_text)
    social_proof = extract_social_proof(combined_text)
    services = extract_services(homepage_soup)

    signal, phrase, notes = determine_signal(
        founding_year=founding_year,
        has_booking=booking,
        tagline=tagline,
        social_proof=social_proof,
        homepage_text=homepage_text,
        homepage_html=homepage_html,
        about_text=about_text,
        triggers=triggers,
        row=row,
        services=services,
        signal_fallbacks=signal_fallbacks,
        company_name=company_name,
    )

    notes_full = f"Pages: {','.join(pages_scraped)} | {notes}"
    if tagline:
        notes_full += f" | H1: {tagline[:60]}"
    if services:
        notes_full += f" | Services: {', '.join(services[:3])}"

    return {"signal": signal, "phrase": phrase, "notes": notes_full, "pages": pages_scraped}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--client", required=True, help="Client folder name, e.g. acme-corp")
    parser.add_argument("--icp", required=True)
    parser.add_argument("--rows", help="e.g. 2,3,4 or 2-20")
    parser.add_argument("--all-empty", action="store_true",
                        help="Process all rows where column U is empty")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true",
                        help="Re-research rows that already have U filled")
    args = parser.parse_args()

    client_cfg = load_client_config(args.client)
    icp_cfg = get_icp_config(client_cfg, args.icp)
    signal_fallbacks = client_cfg.get("signal_fallbacks", {})
    sid = icp_cfg["sheet_id"]
    master_tab = icp_cfg.get("master_tab", "All Leads")

    session = get_session()
    triggers = load_triggers(args.client, args.icp)

    if args.rows:
        target_rows = parse_rows_arg(args.rows)
    elif args.all_empty:
        r = sheets_get(session, sid, f"'{master_tab}'!U2:U200")
        vals = r.get("values", [])
        target_rows = [i + 2 for i, v in enumerate(vals) if not v or not v[0]]
    else:
        print("Specify --rows or --all-empty.")
        sys.exit(1)

    print(f"Client: {args.client} | ICP: {args.icp} | Rows: {target_rows} | dry-run: {args.dry_run}\n")

    for row in target_rows:
        r = sheets_get(session, sid, f"'{master_tab}'!A{row}:U{row}")
        data = r.get("values", [[]])[0]
        while len(data) < 21:
            data.append("")

        company = data[8]
        website = data[9]
        founded = data[17]
        current_u = data[20]

        if current_u and not args.force:
            print(f"  Row {row:3} | {company[:30]:30} | SKIP (U already set: {current_u[:25]})")
            continue

        print(f"  Row {row:3} | {company[:30]:30} | {website[:45]}", end=" ... ", flush=True)

        result = research_lead(website, founded, args.icp, company_name=company,
                               triggers=triggers, row=row, signal_fallbacks=signal_fallbacks)

        signal = result["signal"]
        phrase = result["phrase"]
        notes = result["notes"][:500]

        print(f"{signal} | {len(result['pages'])} pages")

        if args.dry_run:
            print(f"    DRY  phrase: {phrase[:80]}")
            print(f"    DRY  notes:  {notes[:100]}")
            continue

        try:
            sheets_update(sid, f"'{master_tab}'!T{row}:V{row}", [[notes, signal, phrase]])
        except Exception as e:
            print(f"    ERROR writing to sheet: {e}")

    print("\nDone.")


if __name__ == "__main__":
    main()
