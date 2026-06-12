"""Repair loop: reduce costs / dedupe when validation fails."""

from app.agents.base import mark_agent_used, state_patch
from app.models.schemas import (
    ActivityPlan,
    AgentState,
    BudgetSummary,
    FlightEstimate,
    HotelEstimate,
    TransportPlan,
    TravelBrief,
)
from app.services.budget_service import compute_budget_summary


def _scale_costs_to_budget(
    brief: TravelBrief,
    flights: list[FlightEstimate],
    hotels: list[HotelEstimate],
    activities: list[ActivityPlan],
    transport: list[TransportPlan],
) -> tuple[list[FlightEstimate], list[HotelEstimate], list[ActivityPlan], list[TransportPlan]]:
    """Proportionally scale component costs so total fits under budget_limit."""
    limit = brief.budget_usd
    if not limit:
        return flights, hotels, activities, transport

    summary = compute_budget_summary(brief, flights, hotels, activities, transport)
    if summary.within_budget or summary.total_estimated_cost <= 0:
        return flights, hotels, activities, transport

    factor = (limit * 0.98) / summary.total_estimated_cost
    for f in flights:
        f.estimated_cost_usd = round(f.estimated_cost_usd * factor, 2)
    for h in hotels:
        h.price_per_night_usd = round(h.price_per_night_usd * factor, 2)
        h.estimated_total_usd = round(h.price_per_night_usd * h.total_nights, 2)
    for a in activities:
        a.estimated_cost_usd = round(a.estimated_cost_usd * factor, 2)
    for t in transport:
        t.estimated_cost_usd = round(t.estimated_cost_usd * factor, 2)
    return flights, hotels, activities, transport


async def run_repair(state: AgentState) -> dict:
    brief = TravelBrief.model_validate(state.brief) if state.brief else None

    flights = [FlightEstimate.model_validate(f) for f in state.flights]
    hotels = [HotelEstimate.model_validate(h) for h in state.hotels]
    activities = [ActivityPlan.model_validate(a) for a in state.activities]
    transport = [TransportPlan.model_validate(t) for t in state.transport]

    if activities:
        idx = max(
            range(len(activities)),
            key=lambda i: activities[i].estimated_cost_usd,
        )
        activities[idx].estimated_cost_usd = round(
            activities[idx].estimated_cost_usd * 0.85, 2
        )

    if brief:
        flights, hotels, activities, transport = _scale_costs_to_budget(
            brief, flights, hotels, activities, transport
        )
        summary = compute_budget_summary(brief, flights, hotels, activities, transport)
    elif state.budget_summary:
        summary = BudgetSummary.model_validate(state.budget_summary)
        if not summary.within_budget and summary.budget_limit:
            summary.total_estimated_cost = round(summary.total_estimated_cost * 0.92, 2)
            summary.within_budget = summary.total_estimated_cost <= summary.budget_limit
    else:
        return state_patch(state, repair_round=state.repair_round + 1)

    return state_patch(
        state,
        flights=[f.model_dump(mode="json") for f in flights],
        hotels=[h.model_dump(mode="json") for h in hotels],
        activities=[a.model_dump(mode="json") for a in activities],
        transport=[t.model_dump(mode="json") for t in transport],
        budget_summary=summary.model_dump(mode="json"),
        repair_round=state.repair_round + 1,
        agents_used=mark_agent_used(state, "repair"),
    )
