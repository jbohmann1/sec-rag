"""Step 1.2 - Download SEC filings (raw, unmodified) and write a manifest.

Run from the PROJECT ROOT with the venv active:
    python src/download.py --dry-run AAPL   # show what WOULD be downloaded
    python src/download.py AAPL             # download one company
    python src/download.py                  # download all companies
"""
import csv
import hashlib
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()
USER_AGENT = os.getenv("SEC_USER_AGENT")
if not USER_AGENT:
    sys.exit("SEC_USER_AGENT missing. Add it to .env, e.g. SEC_USER_AGENT=Jane Doe jane@example.com")
HEADERS = {"User-Agent": USER_AGENT}

# ---------------------------------------------------------------- config ---
TICKERS = [
    "AAPL", "MSFT", "TXN", "WDAY",                # tech
    "JPM", "BAC", "GS", "CFG",                   # banking
    "WMT", "COST", "DG", "ROST",                 # retail
    "XOM", "COP", "DVN", "MPC",                  # energy
    "EA", "RBLX", "U", "CRSR",                   # gaming
    "ACM", "FLR", "TTEK", "STRL",                # architecture & engineering (NVEE -> STRL: NV5 was acquired by Acuren, 2025)
]
DEV = ["AAPL", "JPM", "WMT", "XOM", "DG", "EA", "ACM"]  # only these also get 10-Qs

# Manual overrides for tickers where SEC's ticker->CIK map can't be trusted:
#   XOM: as of 2026-07-01 Exxon redomiciled NJ->TX; the ticker now maps to the new
#        successor entity "ExxonMobil Holdings Corporation" (CIK 2115436), which has
#        no 10-K history yet. Our FY2023-2025 10-Ks are under the original CIK.
#   EA:  Electronic Arts went private on 2026-08-04 and was delisted, so it no longer
#        appears in company_tickers.json at all. Its historical 10-Ks (all filed while
#        public) are still under its original CIK.
CIK_OVERRIDES = {
    "XOM": (34088, "Exxon Mobil Corp"),
    "EA": (712515, "Electronic Arts Inc."),
}

CUTOFF = "2025-12-31"   # only annual periods ending on/before this date
N_YEARS = 3             # take the N most recent 10-Ks before the cutoff
MIN_INTERVAL = 0.2      # seconds between requests -> max 5/s (SEC limit is 10/s)

RAW_DIR = Path("data/raw")
MANIFEST = Path("data/manifest.csv")
FIELDS = ["ticker", "cik", "company", "form", "filing_date", "report_date",
          "accession", "primary_doc", "url", "local_path", "sha256",
          "size_bytes", "downloaded_at"]

# ------------------------------------------------------- polite HTTP layer ---
_last_request = 0.0


def polite_get(url, retries=5):
    """GET with a minimum gap between requests and exponential backoff."""
    global _last_request
    for attempt in range(retries):
        wait = MIN_INTERVAL - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 200:
                return r
            if r.status_code not in (429, 500, 502, 503, 504):
                # 403 (bad User-Agent?) or 404: retrying will not help
                r.raise_for_status()
        except (requests.ConnectionError, requests.Timeout):
            pass  # transient network problem: fall through to backoff
        time.sleep(2 ** attempt)  # 1, 2, 4, 8, 16 seconds
    raise RuntimeError(f"Gave up after {retries} attempts: {url}")


# ------------------------------------------------------------ EDGAR lookups ---
def load_cik_map():
    """ticker -> (cik as int, company name)."""
    data = polite_get("https://www.sec.gov/files/company_tickers.json").json()
    return {v["ticker"]: (int(v["cik_str"]), v["title"]) for v in data.values()}


def all_filings(cik):
    """Every filing row for a company, including older paginated history."""
    sub = polite_get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json").json()
    tables = [sub["filings"]["recent"]]
    for f in sub["filings"]["files"]:
        if f["filingTo"] < "2022-01-01":
            continue  # older than anything we need
        tables.append(polite_get(f"https://data.sec.gov/submissions/{f['name']}").json())

    keys = ("accessionNumber", "filingDate", "reportDate", "form", "primaryDocument")
    rows = []
    for t in tables:  # each table is columnar: {"form": [...], "reportDate": [...], ...}
        for i in range(len(t["accessionNumber"])):
            rows.append({k: t[k][i] for k in keys})
    return rows


