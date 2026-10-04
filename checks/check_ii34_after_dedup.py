"""Directly check AAPL's 2025-03-29 10-Q Items 3/4 after the dedup fix:
do they now survive dedupe_short_duplicates (confirming the fix works),
and if so, are they being caught afterward by main()'s separate 50-char
minimum-content filter (the same legitimate mechanism as ACM/EA), or is
something else dropping them?

Run from the PROJECT ROOT with the venv active:
    python checks/check_ii34_after_dedup.py
"""
import csv
import sys
import warnings
from pathlib import Path

from bs4 import XMLParsedAsHTMLWarning
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

sys.path.insert(0, "src")
from clean_process import split_into_sections, dedupe_short_duplicates, assign_parts, strip_boilerplate

with open("data/manifest.csv", newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))
row = next(r for r in rows if r["ticker"] == "AAPL" and r["report_date"] == "2025-03-29" and r["form"] == "10-Q")
path = Path(row["local_path"])
html = path.read_text(encoding="utf-8", errors="replace")

raw_sections = split_into_sections(html)
print("BEFORE dedup -- all raw occurrences of id '3' and '4':")
for item_id, title, text in raw_sections:
    if item_id in ("3", "4"):
        print(f"  raw_id={item_id}  title={title!r}  len={len(text)}")
        print(f"    text={text!r}")

deduped = dedupe_short_duplicates(raw_sections)
print(f"\nAFTER dedup -- occurrences of id '3'/'4' surviving: {len([s for s in deduped if s[0] in ('3','4')])}")
for item_id, title, text in deduped:
    if item_id in ("3", "4"):
        cleaned = strip_boilerplate(text)
        print(f"  raw_id={item_id}  title={title!r}  raw_len={len(text)}  cleaned_len={len(cleaned)}")
        print(f"    cleaned={cleaned!r}")
        if len(cleaned) < 50:
            print(f"    --> WOULD BE DROPPED by main()'s final len(cleaned) < 50 filter")

final = assign_parts(deduped, "10-Q")
print("\nFinal item_ids after assign_parts:", [s[0] for s in final])
