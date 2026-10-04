"""One-off: find any manifest.csv row with a missing/blank local_path (the
cause of 'PermissionError: Permission denied: .' in clean_process.py), and
print it so you can see exactly what's wrong before deciding how to fix it.

Run from the PROJECT ROOT with the venv active:
    python check_manifest.py
"""
import csv

with open("data/manifest.csv", newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    rows = list(reader)

print(f"Total rows: {len(rows)}")
print(f"Columns found: {reader.fieldnames}")
print()

bad = [r for r in rows if not r.get("local_path", "").strip()]
print(f"Rows with a blank/missing local_path: {len(bad)}")
for r in bad:
    print(" ", dict(r))
