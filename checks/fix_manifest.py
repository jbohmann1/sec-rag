"""Check whether a clean, correctly-formatted row already exists for the
same filing as the corrupted one, and if so, safely remove only the
corrupted duplicate and rewrite manifest.csv.

Run from the PROJECT ROOT with the venv active:
    python fix_manifest.py
"""
import csv
import shutil

MANIFEST = "data/manifest.csv"
ACCESSION = "0000874238-24-000032"  # the STRL FY2023 10-K accession from the corrupted row

with open(MANIFEST, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    rows = list(reader)

bad_rows = [r for r in rows if not r.get("local_path", "").strip()]
good_match = [r for r in rows if r.get("accession") == ACCESSION]

print(f"Bad (corrupted) rows: {len(bad_rows)}")
print(f"Clean rows with accession {ACCESSION}: {len(good_match)}")

if good_match:
    print("\nA clean row for this filing already exists:")
    print(" ", good_match[0])
    print("\nSafe to delete the corrupted duplicate. Backing up and rewriting manifest.csv...")
    shutil.copy(MANIFEST, MANIFEST + ".bak")
    cleaned = [r for r in rows if r.get("local_path", "").strip()]
    with open(MANIFEST, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(cleaned)
    print(f"Done. {len(rows)} -> {len(cleaned)} rows. Backup saved as manifest.csv.bak")
else:
    print("\nNo clean row found for this filing -- do NOT just delete the bad row.")
    print("Instead: manually remove the corrupted line from manifest.csv in a text editor,")
    print("then re-run: python src/download.py STRL   to regenerate it properly.")
