import ViewSwitch from "../components/ViewSwitch.jsx";

const FEATURES = [
  [ "Ward-level risk map", "All 198 Bengaluru wards scored for flood risk over the next 24h, with a click-through panel that explains WHY each ward is at risk (per-ward model feature attributions)."],
  ["Anomaly feed — citizens as sensors", "Detects wards where flood complaints spike far above their seasonal baseline — an early-warning that can fire before rainfall models, flagging cases the model rated only 'moderate'."],
  ["Insight agent", "An ADK agent investigates each anomaly: correlates rainfall, compares neighbouring wards, checks the model rating, and writes an explainable alert brief."],
  ["SOP-grounded response planner", "An ADK agent reads live risk, searches official NDMA flood-management SOPs, allocates resources, and drafts a prioritized action plan where every action cites the SOP page that justifies it."],
  ["CityPulse analytics", "Ask 5+ years of grievances in plain English → guarded SQL over BigQuery → chart + narrative answer."],
  ["What-if simulator", "Push a hypothetical storm (mm / zone) through the trained model and watch the risk map re-score live."],
  ["Citizen reporting", "Residents upload a waterlogging photo → Gemini Vision estimates severity & water depth → geotagged → appears live on the control-room map."],
  ["Grounded citizen assistant", "Locate your ward, get a safety advisory, and ask questions answered from your ward's real risk + rainfall."],
];

const STATS = [
  ["766,648", "real BBMP grievances", "2020–2025"],
  ["198", "wards mapped", "GeoJSON boundaries"],
  ["385,536", "hourly rainfall records", "Open-Meteo, 8 zones"],
  ["477", "complaint anomalies", "flagged early-warnings"],
];

function Badge({ children }) {
  return (
    <span className="px-2.5 py-1 rounded-full bg-ink-700 border border-ink-600
                     text-[12px] text-slate-300">{children}</span>
  );
}

function Card({ children, className = "" }) {
  return (
    <div className={`rounded-xl border border-ink-600 bg-ink-800 p-5 ${className}`}>
      {children}
    </div>
  );
}

