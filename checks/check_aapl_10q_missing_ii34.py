"""AAPL 10-Q (2025-03-29): does 'Item 3' / 'Item 4' text exist anywhere in
the raw HTML at all (Part II's Defaults/Mine Safety items), or does AAPL
genuinely skip restating not-applicable items entirely?

Run from the PROJECT ROOT with the venv active:
    python checks/check_aapl_10q_missing_ii34.py
"""
import csv
import re
import warnings
from pathlib import Path

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

with open("data/manifest.csv", newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))
row = next(r for r in rows if r["ticker"] == "AAPL" and r["report_date"] == "2025-03-29" and r["form"] == "10-Q")
path = Path(row["local_path"])
html = path.read_text(encoding="utf-8", errors="replace")
soup = BeautifulSoup(html, "lxml")

PATTERN = re.compile(r"item\s*[34]\b", re.IGNORECASE)

count = 0
for tag in soup.find_all(True):
    if tag.find(True) is not None:
        continue
    text = tag.get_text(" ", strip=True)
    if PATTERN.search(text) and len(text) < 150:
        count += 1
        in_table = tag.find_parent("table") is not None
        print(f"MATCH #{count} (in_table={in_table}): text={text!r}")
        print(f"  style: {tag.get('style')!r}")

print(f"\nTotal matches: {count}")

# Also check the sequence: find "Unregistered Sales" (end of II-2) and show
# what comes immediately after it, to see what AAPL actually transitions to.
print()
print("=" * 70)
print("What comes right after Item 2's content, before Item 5?")
idx = html.find("Unregistered Sales")
if idx != -1:
    # grab visible text in a window after this point
    window_soup = BeautifulSoup(html[idx:idx+8000], "lxml")
    text = window_soup.get_text(" ", strip=True)
    print(text[:1500])
