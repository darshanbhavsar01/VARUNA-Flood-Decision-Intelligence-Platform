import { BAND_COLORS, timeAgo } from "../lib/format.js";
import ViewSwitch from "./ViewSwitch.jsx";

function Chip({ band, count }) {
  return (
    <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-ink-700">
      <span className="w-2.5 h-2.5 rounded-full" style={{ background: BAND_COLORS[band] }} />
      <span className="text-sm font-semibold tabular-nums">{count}</span>
      <span className="text-[11px] text-slate-400 capitalize">{band}</span>
    </div>
  );
}

export default function Header({ cityName, summary, view, setView }) {
  const b = summary?.bands || {};
  return (
    <header className="flex items-center gap-4 px-5 h-16 border-b border-ink-600 bg-ink-800/80 backdrop-blur">
      <div className="flex items-baseline gap-2">
        <span className="text-2xl font-extrabold tracking-tight bg-gradient-to-r from-accent to-accent-soft bg-clip-text text-transparent">
          VARUNA
        </span>
        <span className="text-[11px] text-slate-500 hidden sm:inline">Command View</span>
      </div>

      <div className="text-sm text-slate-300">
        <span className="font-medium">{cityName}</span>
        <span className="text-slate-500"> · flood risk</span>
      </div>

      <div className="px-2 py-1 rounded bg-ink-700 text-xs text-accent font-medium">
        Next 24 hours
      </div>

      <div className="flex-1" />

      <div className="hidden md:flex items-center gap-2">
        <Chip band="high" count={b.high ?? 0} />
        <Chip band="moderate" count={b.moderate ?? 0} />
        <Chip band="low" count={b.low ?? 0} />
      </div>

      {summary?.computed_at && (
        <div className="text-[11px] text-slate-500 text-right leading-tight">
          <div>model as of</div>
          <div className="text-slate-300">{timeAgo(summary.computed_at)}</div>
        </div>
      )}
      {setView && <ViewSwitch view={view} setView={setView} />}
    </header>
  );
}
