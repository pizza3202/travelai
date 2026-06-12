from app.agents.base import mark_agent_used, state_patch
from app.models.schemas import (
    ActivityPlan,
    AgentState,
    FlightEstimate,
    HotelEstimate,
    TransportPlan,
    TravelBrief,
)
from app.services.budget_service import compute_budget_summary


async def run_budget(state: AgentState) -> dict:
    brief = TravelBrief.model_validate(state.brief) if state.brief else None
    if not brief:
        return state_patch(state)
    summary = compute_budget_summary(
        brief,
        [FlightEstimate.model_validate(f) for f in state.flights],
        [HotelEstimate.model_validate(h) for h in state.hotels],
        [ActivityPlan.model_validate(a) for a in state.activities],
        [TransportPlan.model_validate(t) for t in state.transport],
    )
    return state_patch(
        state,
        budget_summary=summary.model_dump(mode="json"),
        agents_used=mark_agent_used(state, "budget"),
    )
