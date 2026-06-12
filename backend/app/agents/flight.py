from app.agents.base import mark_agent_used, state_patch
from app.models.schemas import AgentState, FlightEstimate, TravelBrief
from app.services.travel_tools import search_flights


async def run_flight(state: AgentState) -> dict:
    brief = TravelBrief.model_validate(state.brief) if state.brief else None
    if not brief or not brief.destination:
        return state_patch(state)
    dep = brief.departure_city or state.departure_city or "San Francisco"
    raw = await search_flights(dep, brief.destination, brief.budget_usd or 5000)
    flights = [FlightEstimate.model_validate(f) for f in raw]
    return state_patch(
        state,
        flights=[f.model_dump(mode="json") for f in flights],
        agents_used=mark_agent_used(state, "flight"),
    )
