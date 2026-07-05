# VARUNA — Flood Decision Intelligence Platform

> **Varuna** (Vedic deity of water) — **W**ard-level **A**nalytics, **R**isk & **U**rban **N**owcasting **A**gent.
> Built for the Hack2skill × Google Cloud APAC Gen AI Academy Hackathon. Prototyped on Bengaluru, architected for 4,500 ULBs.

## The one-liner
Citizen complaints are a city's largest untapped sensor network. VARUNA turns them into predictive flood infrastructure — fusing rainfall forecasts, official flood-prone maps, and 5+ years of real BBMP grievance data into ward-level risk, proactive anomaly alerts, and an agentic response planner grounded in disaster-management SOPs.

## Status
🚧 Under active construction. See [CLAUDE.md](CLAUDE.md) for the full plan and build order.

## Architecture (target)
- **Frontend + API:** React (Vite/Tailwind/Leaflet) served by FastAPI, single container on **Cloud Run** (scale-to-zero).
- **Warehouse + ML:** **BigQuery + BQML** (boosted-tree risk model, ARIMA_PLUS anomaly detection).
- **LLM:** Gemini 2.x Flash via google-genai SDK. **Agents:** google-adk (RiskAnalyst, ResponsePlanner, CityPulse Insight).
- **State / citizen reports:** Firestore. **RAG:** Gemini embeddings + in-container ChromaDB.

## Honest limitations (kept current — never hidden)
- **Complaint proxy bias:** waterlogging risk is trained on citizen complaints, which over-represent affluent/tech corridors that report more. We control for ward reporting propensity but the bias is real. Framed as "complaint-verified waterlogging risk", not "flood prediction".
- **No drain-network data:** no public drain shapefile or real-time drain sensors exist. Architecture is "sensor-ready".
- **Ward-name joins:** grievance ward strings vs. GeoJSON ward names require fuzzy matching; residual mismatches are documented in the join report.
- **Simulated elements:** resource inventory (pumps/crews) and alert dispatch are clearly labeled *simulated* in UI and code.

## Data sources
See [CLAUDE.md §5](CLAUDE.md). All datasets are real & public (OpenCity BBMP grievances, BBMP flood-prone locations, ward GeoJSON, Open-Meteo rainfall).

## Setup
_TODO: fill in as the pipeline lands._
