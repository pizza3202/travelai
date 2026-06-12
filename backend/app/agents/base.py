"""Base agent utilities."""

from typing import Any

from app.models.schemas import AgentState


def mark_agent_used(state: AgentState, agent_name: str) -> list[str]:
    used = list(state.agents_used)
    if agent_name not in used:
        used.append(agent_name)
    return used


def state_patch(state: AgentState, **kwargs: Any) -> dict[str, Any]:
    data = state.model_dump(mode="json")
    data.update(kwargs)
    return data
