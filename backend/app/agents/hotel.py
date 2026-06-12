from app.agents.base import mark_agent_used, state_patch
from app.models.schemas import AgentState, HotelEstimate, TravelBrief
from app.services.travel_tools import search_hotels


async def run_hotel(state: AgentState) -> dict:
    brief = TravelBrief.model_validate(state.brief) if state.brief else None
    if not brief or not brief.destination:
        return state_patch(state)
    nights = max((brief.duration_days or 1) - 1, 1)
    per_night = (brief.budget_usd or 2000) / max(nights, 1) * 0.35
    raw = await search_hotels(brief.destination, per_night)
    hotels = []
    for h in raw[:3]:
        ppn = h.get("price_per_night_usd", 100)
        hotels.append(
            HotelEstimate(
                name=h["name"],
                neighborhood=h.get("neighborhood", ""),
                price_per_night_usd=ppn,
                total_nights=nights,
                estimated_total_usd=round(ppn * nights, 2),
            )
        )
    return state_patch(
        state,
        hotels=[h.model_dump(mode="json") for h in hotels],
        agents_used=mark_agent_used(state, "hotel"),
    )
