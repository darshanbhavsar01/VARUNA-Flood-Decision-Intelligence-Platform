import { useEffect } from "react";
import { MapContainer, TileLayer, GeoJSON, CircleMarker, Tooltip, useMap }
  from "react-leaflet";
import { BAND_COLORS } from "../lib/format.js";

const BLR_CENTER = [12.96, 77.59];

// Bounding box [[minLat,minLng],[maxLat,maxLng]] of a GeoJSON Polygon/MultiPolygon.
function featureBounds(geom) {
  let minLat = 90, minLng = 180, maxLat = -90, maxLng = -180;
  const walk = (a) => {
    if (typeof a[0] === "number") {
      const [lng, lat] = a;
      minLat = Math.min(minLat, lat); maxLat = Math.max(maxLat, lat);
      minLng = Math.min(minLng, lng); maxLng = Math.max(maxLng, lng);
    } else a.forEach(walk);
  };
  walk(geom.coordinates);
  return [[minLat, minLng], [maxLat, maxLng]];
}

function FlyToWard({ geojson, selectedWard }) {
  const map = useMap();
  useEffect(() => {
    if (!geojson || selectedWard == null) return;
    const f = geojson.features.find((x) => x.properties.ward_id === selectedWard);
    if (f?.geometry) map.flyToBounds(featureBounds(f.geometry), { maxZoom: 14, duration: 0.8 });
  }, [selectedWard, geojson, map]);
  return null;
}

const band = (s) =>
  s == null ? "unknown" : s >= 0.6 ? "high" : s >= 0.3 ? "moderate" : "low";

export default function RiskMap({
  geojson, horizon, selectedWard, onSelectWard,
  scoreOverride = null,   // {ward_id: newScore} for what-if
  reports = [],           // citizen reports to plot
}) {
  const dataKey = `${horizon}-${geojson?.features?.length || 0}-${scoreOverride ? "wi" : "base"}`;

  function scoreOf(p) {
    if (scoreOverride && scoreOverride[p.ward_id] != null) return scoreOverride[p.ward_id];
    return p.risk_score;
  }

  function style(feature) {
    const p = feature.properties;
    const s = scoreOf(p);
    const selected = selectedWard === p.ward_id;
    return {
      color: selected ? "#e6eef5" : "#0a1018",
      weight: selected ? 2.5 : 0.6,
      fillColor: BAND_COLORS[band(s)],
      fillOpacity: s == null ? 0.25 : 0.62,
    };
  }

  function onEach(feature, layer) {
    const p = feature.properties;
    const s = scoreOf(p);
    const label = s == null ? "no score" : `${Math.round(s * 100)}%`;
    layer.bindTooltip(
      `<b>${p.ward_name}</b><br/>${p.zone} · risk ${label}` +
        (scoreOverride && scoreOverride[p.ward_id] != null ? " (what-if)" : ""),
      { sticky: true }
    );
    layer.on({
      click: () => onSelectWard(p.ward_id),
      mouseover: (e) => e.target.setStyle({ weight: 2, color: "#4fc3f7" }),
      mouseout: (e) => e.target.setStyle(style(feature)),
    });
  }

  const sevColor = { severe: "#ef4444", high: "#f97316", moderate: "#f59e0b", low: "#38bdf8" };

  return (
    <MapContainer center={BLR_CENTER} zoom={11} className="h-full w-full" preferCanvas={true}>
      <TileLayer
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        attribution='&copy; OpenStreetMap &copy; CARTO'
        subdomains="abcd"
      />
      {geojson && (
        <GeoJSON key={dataKey} data={geojson} style={style} onEachFeature={onEach} />
      )}
      <FlyToWard geojson={geojson} selectedWard={selectedWard} />
      {reports.filter((r) => r.lat && r.lng).map((r) => (
        <CircleMarker
          key={r.id}
          center={[r.lat, r.lng]}
          radius={6}
          pathOptions={{
            color: "#e6eef5", weight: 1.5,
            fillColor: sevColor[r.analysis_severity] || "#38bdf8", fillOpacity: 0.9,
          }}
        >
          <Tooltip>
            <b>Citizen report</b>
            <br />
            {r.ward_name || "unmapped"} · {r.analysis_category_norm || "—"}
            <br />
            severity: {r.analysis_severity || "—"}
            {r.analysis_summary ? <><br />{r.analysis_summary}</> : null}
          </Tooltip>
        </CircleMarker>
      ))}
    </MapContainer>
  );
}
