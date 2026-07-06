"""Agent endpoints (§9). The ResponsePlanner is the demo's "Generate Response Plan"
button; RiskAnalyst backs the situation summary. Both show their tool trace.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..agents import orchestrator, sop_rag
from ..services.settings import get_settings

router = APIRouter(prefix="/api/agents", tags=["agents"])


class PlanIn(BaseModel):
    focus: str | None = None   # optional ward/zone to emphasize


def _is_rate_limit(msg: str) -> bool:
    return "429" in msg or "RESOURCE_EXHAUSTED" in msg or "quota" in msg.lower()


async def _run(agent: str, prompt: str) -> dict:
    try:
        out = await orchestrator.run_agent(agent, prompt)
        out["ok"] = True
        return out
    except Exception as e:  # noqa: BLE001 — degrade gracefully (§13)
        msg = str(e)
        friendly = ("The AI is momentarily rate-limited; please try again shortly."
                    if _is_rate_limit(msg) else f"Agent failed: {msg[:200]}")
        return {"ok": False, "error": friendly, "text": "", "tools_used": [],
                "sop_citations": []}


@router.get("/status")
def status():
    return {"sops_available": sop_rag.available(),
            "sop_sources": sop_rag.sources(),
            "agent_model": get_settings().agent_model}


@router.post("/situation")
async def situation():
    return await _run("risk_analyst",
                      "Give me the current Bengaluru flood situation assessment.")


@router.post("/response-plan")
async def response_plan(body: PlanIn | None = None):
    focus = (body.focus if body else None)
    prompt = "Generate the current Bengaluru urban-flood response plan."
    if focus:
        prompt += f" Pay particular attention to {focus}."
    return await _run("response_planner", prompt)


class InvestigateIn(BaseModel):
    ward_id: int
    category_norm: str
    date: str                 # YYYY-MM-DD
    observed: float | None = None
    expected: float | None = None
    deviation: float | None = None


@router.post("/investigate")
async def investigate(body: InvestigateIn):
    prompt = (
        f"A complaint anomaly fired for ward_id={body.ward_id}, category="
        f"{body.category_norm}, date={body.date}: {int(body.observed or 0)} complaints "
        f"vs an expected {body.expected} (~{body.deviation}x the seasonal baseline). "
        "Investigate and write the alert brief.")
    return await _run("insight", prompt)
