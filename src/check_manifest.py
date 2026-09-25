"""Diagnostic: sanity-check the manifest after a download run.

Run from the PROJECT ROOT with the venv active:
    python src/check_manifest.py
"""
import pandas as pd

df = pd.read_csv("data/manifest.csv")

print(f"Total rows: {len(df)}")
print(f"Distinct tickers: {df['ticker'].nunique()}\n")

print("--- Counts per ticker x form ---")
pivot = df.pivot_table(index="ticker", columns="form", values="accession",
                        aggfunc="count", fill_value=0)
print(pivot)

print("\n--- WMT and DG period-end dates (10-K only) ---")
mask = df["ticker"].isin(["WMT", "DG"]) & (df["form"] == "10-K")
print(df.loc[mask, ["ticker", "report_date", "filing_date"]]
        .sort_values(["ticker", "report_date"]))
