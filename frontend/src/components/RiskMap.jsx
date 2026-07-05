import { MapContainer, TileLayer, GeoJSON } from "react-leaflet";
import { BAND_COLORS } from "../lib/format.js";

const BLR_CENTER = [12.96, 77.59];

export default function RiskMap({ geojson, horizon, selectedWard, onSelectWard }) {
  // key forces the GeoJSON layer to re-style when data/horizon changes
  const dataKey = `${horizon}-${geojson?.features?.length || 0}`;

  function style(feature) {
    const p = feature.properties;
    const selected = selectedWard === p.ward_id;
    return {
      color: selected ? "#e6eef5" : "#0a1018",
      weight: selected ? 2.5 : 0.6,
      fillColor: BAND_COLORS[p.risk_band] || BAND_COLORS.unknown,
      fillOpacity: p.risk_score == null ? 0.25 : 0.62,
    };
  }

  function onEach(feature, layer) {
    const p = feature.properties;
    const risk = p.risk_score == null ? "no score" : `${Math.round(p.risk_score * 100)}%`;
    layer.bindTooltip(
      `<b>${p.ward_name}</b><br/>${p.zone} · risk ${risk}` +
        (p.risk_rank ? ` · #${p.risk_rank}` : ""),
      { sticky: true }
    );
    layer.on({
      click: () => onSelectWard(p.ward_id),
      mouseover: (e) => e.target.setStyle({ weight: 2, color: "#4fc3f7" }),
      mouseout: (e) => e.target.setStyle(style(feature)),
    });
  }

  return (
    <MapContainer
      center={BLR_CENTER}
      zoom={11}
      className="h-full w-full"
      zoomControl={true}
      preferCanvas={true}
    >
      <TileLayer
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        attribution='&copy; OpenStreetMap &copy; CARTO'
        subdomains="abcd"
      />
      {geojson && (
        <GeoJSON key={dataKey} data={geojson} style={style} onEachFeature={onEach} />
      )}
    </MapContainer>
  );
}
