import { useEffect, useState } from "react";
import api from "../api.js";
import ViewSwitch from "../components/ViewSwitch.jsx";
import { BAND_COLORS, BAND_LABEL, pct } from "../lib/format.js";

const CITY = "blr";

function RiskCard({ advisory }) {
  if (!advisory) return null;
  const band = advisory.risk_band;
  return (
    <div className="rounded-xl border border-ink-600 bg-ink-800 p-4">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-lg font-semibold">{advisory.ward_name}</div>
          <div className="text-xs text-slate-400">{advisory.zone} zone</div>
        </div>
        <div className="text-right">
          <div className="text-2xl font-bold" style={{ color: BAND_COLORS[band] }}>
            {pct(advisory.risk_score)}
          </div>
          <div className="text-[11px] uppercase" style={{ color: BAND_COLORS[band] }}>
            {BAND_LABEL[band]} risk
          </div>
        </div>
      </div>
      <p className="mt-3 text-sm text-slate-200 leading-relaxed">🛟 {advisory.advisory}</p>
    </div>
  );
}

function Chat({ wardId }) {
  const [q, setQ] = useState("");
  const [msgs, setMsgs] = useState([]);
  const [busy, setBusy] = useState(false);
  async function send(text) {
    const question = (text ?? q).trim();
    if (!question || busy) return;
    setMsgs((m) => [...m, { role: "user", text: question }]);
    setQ(""); setBusy(true);
    try {
      const r = await api.citizenAsk(wardId, question, CITY);
      setMsgs((m) => [...m, { role: "bot", text: r.answer }]);
    } catch (e) {
      setMsgs((m) => [...m, { role: "bot", text: "Sorry — " + e }]);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="rounded-xl border border-ink-600 bg-ink-800 p-4">
      <div className="text-sm font-semibold mb-2">Ask about your area</div>
      <div className="space-y-2 max-h-52 overflow-auto mb-2">
        {msgs.length === 0 && (
          <div className="flex flex-wrap gap-1.5">
            {["Will my area flood this evening?", "Is it safe to drive out?"].map((s) => (
              <button key={s} onClick={() => send(s)}
                className="text-[11px] px-2 py-0.5 rounded-full border border-ink-600
                           text-slate-400 hover:text-accent hover:border-accent">
                {s}
              </button>
            ))}
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={m.role === "user" ? "text-right" : ""}>
            <span className={`inline-block px-3 py-1.5 rounded-lg text-sm ${
              m.role === "user" ? "bg-accent text-ink-900" : "bg-ink-700 text-slate-100"}`}>
              {m.text}
            </span>
          </div>
        ))}
        {busy && <div className="text-xs text-slate-500">Thinking…</div>}
      </div>
      <div className="flex gap-2">
        <input value={q} onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Type your question…"
          className="flex-1 bg-ink-900 border border-ink-600 rounded px-3 py-1.5 text-sm
                     outline-none focus:border-accent" />
        <button onClick={() => send()} disabled={busy}
          className="px-3 py-1.5 rounded bg-accent text-ink-900 text-sm font-semibold
                     disabled:opacity-50">Ask</button>
      </div>
    </div>
  );
}

