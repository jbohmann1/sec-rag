"""Find filings missing Item 2 that aren't COP/DVN's combined-item (I-1-2) 10-Ks.

Run from the PROJECT ROOT with the venv active:
    python check_missing_item2.py
"""
import json
from collections import defaultdict

by_filing = defaultdict(set)
form_by_filing = {}

with open("data/processed/records.jsonl", encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        key = (r["ticker"], r["report_date"])
        by_filing[key].add(r["item_id"])
        form_by_filing[key] = r["form"]

missing_i2 = []
for key, items in by_filing.items():
    if "I-1-2" in items:
        continue  # combined-item filing (COP/DVN) -- expected, not a gap
    if "I-2" not in items:
        missing_i2.append(key)

print(f"{len(missing_i2)} filings missing Item 2 (excluding combined-item filings):\n")
for ticker, report_date in sorted(missing_i2):
    form = form_by_filing[(ticker, report_date)]
    items = sorted(by_filing[(ticker, report_date)])
    print(f"  {ticker:6} {report_date}  ({form})  -- items: {items}")
