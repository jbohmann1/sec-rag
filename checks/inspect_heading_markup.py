"""Sanity-check: does this file actually contain real narrative 10-K text,
or is it something else (e.g. an XBRL viewer page)? Prints total extracted
text length and searches for a phrase we'd expect only in the real Business
section.

Usage:
    python inspect_heading_markup.py data/raw/INTC/10-K_....htm
"""
import sys
import warnings

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

path = sys.argv[1]
html = open(path, encoding="utf-8", errors="replace").read()
print(f"Raw HTML file size: {len(html):,} chars")

soup = BeautifulSoup(html, "lxml")
text = soup.get_text(" ", strip=True)
print(f"Extracted plain text length: {len(text):,} chars")

for phrase in ["Intel Corporation", "Santa Clara", "semiconductor", "Item 1"]:
    idx = text.lower().find(phrase.lower())
    if idx == -1:
        print(f"NOT FOUND: {phrase!r}")
    else:
        print(f"FOUND {phrase!r} at position {idx}: ...{text[max(0,idx-60):idx+80]!r}...")
