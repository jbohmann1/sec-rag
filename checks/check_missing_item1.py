"""One-off diagnostic: which filings have no 'I-1' section at all?
Every 10-K (Item 1 = Business) and every 10-Q (Item 1 = Financial Statements)
should have one, so any filing missing it had its very first heading go
undetected entirely.

Run from the PROJECT ROOT with the venv active:
    python check_missing_item1.py
"""
import json
from collections import defaultdict

sections_by_filing = defaultdict(set)
form_by_filing = {}

with open("data/processed/records.jsonl", encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        key = (r["ticker"], r["report_date"])
        sections_by_filing[key].add(r["item_id"])
        form_by_filing[key] = r["form"]

missing = [(t, d) for (t, d) in sections_by_filing if "I-1" not in sections_by_filing[(t, d)]]

print(f"{len(missing)} filings missing I-1 (out of {len(sections_by_filing)} total filings):\n")
by_form = defaultdict(int)
for t, d in sorted(missing):
    form = form_by_filing[(t, d)]
    by_form[form] += 1
    items = sorted(sections_by_filing[(t, d)])
    print(f"  {t:6} {d}  ({form})  -- items found: {items}")

print("\nBreakdown by form type:")
for form, count in by_form.items():
    print(f"  {form}: {count}")
