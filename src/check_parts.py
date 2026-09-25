"""One-off diagnostic: find which tickers have sections missing a PART- prefix,
meaning Part-tracking (PART_RE) failed to detect "PART I"/"PART II" etc. as a
bold heading somewhere in that filer's HTML, so their Item headings fell back
to old bare numbering (e.g. "1" instead of "I-1").

Run from the PROJECT ROOT with the venv active:
    python check_parts.py
"""
import json
from collections import Counter

bare_by_ticker = Counter()
total_by_ticker = Counter()

with open("data/processed/records.jsonl", encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        if r["item_id"] == "FRONT":
            continue
        total_by_ticker[r["ticker"]] += 1
        if "-" not in r["item_id"]:
            bare_by_ticker[r["ticker"]] += 1

print("Tickers with sections missing a PART- prefix (Part detection failed):")
for ticker in sorted(total_by_ticker):
    if bare_by_ticker[ticker]:
        print(f"  {ticker}: {bare_by_ticker[ticker]} / {total_by_ticker[ticker]} sections have no part prefix")
