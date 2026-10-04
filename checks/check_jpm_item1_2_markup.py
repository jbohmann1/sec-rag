"""JPM 10-Q: find every leaf whose text contains 'Item 1' or 'Item 2'
ANYWHERE in the document (no length cap, inside or outside tables), to see
exactly how -- or whether -- 'Item 1. Financial Statements' and 'Item 2.
...Analysis' are styled, since neither has ever shown up in any prior scan.

Run from the PROJECT ROOT with the venv active:
    python checks/check_jpm_item1_2_markup.py
"""
import re
import warnings
from pathlib import Path

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

path = Path("data/raw/JPM/10-Q_2025-03-31_0000019617-25-000421.htm")
html = path.read_text(encoding="utf-8", errors="replace")
soup = BeautifulSoup(html, "lxml")

PATTERN = re.compile(r"item\s*1\b|item\s*2\b", re.IGNORECASE)

count = 0
for tag in soup.find_all(True):
    if tag.find(True) is not None:
        continue
    text = tag.get_text(" ", strip=True)
    if PATTERN.search(text) and len(text) < 120:
        count += 1
        in_table = tag.find_parent("table") is not None
        print("=" * 70)
        print(f"MATCH #{count} (in_table={in_table}): text={text!r}")
        print(f"  style: {tag.get('style')!r}")

print(f"\nTotal matches: {count}")

# Also: does the phrase "Financial Statements" appear as a short leaf anywhere
# outside a table, regardless of whether it says "Item 1"?
print()
print("=" * 70)
print("Leaves containing 'Financial Statements' (outside tables, <80 chars):")
for tag in soup.find_all(True):
    if tag.find(True) is not None:
        continue
    if tag.find_parent("table") is not None:
        continue
    text = tag.get_text(" ", strip=True)
    if "financial statements" in text.lower() and len(text) < 80:
        print(f"  text={text!r}  style={tag.get('style')!r}")