export default function HomeView({ view, setView }) {
  return (
    <div className="flex-1 overflow-auto bg-ink-900">
      <header className="flex items-center gap-3 px-5 h-16 border-b border-ink-600
                         bg-ink-800/80 backdrop-blur sticky top-0 z-10">
        <span className="text-2xl font-extrabold tracking-tight bg-gradient-to-r
                         from-accent to-accent-soft bg-clip-text text-transparent">
          VARUNA
        </span>
        <span className="text-[11px] text-slate-500 hidden sm:inline">
          Flood Decision Intelligence
        </span>
        <div className="flex-1" />
        <ViewSwitch view={view} setView={setView} />
      </header>

      <div className="max-w-5xl mx-auto px-5 py-10 space-y-12">
        {/* Hero */}
        <section className="text-center">
          <div className="text-5xl font-extrabold tracking-tight bg-gradient-to-r
                          from-accent to-accent-soft bg-clip-text text-transparent">
            VARUNA
          </div>
          <p className="mt-2 text-slate-400 text-sm">
            Ward-level Analytics, Risk &amp; Urban Nowcasting Agent
          </p>
          <h1 className="mt-5 text-2xl sm:text-3xl font-bold text-slate-100 leading-snug">
            Citizen complaints are a city's largest untapped sensor network.
            <br className="hidden sm:block" />
            <span className="text-accent"> VARUNA turns them into predictive flood infrastructure.</span>
          </h1>
          <p className="mt-4 text-slate-400 max-w-2xl mx-auto">
            A flood decision-intelligence platform for Indian cities — fusing rainfall
            forecasts, official flood-prone maps, and 5+ years of real citizen grievance
            data into ward-level risk, proactive anomaly alerts, and agentic response
            plans grounded in disaster-management SOPs. Prototyped on Bengaluru,
            architected for 4,500 ULBs.
          </p>
          <div className="mt-6 flex gap-3 justify-center">
            <button onClick={() => setView("command")}
              className="px-5 py-2.5 rounded-lg bg-accent text-ink-900 font-semibold
                         hover:brightness-110">Open Command View →</button>
            <button onClick={() => setView("citizen")}
              className="px-5 py-2.5 rounded-lg border border-ink-600 text-slate-200
                         hover:border-accent">Citizen View</button>
          </div>
        </section>

        {/* Stats */}
        <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {STATS.map(([n, label, sub]) => (
            <Card key={label} className="text-center">
              <div className="text-2xl font-extrabold text-accent tabular-nums">{n}</div>
              <div className="text-sm text-slate-200 mt-1">{label}</div>
              <div className="text-[11px] text-slate-500">{sub}</div>
            </Card>
          ))}
        </section>

        {/* Features */}
        <section>
          <h2 className="text-lg font-bold text-slate-100 mb-4">What it does</h2>
          <div className="grid sm:grid-cols-2 gap-3">
            {FEATURES.map(([icon, title, desc]) => (
              <Card key={title}>
                <div className="flex items-start gap-3">
                  <div className="text-2xl">{icon}</div>
                  <div>
                    <div className="font-semibold text-slate-100">{title}</div>
                    <div className="text-[13px] text-slate-400 mt-1 leading-relaxed">{desc}</div>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        </section>

        {/* Under the hood */}
        <section>
          <h2 className="text-lg font-bold text-slate-100 mb-4">Under the hood</h2>
          <div className="grid md:grid-cols-3 gap-3">
            <Card>
              <div className="text-accent font-semibold mb-2"> Data</div>
              <ul className="text-[13px] text-slate-300 space-y-1.5 list-disc ml-4">
                <li>766,648 BBMP grievances (2020–2025), ward-tagged &amp; categorized</li>
                <li>198-ward BBMP boundaries (GeoJSON)</li>
                <li>270 flood-prone + 129 low-lying hazard points</li>
                <li>385,536 hourly rainfall records (Open-Meteo, 8 zones)</li>
                <li>2 NDMA flood-management SOP PDFs → 200 embedded chunks</li>
              </ul>
              <div className="text-[11px] text-slate-500 mt-2">
                All real &amp; public. Ingested → normalized → BigQuery.
              </div>
            </Card>
            <Card>
              <div className="text-accent font-semibold mb-2"> Models trained</div>
              <ul className="text-[13px] text-slate-300 space-y-1.5 list-disc ml-4">
                <li><b>BigQuery ML BOOSTED_TREE_CLASSIFIER</b> — ward flood-risk model</li>
                <li>Temporal eval: <b>ROC-AUC 0.87</b>, PR-AUC 0.16–0.21, recall@top-20 ≈ 0.59</li>
                <li>Per-ward explanations via <b>ML.EXPLAIN_PREDICT</b></li>
                <li>Rolling z-score anomaly detector over daily complaint counts</li>
              </ul>
              <div className="text-[11px] text-slate-500 mt-2">
                Honest framing: complaint-verified waterlogging risk, not certainty.
              </div>
            </Card>
            <Card>
              <div className="text-accent font-semibold mb-2">AI in use</div>
              <ul className="text-[13px] text-slate-300 space-y-1.5 list-disc ml-4">
                <li><b>Gemini 2.5 Flash</b> — NL-to-SQL, Vision, agents</li>
                <li><b>gemini-embedding-001</b> — SOP RAG (cosine retrieval)</li>
                <li><b>Google ADK</b> — 3 agents: RiskAnalyst, ResponsePlanner, Insight</li>
                <li>Gemini Vision — citizen photo severity/depth extraction</li>
              </ul>
            </Card>
          </div>
        </section>

        {/* Stack */}
        <section>
          <h2 className="text-lg font-bold text-slate-100 mb-3">Deployed on Google Cloud</h2>
          <div className="flex flex-wrap gap-2">
            {["Cloud Run (scale-to-zero)", "BigQuery + BQML", "Firestore", "Gemini (AI Studio)",
              "Google ADK", "FastAPI", "React + Vite", "Tailwind", "Leaflet", "Recharts",
              "Open-Meteo"].map((t) => <Badge key={t}>{t}</Badge>)}
          </div>
        </section>

        <footer className="text-center text-[11px] text-slate-600 pb-6">
          VARUNA · built by{" "}
          <a href="https://www.linkedin.com/in/darshan01/" target="_blank"
             rel="noopener noreferrer" className="text-slate-400 hover:text-accent">
            Darshan Bhavsar
          </a>{" "}
          · deployed for Bengaluru, architected for 4,500 ULBs.
        </footer>
      </div>
    </div>
  );
}
