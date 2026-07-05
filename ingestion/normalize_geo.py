"""Turn the raw KML geography into VARUNA's canonical, multi-city-shaped outputs.

Inputs  (data/raw):  ward KML (polygons w/ ExtendedData), flood/low-lying point KMLs.
Outputs (data/processed):
  - wards.geojson         FeatureCollection: one ward per feature with
                          {city_id, ward_id, ward_name, zone, is_low_lying,
                           historical_flood_count}
  - wards.csv             the same attributes, flat (BQ `wards` table minus GEOGRAPHY)
  - ward_points_flood.geojson / _lowlying.geojson   the raw hazard points, ward-tagged
  - sample_wards.geojson  first 3 wards, committed to git as a schema sample

Usage:  python ingestion/normalize_geo.py --city bengaluru
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET

import yaml
from shapely.geometry import Point, Polygon, MultiPolygon, mapping
from shapely.prepared import prep

REPO = Path(__file__).resolve().parents[1]
RAW = REPO / "data" / "raw"
PROC = REPO / "data" / "processed"
CONFIGS = REPO / "configs"


def local(tag: str) -> str:
    """Strip XML namespace: '{...}Placemark' -> 'placemark'."""
    return tag.rsplit("}", 1)[-1].lower()


def iter_placemarks(root: ET.Element):
    for el in root.iter():
        if local(el.tag) == "placemark":
            yield el


def get_name(pm: ET.Element) -> str:
    for c in pm:
        if local(c.tag) == "name":
            return (c.text or "").strip()
    return ""


def get_extended(pm: ET.Element) -> dict:
    out = {}
    for el in pm.iter():
        if local(el.tag) == "data":
            key = el.get("name", "").strip()
            val = ""
            for c in el:
                if local(c.tag) == "value":
                    val = (c.text or "").strip()
            if key:
                out[key] = val
    return out


def parse_coords(text: str) -> list[tuple[float, float]]:
    pts = []
    for tok in text.replace("\n", " ").split():
        parts = tok.split(",")
        if len(parts) >= 2:
            try:
                pts.append((float(parts[0]), float(parts[1])))  # lng, lat
            except ValueError:
                continue
    return pts


def placemark_polygons(pm: ET.Element):
    """Yield shapely Polygons (outer ring only; holes rare in this data)."""
    for poly in pm.iter():
        if local(poly.tag) != "polygon":
            continue
        outer = None
        for ring in poly.iter():
            if local(ring.tag) == "outerboundaryis":
                for coords in ring.iter():
                    if local(coords.tag) == "coordinates" and coords.text:
                        pts = parse_coords(coords.text)
                        if len(pts) >= 3:
                            outer = Polygon(pts)
        if outer is not None and outer.is_valid is False:
            outer = outer.buffer(0)  # fix self-intersections
        if outer is not None:
            yield outer


def placemark_points(pm: ET.Element):
    for pt in pm.iter():
        if local(pt.tag) == "point":
            for coords in pt.iter():
                if local(coords.tag) == "coordinates" and coords.text:
                    c = parse_coords(coords.text)
                    if c:
                        yield Point(c[0])


def load_wards(kml_path: Path, city_id: str) -> list[dict]:
    root = ET.parse(kml_path).getroot()
    wards = []
    for pm in iter_placemarks(root):
        ext = get_extended(pm)
        name_tag = get_name(pm)
        m = re.search(r"(\d+)", name_tag)
        # skip the document-level placemark if any (no ward number, no ExtendedData)
        ward_name = ext.get("Ward Name", "").strip()
        if not ward_name and m is None:
            continue
        polys = list(placemark_polygons(pm))
        if not polys:
            continue
        geom = polys[0] if len(polys) == 1 else MultiPolygon(
            [p for p in polys if isinstance(p, Polygon)]) if all(
            isinstance(p, Polygon) for p in polys) else None
        if geom is None:  # buffer(0) may have made a MultiPolygon; unary fallback
            from shapely.ops import unary_union
            geom = unary_union(polys)
        wards.append({
            "city_id": city_id,
            "ward_id": int(m.group(1)) if m else None,
            "ward_name": ward_name or name_tag,
            "zone": ext.get("Zone", "").strip(),
            "geometry": geom,
        })
    return wards


def load_points(kml_path: Path) -> list[tuple[str, Point]]:
    if not kml_path.exists():
        return []
    root = ET.parse(kml_path).getroot()
    out = []
    for pm in iter_placemarks(root):
        name = get_name(pm)
        for p in placemark_points(pm):
            out.append((name, p))
    return out


def assign_points_to_wards(points, wards) -> dict:
    """Point-in-polygon -> {ward_id: count}. Uses prepared geoms for speed."""
    prepared = [(w["ward_id"], prep(w["geometry"]), w["geometry"]) for w in wards]
    counts: dict[int, int] = {}
    unmatched = 0
    for _name, pt in points:
        hit = None
        for wid, pg, _ in prepared:
            if pg.contains(pt):
                hit = wid
                break
        if hit is None:  # nearest-ward fallback within a small tolerance
            best, bestd = None, 0.02  # ~2km in degrees
            for wid, _, g in prepared:
                d = g.distance(pt)
                if d < bestd:
                    best, bestd = wid, d
            hit = best
        if hit is None:
            unmatched += 1
        else:
            counts[hit] = counts.get(hit, 0) + 1
    return counts, unmatched


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", required=True)
    args = ap.parse_args()

    cfg = yaml.safe_load((CONFIGS / f"{args.city}.yaml").read_text(encoding="utf-8"))
    city_id = cfg["city_id"]
    PROC.mkdir(parents=True, exist_ok=True)

    # config's ward_geojson is the processed target; the raw source is the KML.
    ward_kml = RAW / "blr_wards_198.kml"

    wards = load_wards(ward_kml, city_id)
    print(f"Parsed {len(wards)} wards from {ward_kml.name}")
    ids = [w["ward_id"] for w in wards]
    print(f"  ward_id range: {min(ids)}..{max(ids)}  distinct: {len(set(ids))}")

    flood_pts = load_points(RAW / "blr_flood_prone.kml") \
        + load_points(RAW / "blr_flood_vulnerable.kml")
    low_pts = load_points(RAW / "blr_low_lying.kml")
    print(f"Flood-prone points: {len(flood_pts)}  Low-lying points: {len(low_pts)}")

    flood_counts, f_un = assign_points_to_wards(flood_pts, wards)
    low_counts, l_un = assign_points_to_wards(low_pts, wards)
    print(f"  flood points unmatched to any ward: {f_un}")
    print(f"  low-lying points unmatched to any ward: {l_un}")

    for w in wards:
        w["historical_flood_count"] = flood_counts.get(w["ward_id"], 0)
        w["is_low_lying"] = low_counts.get(w["ward_id"], 0) > 0

    # --- wards.geojson ---
    features = [{
        "type": "Feature",
        "properties": {k: w[k] for k in
                       ("city_id", "ward_id", "ward_name", "zone",
                        "is_low_lying", "historical_flood_count")},
        "geometry": mapping(w["geometry"]),
    } for w in wards]
    fc = {"type": "FeatureCollection", "features": features}
    (PROC / "wards.geojson").write_text(json.dumps(fc), encoding="utf-8")

    # --- wards.csv (flat, BQ-shaped minus geometry) ---
    import csv
    with open(PROC / "wards.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["city_id", "ward_id", "ward_name", "zone",
                     "is_low_lying", "historical_flood_count"])
        for w in sorted(wards, key=lambda x: x["ward_id"] or 0):
            wr.writerow([w["city_id"], w["ward_id"], w["ward_name"], w["zone"],
                         w["is_low_lying"], w["historical_flood_count"]])

    # --- committed sample ---
    (PROC / "sample_wards.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": features[:3]}, indent=2),
        encoding="utf-8")

    n_low = sum(w["is_low_lying"] for w in wards)
    n_flood = sum(1 for w in wards if w["historical_flood_count"] > 0)
    print(f"\nWrote wards.geojson, wards.csv ({len(wards)} wards)")
    print(f"  low-lying wards: {n_low}   wards with >=1 flood-prone spot: {n_flood}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
