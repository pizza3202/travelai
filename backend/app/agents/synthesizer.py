from app.agents.base import mark_agent_used, state_patch
from app.models.schemas import (
    ActivityPlan,
    AgentState,
    BudgetSummary,
    GraphMode,
    TravelBrief,
    TravelPlanResponse,
    ValidationResult,
)
from app.rag.retriever import retrieve_destination_context
from app.services.synthesizer_service import (
    build_itinerary_deterministic,
    build_itinerary_with_llm,
)


async def run_synthesizer(state: AgentState) -> dict:
    brief = TravelBrief.model_validate(state.brief) if state.brief else None
    if not brief:
        return state_patch(state)

    activities = [ActivityPlan.model_validate(a) for a in state.activities]
    rag_extra = list(state.rag_context) + list(state.web_search_snippets)
    if not rag_extra and state.mode != GraphMode.R1:
        rag_extra = await retrieve_destination_context(brief.destination, top_k=3)

    itinerary = await build_itinerary_with_llm(
        brief,
        activities,
        list(state.rag_context),
        list(state.web_search_snippets),
        state.flights,
        state.hotels,
        state.transport,
        session_id=state.session_id,
        conversation_id=state.conversation_id,
    )
    if not itinerary:
        itinerary = build_itinerary_deterministic(brief, activities, rag_extra)

    validation = (
        ValidationResult.model_validate(state.validation)
        if state.validation
        else None
    )
    budget = (
        BudgetSummary.model_validate(state.budget_summary)
        if state.budget_summary
        else None
    )

    from app.models.schemas import FlightEstimate, HotelEstimate, TransportPlan

    plan = TravelPlanResponse(
        itinerary=itinerary,
        budget_summary=budget,
        flights=[FlightEstimate.model_validate(f) for f in state.flights],
        hotels=[HotelEstimate.model_validate(h) for h in state.hotels],
        activities=activities,
        transport=[TransportPlan.model_validate(t) for t in state.transport],
        validation=validation,
        agents_used=mark_agent_used(state, "synthesizer"),
        mode=GraphMode(state.mode) if state.mode else GraphMode.OPTIMIZED,
        conversation_id=state.conversation_id,
        session_id=state.session_id,
    )

    return state_patch(
        state,
        itinerary=[d.model_dump(mode="json") for d in itinerary],
        final_response=plan.model_dump(mode="json"),
        agents_used=plan.agents_used,
    )
