"""Print the actual schema of the raw downloads so normalization is data-driven,
not guesswork. Read-only diagnostics.

    python ingestion/inspect_raw.py
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
RAW = REPO / "data" / "raw"


def sep():
    print("\n" + "=" * 72)


def inspect_grievances():
    sep(); print("GRIEVANCE CSVs")
    files = sorted(RAW.glob("grievances_*.csv"))
    for i, f in enumerate(files):
        # read a sample to learn columns + dtypes cheaply
        df = pd.read_csv(f, nrows=2000, low_memory=False)
        if i == 0:
            print(f"\nColumns ({len(df.columns)}) in {f.name}:")
            for c in df.columns:
                sample = df[c].dropna().astype(str).head(1).tolist()
                print(f"  - {c!r:40} e.g. {sample}")
        else:
            # just confirm column parity across years
            print(f"\n{f.name}: {len(df.columns)} cols "
                  f"{'== year1' if list(df.columns) else ''}")


def inspect_categories():
    sep(); print("CATEGORY-LIKE COLUMN VALUES (full 2025 file)")
    f = RAW / "grievances_2025.csv"
    df = pd.read_csv(f, low_memory=False)
    print(f"{f.name}: {len(df):,} rows, {len(df.columns)} cols")
    cat_cols = [c for c in df.columns
                if re.search(r"categ|type|complaint|subject|department|service",
                             c, re.I)]
    for c in cat_cols:
        vc = df[c].astype(str).str.strip().value_counts().head(25)
        print(f"\n  Column {c!r} — top {min(25, df[c].nunique())} of "
              f"{df[c].nunique()} distinct:")
        for val, n in vc.items():
            print(f"    {n:7,}  {val}")


def inspect_ward_field():
    sep(); print("WARD-LIKE COLUMN VALUES (full 2025 file)")
    f = RAW / "grievances_2025.csv"
    df = pd.read_csv(f, low_memory=False)
    ward_cols = [c for c in df.columns if re.search(r"ward|zone|area|location",
                                                    c, re.I)]
    for c in ward_cols:
        n = df[c].nunique()
        print(f"\n  Column {c!r} — {n} distinct. Samples:")
        for v in df[c].dropna().astype(str).str.strip().drop_duplicates().head(20):
            print(f"    {v}")


def inspect_ward_info():
    sep(); print("WARD INFO CSV")
    f = RAW / "blr_ward_info.csv"
    df = pd.read_csv(f)
    print(f"{f.name}: {len(df)} rows, cols={list(df.columns)}")
    print(df.head(5).to_string())


def inspect_kml():
    sep(); print("KML FILES (placemark names + structure peek)")
    for f in sorted(RAW.glob("*.kml")):
        text = f.read_text(encoding="utf-8", errors="replace")
        names = re.findall(r"<name>(.*?)</name>", text, re.S)
        n_place = text.count("<Placemark")
        n_poly = text.count("<Polygon")
        n_point = text.count("<Point")
        print(f"\n  {f.name}: {n_place} placemarks, {n_poly} polygons, "
              f"{n_point} points, {len(names)} <name> tags")
        # show first handful of names (skip doc/folder names heuristically)
        shown = [n.strip() for n in names if n.strip()][:12]
        for nm in shown:
            print(f"    name: {nm[:80]}")


if __name__ == "__main__":
    inspect_grievances()
    inspect_categories()
    inspect_ward_field()
    inspect_ward_info()
    inspect_kml()
