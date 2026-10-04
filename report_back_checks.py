"""Step 1.4 report-back diagnostics: full item_id breakdown, one full sample
record, the INTC image-vs-text check, and a search for boilerplate-stripper
false positives across real, long sections.

Run from the PROJECT ROOT with the venv active:
    python report_back_checks.py
"""
import csv
import json
import sys
from collections import Counter
from pathlib import Path

# ---------- 1. Full item_id breakdown ----------
print("=" * 70)
print("1. FULL item_id BREAKDOWN")
print("=" * 70)
records = []
with open("data/processed/records.jsonl", encoding="utf-8") as f:
    for line in f:
        records.append(json.loads(line))

counts = Counter(r["item_id"] for r in records)
for item_id, count in sorted(counts.items()):
    print(f"  {item_id:8} {count}")
print(f"  TOTAL RECORDS: {len(records)}")

# ---------- 3. One full sample record (a short one, so nothing's truncated) ----------
print()
print("=" * 70)
print("3. ONE FULL SAMPLE RECORD (a short section, so it's genuinely complete)")
print("=" * 70)
non_front = [r for r in records if r["item_id"] != "FRONT"]
short_candidates = [r for r in non_front if 50 <= r["char_count"] < 500]
sample = (sorted(short_candidates, key=lambda r: r["char_count"])[len(short_candidates) // 2]
          if short_candidates else min(non_front, key=lambda r: r["char_count"]))
print(json.dumps(sample, indent=2, ensure_ascii=False))

# ---------- 4. INTC image-vs-text check ----------
print()
print("=" * 70)
print("4. INTC: is 'General development of business' near an <img> tag?")
print("=" * 70)
intc_dir = Path("data/raw/INTC")
intc_files = list(intc_dir.glob("10-K_*.htm")) if intc_dir.exists() else []
if not intc_files:
    print("No INTC files found under data/raw/INTC/ -- were they removed after the TXN swap?")
else:
    html = intc_files[0].read_text(encoding="utf-8", errors="replace")
    idx = html.lower().find("general development of business")
    if idx == -1:
        print("Phrase not found anywhere in the raw HTML.")
    else:
        window = html[max(0, idx - 3000):idx + 3000]
        img_count = window.lower().count("<img")
        print(f"Found phrase at char {idx} of {len(html)}. <img> tags within +/-3000 chars: {img_count}")
        if img_count:
            img_idx = window.lower().find("<img")
            print("Context around the first nearby <img> tag:")
            print(window[max(0, img_idx - 200):img_idx + 300])
        else:
            print("No <img> tags nearby -- the heading is genuinely absent as text,")
            print("not replaced by an image.")

# ---------- 5. Boilerplate false-positive check on real, long sections ----------
print()
print("=" * 70)
print("5. False-positive check: short repeated lines stripped from real sections")
print("=" * 70)
sys.path.insert(0, "src")
from clean_process import split_into_sections, strip_boilerplate

with open("data/manifest.csv", newline="", encoding="utf-8") as f:
    manifest_rows = list(csv.DictReader(f))

sample_tickers = {"GS", "RBLX", "JPM", "COST", "AAPL"}
checked = 0
for row in manifest_rows:
    if row["ticker"] not in sample_tickers or row["form"] != "10-K" or checked >= 5:
        continue
    path = Path(row["local_path"])
    if not path.exists():
        continue
    html = path.read_text(encoding="utf-8", errors="replace")
    sections = split_into_sections(html)
    big_sections = [s for s in sections if len(s[2]) >= 20000]
    if not big_sections:
        continue
    item_id, title, raw = big_sections[0]
    lines = [l.strip() for l in raw.split("\n") if l.strip()]
    line_counts = Counter(lines)
    cleaned = strip_boilerplate(raw)
    cleaned_lines = set(l.strip() for l in cleaned.split("\n") if l.strip())
    removed_repeats = [(l, c) for l, c in line_counts.items()
                        if l not in cleaned_lines and c >= 2 and len(l) < 100]
    print(f"\n{row['ticker']} item {item_id} (raw {len(raw)} chars):")
    if removed_repeats:
        for l, c in sorted(removed_repeats, key=lambda x: -x[1])[:10]:
            print(f"    x{c}: {l!r}")
    else:
        print("    (no repeated short lines were stripped -- clean)")
    checked += 1
