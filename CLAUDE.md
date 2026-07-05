# PROJECT VARUNA — Flood Decision Intelligence Platform
### (Varuna: Vedic deity of water — Ward-level Analytics, Risk & Urban Nowcasting Agent)

> **This file is the single source of truth for Claude Code.** It captures the full ideation, research, architecture, and constraints decided during planning. Read it fully before writing any code. When in doubt, prefer decisions written here over improvisation.

---

## 1. CONTEXT: What this is and why it exists

We are building a prototype for the **Hack2skill × Google Cloud APAC Gen AI Academy Hackathon**.

**Official problem statement (verbatim summary):** Build an AI-powered Decision Intelligence Platform that leverages data, AI models, and intelligent automation to help individuals, communities, organizations, and city stakeholders analyze information, generate insights, predict outcomes, and make better decisions. Solutions must be able to: understand and analyze data, answer questions in natural language, identify patterns and anomalies, generate recommendations, automate workflows, and support decision-making through AI-powered assistance. **The prototype MUST be deployed on Google Cloud.**

**What wins (from research on the same organizer's previous hackathon, Gen AI Exchange 2025):**
- Judges rewarded agentic systems and explainable models built for production, NOT prototype-style chatbot demos.
- Teams were grilled on real-world constraints: data availability, privacy, reliability, cost at scale.
- Last cycle's winners covered: citizen governance (GovernAI — overall winner), mental health, legal doc simplification, misinformation detection, career advisors, trip planning, cement plant optimization. **These categories are saturated — we deliberately avoid them.**
- Honest metric interpretation and transparent design tradeoffs are rewarded (this is also the team's style — keep it).

**Our winning formula:** sharp real-world domain + real government data + prediction (not just chat) + agentic workflow + explainability + dual stakeholder views + genuinely deployed on Cloud Run + credible pan-India scalability story.

---

## 2. THE IDEA (final, decided)

**VARUNA is a flood/monsoon decision-intelligence platform for Indian cities, prototyped on Bengaluru.** It fuses three signals nobody else combines:

1. **Weather signal** — rainfall forecasts + historical rainfall (Open-Meteo API).
2. **Infrastructure signal** — BBMP's official flood-prone / low-lying location data.
3. **Human sensor network** — 5+ years of real citizen grievance data (700K+ records). Waterlogging/drainage complaints act as real-time ground-truth sensors. A spike in water-stagnation complaints in a ward is an early-warning signal that fires HOURS before a rainfall model alone would flag risk.

**Embedded module — "CityPulse":** a conversational decision-intelligence engine over the full grievance corpus (NL-to-SQL analytics + proactive anomaly detection). This was originally a separate idea; we merged it in because ~70% of the architecture is shared. It makes the platform useful year-round, not just during monsoon.

**Core narrative for judges:** "Citizen complaints are a city's largest untapped sensor network. VARUNA turns them into predictive infrastructure. Deployed for Bengaluru. Architected for 4,500 ULBs."

**Differentiation vs. last cycle's GovernAI (must be visibly true in the product):** GovernAI was a *reactive* grievance portal (citizen files → system routes). VARUNA is *proactive*: the system detects anomalies and predicts risk before anyone asks, and the agent drafts a response plan justified against official SOPs.

---

## 3. USERS & VIEWS (two personas, two dashboards)

### Persona A: City authority (BBMP zonal officer / control room)
**"Command View"** — the money screen for the demo:
- Live ward-level flood risk map of Bengaluru (198 wards, choropleth, next 6/24/48 hrs).
- Anomaly feed: proactive alerts from the grievance stream ("Water-stagnation complaints in Bellandur ward at 4× the seasonal baseline in the last 6 hours").
- Explainability panel: WHY a ward is high risk (top feature attributions: forecast rain mm, historical flood incidents, low-lying flag, live complaint velocity).
- Agent-generated Response Plan: pre-position pumps/crews, draft citizen alert text, each recommendation citing the SOP passage that justifies it.
- Conversational analytics (CityPulse): ask anything over 5 years of grievances in natural language → SQL → chart + narrative answer.
- What-if simulator: "What if 80mm falls in 2 hours over Koramangala?" → re-scored risk map.

### Persona B: Citizen
**"Citizen View"** — lightweight, mobile-friendly:
- NL chat: "Will Silk Board area flood tomorrow evening?" → grounded answer from the risk model + forecast.
- Report an issue: upload photo (+ optional voice note) of waterlogging → Gemini Vision extracts severity/water-depth estimate/category → geotagged → appears on Command View map in real time.
- Safety advisories for their ward, generated from the current risk state.

---

## 4. FEATURES with build priority

**P0 — must exist for submission (the demo dies without these):**
1. Data pipeline: grievances + flood-prone locations + ward GeoJSON + rainfall → BigQuery (multi-city schema, see §7).
2. Ward-level flood risk model (see §8) with per-ward explanation.
3. Command View: risk map (Leaflet) + explainability panel.
4. CityPulse NL-to-SQL conversational analytics with chart rendering.
5. Citizen photo report → Gemini Vision analysis → Firestore → live on map.
6. ADK Response Planner agent with RAG over disaster SOPs (NDMA/KSDMA/BBMP PDFs).
7. Deployed on Cloud Run, publicly reachable URL.

**P1 — strongly boosts winning odds:**
8. Anomaly detection job (BQML ARIMA_PLUS per ward×category) feeding the anomaly feed + insight agent that investigates and writes an alert brief.
9. What-if rainfall simulator.
10. Citizen NL chat grounded on risk model output.
11. City switcher with "second city lite" (Mumbai or Chennai, rainfall-risk-only mode) — proves multi-city architecture in one click. **Timebox: max half a day. First thing to cut if behind.**

**P2 — only if time remains:**
12. Voice note input (Gemini audio understanding).
13. Alert dispatch simulation (drafted SMS/WhatsApp-style messages).
14. Historical replay mode (scrub through the May 2025 red-alert event showing how VARUNA would have flagged it early — this event is real and documented in the data).

**Non-goals (do NOT build):** authentication/user accounts, real SMS sending, payment, mobile apps, real-time drain sensors, admin CRUD. This is a judged prototype.

---

## 5. REAL DATA SOURCES (verified to exist — download these first)

| Dataset | Source | Notes |
|---|---|---|
| BBMP grievances 2020–2025 (~700K+ records, ward-level, categorized, timestamped, resolution status) | OpenCity data portal: https://data.opencity.in/dataset/bbmp-grievances-data | THE core dataset. Contains flooding/waterlogging/drainage categories → training labels AND CityPulse corpus. 126,974 records in H1 2025 alone. |
| Flood-prone / low-lying locations (BBMP) | OpenCity: https://data.opencity.in/dataset/flooding-locations-in-bengaluru-urban (KML resource available) | BBMP identified 200+ flood-prone spots in 2020 with root causes; also a low-lying-areas KML. Static risk features. |
| Ward boundaries GeoJSON (198 wards) | OpenCity / Bengaluru GIS portal (search "BBMP ward boundaries GeoJSON" on data.opencity.in) | Join key for everything. If 198 vs 225 ward-delimitation versions conflict, use the version matching the grievance data's ward names. |
| Rainfall — historical hourly + 7-day forecast | Open-Meteo API (free, no key): https://open-meteo.com — forecast: `api.open-meteo.com/v1/forecast`, historical: `archive-api.open-meteo.com/v1/archive` | Pan-India coverage. Sample a grid of points across Bengaluru (e.g., 8 zone centroids) rather than one city point. |
| Disaster SOPs for RAG | NDMA urban flooding guidelines PDF (ndma.gov.in), Karnataka SDMA / BBMP disaster management plan PDFs | Download 3–5 PDFs, chunk + embed for the Response Planner agent's citations. |

**Known data gaps — handle honestly, never hide:** no public drain-network shapefile, no real-time drain sensors, complaint data has reporting bias (affluent/tech corridors report more). The UI/pitch must state these as limitations and the architecture must be described as "sensor-ready."

---

## 6. GCP ARCHITECTURE & HARD BUDGET CONSTRAINT

**BUDGET: ₹0 target, ₹1000 absolute ceiling (~$12). No credits available. This constraint overrides convenience. Set a GCP budget alert at ₹500 immediately.**

| Layer | Service | Why / cost tactic |
|---|---|---|
| Frontend + Backend | **Cloud Run** (scale-to-zero, min-instances=0) | Free tier: 2M req + 360K GB-sec/month. Prefer ONE container serving both API and built frontend to keep it simple. |
| Warehouse + ML | **BigQuery + BQML** | Free: 10GB storage, 1TB query/month. Our data <1GB. BQML training fits free tier. |
| LLM | **Gemini 2.x Flash via Google AI Studio API key** (google-genai Python SDK) | CRITICAL: do NOT create Vertex AI online endpoints (always-on billing = budget killer). AI Studio free tier + cheap paid Flash calls. The SDK can flip to Vertex with a config change if judges require — mention this in README. |
| App state / citizen reports | **Firestore (native mode)** | Free: 1GB, 50K reads/day. |
| Agents | **ADK (google-adk)** running inside the Cloud Run container | It's a Python library; costs nothing itself. Judges explicitly value ADK usage. |
| Embeddings/RAG | Gemini embedding API + **in-container ChromaDB** (persisted to container image or GCS) | Avoid managed vector DBs. Alternatively BigQuery vector search — pick whichever is less code. |
| Scheduled ingestion | **Cloud Scheduler → Cloud Run job** (hourly Open-Meteo pull) | Free tier covers it. For the demo, an on-demand refresh endpoint is an acceptable fallback. |
| Maps | **Leaflet + OpenStreetMap tiles** | Free. Do NOT use Google Maps JS API (metering risk). |
| Secrets | Env vars on Cloud Run (GEMINI_API_KEY). Never commit keys. | |

**Explicitly banned services (cost traps):** Vertex AI endpoints, AlloyDB, Cloud SQL, GKE, Memorystore, always-on VMs, paid Looker.

---

## 7. DATA MODEL — multi-city from day one (non-negotiable design rule)

Every table carries `city_id`. Geography is generic: `city → zone → ward`. Nothing hardcodes "BBMP".

BigQuery dataset: `varuna`
- `cities(city_id, name, bbox, config_json)`
- `wards(city_id, ward_id, ward_name, zone, geometry GEOGRAPHY, is_low_lying BOOL, historical_flood_count INT)`
- `grievances(city_id, grievance_id, ward_id, category_raw, category_norm, description, created_at, status, lat, lng)` — `category_norm` maps each city's taxonomy to a shared one (WATERLOGGING, DRAINAGE, GARBAGE, ROADS, WATER_SUPPLY, STREETLIGHT, OTHER...). Mapping lives in the city config, not code.
- `rainfall_hourly(city_id, grid_point_id, ts, rain_mm, source)` (historical + forecast rows, `is_forecast` flag)
- `risk_scores(city_id, ward_id, horizon_hrs, score, computed_at, top_features JSON)`
- `anomalies(city_id, ward_id, category_norm, ts, observed, expected, deviation, status)`
- `citizen_reports` lives in Firestore (real-time needs), mirrored to BQ nightly if needed.

**City onboarding = a config file** (`configs/bengaluru.yaml`, `configs/mumbai.yaml`): bbox, ward GeoJSON path, category mapping, data adapters, mode: `full | rain_only`.

---

## 8. ML DESIGN

### 8a. Flood risk model (P0)
- **Label:** for each (ward, day) in 2020–2025: `1` if waterlogging/drainage/flooding complaints ≥ threshold (tune; e.g., ≥2 to cut noise), else `0`. Complaints are a proxy for flooding — this is a defensible, documented choice; state the reporting-bias caveat.
- **Features:** rain last 3/6/24/72 hrs (nearest grid point), forecast rain next 6/24 hrs, `is_low_lying`, historical flood-prone count in ward, month/monsoon flag, ward complaint baseline (reporting-propensity control), rolling complaint velocity.
- **Model:** BQML `BOOSTED_TREE_CLASSIFIER` (XGBoost under the hood — team has deep LightGBM/SHAP experience from a prior project called TRAVIS; keep the same honest-metrics style). Use `ML.EXPLAIN_PREDICT` for per-ward feature attributions → the explainability panel.
- **Evaluation:** temporal split (train ≤2023, validate 2024, test 2025 incl. the May 2025 red-alert event). Report PR-AUC and recall@top-20-wards, NOT just accuracy (heavy class imbalance). Honest framing: "complaint-verified waterlogging risk", not "flood prediction".
- Fallback if BQML fights us: train LightGBM locally in Python, ship the model file inside the Cloud Run container. Equivalent story, zero cost.

### 8b. Anomaly detection (P1)
- BQML `ARIMA_PLUS` per (ward × category_norm) on daily complaint counts, or a simpler rolling z-score vs. seasonal baseline if ARIMA_PLUS per-series count gets unwieldy (198 wards × ~8 categories — consider modeling only top categories, or zone level). Simplicity > sophistication; the agent narrative on top matters more than the detector.
- Output rows → `anomalies` table → anomaly feed + Insight Agent.

---

## 9. AGENT DESIGN (ADK)

Three agents, orchestrated, all inside the Cloud Run app. Every agent output must show its reasoning/citations in the UI — visible agency is the demo.

1. **RiskAnalyst Agent** — tools: query risk_scores, query rainfall forecast, query anomaly feed. Job: compose the current situation assessment ("which wards, why, confidence").
2. **ResponsePlanner Agent** — tools: RAG search over SOP PDFs, risk assessment from RiskAnalyst, (mock) resource inventory (JSON of pumps/crews/shelters per zone — clearly labeled simulated). Job: produce a prioritized action plan; EACH action cites the SOP chunk justifying it (e.g., "NDMA Urban Flooding Guidelines §4.2"). Also drafts the citizen advisory text.
3. **CityPulse Insight Agent** — trigger: new anomaly row. Tools: NL-to-SQL over grievances, rainfall lookup. Job: investigate the anomaly (correlate with rain, history, neighboring wards) and write a short explainable alert brief.

**NL-to-SQL (CityPulse chat):** Gemini Flash with the full table schemas + category vocabulary + 8–10 few-shot examples in the system prompt. Guardrails: SELECT-only, table allowlist, LIMIT enforced, dry-run for bytes-scanned cap, on SQL error retry once with the error message. Render results as table + auto-picked chart (recharts) + one-paragraph narrative answer.

---

## 10. TECH STACK & REPO STRUCTURE

- **Backend:** Python 3.11, FastAPI, google-genai SDK, google-adk, google-cloud-bigquery, google-cloud-firestore, chromadb, pypdf (SOP ingestion).
- **Frontend:** React + Vite + Tailwind, Leaflet (react-leaflet), recharts. Built and served as static files by FastAPI (single container). A polished custom UI beats Streamlit for judging — invest here.
- **Deploy:** single Dockerfile → Cloud Run (`gcloud run deploy --source .`), min-instances 0, region asia-south1.

```
varuna/
├── CLAUDE.md                  # this file
├── README.md                  # judge-facing: problem, architecture diagram, honest limitations, setup
├── configs/                   # bengaluru.yaml, mumbai.yaml (city onboarding = config)
├── data/                      # raw downloads (gitignored) + small processed samples
├── ingestion/                 # download/clean scripts, BQ loaders, open-meteo puller, SOP pdf → chroma
├── ml/                        # BQML SQL for risk model + ARIMA_PLUS, eval notebook/script, lightgbm fallback
├── backend/
│   ├── main.py                # FastAPI app
│   ├── routers/               # risk, citypulse_chat, reports, whatif, agents
│   ├── agents/                # ADK: risk_analyst, response_planner, insight_agent + tools
│   └── services/              # bq client, gemini client, nl2sql guardrails, firestore
├── frontend/                  # React app: CommandView, CitizenView, city switcher
├── Dockerfile
└── deploy/                    # cloudbuild/deploy notes, budget-alert setup note
```

---

## 11. BUILD ORDER (dependency-driven — follow this sequence)

1. **Data foundation:** download all datasets → clean → normalize categories → load BigQuery (multi-city schema) → validate ward-name joins between grievances and GeoJSON (this join WILL be messy; budget time for fuzzy matching).
2. **Risk model:** rainfall backfill → feature SQL → BQML training → temporal eval → `risk_scores` populated with explanations.
3. **Backend API:** risk endpoints, NL-to-SQL chat with guardrails, photo-report endpoint (Gemini Vision → Firestore).
4. **Command View UI:** map + explainability + CityPulse chat panel.
5. **Agents:** SOP RAG → ResponsePlanner → RiskAnalyst → wire "Generate Response Plan" button. Then Insight Agent + anomaly job (P1).
6. **Citizen View + what-if + polish.**
7. **Deploy to Cloud Run early (by end of step 3) and keep deploying** — deployment is a submission requirement, never leave it for the end.
8. **Second city lite mode** (P1, timeboxed) + demo script + README.

---

## 12. DEMO SCRIPT (3 minutes — build toward exactly this)

1. Open Command View: "It rained hard last night. VARUNA has already ranked all 198 wards by flood risk for the next 24 hours." (map, explain one red ward via feature attributions)
2. Anomaly feed pings: complaints spiking in a ward the rain model rated moderate — "citizens are our sensor network."
3. Click **Generate Response Plan** → agent visibly reasons → plan with SOP citations + drafted citizen advisory.
4. Switch to Citizen View → upload waterlogging photo → Gemini Vision severity → dot appears live on Command map.
5. CityPulse: type "Compare drainage complaints in Mahadevapura vs Bommanahalli during the May 2025 red-alert week" → SQL → chart → narrative.
6. City switcher → Mumbai (rain-only mode): "same platform, config-driven — Bengaluru is full-mode only because its data is open. Any ULB's Swachhata/ICCC feed makes it full-mode. Deployed for Bengaluru, architected for 4,500 ULBs."

---

## 13. GUARDRAILS FOR CLAUDE CODE

- Respect the budget bans in §6 absolutely. If a step seems to need a banned service, stop and propose an alternative.
- Never fabricate data. Simulated things (resource inventory, alert dispatch) must be labeled "simulated" in UI and README.
- Keep the honest-limitations section in README current (complaint proxy bias, no drain sensors, ward-join caveats).
- Prefer boring, working code over clever code. P0 completeness beats P1 sophistication.
- Every agent/LLM feature must degrade gracefully (API error → readable fallback, never a blank screen during judging).
- Commit early, commit often; keep `gcloud run deploy` working at all times after step 3.


## Git Commit Guidelines
- Do not include AI attribution or co-author lines in commit messages.