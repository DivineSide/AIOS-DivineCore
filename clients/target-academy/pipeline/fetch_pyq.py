"""Fetch UKSSSC previous-year question papers (PYQs) into the corpus.

Source: theexampillar.com hosts full papers (with answer keys) as paginated
HTML in Unicode Hindi — no OCR needed. For each paper: fetch all pages,
extract the article body, save raw HTML to resources/pyq/ (gitignored,
reproducibility) and cleaned text to corpus/pyq/<slug>.md.

Politeness: 1s delay between requests, plain UA, ~7 papers total.
"""

import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE = Path(__file__).resolve().parents[1]
RAW = BASE / "resources" / "pyq"
OUT = BASE / "corpus" / "pyq"

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# Exam papers most relevant to the institute's next batches (Patwari/VDO/Group C).
PAPERS = {
    "patwari-lekhpal-2023-02-12": "https://theexampillar.com/uttarakhand-revenue-inspector-patwari-lekhpal-exam-12-feb-2023-answer-key/",
    "patwari-lekhpal-2023-01-08": "https://theexampillar.com/uttarakhand-patwari-lekhpal-exam-08-jan-2023-answer-key/",
    "vdo-vpdo-2023-12-31": "https://theexampillar.com/uksssc-vdo-vpdo-exam-paper-31-dec-2023-answer-key/",
    "vdo-vpdo-2023-07-09": "https://theexampillar.com/uksssc-vdo-vpdo-re-exam-paper-09-july-2023-answer-key/",
    "vdo-vpdo-2021-12-05-morning": "https://theexampillar.com/uksssc-vdo-vpdo-exam-paper-05-dec-2021-morning-shift-answer-key/",
    "group-c-2018-11-25": "https://theexampillar.com/uksssc-group-c-25-november-2018-exam-paper-answer-key/",
    "lekhpal-patwari-2016": "https://theexampillar.com/uttarakhand-lekhpal-patwari-exam-2016-solved-paper/",
}


def fetch(url: str) -> str:
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    time.sleep(1.0)
    return r.text


def page_urls(first_html: str, base_url: str) -> list[str]:
    """Discover /2/, /3/, ... pagination links for this paper."""
    pat = re.escape(base_url.rstrip("/")) + r"/(\d+)/"
    nums = sorted({int(m.group(1)) for m in re.finditer(pat, first_html)})
    return [f"{base_url.rstrip('/')}/{n}/" for n in nums]


def extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    body = soup.find("div", class_="entry-content") or soup.find("article") or soup
    for tag in body.find_all(["script", "style", "ins", "iframe", "nav"]):
        tag.decompose()
    text = body.get_text("\n")
    # collapse blank-line runs and strip boilerplate-ish whitespace
    lines = [ln.strip() for ln in text.splitlines()]
    out, blank = [], 0
    for ln in lines:
        if not ln:
            blank += 1
            if blank > 1:
                continue
        else:
            blank = 0
        out.append(ln)
    return "\n".join(out).strip()


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    RAW.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    for slug, url in PAPERS.items():
        try:
            first = fetch(url)
            pages = [first] + [fetch(u) for u in page_urls(first, url)]
            (RAW / f"{slug}.html").write_text("\n<!-- PAGE BREAK -->\n".join(pages), encoding="utf-8")
            text = "\n\n".join(extract_text(p) for p in pages)
            header = f"<!-- source: {url} (+pagination) | UKSSSC PYQ with answer key -->\n\n"
            (OUT / f"{slug}.md").write_text(header + text, encoding="utf-8")
            n_q = len(re.findall(r"^\d{1,3}\.", text, re.M))
            print(f"{slug}: {len(pages)} pages, {len(text):,} chars, ~{n_q} numbered questions")
        except Exception as e:  # keep going; report at the end
            print(f"{slug}: FAILED — {e}")


if __name__ == "__main__":
    main()
