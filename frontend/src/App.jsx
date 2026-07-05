import { useEffect, useState } from "react";
import api from "./api.js";
import Header from "./components/Header.jsx";
import RiskMap from "./components/RiskMap.jsx";
import WardPanel from "./components/WardPanel.jsx";
import RankedList from "./components/RankedList.jsx";
import CityPulse from "./components/CityPulse.jsx";
import ResponsePlan from "./components/ResponsePlan.jsx";
import { BAND_COLORS, BAND_LABEL } from "./lib/format.js";

const CITY = "blr";
const HORIZON = 24;

function Legend() {
  return (
    <div className="absolute bottom-4 left-4 z-[500] bg-ink-800/90 backdrop-blur rounded-lg
                    border border-ink-600 px-3 py-2 text-[11px] space-y-1">
      <div className="text-slate-400 mb-1">Flood risk (next 24h)</div>
      {["high", "moderate", "low", "unknown"].map((b) => (
        <div key={b} className="flex items-center gap-2">
          <span className="w-3 h-3 rounded-sm" style={{ background: BAND_COLORS[b] }} />
          <span className="text-slate-300">{BAND_LABEL[b]}</span>
        </div>
      ))}
    </div>
  );
}

export default function App() {
  const [summary, setSummary] = useState(null);
  const [geojson, setGeojson] = useState(null);
  const [ranked, setRanked] = useState([]);
  const [selectedWard, setSelectedWard] = useState(null);
  const [tab, setTab] = useState("wards");
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([
      api.summary(CITY, HORIZON),
      api.wardsGeojson(CITY, HORIZON),
      api.wardsRanked(CITY, HORIZON),
    ])
      .then(([s, g, r]) => {
        setSummary(s);
        setGeojson(g);
        setRanked(r.wards || []);
      })
      .catch((e) => setError(String(e)));
  }, []);

  function selectWard(id) {
    setSelectedWard(id);
    setTab("wards");
  }

  return (
    <div className="h-full flex flex-col">
      <Header cityName="Bengaluru" summary={summary} />

      {error && (
        <div className="bg-risk-high/20 text-risk-high text-sm px-5 py-2 border-b border-risk-high/30">
          Failed to load data: {error}
        </div>
      )}

      <div className="flex-1 flex min-h-0">
        {/* Map */}
        <div className="relative flex-1 min-w-0">
          <RiskMap
            geojson={geojson}
            horizon={HORIZON}
            selectedWard={selectedWard}
            onSelectWard={selectWard}
          />
          <Legend />
          {!geojson && !error && (
            <div className="absolute inset-0 grid place-items-center text-slate-400 z-[400]">
              Loading risk map…
            </div>
          )}
        </div>

        {/* Sidebar */}
        <aside className="w-[440px] shrink-0 border-l border-ink-600 bg-ink-800 flex flex-col">
          <div className="flex border-b border-ink-600">
            {[
              ["wards", "Ward risk"],
              ["plan", "Response Plan"],
              ["citypulse", "CityPulse"],
            ].map(([id, label]) => (
              <button
                key={id}
                onClick={() => setTab(id)}
                className={`flex-1 py-2.5 text-sm font-medium border-b-2 transition
                  ${tab === id
                    ? "border-accent text-accent"
                    : "border-transparent text-slate-400 hover:text-slate-200"}`}
              >
                {label}
              </button>
            ))}
          </div>

          {tab === "wards" && (
            <div className="flex-1 flex flex-col min-h-0">
              <div className="border-b border-ink-600">
                <WardPanel wardId={selectedWard} city={CITY} horizon={HORIZON} />
              </div>
              <div className="px-4 py-2 text-[11px] uppercase tracking-wide text-slate-500">
                All wards by risk
              </div>
              <div className="flex-1 overflow-auto">
                <RankedList
                  wards={ranked}
                  selectedWard={selectedWard}
                  onSelectWard={selectWard}
                />
              </div>
            </div>
          )}
          {tab === "plan" && (
            <ResponsePlan
              focus={ranked.find((w) => w.ward_id === selectedWard)?.ward_name}
            />
          )}
          {tab === "citypulse" && <CityPulse />}
        </aside>
      </div>
    </div>
  );
}