def select_10ks(rows):
    """The N most recent original 10-Ks whose period ends on/before CUTOFF."""
    ks = [r for r in rows
          if r["form"] == "10-K" and r["reportDate"] and r["reportDate"] <= CUTOFF]
    ks.sort(key=lambda r: r["reportDate"], reverse=True)
    return ks[:N_YEARS]


def select_10qs(rows, tenks):
    """YOUR TURN. Return the three 10-Qs inside the most recent selected fiscal year.

    Rule: form == "10-Q" and reportDate strictly AFTER the second-newest selected
    10-K's reportDate and strictly BEFORE the newest selected 10-K's reportDate.
    """
    if len(tenks) < 2:
        return []  # can't bound a fiscal year without two 10-Ks

    newest_end = tenks[0]["reportDate"]
    prior_end = tenks[1]["reportDate"]

    qs = [r for r in rows
          if r["form"] == "10-Q" and prior_end < r["reportDate"] < newest_end]
    qs.sort(key=lambda r: r["reportDate"])
    return qs


# ------------------------------------------------------------------ manifest ---
def load_manifest():
    if not MANIFEST.exists():
        return {}
    with open(MANIFEST, newline="", encoding="utf-8") as f:
        return {row["accession"]: row for row in csv.DictReader(f)}


def save_manifest(manifest):
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(manifest.values())


# ------------------------------------------------------------------ download ---
def download(ticker, cik, company, r, manifest):
    acc = r["accessionNumber"]
    if acc in manifest and Path(manifest[acc]["local_path"]).exists():
        print(f"    skip (already have) {r['form']} {r['reportDate']}")
        return
    if not r["primaryDocument"]:
        print(f"    WARNING no primary document for {acc}, skipped")
        return

    url = (f"https://www.sec.gov/Archives/edgar/data/{cik}/"
           f"{acc.replace('-', '')}/{r['primaryDocument']}")
    content = polite_get(url).content  # bytes: written exactly as received
    if len(content) < 100_000:
        print(f"    WARNING small file ({len(content)} bytes): inspect {url}")

    ext = Path(r["primaryDocument"]).suffix or ".htm"
    path = RAW_DIR / ticker / f"{r['form']}_{r['reportDate']}_{acc}{ext}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)

    manifest[acc] = {
        "ticker": ticker, "cik": cik, "company": company,
        "form": r["form"], "filing_date": r["filingDate"], "report_date": r["reportDate"],
        "accession": acc, "primary_doc": r["primaryDocument"], "url": url,
        "local_path": path.as_posix(),
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
        "downloaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    print(f"    saved {path.name} ({len(content) / 1e6:.1f} MB)")


def main():
    dry_run = "--dry-run" in sys.argv
    tickers = [a.upper() for a in sys.argv[1:] if not a.startswith("--")] or TICKERS

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    cik_map = load_cik_map()
    manifest = load_manifest()

    for ticker in tickers:
        if ticker in CIK_OVERRIDES:
            cik, company = CIK_OVERRIDES[ticker]
        elif ticker in cik_map:
            cik, company = cik_map[ticker]
        else:
            print(f"{ticker}: not found in SEC ticker list, skipped")
            continue
        print(f"{ticker} ({company}, CIK {cik})")
        rows = all_filings(cik)

        selected = select_10ks(rows)
        if ticker in DEV:
            selected += select_10qs(rows, selected)

        for r in selected:
            print(f"  {r['form']:5} period {r['reportDate']}  filed {r['filingDate']}")
            if not dry_run:
                download(ticker, cik, company, r, manifest)
        if not dry_run:
            save_manifest(manifest)  # save per company so a crash loses nothing

    print("Done." if not dry_run else "Dry run complete, nothing downloaded.")


if __name__ == "__main__":
    main()
