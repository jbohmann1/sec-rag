"""For a JPM 10-Q missing all its Part II labels: show every raw occurrence
of item_id '1' BEFORE dedup and Part-assignment, and whether dedup's
TOC-shape/length checks are correctly or incorrectly discarding one of them.

Run from the PROJECT ROOT with the venv active:
    python checks/check_jpm_item1_occurrences.py
"""
import sys
import warnings
from pathlib import Path

from bs4 import XMLParsedAsHTMLWarning
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

sys.path.insert(0, "src")
from clean_process import split_into_sections, dedupe_short_duplicates, looks_like_toc, assign_parts

path = Path("data/raw/JPM/10-Q_2025-03-31_0000019617-25-000421.htm")
html = path.read_text(encoding="utf-8", errors="replace")

sections = split_into_sections(html)

print("=== RAW sections with item_id == '1' (before dedup) ===")
raw_ones = [s for s in sections if s[0] == "1"]
for item_id, title, text in raw_ones:
    print(f"  len={len(text):6}  looks_like_toc={looks_like_toc(text)}  title={title!r}")
    print(f"    text_start={text[:150]!r}")

print(f"\nTotal raw sections: {len(sections)}")
print("All raw item_ids in order:", [s[0] for s in sections])

deduped = dedupe_short_duplicates(sections)
print(f"\nAfter dedup: {len(deduped)} sections")
print("Item_ids with id=='1' after dedup:", [s[0] for s in deduped if s[0] == "1"])

final = assign_parts(deduped, "10-Q")
print("\nFinal item_ids after assign_parts:", [s[0] for s in final])
