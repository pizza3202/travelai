from app.agents.base import mark_agent_used, state_patch
from app.models.schemas import AgentState, TransportPlan, TravelBrief
from app.services.travel_tools import estimate_transport


async def run_transport(state: AgentState) -> dict:
    brief = TravelBrief.model_validate(state.brief) if state.brief else None
    if not brief or not brief.destination:
        return state_patch(state)
    days = brief.duration_days or 5
    raw = await estimate_transport(brief.destination, days)
    transport = [TransportPlan.model_validate(t) for t in raw]
    return state_patch(
        state,
        transport=[t.model_dump(mode="json") for t in transport],
        agents_used=mark_agent_used(state, "transport"),
    )
