"""ADK agents for VARUNA (§9). Two orchestrated LlmAgents, run inside the Cloud Run
app. Every run returns the final text AND the tool-call trace, so the UI can show
the agent's reasoning (visible agency is the demo).

  RiskAnalyst    — tools: risk assessment, rainfall outlook. Composes the current
                   situation ("which wards, why, confidence").
  ResponsePlanner— tools: risk assessment, SOP RAG search, (simulated) resource
                   inventory. Produces a prioritized action plan where EACH action
                   cites the SOP passage that justifies it, plus a citizen advisory.
"""
from __future__ import annotations

import functools
import os

from ..services.settings import get_settings
from . import tools


def _configure_env():
    s = get_settings()
    # ADK reads GOOGLE_API_KEY; use the AI Studio key, not Vertex (§6).
    if s.gemini_api_key:
        os.environ.setdefault("GOOGLE_API_KEY", s.gemini_api_key)
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "0")


RISK_ANALYST_INSTRUCTION = """
You are VARUNA's RiskAnalyst for Bengaluru urban flooding. Assess the CURRENT
situation for a control-room officer.
1. Call get_risk_assessment to see how many wards are High/Moderate/Low and which
   wards are top risk.
2. Call get_rainfall_outlook to see recent rainfall per zone.
Then write a crisp situation assessment (<=180 words): the headline (how many wards
at high risk), the specific wards/zones of greatest concern and WHY (rain + low-lying
+ history), and a one-line confidence note. Be factual; use the numbers from the tools.
Frame it as complaint-verified waterlogging risk, not a certain flood forecast.
""".strip()

RESPONSE_PLANNER_INSTRUCTION = """
You are VARUNA's ResponsePlanner for Bengaluru urban flooding. Produce an actionable
response plan for a BBMP control-room officer.

Be economical with tool calls (each costs quota):
1. Call get_risk_assessment ONCE to identify the highest-risk wards/zones.
2. Call search_sops at most 3 times, for your 3 most important action themes
   (e.g. pumping/dewatering, drain clearing, warnings & evacuation).
3. Call get_resource_inventory ONCE with no zone argument to get all zones.

Then output GitHub-flavored markdown with these sections:
## Situation
One or two sentences on the headline risk.
## Prioritized Actions
A numbered list. For EACH action: what to do, which ward/zone, which resources to
allocate, and a citation to the SOP that justifies it in the form
`— <cite>, p.<page>` using the exact `cite` and `page` returned by search_sops.
Do NOT invent citations; only cite passages search_sops actually returned.
## Citizen Advisory
A short (<=60 words) plain-language safety message for residents of the top-risk area.

Note in one line that the resource inventory is simulated demo data.
""".strip()


def _is_retriable(exc) -> bool:
    """Quota (429) OR transient overload (503) OR missing model (404) -> try next."""
    s = str(exc).lower()
    return any(k in s for k in
               ("429", "resource_exhausted", "quota", "503", "unavailable",
                "high demand", "overloaded", "404", "not_found"))


@functools.lru_cache
def _build_agent(agent_name: str, model: str):
    _configure_env()
    from google.adk.agents import LlmAgent
    if agent_name == "risk_analyst":
        return LlmAgent(
            name="risk_analyst", model=model,
            description="Assesses current ward-level flood risk and rainfall.",
            instruction=RISK_ANALYST_INSTRUCTION,
            tools=[tools.get_risk_assessment, tools.get_rainfall_outlook])
    return LlmAgent(
        name="response_planner", model=model,
        description="Drafts an SOP-cited flood response plan and citizen advisory.",
        instruction=RESPONSE_PLANNER_INSTRUCTION,
        tools=[tools.get_risk_assessment, tools.search_sops,
               tools.get_resource_inventory])


def _agent_model_chain() -> list[str]:
    # ADK uses one model per run; on quota we retry the whole run with the next.
    # Start with the configured agent_model, then the general fallback chain.
    s = get_settings()
    chain = [s.agent_model] + [m for m in s.gemini_model_chain if m != s.agent_model]
    return chain


async def run_agent(agent_name: str, prompt: str) -> dict:
    """Run an agent to completion, retrying across the model chain on quota (429).
    Returns {text, tools_used, sop_citations, model}."""
    last_err = None
    for model in _agent_model_chain():
        try:
            out = await _run_once(_build_agent(agent_name, model), prompt)
            out["model"] = model
            return out
        except Exception as e:  # noqa: BLE001
            last_err = e
            if _is_retriable(e):
                continue          # exhausted/overloaded -> try the next model
            raise
    raise last_err or RuntimeError("no agent model succeeded")


async def _run_once(agent, prompt: str) -> dict:
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    runner = InMemoryRunner(agent=agent, app_name="varuna")
    session = await runner.session_service.create_session(
        app_name="varuna", user_id="officer")
    msg = types.Content(role="user", parts=[types.Part(text=prompt)])

    text_parts, tools_used, sop_citations = [], [], []
    async for ev in runner.run_async(user_id="officer", session_id=session.id,
                                     new_message=msg):
        if not ev.content:
            continue
        for p in ev.content.parts:
            fc = getattr(p, "function_call", None)
            if fc:
                tools_used.append(fc.name)
            fr = getattr(p, "function_response", None)
            if fr and fr.name == "search_sops":
                resp = fr.response or {}
                for pas in (resp.get("passages") or []):
                    key = (pas.get("cite"), pas.get("page"))
                    if key not in [(c["cite"], c["page"]) for c in sop_citations]:
                        sop_citations.append({"cite": pas.get("cite"),
                                              "page": pas.get("page")})
            if getattr(p, "text", None) and ev.is_final_response():
                text_parts.append(p.text)

    return {"text": "".join(text_parts).strip(),
            "tools_used": tools_used, "sop_citations": sop_citations}
