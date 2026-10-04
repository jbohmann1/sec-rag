"""Inspect the actual II-5 / II-6 records before the namespacing fix lands,
to see exactly what was colliding -- specifically the 3 10-Ks with an
Item 6, which shouldn't exist post-2021.

Run from the PROJECT ROOT with the venv active (against the OLD,
non-namespaced records.jsonl -- run this BEFORE regenerating with the fix):
    python check_ii_collision.py
"""
import json
from collections import defaultdict

by_item = defaultdict(list)
with open("data/processed/records.jsonl", encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        if r["item_id"] in ("II-5", "II-6"):
            by_item[r["item_id"]].append(r)

for item_id in ("II-5", "II-6"):
    recs = by_item[item_id]
    by_form = defaultdict(list)
    for r in recs:
        by_form[r["form"]].append(r)
    print(f"=== {item_id}: {len(recs)} total ===")
    for form, group in by_form.items():
        print(f"  {form}: {len(group)}")
        if item_id == "II-6" and form == "10-K":
            print("    (the surprising ones -- Item 6 was eliminated in 2021)")
            for r in group:
                print(f"    {r['ticker']} {r['report_date']}  title={r['item_title']!r}  text_start={r['text'][:150]!r}")
    print()
