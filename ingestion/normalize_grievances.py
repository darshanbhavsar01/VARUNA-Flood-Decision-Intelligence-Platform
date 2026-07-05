"""Clean + normalize the raw BBMP grievance CSVs into VARUNA's canonical `grievances`
shape, joining each complaint to a ward_id via fuzzy name matching.

Outputs (data/processed):
  - grievances.csv          full canonical table (gitignored; loads to BQ)
  - sample_grievances.csv   first 500 rows, committed as a schema sample
  - ward_join_report.md     honest audit of the messy ward join (§5 caveat)
  - category_map_report.md   raw category/sub -> category_norm distribution

Canonical columns (§7):
  city_id, grievance_id, ward_id, ward_name_raw, ward_name_canon,
  category_raw, sub_category_raw, category_norm, description, created_at, status,
  lat, lng

Usage:  python ingestion/normalize_grievances.py --city bengaluru
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd
import yaml
from rapidfuzz import fuzz, process

REPO = Path(__file__).resolve().parents[1]
RAW = REPO / "data" / "raw"
PROC = REPO / "data" / "processed"
CONFIGS = REPO / "configs"

# ---------- category normalization ----------
def build_category_fn(mapping: dict):
    # mapping: ordered {NORM: [patterns]}; first NORM with a substring hit wins.
    ordered = [(norm, [p.lower() for p in pats]) for norm, pats in mapping.items()]

    def norm_of(category: str, sub: str) -> str:
        text = f"{category or ''} {sub or ''}".lower()
        for norm, pats in ordered:
            if any(p in text for p in pats):
                return norm
        return "OTHER"

    return norm_of


# ---------- ward-name normalization for matching ----------
def norm_ward(s: str) -> str:
    s = str(s or "").lower().strip()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)      # drop punctuation
    s = re.sub(r"\bward\b", " ", s)          # 'Kempegowda Ward' ~ 'Kempegowda'
    s = re.sub(r"\s+", " ", s).strip()
    return s


def build_ward_matcher(wards: pd.DataFrame, join_cfg: dict):
    threshold = int(join_cfg.get("fuzzy_threshold", 84))
    aliases = {norm_ward(k): norm_ward(v) for k, v in
               (join_cfg.get("aliases") or {}).items()}
    absent = {norm_ward(x) for x in (join_cfg.get("known_absent") or [])}

    canon = {}          # normalized(no spaces stripped) -> (ward_id, ward_name_canon)
    desp = {}           # despaced normalized -> normalized key
    for _, r in wards.iterrows():
        key = norm_ward(r["ward_name"])
        canon[key] = (int(r["ward_id"]), r["ward_name"])
        desp[key.replace(" ", "")] = key
    desp_choices = list(desp.keys())

    def match(raw: str):
        key = norm_ward(raw)
        if key in absent:
            return (None, None, "known_absent", 0)
        if key in canon:
            return (*canon[key], "exact", 100)
        if key in aliases and aliases[key] in canon:
            return (*canon[aliases[key]], "alias", 100)
        dkey = key.replace(" ", "")
        if dkey in desp:                       # despaced exact (spacing variants)
            return (*canon[desp[dkey]], "despaced", 100)
        best = process.extractOne(dkey, desp_choices, scorer=fuzz.ratio)
        if best and best[1] >= threshold:
            wid, name = canon[desp[best[0]]]
            return (wid, name, "fuzzy", int(best[1]))
        return (None, None, "unmatched", int(best[1]) if best else 0)

    return match


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", required=True)
    args = ap.parse_args()

    cfg = yaml.safe_load((CONFIGS / f"{args.city}.yaml").read_text(encoding="utf-8"))
    city_id = cfg["city_id"]
    cols = cfg["data_adapters"]["grievance_columns"]
    flood_norms = set(cfg["flood_signal_categories"])
    norm_of = build_category_fn(cfg["category_mapping"])

    wards = pd.read_csv(PROC / "wards.csv")
    match = build_ward_matcher(wards, cfg.get("ward_join") or {})

    # --- load all yearly files ---
    frames = []
    for f in sorted(RAW.glob("grievances_*.csv")):
        df = pd.read_csv(f, low_memory=False)
        df["__src"] = f.name
        frames.append(df)
    raw = pd.concat(frames, ignore_index=True)
    print(f"Loaded {len(raw):,} grievance rows from {len(frames)} files")

    out = pd.DataFrame()
    out["city_id"] = city_id
    out["grievance_id"] = raw[cols["id"]].astype(str)
    out["ward_name_raw"] = raw[cols["ward"]].astype(str).str.strip()
    out["category_raw"] = raw[cols["category"]].astype(str).str.strip()
    out["sub_category_raw"] = raw[cols["sub_category"]].astype(str).str.strip()
    out["status"] = raw[cols["status"]].astype(str).str.strip()
    out["created_at"] = pd.to_datetime(raw[cols["created_at"]], errors="coerce")
    out["description"] = None
    out["lat"] = pd.NA
    out["lng"] = pd.NA
    out["city_id"] = city_id

    # category_norm
    out["category_norm"] = [norm_of(c, s) for c, s in
                            zip(out["category_raw"], out["sub_category_raw"])]

    # ward join — match on the ~unique raw names only, then map (fast for 700k rows)
    uniq = out["ward_name_raw"].dropna().unique()
    lut = {name: match(name) for name in uniq}
    # nullable integer so the CSV writes "14"/"" (not "14.0") -> loads clean into BQ INT64
    out["ward_id"] = out["ward_name_raw"].map(
        lambda n: lut.get(n, (None,))[0]).astype("Int64")
    out["ward_name_canon"] = out["ward_name_raw"].map(
        lambda n: lut.get(n, (None, None))[1])
    match_method = out["ward_name_raw"].map(lambda n: lut.get(n, (None, None, "unmatched"))[2])

    # order columns per schema
    out = out[["city_id", "grievance_id", "ward_id", "ward_name_raw",
               "ward_name_canon", "category_raw", "sub_category_raw",
               "category_norm", "description", "created_at", "status", "lat", "lng"]]

    # --- drop rows with unparseable dates? keep but report ---
    bad_dates = out["created_at"].isna().sum()

    PROC.mkdir(parents=True, exist_ok=True)
    out.to_csv(PROC / "grievances.csv", index=False)
    out.head(500).to_csv(PROC / "sample_grievances.csv", index=False)

    # ---------- reports ----------
    n = len(out)
    matched = out["ward_id"].notna().sum()
    method_counts = match_method.value_counts().to_dict()

    # unmatched raw names (with volumes) — the actionable audit
    um = out.loc[out["ward_id"].isna(), "ward_name_raw"].value_counts()

    # fuzzy matches with their scores/targets, for eyeballing
    fuzzy_rows = []
    for name, (wid, canon, meth, score) in sorted(lut.items()):
        if meth == "fuzzy":
            fuzzy_rows.append((name, canon, score, int((out["ward_name_raw"] == name).sum())))
    fuzzy_rows.sort(key=lambda x: x[2])  # lowest score first (riskiest)

    rep = ["# Ward Join Report — {} ({} grievances)".format(city_id, f"{n:,}"), ""]
    rep.append(f"- Canonical wards: **{len(wards)}**  |  distinct raw ward names: "
               f"**{out['ward_name_raw'].nunique()}**")
    rep.append(f"- Matched to a ward: **{matched:,} / {n:,} "
               f"({matched/n*100:.2f}%)**")
    rep.append(f"- Match method: " + ", ".join(f"`{k}`={v:,}" for k, v in method_counts.items()))
    rep.append(f"- Rows with unparseable date: **{bad_dates:,}**")
    rep.append(f"- Fuzzy threshold (despaced fuzz.ratio): "
               f"**{(cfg.get('ward_join') or {}).get('fuzzy_threshold', 84)}**")
    rep.append("")
    rep.append("## Unmatched raw ward names (volume-ranked — fix these first)")
    if len(um) == 0:
        rep.append("_None — 100% of distinct ward names matched._")
    else:
        rep.append("| raw ward name | rows |")
        rep.append("|---|---|")
        for name, cnt in um.items():
            rep.append(f"| {name} | {cnt:,} |")
    rep.append("")
    rep.append("## Fuzzy matches (lowest confidence first — verify these)")
    rep.append("| raw name | matched canonical | score | rows |")
    rep.append("|---|---|---|---|")
    for name, canon, score, cnt in fuzzy_rows[:40]:
        rep.append(f"| {name} | {canon} | {score} | {cnt:,} |")
    (PROC / "ward_join_report.md").write_text("\n".join(rep), encoding="utf-8")

    # category report
    cat = out["category_norm"].value_counts()
    flood_rows = out["category_norm"].isin(flood_norms).sum()
    crep = ["# Category Normalization Report — {}".format(city_id), ""]
    crep.append(f"Total: **{n:,}** grievances. Flood-signal "
                f"({', '.join(sorted(flood_norms))}): **{flood_rows:,} "
                f"({flood_rows/n*100:.2f}%)**.")
    crep.append("")
    crep.append("| category_norm | count | share |")
    crep.append("|---|---|---|")
    for k, v in cat.items():
        crep.append(f"| {k} | {v:,} | {v/n*100:.2f}% |")
    # show what raw pairs fed each flood-signal norm (transparency)
    crep.append("\n## Top raw (Category / Sub Category) -> WATERLOGGING & DRAINAGE")
    for norm in ("WATERLOGGING", "DRAINAGE"):
        crep.append(f"\n### {norm}")
        sub = out[out["category_norm"] == norm]
        pairs = (sub["category_raw"] + "  |  " + sub["sub_category_raw"]
                 ).value_counts().head(15)
        crep.append("| raw Category | raw Sub Category | count |")
        crep.append("|---|---|---|")
        for pair, c in pairs.items():
            cat_r, sub_r = pair.split("  |  ", 1)
            crep.append(f"| {cat_r} | {sub_r} | {c:,} |")
    (PROC / "category_map_report.md").write_text("\n".join(crep), encoding="utf-8")

    print(f"\nWrote grievances.csv ({n:,} rows), sample, and reports.")
    print(f"  ward match: {matched/n*100:.2f}%  | methods: {method_counts}")
    print(f"  flood-signal rows: {flood_rows:,} ({flood_rows/n*100:.2f}%)")
    print(f"  category_norm: {cat.to_dict()}")
    if len(um):
        print(f"  UNMATCHED distinct names: {len(um)} "
              f"(top: {um.index[0]!r} x{um.iloc[0]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
