"""Two checks:
1. Confirm I-5 and I-6 each appear exactly 3 times among 10-Qs (the
   JPM-mislabeled versions, per Issue 14) -- not fewer.
2. Find every 10-Q missing II-5, separate JPM's (expected, per Issue 14)
   from any non-JPM filing (would be a distinct, unexplained gap), and
   if one exists, show its actual content to check whether it's a
   legitimate short/None. case or something else.

Handles both namespaced ("10-Q:I-5") and non-namespaced ("I-5") item_id
formats automatically.

Run from the PROJECT ROOT with the venv active:
    python checks/check_jpm_i5_i6_and_extra_gap.py
"""
import json
from collections import defaultdict

records = []
with open("data/processed/records.jsonl", encoding="utf-8") as f:
    for line in f:
        records.append(json.loads(line))

def bare_id(item_id):
    return item_id.split(":")[-1] if ":" in item_id else item_id

# ---------- Check 1: I-5 / I-6 counts among 10-Qs ----------
print("=" * 70)
print("CHECK 1: I-5 and I-6 counts among 10-Q filings")
print("=" * 70)
i5_10q = [r for r in records if r["form"] == "10-Q" and bare_id(r["item_id"]) == "I-5"]
i6_10q = [r for r in records if r["form"] == "10-Q" and bare_id(r["item_id"]) == "I-6"]

print(f"I-5 among 10-Qs: {len(i5_10q)} -- tickers/dates: {[(r['ticker'], r['report_date']) for r in i5_10q]}")
print(f"I-6 among 10-Qs: {len(i6_10q)} -- tickers/dates: {[(r['ticker'], r['report_date']) for r in i6_10q]}")

# ---------- Check 2: every 10-Q missing II-5, JPM vs non-JPM ----------
print()
print("=" * 70)
print("CHECK 2: every 10-Q missing II-5")
print("=" * 70)
by_filing = defaultdict(set)
form_by_filing = {}
for r in records:
    key = (r["ticker"], r["report_date"])
    by_filing[key].add(bare_id(r["item_id"]))
    form_by_filing[key] = r["form"]

missing_ii5 = [k for k, items in by_filing.items()
               if form_by_filing[k] == "10-Q" and "II-5" not in items]

print(f"{len(missing_ii5)} 10-Qs missing II-5:")
for ticker, report_date in sorted(missing_ii5):
    print(f"  {ticker:6} {report_date}  items: {sorted(by_filing[(ticker, report_date)])}")

non_jpm = [k for k in missing_ii5 if k[0] != "JPM"]
print(f"\nNon-JPM filings missing II-5: {len(non_jpm)}")
for key in non_jpm:
    print(f"  -> {key}")
    # pull the actual record closest to where II-5 should be, if anything exists nearby
    matches = [r for r in records if (r["ticker"], r["report_date"]) == key]
    for r in matches:
        if bare_id(r["item_id"]) in ("II-4", "II-6", "I-5"):
            print(f"     nearby record: item_id={r['item_id']}  char_count={r['char_count']}  title={r['item_title']!r}")
            print(f"     text: {r['text'][:200]!r}")
