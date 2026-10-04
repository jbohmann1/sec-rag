"""Check the ACTUAL content and length of AAPL's 2025-03-29 10-Q Part II
Items 3, 4, and 5, before the <50-char filter drops them -- confirming
whether this is the same legitimate short-content mechanism as ACM/EA's
Item 2, or something else.

Run from the PROJECT ROOT with the venv active:
    python checks/check_aapl_10q_ii345.py
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

sections = split_into_sections(html)
sections = dedupe_short_duplicates(sections)
final = assign_parts(sections, "10-Q")

print("All sections for this filing, raw AND cleaned lengths:")
for item_id, title, raw_text in final:
    cleaned = strip_boilerplate(raw_text)
    flag = "  <-- DROPPED (cleaned < 50 chars)" if len(cleaned) < 50 else ""
    print(f"  {item_id:8} title={title!r}  raw_len={len(raw_text)}  cleaned_len={len(cleaned)}{flag}")
    if item_id in ("II-3", "II-4", "II-5"):
        print(f"    RAW TEXT: {raw_text!r}")
        print(f"    CLEANED:  {cleaned!r}")
