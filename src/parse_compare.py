"""Step 1.3 - Compare parsing approaches on a sample of filings.

Runs three approaches on each sampled filing and writes output files under
experiments/parsing_compare/<approach>/<ticker>_<form>_<date>.txt
so you can open matching files side by side in VS Code and compare.

One-time install (only needed for this step):
    pip install html2text

Run from the PROJECT ROOT with the venv active:
    python src/parse_compare.py
"""
import csv
import re
from pathlib import Path

import html2text
from bs4 import BeautifulSoup

MANIFEST = Path("data/manifest.csv")
OUT_DIR = Path("experiments/parsing_compare")

# One filing per sector from the dev subset, plus three picked to stress
# specific hard structures: GS (dense regulatory-capital tables), RBLX
# (bookings-vs-GAAP-revenue reconciliation), COST (membership-fee revenue
# recognition). Swap these if you'd rather look at different filings --
# the point is structural variety, not this exact list.
SAMPLE_TICKERS = ["AAPL", "JPM", "WMT", "XOM", "DG", "EA", "ACM", "GS", "RBLX", "COST"]


def load_sample():
    """The most recent 10-K row for each ticker in SAMPLE_TICKERS."""
    with open(MANIFEST, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["form"] == "10-K"]
    by_ticker = {}
    for r in rows:
        if r["ticker"] in SAMPLE_TICKERS:
            cur = by_ticker.get(r["ticker"])
            if cur is None or r["report_date"] > cur["report_date"]:
                by_ticker[r["ticker"]] = r
    missing = set(SAMPLE_TICKERS) - by_ticker.keys()
    if missing:
        print(f"WARNING: no 10-K found in manifest for {missing}")
    return list(by_ticker.values())


# ------------------------------------------------------------- approach 1 ---
def parse_bs4_naive(html):
    """Strip scripts/styles, then get_text(). The 'do nothing clever'
    baseline -- fast, but headings, tables and lists all flatten into one
    undifferentiated stream of text.
    """
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    return re.sub(r"\n{3,}", "\n\n", text).strip()  # collapse blank-line runs


# ------------------------------------------------------------- approach 2 ---
def parse_bs4_structured(html):
    """Same as above, but every <table> is walked row by row into
    tab-separated lines first, so a number stays attached to its row and
    column labels instead of being flattened into a run-on sentence.
    """
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()

    for table in soup.find_all("table"):
        lines = []
        for row in table.find_all("tr"):
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if any(cells):
                lines.append("\t".join(cells))
        table.replace_with("\n[TABLE]\n" + "\n".join(lines) + "\n[/TABLE]\n")

    text = soup.get_text(separator="\n")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# ------------------------------------------------------------- approach 3 ---
def parse_html2text(html):
    """A third-party library's opinion on structure: headings become
    '#'/'##', tables become markdown pipe-tables, links are dropped.
    """
    h = html2text.HTML2Text()
    h.ignore_links = True
    h.ignore_images = True
    h.body_width = 0  # don't hard-wrap lines mid-sentence
    return h.handle(html)


PARSERS = {
    "bs4_naive": parse_bs4_naive,
    "bs4_structured": parse_bs4_structured,
    "html2text": parse_html2text,
}


def main():
    sample = load_sample()
    print(f"Comparing {len(PARSERS)} parsers on {len(sample)} filings\n")

    for name in PARSERS:
        (OUT_DIR / name).mkdir(parents=True, exist_ok=True)

    for row in sample:
        path = Path(row["local_path"])
        if not path.exists():
            print(f"  MISSING FILE: {path} (ticker {row['ticker']})")
            continue
        html = path.read_text(encoding="utf-8", errors="replace")
        stem = f"{row['ticker']}_{row['form']}_{row['report_date']}"

        print(f"{row['ticker']:6} {row['report_date']}  ({len(html) / 1e6:.1f} MB html)")
        for name, fn in PARSERS.items():
            out_path = OUT_DIR / name / f"{stem}.txt"
            try:
                result = fn(html)
            except Exception as e:
                result = f"[PARSE ERROR] {type(e).__name__}: {e}"
            out_path.write_text(result, encoding="utf-8")
            print(f"    {name:15} -> {out_path}  ({len(result) / 1000:.0f}K chars)")

    print("\nNow open matching files across the three folders side by side in "
          "VS Code and inspect: headings, tables, boilerplate, page headers/footers.")


if __name__ == "__main__":
    main()
