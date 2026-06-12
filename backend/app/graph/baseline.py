"""
Baseline graph: single-agent planner/synthesizer — no RAG, no validator, no repair.
Used for eval comparison (--mode baseline).
"""

from app.agents.base import mark_agent_used, state_patch
from app.models.schemas import (
    ActivityPlan,
    AgentState,
    BudgetSummary,
    BudgetLineItem,
    DayPlan,
    GraphMode,
    ItineraryItem,
    TravelPlanResponse,
)
from app.services.planner_service import extract_travel_brief_async
from app.services.travel_tools import search_activities, search_flights, search_hotels


async def run_baseline_graph(initial: AgentState) -> AgentState:
    """Single pass: extract brief, mock tool calls, build itinerary — no validation/RAG."""
    state = AgentState.from_graph_dict(
        {**initial.to_graph_dict(), "mode": GraphMode.BASELINE.value}
    )
    brief = await extract_travel_brief_async(
        state.message,
        state.departure_city,
        session_id=state.session_id,
        conversation_id=state.conversation_id,
    )

    if brief.needs_clarification:
        return AgentState.from_graph_dict(
            {
                **state.to_graph_dict(),
                "brief": brief.model_dump(mode="json"),
                "needs_clarification": True,
                "clarification_message": "\n".join(brief.clarification_questions),
                "agents_used": ["baseline_planner"],
            }
        )

    dep = brief.departure_city or "San Francisco"
    flights_raw = await search_flights(dep, brief.destination or "", brief.budget_usd or 3000)
    hotels_raw = await search_hotels(
        brief.destination or "", (brief.budget_usd or 2000) / 10
    )
    activities_raw = await search_activities(
        brief.destination or "",
        brief.interests,
        (brief.budget_usd or 2000) * 0.3,
    )

    days = brief.duration_days or 5
    activities = [ActivityPlan.model_validate(a) for a in activities_raw[: days + 2]]
    itinerary = [
        DayPlan(
            day=d,
            theme=f"Day {d}",
            items=[
                ItineraryItem(
                    title=activities[min(d - 1, len(activities) - 1)].name
                    if activities
                    else "Free exploration",
                    category="general",
                )
            ],
        )
        for d in range(1, days + 1)
    ]

    total = sum(a.estimated_cost_usd for a in activities)
    total += sum(f.get("estimated_cost_usd", 0) for f in flights_raw)
    total += sum(
        h.get("price_per_night_usd", 0) * max(days - 1, 1) for h in hotels_raw[:1]
    )
    budget_summary = BudgetSummary(
        total_estimated_cost=round(total, 2),
        budget_limit=brief.budget_usd or 0,
        within_budget=total <= (brief.budget_usd or total),
        line_items=[BudgetLineItem(category="combined", estimated_cost_usd=total)],
    )

    from app.models.schemas import FlightEstimate, HotelEstimate

    plan = TravelPlanResponse(
        itinerary=itinerary,
        budget_summary=budget_summary,
        flights=[FlightEstimate.model_validate(f) for f in flights_raw[:2]],
        hotels=[],
        activities=activities,
        transport=[],
        validation=None,
        agents_used=["baseline_planner"],
        mode=GraphMode.BASELINE,
    )

    return AgentState.from_graph_dict(
        {
            **state.to_graph_dict(),
            "brief": brief.model_dump(mode="json"),
            "itinerary": [d.model_dump(mode="json") for d in itinerary],
            "budget_summary": budget_summary.model_dump(mode="json"),
            "final_response": plan.model_dump(mode="json"),
            "agents_used": mark_agent_used(state, "baseline_planner"),
        }
    )
