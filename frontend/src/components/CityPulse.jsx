import { useState } from "react";
import api from "../api.js";
import AutoChart from "./AutoChart.jsx";

const SUGGESTIONS = [
  "Top 5 wards by waterlogging complaints in 2024",
  "Monthly drainage complaints trend in 2023",
  "Compare drainage complaints between Mahadevapura and Bommanahalli zones",
  "Which 10 wards have the highest current flood risk?",
];

function ResultTable({ columns, rows }) {
  if (!rows?.length) return null;
  return (
    <div className="overflow-auto max-h-52 rounded border border-ink-600 mt-2">
      <table className="w-full text-xs">
        <thead className="bg-ink-700 sticky top-0">
          <tr>{columns.map((c) => <th key={c} className="text-left px-2 py-1 font-medium text-slate-300">{c}</th>)}</tr>
        </thead>
        <tbody>
          {rows.slice(0, 100).map((r, i) => (
            <tr key={i} className="odd:bg-ink-800/40">
              {columns.map((c) => (
                <td key={c} className="px-2 py-1 tabular-nums text-slate-200">{String(r[c])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function CityPulse() {
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);
  const [err, setErr] = useState(null);

  async function ask(question) {
    const text = (question ?? q).trim();
    if (!text || busy) return;
    setQ(text); setBusy(true); setErr(null); setRes(null);
    try {
      setRes(await api.cityPulse(text));
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 pt-3 pb-2 border-b border-ink-600">
        <div className="text-sm font-semibold flex items-center gap-2">
          <span className="text-accent">CityPulse</span>
          <span className="text-[11px] text-slate-500 font-normal">
            ask 5 years of grievances in plain English
          </span>
        </div>
        <div className="mt-2 flex gap-2">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && ask()}
            placeholder="e.g. top wards by waterlogging in 2024"
            className="flex-1 bg-ink-800 border border-ink-600 rounded px-3 py-1.5 text-sm
                       outline-none focus:border-accent placeholder:text-slate-600"
          />
          <button
            onClick={() => ask()}
            disabled={busy}
            className="px-3 py-1.5 rounded bg-accent text-ink-900 text-sm font-semibold
                       disabled:opacity-50"
          >
            {busy ? "…" : "Ask"}
          </button>
        </div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {SUGGESTIONS.map((s) => (
            <button key={s} onClick={() => ask(s)}
              className="text-[11px] px-2 py-0.5 rounded-full border border-ink-600
                         text-slate-400 hover:text-accent hover:border-accent">
              {s}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-auto p-4">
        {busy && <div className="text-sm text-slate-400">Thinking… generating SQL and querying BigQuery.</div>}
        {err && <div className="text-sm text-risk-high">Error: {err}</div>}
        {res && !res.ok && (
          <div className="text-sm text-amber-400">
            {res.narrative || res.error || "Couldn't answer that."}
          </div>
        )}
        {res && res.ok && (
          <div className="space-y-2">
            <p className="text-sm text-slate-100 leading-relaxed">{res.narrative}</p>
            <AutoChart chart={res.chart} rows={res.rows} />
            <ResultTable columns={res.columns} rows={res.rows} />
            <details className="text-[11px] text-slate-500">
              <summary className="cursor-pointer hover:text-slate-300">
                SQL · {res.row_count} rows · {(res.bytes_scanned / 1e6).toFixed(1)} MB scanned
              </summary>
              <pre className="mt-1 whitespace-pre-wrap bg-ink-800 rounded p-2 border border-ink-600">{res.sql}</pre>
            </details>
          </div>
        )}
        {!res && !busy && !err && (
          <div className="text-sm text-slate-500">
            Ask a question or tap a suggestion. Answers are generated as guarded,
            read-only SQL over the live grievance warehouse.
          </div>
        )}
      </div>
    </div>
  );
}
