from app.agents.base import mark_agent_used, state_patch
from app.models.schemas import ActivityPlan, AgentState, GraphMode, TravelBrief
from app.rag.retriever import retrieve_destination_context
from app.services.tavily_search import (
    search_travel_web,
    should_use_web_search,
    snippets_as_context,
)
from app.services.travel_tools import search_activities


async def run_activity(state: AgentState) -> dict:
    brief = TravelBrief.model_validate(state.brief) if state.brief else None
    if not brief or not brief.destination:
        return state_patch(state)

    # R1 ablation: specialists only — no RAG / web (isolated in eval)
    rag_chunks: list[str] = []
    if state.mode != GraphMode.R1:
        rag_chunks = await retrieve_destination_context(
            brief.destination, interests=brief.interests
        )

    # Tavily — optional web search (skipped for R1 ablation)
    web_snippets: list[str] = []
    if state.mode != GraphMode.R1 and should_use_web_search(
        state.message, len(rag_chunks)
    ):
        web_results = await search_travel_web(
            brief.destination,
            brief.interests,
            state.message,
        )
        web_snippets = snippets_as_context(web_results)

    # 3) Mock structured activities — fallback for costs / day hints
    activity_budget = (brief.budget_usd or 2000) * 0.25
    raw = await search_activities(
        brief.destination, brief.interests, activity_budget
    )

    activity_source = "mock"
    if rag_chunks and web_snippets:
        activity_source = "rag+web"
    elif rag_chunks:
        activity_source = "rag"
    elif web_snippets:
        activity_source = "web"

    activities = [
        ActivityPlan(
            name=a["name"],
            category=a.get("category", "general"),
            estimated_cost_usd=a.get("estimated_cost_usd", 0),
            day_hint=a.get("day_hint"),
            source=activity_source,
        )
        for a in raw
    ]

    return state_patch(
        state,
        activities=[a.model_dump(mode="json") for a in activities],
        rag_context=rag_chunks,
        web_search_snippets=web_snippets,
        agents_used=mark_agent_used(state, "activity"),
    )
