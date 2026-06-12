from app.agents.base import mark_agent_used, state_patch
from app.models.schemas import AgentState
from app.services.planner_service import extract_travel_brief_async


async def run_planner(state: AgentState) -> dict:
    brief = await extract_travel_brief_async(
        state.message,
        state.departure_city,
        session_id=state.session_id,
        conversation_id=state.conversation_id,
    )
    agents_to_run = [a.value for a in brief.agents_to_run]
    patch = {
        "brief": brief.model_dump(mode="json"),
        "agents_to_run": agents_to_run,
        "needs_clarification": brief.needs_clarification,
        "clarification_message": (
            "\n".join(brief.clarification_questions) if brief.needs_clarification else None
        ),
        "agents_used": mark_agent_used(state, "planner"),
    }
    return state_patch(state, **patch)
