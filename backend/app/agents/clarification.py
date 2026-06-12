from app.agents.base import mark_agent_used, state_patch
from app.models.schemas import AgentState, TravelBrief


async def run_clarification(state: AgentState) -> dict:
    brief = TravelBrief.model_validate(state.brief) if state.brief else None
    msg = state.clarification_message or "Please provide destination, trip length, and budget."
    if brief and brief.clarification_questions:
        msg = "\n".join(brief.clarification_questions)
    return state_patch(
        state,
        needs_clarification=True,
        clarification_message=msg,
        agents_used=mark_agent_used(state, "clarification"),
    )
