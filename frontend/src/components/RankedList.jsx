import { BAND_COLORS, pct } from "../lib/format.js";

export default function RankedList({ wards, selectedWard, onSelectWard }) {
  const scored = (wards || []).filter((w) => w.risk_score != null);
  return (
    <div className="divide-y divide-ink-600">
      {scored.map((w) => {
        const sel = selectedWard === w.ward_id;
        return (
          <button
            key={w.ward_id}
            onClick={() => onSelectWard(w.ward_id)}
            className={`w-full text-left px-4 py-2 flex items-center gap-3 hover:bg-ink-700 transition
                        ${sel ? "bg-ink-700" : ""}`}
          >
            <span className="w-6 text-xs text-slate-500 tabular-nums">
              {w.risk_rank}
            </span>
            <span
              className="w-2 h-2 rounded-full shrink-0"
              style={{ background: BAND_COLORS[w.risk_band] }}
            />
            <span className="flex-1 min-w-0">
              <span className="block text-sm truncate">{w.ward_name}</span>
              <span className="block text-[11px] text-slate-500">{w.zone}</span>
            </span>
            <span className="text-sm font-semibold tabular-nums"
                  style={{ color: BAND_COLORS[w.risk_band] }}>
              {pct(w.risk_score)}
            </span>
          </button>
        );
      })}
    </div>
  );
}
