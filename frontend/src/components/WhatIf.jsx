import { useState } from "react";
import api from "../api.js";
import { BAND_COLORS } from "../lib/format.js";

const ZONES = ["", "East", "West", "South", "Bommanahalli", "Mahadevapura",
  "Yelahanka", "Dasarahalli", "Rajarajeswari Nagar"];

export default function WhatIf({ city, onResult, onClear, active }) {
  const [rain, setRain] = useState(80);
  const [hours, setHours] = useState(2);
  const [zone, setZone] = useState("Bommanahalli");
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);
  const [err, setErr] = useState(null);

  async function simulate() {
    if (busy) return;
    setBusy(true); setErr(null);
    try {
      const r = await api.whatif({ rain_mm: Number(rain), hours: Number(hours),
        zone: zone || null, city });
      setRes(r);
      const map = {};
      r.wards.forEach((w) => (map[w.ward_id] = w.new_score));
      onResult(map, r);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  function clear() {
    setRes(null); onClear();
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 pt-3 pb-3 border-b border-ink-600 space-y-2">
        <div className="text-sm font-semibold">
          <span className="text-accent">What-if simulator</span>
          <span className="text-[11px] text-slate-500 font-normal ml-2">
            re-scores wards with the model
          </span>
        </div>
        <label className="block text-[12px] text-slate-400">
          Rainfall: <b className="text-slate-200">{rain} mm</b>
          <input type="range" min="10" max="200" step="5" value={rain}
            onChange={(e) => setRain(e.target.value)}
            className="w-full accent-accent" />
        </label>
        <div className="flex gap-2">
          <label className="text-[12px] text-slate-400 flex-1">
            over hours
            <input type="number" min="1" max="24" value={hours}
              onChange={(e) => setHours(e.target.value)}
              className="w-full mt-1 bg-ink-800 border border-ink-600 rounded px-2 py-1
                         text-sm text-slate-100 outline-none focus:border-accent" />
          </label>
          <label className="text-[12px] text-slate-400 flex-[2]">
            over zone
            <select value={zone} onChange={(e) => setZone(e.target.value)}
              className="w-full mt-1 bg-ink-800 border border-ink-600 rounded px-2 py-1
                         text-sm text-slate-100 outline-none focus:border-accent">
              {ZONES.map((z) => (
                <option key={z} value={z}>{z === "" ? "Citywide" : z}</option>
              ))}
            </select>
          </label>
        </div>
        <div className="flex gap-2">
          <button onClick={simulate} disabled={busy}
            className="flex-1 py-2 rounded bg-accent text-ink-900 text-sm font-semibold
                       disabled:opacity-50">
            {busy ? "Simulating…" : "Simulate storm"}
          </button>
          {active && (
            <button onClick={clear}
              className="px-3 py-2 rounded border border-ink-600 text-slate-300 text-sm
                         hover:text-accent">
              Reset
            </button>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-auto p-4">
        {err && <div className="text-sm text-risk-high">Error: {err}</div>}
        {res && (
          <div className="space-y-3">
            <div className="text-sm text-slate-200">
              Simulated <b>{res.scenario.rain_mm} mm</b>
              {res.scenario.hours ? ` in ${res.scenario.hours}h` : ""} over{" "}
              <b>{res.scenario.zone}</b>. The map now shows the re-scored risk.
            </div>
            <div className="flex gap-2">
              {["high", "moderate", "low"].map((b) => (
                <div key={b} className="flex-1 rounded bg-ink-700 px-2 py-1.5 text-center">
                  <div className="text-lg font-bold tabular-nums"
                    style={{ color: BAND_COLORS[b] }}>{res.bands[b]}</div>
                  <div className="text-[10px] text-slate-400 capitalize">{b}</div>
                </div>
              ))}
            </div>
            <div>
              <div className="text-[11px] uppercase tracking-wide text-slate-500 mb-1">
                Biggest risk jumps
              </div>
              <div className="space-y-1">
                {[...res.wards].sort((a, b) => b.delta - a.delta).slice(0, 6).map((w) => (
                  <div key={w.ward_id} className="flex items-center gap-2 text-xs">
                    <span className="flex-1 truncate text-slate-200">{w.ward_name}</span>
                    <span className="text-slate-500">{Math.round(w.base_score * 100)}%</span>
                    <span className="text-slate-500">→</span>
                    <span className="font-semibold" style={{ color: BAND_COLORS[w.new_band] }}>
                      {Math.round(w.new_score * 100)}%
                    </span>
                    <span className="w-12 text-right text-risk-high">
                      +{Math.round(w.delta * 100)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
        {!res && !err && (
          <div className="text-sm text-slate-500">
            Set a hypothetical storm and hit <b className="text-slate-300">Simulate</b>.
            VARUNA feeds the scenario through the trained risk model and re-colors the
            map — showing which wards would tip into high risk.
          </div>
        )}
      </div>
    </div>
  );
}
