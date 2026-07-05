# VARUNA — Flood Decision Intelligence Platform

> **Varuna** (Vedic deity of water) — **W**ard-level **A**nalytics, **R**isk & **U**rban **N**owcasting **A**gent.
> Built for the Hack2skill × Google Cloud APAC Gen AI Academy Hackathon. Prototyped on Bengaluru, architected for 4,500 ULBs.

## The one-liner
Citizen complaints are a city's largest untapped sensor network. VARUNA turns them into predictive flood infrastructure — fusing rainfall forecasts, official flood-prone maps, and 5+ years of real BBMP grievance data into ward-level risk, proactive anomaly alerts, and an agentic response planner grounded in disaster-management SOPs.

## Status
🚧 Under active construction. See [CLAUDE.md](CLAUDE.md) for the full plan and build order.

**Live demo (API + landing):** https://varuna-229692962627.asia-south1.run.app
Data foundation, flood-risk model, and backend API (risk map, CityPulse NL-to-SQL,
citizen photo reports) are deployed on Cloud Run. Command/Citizen View UI is next.

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
- **Risk model leans on ward baseline.** The strongest feature is `ward_flood_baseline` (chronic per-ward complaint rate, gain ≈ 0.58) — i.e. the model partly learns "which wards habitually complain." Dynamic risk still comes from rainfall + citizen-complaint velocity (next-strongest features), and notably `velocity_prev_3d` (the human-sensor signal) outranks the rain forecast. Honest reading: on a dry day risk ≈ a ward's chronic propensity; rain and complaint spikes move it. Framed as *complaint-verified waterlogging risk*, not ground-truth flood prediction.

## Risk model — current numbers (temporal eval, §8a)
Trained on ≤2023, validated 2024, tested 2025 (incl. the real May-2025 red-alert event). Heavy class imbalance (~1–2.5% positive) → PR-AUC & recall@top-20, not accuracy.

| split | ROC-AUC | PR-AUC | recall@top-20 wards/day |
|---|---|---|---|
| val (2024) | 0.866 | 0.158 | 0.563 |
| test (2025) | 0.866 | 0.207 | 0.594 |

PR-AUC is ~8–10× the positive base rate. Sanity check: the top-ranked wards (Bellandur, Begur, Horamavu) are well-known Bengaluru flooding hotspots. Full report: `ml/eval_report.md`.

## Data sources
See [CLAUDE.md §5](CLAUDE.md). All datasets are real & public (OpenCity BBMP grievances, BBMP flood-prone locations, ward GeoJSON, Open-Meteo rainfall).

## Setup
_TODO: fill in as the pipeline lands._
