"""
Lead Copy Generator — US ICPs.

Reads leads from Google Sheet, uses Style column (U) + Phrase column (V) +
lead data (A-R) to generate copy. Writes copy to columns S-Z.

Usage:
    python scripts/generate-copy-us.py --client <client> --icp <icp> --rows 2,3,4
    python scripts/generate-copy-us.py --client <client> --icp <icp> --all-signaled
    python scripts/generate-copy-us.py --client <client> --icp <icp> --rows 2-9 --dry-run

Prerequisite: Columns U + V already filled (by enrich step).
"""

import argparse
import sys
from pathlib import Path
from urllib.parse import quote

import yaml
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import AuthorizedSession, Request

ROOT = Path(__file__).resolve().parents[2]
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
BASE_URL = "https://sheets.googleapis.com/v4/spreadsheets"


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


def load_templates(client: str, icp_cfg: dict) -> dict:
    path = ROOT / "clients" / client / icp_cfg["email_template"]
    text = path.read_text(encoding="utf-8")
    templates = {}
    for doc in yaml.safe_load_all(text):
        if not doc:
            continue
        if "signal_type" in doc:
            templates[doc["signal_type"]] = doc
    return templates


def get_session() -> AuthorizedSession:
    creds = Credentials.from_authorized_user_file(ROOT / "token.json", SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        (ROOT / "token.json").write_text(creds.to_json())
    return AuthorizedSession(creds)


def sheets_get(session: AuthorizedSession, sid: str, range_: str) -> dict:
    import time as _time
    url = f"{BASE_URL}/{sid}/values/{quote(range_, safe='')}"
    for attempt in range(5):
        r = session.get(url, timeout=30)
        if r.status_code == 429:
            wait = 2 ** attempt
            print(f"    429 — waiting {wait}s...")
            _time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()


def sheets_update(session: AuthorizedSession, sid: str, range_: str, values: list):
    url = f"{BASE_URL}/{sid}/values/{quote(range_, safe='')}?valueInputOption=RAW"
    r = session.put(url, json={"values": values}, timeout=30)
    r.raise_for_status()
    return r.json()


def find_scrape_tab(session: AuthorizedSession, sid: str) -> str | None:
    r = session.get(f"{BASE_URL}/{sid}", timeout=30)
    r.raise_for_status()
    meta = r.json()
    scrape_tabs = [
        s["properties"]["title"]
        for s in meta.get("sheets", [])
        if s["properties"]["title"].startswith("Scrape ")
    ]
    return sorted(scrape_tabs)[-1] if scrape_tabs else None


def parse_style(style_cell: str, pain_questions: dict) -> tuple[str | None, str]:
    s = style_cell.strip()
    known_variants = list(pain_questions.keys()) + ["fallback"]
    for variant in known_variants:
        if s.startswith(variant):
            path = "fallback" if "(fallback)" in s else "primary"
            return variant, path
    return None, None


def determine_salutation(first_name, last_name):
    fn = (first_name or "").strip()
    ln = (last_name or "").strip()
    return fn or ln


def build_opener_line(variant, path, phrase_or_observation):
    if path == "primary":
        return phrase_or_observation.strip('"').strip('„').strip('"').strip()
    return phrase_or_observation


def generate_copy(templates, variant, first_name, opener_line, company_name, founded_year):
    tmpl = templates.get(variant)
    if not tmpl:
        return None, None, None, None

    ft_subject = tmpl["first_touch"]["subject"]
    ft_body = tmpl["first_touch"]["body"]
    st_subject = tmpl["second_touch"]["subject"]
    st_body = tmpl["second_touch"]["body"]

    replacements = {
        "{{first_name}}": first_name,
        "{{opener_line}}": opener_line or "",
        "{{company_name}}": company_name or "",
        "{{founded_year}}": str(founded_year or ""),
    }
    for old, new in replacements.items():
        ft_subject = ft_subject.replace(old, new)
        ft_body = ft_body.replace(old, new)
        st_subject = st_subject.replace(old, new)
        st_body = st_body.replace(old, new)

    import re as _re
    ft_body = _re.sub(r'\n{3,}', '\n\n', ft_body)
    st_body = _re.sub(r'\n{3,}', '\n\n', st_body)

    return ft_subject.strip(), ft_body.strip(), st_subject.strip(), st_body.strip()


def pflicht_check(first_touch: str, quality_gate: dict) -> tuple[bool, dict, int]:
    word_count = len(first_touch.split())
    max_words = quality_gate.get("max_words", 200)
    checks = {
        f"under_{max_words}_words": word_count < max_words,
    }
    return all(checks.values()), checks, word_count


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--client", required=True, help="Client folder name, e.g. acme-corp")
    parser.add_argument("--icp", required=True)
    parser.add_argument("--rows", help="Row numbers, e.g. 2,3,4 or 2-9")
    parser.add_argument("--all-signaled", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    client_cfg = load_client_config(args.client)
    icp_cfg = get_icp_config(client_cfg, args.icp)
    pain_questions = client_cfg.get("pain_questions", {})
    quality_gate = client_cfg.get("quality_gate", {})
    sid = icp_cfg["sheet_id"]
    master_tab = icp_cfg.get("master_tab", "All Leads")

    templates = load_templates(args.client, icp_cfg)
    print(f"Client: {args.client} | ICP: {args.icp} | Sheet: {sid[:12]}... | Templates: {list(templates.keys())}")

    session = get_session()
    scrape_tab = find_scrape_tab(session, sid)
    print(f"Scrape tab: {scrape_tab}")

    if args.rows:
        target_rows = parse_rows_arg(args.rows)
    elif args.all_signaled:
        r = sheets_get(session, sid, f"'{master_tab}'!S2:S200")
        stages = r.get("values", [])
        target_rows = [i + 2 for i, s in enumerate(stages) if s and s[0] == "signaled"]
    else:
        print("Please specify --rows or --all-signaled.")
        sys.exit(1)

    print(f"Rows: {target_rows}\n")

    for row in target_rows:
        r = sheets_get(session, sid, f"'{master_tab}'!A{row}:V{row}")
        data = r.get("values", [[]])[0]
        while len(data) < 22:
            data.append("")

        first_name, last_name = data[0], data[1]
        company = data[8]
        founded_year = data[17]
        style_cell = data[20]
        phrase_or_obs = data[21]

        if not company or not first_name:
            print(f"  Row {row} | EMPTY LEAD -> skip")
            continue

        if not style_cell:
            print(f"  Row {row} | {company} | NO STYLE -> skip")
            continue

        variant, path = parse_style(style_cell, pain_questions)
        if not variant:
            print(f"  Row {row} | {company} | UNKNOWN STYLE: {style_cell} -> skip")
            continue

        first_name_clean = determine_salutation(first_name, last_name)

        opener_line = ""
        if variant in pain_questions:
            opener_line = build_opener_line(variant, path, phrase_or_obs)

        ft_subj, ft_body, st_subj, st_body = generate_copy(
            templates, variant, first_name_clean, opener_line, company, founded_year
        )

        if not ft_body:
            print(f"  Row {row} | {company} | Template '{variant}' not found -> skip")
            continue

        ok, checks, wc = pflicht_check(ft_body, quality_gate)
        status = "PASS" if ok else "FAIL"
        print(f"  Row {row:3} | {company[:30]:30} | {variant} ({path}) | {wc}W | {status}")

        if not ok:
            for k, v in checks.items():
                if not v:
                    print(f"    FAIL: {k}")
            continue

        if args.dry_run:
            continue

        r_t = sheets_get(session, sid, f"'{master_tab}'!T{row}")
        research = r_t.get("values", [[""]])[0][0] if r_t.get("values") else ""

        values = [["copy_done", research, style_cell, phrase_or_obs, ft_subj, ft_body, st_subj, st_body]]

        for tab in [master_tab] + ([scrape_tab] if scrape_tab else []):
            try:
                sheets_update(session, sid, f"'{tab}'!S{row}:Z{row}", values)
            except Exception as e:
                print(f"    {tab}: ERROR {e}")

    print("\nDone.")


if __name__ == "__main__":
    main()
