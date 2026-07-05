import { useEffect, useState } from "react";
import api from "../api.js";
import { BAND_COLORS, BAND_LABEL, featureLabel, pct } from "../lib/format.js";

// Signed feature-attribution bar: positive pushes risk up (red), negative down (green).
function AttrBar({ feature, attribution, max }) {
  const w = max ? Math.min(100, (Math.abs(attribution) / max) * 100) : 0;
  const up = attribution >= 0;
  return (
    <div className="flex items-center gap-2 text-xs">
      <div className="w-40 shrink-0 text-slate-300">{featureLabel(feature)}</div>
      <div className="flex-1 flex items-center">
        <div className="w-1/2 flex justify-end">
          {!up && <div className="h-2 rounded-l" style={{ width: `${w}%`, background: BAND_COLORS.low }} />}
        </div>
        <div className="w-px h-3 bg-slate-600" />
        <div className="w-1/2">
          {up && <div className="h-2 rounded-r" style={{ width: `${w}%`, background: BAND_COLORS.high }} />}
        </div>
      </div>
      <div className={`w-12 text-right tabular-nums ${up ? "text-risk-high" : "text-risk-low"}`}>
        {attribution >= 0 ? "+" : ""}{attribution.toFixed(3)}
      </div>
    </div>
  );
}

export default function WardPanel({ wardId, city, horizon }) {
  const [d, setD] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    if (!wardId) return;
    setD(null); setErr(null);
    api.wardDetail(wardId, city, horizon).then(setD).catch((e) => setErr(String(e)));
  }, [wardId, city, horizon]);

  if (!wardId)
    return (
      <div className="p-4 text-sm text-slate-400">
        Select a ward on the map to see why it's at risk.
      </div>
    );
  if (err) return <div className="p-4 text-sm text-risk-high">Error: {err}</div>;
  if (!d) return <div className="p-4 text-sm text-slate-400">Loading ward…</div>;

  const maxAttr = Math.max(...(d.top_features || []).map((f) => Math.abs(f.attribution)), 0.0001);

  return (
    <div className="p-4 space-y-3">
      <div className="flex items-start justify-between">
        <div>
          <div className="text-lg font-semibold">{d.ward_name}</div>
          <div className="text-xs text-slate-400">
            {d.zone} · Ward {d.ward_id}
            {d.risk_rank ? ` · rank #${d.risk_rank}` : ""}
          </div>
        </div>
        <div className="text-right">
          <div className="text-2xl font-bold tabular-nums"
               style={{ color: BAND_COLORS[d.risk_band] }}>
            {pct(d.risk_score)}
          </div>
          <div className="text-[11px] uppercase tracking-wide"
               style={{ color: BAND_COLORS[d.risk_band] }}>
            {BAND_LABEL[d.risk_band]} risk
          </div>
        </div>
      </div>

      <div className="flex gap-2 text-[11px]">
        {d.is_low_lying && (
          <span className="px-2 py-0.5 rounded bg-ink-600 text-accent">low-lying</span>
        )}
        <span className="px-2 py-0.5 rounded bg-ink-600 text-slate-300">
          {d.historical_flood_count} flood-prone spot{d.historical_flood_count === 1 ? "" : "s"}
        </span>
      </div>

      <div>
        <div className="text-xs font-medium text-slate-300 mb-2">
          Why this score — feature contributions
        </div>
        <div className="space-y-1.5">
          {(d.top_features || []).map((f) => (
            <AttrBar key={f.feature} feature={f.feature}
                     attribution={f.attribution} max={maxAttr} />
          ))}
        </div>
        <div className="mt-2 flex justify-between text-[10px] text-slate-500">
          <span>← lowers risk</span><span>raises risk →</span>
        </div>
      </div>
      <p className="text-[11px] text-slate-500 leading-relaxed">
        Complaint-verified waterlogging risk (BQML boosted-tree, ML.EXPLAIN_PREDICT).
        Not a ground-truth flood forecast.
      </p>
    </div>
  );
}
