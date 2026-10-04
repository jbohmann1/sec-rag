"""Find the 3 10-Qs missing an II-6 (Exhibits) record, and search their raw
HTML for how 'Item 6' is actually styled there -- to distinguish a genuine
short/incorporated-by-reference case from a real heading-detection miss.

Run from the PROJECT ROOT with the venv active:
    python check_missing_ii6.py
"""
import csv
import json
import re
import sys
import warnings
from collections import defaultdict
from pathlib import Path

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# ---------- find which 10-Qs are missing II-6 ----------
by_filing = defaultdict(set)
form_by_filing = {}
with open("data/processed/records.jsonl", encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        key = (r["ticker"], r["report_date"])
        # item_id may be namespaced ("10-Q:II-6") or not, depending on which
        # version of records.jsonl you're running -- handle both
        item_id = r["item_id"].split(":")[-1] if ":" in r["item_id"] else r["item_id"]
        by_filing[key].add(item_id)
        form_by_filing[key] = r["form"]

missing = [k for k, items in by_filing.items()
           if form_by_filing[k] == "10-Q" and "II-6" not in items]

print(f"{len(missing)} 10-Qs missing II-6:")
for ticker, report_date in sorted(missing):
    print(f"  {ticker} {report_date} -- items: {sorted(by_filing[(ticker, report_date)])}")

# ---------- look at the raw HTML for each ----------
with open("data/manifest.csv", newline="", encoding="utf-8") as f:
    manifest_rows = {(row["ticker"], row["report_date"]): row for row in csv.DictReader(f)}

print()
for key in missing:
    row = manifest_rows.get(key)
    if not row:
        print(f"{key}: no manifest row found")
        continue
    path = Path(row["local_path"])
    if not path.exists():
        print(f"{key}: file not found at {path}")
        continue

    print("=" * 70)
    print(f"{key} -- {path}")
    html = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "lxml")

    found_any = False
    for tag in soup.find_all(True):
        if tag.find(True) is not None:
            continue
        text = tag.get_text(" ", strip=True)
        if re.match(r"^\s*item\s*6\b", text, re.IGNORECASE) and len(text) < 80:
            found_any = True
            in_table = tag.find_parent("table") is not None
            print(f"  MATCH: text={text!r}  style={tag.get('style')!r}  in_table={in_table}")
            nxt = tag.find_next(True)
            if nxt:
                print(f"    next leaf: {nxt.get_text(' ', strip=True)[:100]!r}")
    if not found_any:
        print("  NO 'Item 6...' leaf found anywhere in this document.")