function ReportForm({ wardId, geo }) {
  const [file, setFile] = useState(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [err, setErr] = useState(null);

  async function submit() {
    if (!file || busy) return;
    setBusy(true); setErr(null); setResult(null);
    try {
      const fd = new FormData();
      fd.append("image", file);
      fd.append("city", CITY);
      if (note) fd.append("note", note);
      if (wardId) fd.append("ward_id", String(wardId));
      if (geo) { fd.append("lat", geo.lat); fd.append("lng", geo.lng); }
      const r = await api.createReport(fd);
      setResult(r.report);
      setFile(null); setNote("");
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-xl border border-ink-600 bg-ink-800 p-4">
      <div className="text-sm font-semibold mb-2">Report waterlogging 📸</div>
      <input type="file" accept="image/*" capture="environment"
        onChange={(e) => setFile(e.target.files?.[0] || null)}
        className="block w-full text-sm text-slate-300 file:mr-3 file:py-1.5 file:px-3
                   file:rounded file:border-0 file:bg-ink-600 file:text-slate-100 mb-2" />
      <input value={note} onChange={(e) => setNote(e.target.value)}
        placeholder="Optional note (e.g. knee-deep near the junction)"
        className="w-full bg-ink-900 border border-ink-600 rounded px-3 py-1.5 text-sm
                   outline-none focus:border-accent mb-2" />
      <button onClick={submit} disabled={!file || busy}
        className="w-full py-2 rounded bg-accent text-ink-900 text-sm font-semibold
                   disabled:opacity-50">
        {busy ? "Analyzing photo…" : "Submit report"}
      </button>
      {err && <div className="mt-2 text-sm text-risk-high">Error: {err}</div>}
      {result && (
        <div className="mt-3 text-sm text-slate-200 border-t border-ink-600 pt-2">
          ✅ Reported{result.ward_name ? ` in ${result.ward_name}` : ""}. Gemini Vision:{" "}
          <b>{result.analysis_category_norm}</b>, severity{" "}
          <b>{result.analysis_severity}</b>
          {result.analysis_water_depth_estimate_cm != null &&
            `, ~${result.analysis_water_depth_estimate_cm} cm water`}
          .
          <div className="text-[11px] text-slate-500 mt-1">{result.analysis_summary}</div>
          <div className="text-[11px] text-slate-500 mt-1">
            It now appears on the control-room map.
          </div>
        </div>
      )}
    </div>
  );
}

export default function CitizenView({ view, setView }) {
  const [wards, setWards] = useState([]);
  const [wardId, setWardId] = useState(null);
  const [geo, setGeo] = useState(null);
  const [advisory, setAdvisory] = useState(null);
  const [locating, setLocating] = useState(false);

  useEffect(() => {
    api.wardsRanked(CITY).then((r) => setWards(r.wards || [])).catch(() => {});
  }, []);

  useEffect(() => {
    if (!wardId) { setAdvisory(null); return; }
    setAdvisory(null);
    api.advisory(wardId, CITY).then(setAdvisory).catch(() => {});
  }, [wardId]);

  function useMyLocation() {
    if (!navigator.geolocation) return;
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const { latitude: lat, longitude: lng } = pos.coords;
        setGeo({ lat, lng });
        try {
          const w = await api.locate(lat, lng, CITY);
          setWardId(w.ward_id);
        } catch {
          // outside Bengaluru — leave ward unset
        }
        setLocating(false);
      },
      () => setLocating(false),
      { enableHighAccuracy: true, timeout: 8000 }
    );
  }

  const sorted = [...wards].sort((a, b) => a.ward_name.localeCompare(b.ward_name));

  return (
    <div className="flex-1 overflow-auto bg-ink-900">
      <header className="flex items-center gap-3 px-4 h-14 border-b border-ink-600
                         bg-ink-800/80 backdrop-blur sticky top-0 z-10">
        <span className="text-xl font-extrabold bg-gradient-to-r from-accent to-accent-soft
                         bg-clip-text text-transparent">VARUNA</span>
        <span className="text-[11px] text-slate-500">Citizen</span>
        <div className="flex-1" />
        <ViewSwitch view={view} setView={setView} />
      </header>

      <div className="max-w-md mx-auto p-4 space-y-4">
        <div className="rounded-xl border border-ink-600 bg-ink-800 p-4">
          <div className="text-sm font-semibold mb-2">Your area</div>
          <div className="flex gap-2">
            <select value={wardId || ""} onChange={(e) => setWardId(Number(e.target.value) || null)}
              className="flex-1 bg-ink-900 border border-ink-600 rounded px-2 py-1.5 text-sm
                         text-slate-100 outline-none focus:border-accent">
              <option value="">Select your ward…</option>
              {sorted.map((w) => (
                <option key={w.ward_id} value={w.ward_id}>
                  {w.ward_name} ({w.zone})
                </option>
              ))}
            </select>
            <button onClick={useMyLocation} disabled={locating}
              className="px-3 py-1.5 rounded border border-ink-600 text-accent text-sm
                         hover:border-accent disabled:opacity-50 whitespace-nowrap">
              {locating ? "…" : "📍 Locate"}
            </button>
          </div>
        </div>

        {wardId ? (
          <>
            <RiskCard advisory={advisory} />
            <Chat wardId={wardId} />
            <ReportForm wardId={wardId} geo={geo} />
          </>
        ) : (
          <div className="text-sm text-slate-500 text-center py-8">
            Pick your ward or tap <b className="text-slate-300">Locate</b> to see your
            flood risk, ask questions, and report waterlogging.
          </div>
        )}
        <div className="text-center text-[10px] text-slate-600 pb-4">
          Complaint-verified waterlogging risk — not a guaranteed forecast.
        </div>
      </div>
    </div>
  );
}
