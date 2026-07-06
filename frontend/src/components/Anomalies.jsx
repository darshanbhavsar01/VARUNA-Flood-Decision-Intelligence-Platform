import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import api from "../api.js";
import { BAND_COLORS } from "../lib/format.js";

const TOOL_LABEL = {
  get_ward_profile: "Ward profile",
  get_rainfall_context: "Rainfall",
  get_zone_spike_comparison: "Neighbours",
  get_complaint_trend: "Trend",
};

function Card({ a, onSelectWard }) {
  const [busy, setBusy] = useState(false);
  const [brief, setBrief] = useState(null);
  const [err, setErr] = useState(null);

  async function investigate() {
    if (busy) return;
    setBusy(true); setErr(null);
    try {
      const r = await api.investigate(a);
      if (r.ok) setBrief(r);
      else setErr(r.error || "Investigation failed");
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  const rainDriven = a.rain_mm_that_day >= 10;
  return (
    <div className="px-4 py-3 border-b border-ink-600">
      <button onClick={() => onSelectWard(a.ward_id)} className="w-full text-left">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-sm font-semibold text-slate-100 truncate">
            {a.ward_name}
          </span>
          <span className="text-[11px] text-slate-500 shrink-0">{a.date}</span>
        </div>
        <div className="mt-0.5 text-sm text-slate-300">
          <span className="text-accent font-semibold">{a.category_norm.toLowerCase()}</span>{" "}
          complaints at{" "}
          <span className="font-bold text-risk-high">{a.deviation}×</span> baseline
          <span className="text-slate-500"> ({a.observed} vs {a.expected})</span>
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px]">
          <span className="px-1.5 py-0.5 rounded" style={{
            background: "#1d2a3a", color: BAND_COLORS[a.risk_band] }}>
            model: {a.risk_band}
          </span>
          <span className="px-1.5 py-0.5 rounded bg-ink-700 text-slate-400">
            {a.rain_mm_that_day} mm rain
          </span>
          {a.risk_band !== "high" && (
            <span className="px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300">
              caught before model
            </span>
          )}
        </div>
      </button>

      {!brief && (
        <button onClick={investigate} disabled={busy}
          className="mt-2 text-[12px] px-2 py-1 rounded border border-ink-600
                     text-accent hover:border-accent disabled:opacity-50">
          {busy ? "🔎 Insight agent investigating…" : "🔎 Investigate"}
        </button>
      )}
      {err && <div className="mt-2 text-[12px] text-risk-high">{err}</div>}
      {brief && (
        <div className="mt-2 rounded-lg bg-ink-900 border border-ink-600 p-3">
          <div className="flex flex-wrap gap-1 mb-2">
            {[...new Set(brief.tools_used)].map((t) => (
              <span key={t} className="text-[10px] px-1.5 py-0.5 rounded-full
                               bg-ink-700 text-accent border border-ink-600">
                {TOOL_LABEL[t] || t}
              </span>
            ))}
          </div>
          <div className="prose-plan text-[13px]">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{brief.text}</ReactMarkdown>
          </div>
          <div className="mt-1 text-[10px] text-slate-600">
            Insight agent ({brief.model})
          </div>
        </div>
      )}
    </div>
  );
}

export default function Anomalies({ city, onSelectWard }) {
  const [items, setItems] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    api.anomalies(city).then((d) => setItems(d.anomalies || [])).catch((e) => setErr(String(e)));
  }, [city]);

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 pt-3 pb-2 border-b border-ink-600">
        <div className="text-sm font-semibold">
          <span className="text-accent">Anomaly feed</span>
          <span className="text-[11px] text-slate-500 font-normal ml-2">
            citizens as sensors
          </span>
        </div>
        <p className="text-[11px] text-slate-500 mt-1">
          Wards where flood-signal complaints spiked far above their seasonal baseline.
          Tap <b className="text-slate-300">Investigate</b> to have the CityPulse
          Insight agent explain each one.
        </p>
      </div>
      <div className="flex-1 overflow-auto">
        {err && <div className="p-4 text-sm text-risk-high">{err}</div>}
        {!items && !err && <div className="p-4 text-sm text-slate-400">Loading alerts…</div>}
        {items && items.length === 0 && (
          <div className="p-4 text-sm text-slate-500">No anomalies detected.</div>
        )}
        {items && items.map((a, i) => (
          <Card key={i} a={a} onSelectWard={onSelectWard} />
        ))}
      </div>
    </div>
  );
}
