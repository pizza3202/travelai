"""
Optimized LangGraph workflow.

Flow:
  planner -> clarification | specialists -> budget -> validator
  -> repair (if needed) -> synthesizer
"""

from __future__ import annotations

import time
from typing import Any, Literal
from uuid import UUID

from app.agents import (
    run_activity,
    run_budget,
    run_clarification,
    run_flight,
    run_hotel,
    run_planner,
    run_repair,
    run_synthesizer,
    run_transport,
    run_validator,
)
from app.config import get_settings
from app.models.schemas import AgentState, GraphMode, TravelBrief, ValidationResult
from app.observability.agent_run_logger import log_agent_run

try:
    from langgraph.graph import END, START, StateGraph

    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False


async def _log_step(state: AgentState, agent_name: str, status: str, latency_ms: int) -> None:
    try:
        await log_agent_run(
            session_id=UUID(state.session_id),
            conversation_id=UUID(state.conversation_id),
            agent_name=agent_name,
            status=status,
            latency_ms=latency_ms,
            graph_mode=state.mode.value if state.mode else "optimized",
        )
    except (ValueError, TypeError):
        pass


async def _run_agent(agent_name: str, runner, state: AgentState) -> dict:
    start = time.perf_counter()
    patch = await runner(state)
    latency_ms = int((time.perf_counter() - start) * 1000)
    await _log_step(state, agent_name, "completed", latency_ms)
    return patch


def _route_after_planner(state: dict) -> Literal["clarification", "specialists"]:
    brief_data = state.get("brief")
    if not brief_data:
        return "clarification"
    brief = TravelBrief.model_validate(brief_data)
    if brief.needs_clarification or not brief.has_required_fields:
        return "clarification"
    return "specialists"


def _route_after_validator(state: dict) -> Literal["repair", "synthesizer"]:
    validation = state.get("validation")
    repair_round = state.get("repair_round", 0)
    max_rounds = get_settings().max_repair_rounds
    if not validation:
        return "synthesizer"
    v = ValidationResult.model_validate(validation)
    if v.valid or repair_round >= max_rounds:
        return "synthesizer"
    if v.repair_suggested:
        return "repair"
    return "synthesizer"


async def _run_specialists_parallel(state: AgentState) -> dict:
    """Fan-out to selected specialist agents (M2: sequential; future: LangGraph Send)."""
    agents = set(state.agents_to_run or [])
    s = state
    if "flight" in agents:
        patch = await _run_agent("flight", run_flight, s)
        s = AgentState.from_graph_dict({**s.to_graph_dict(), **patch})
    if "hotel" in agents:
        patch = await _run_agent("hotel", run_hotel, s)
        s = AgentState.from_graph_dict({**s.to_graph_dict(), **patch})
    if "activity" in agents:
        patch = await _run_agent("activity", run_activity, s)
        s = AgentState.from_graph_dict({**s.to_graph_dict(), **patch})
    if "transport" in agents:
        patch = await _run_agent("transport", run_transport, s)
        s = AgentState.from_graph_dict({**s.to_graph_dict(), **patch})
    return s.to_graph_dict()


async def run_multi_agent_graph(
    initial: AgentState,
    *,
    mode: GraphMode,
    enable_validator: bool,
) -> AgentState:
    """Shared pipeline for R1 / R2 / R3 (optimized) ablation rounds."""
    data = {**initial.to_graph_dict(), "mode": mode.value}
    state = AgentState.from_graph_dict(data)

    patch = await _run_agent("planner", run_planner, state)
    state = AgentState.from_graph_dict({**state.to_graph_dict(), **patch})

    if _route_after_planner(state.to_graph_dict()) == "clarification":
        patch = await _run_agent("clarification", run_clarification, state)
        return AgentState.from_graph_dict({**state.to_graph_dict(), **patch})

    patch = await _run_specialists_parallel(state)
    state = AgentState.from_graph_dict({**state.to_graph_dict(), **patch})

    patch = await _run_agent("budget", run_budget, state)
    state = AgentState.from_graph_dict({**state.to_graph_dict(), **patch})

    if enable_validator:
        brief = TravelBrief.model_validate(state.brief)
        if brief and brief.duration_days and not state.itinerary:
            from app.models.schemas import DayPlan

            stub_days = [
                DayPlan(day=d, theme=f"Day {d}", items=[])
                for d in range(1, brief.duration_days + 1)
            ]
            state = AgentState.from_graph_dict(
                {
                    **state.to_graph_dict(),
                    "itinerary": [d.model_dump(mode="json") for d in stub_days],
                }
            )

        patch = await _run_agent("validator", run_validator, state)
        state = AgentState.from_graph_dict({**state.to_graph_dict(), **patch})

        while _route_after_validator(state.to_graph_dict()) == "repair":
            patch = await _run_agent("repair", run_repair, state)
            state = AgentState.from_graph_dict({**state.to_graph_dict(), **patch})
            patch = await _run_agent("validator", run_validator, state)
            state = AgentState.from_graph_dict({**state.to_graph_dict(), **patch})

    patch = await _run_agent("synthesizer", run_synthesizer, state)
    return AgentState.from_graph_dict({**state.to_graph_dict(), **patch})


async def run_r1_graph(initial: AgentState) -> AgentState:
    """R1: multi-agent specialists + budget; no RAG, validator, or repair."""
    return await run_multi_agent_graph(
        initial, mode=GraphMode.R1, enable_validator=False
    )


async def run_r2_graph(initial: AgentState) -> AgentState:
    """R2: R1 + RAG; no validator or repair."""
    return await run_multi_agent_graph(
        initial, mode=GraphMode.R2, enable_validator=False
    )


async def run_optimized_graph(initial: AgentState) -> AgentState:
    """R3: full optimized pipeline (RAG + validator + repair)."""
    return await run_multi_agent_graph(
        initial, mode=GraphMode.OPTIMIZED, enable_validator=True
    )


def build_optimized_graph() -> Any:
    """Build LangGraph StateGraph when langgraph is available (M2 compiles)."""
    if not LANGGRAPH_AVAILABLE:
        return None

    graph = StateGraph(dict)

    async def planner_node(s: dict) -> dict:
        st = AgentState.from_graph_dict(s)
        return {**s, **(await run_planner(st))}

    async def clarification_node(s: dict) -> dict:
        st = AgentState.from_graph_dict(s)
        return {**s, **(await run_clarification(st))}

    async def specialists_node(s: dict) -> dict:
        st = AgentState.from_graph_dict(s)
        return {**s, **(await _run_specialists_parallel(st))}

    async def budget_node(s: dict) -> dict:
        st = AgentState.from_graph_dict(s)
        return {**s, **(await run_budget(st))}

    async def validator_node(s: dict) -> dict:
        st = AgentState.from_graph_dict(s)
        return {**s, **(await run_validator(st))}

    async def repair_node(s: dict) -> dict:
        st = AgentState.from_graph_dict(s)
        return {**s, **(await run_repair(st))}

    async def synthesizer_node(s: dict) -> dict:
        st = AgentState.from_graph_dict(s)
        return {**s, **(await run_synthesizer(st))}

    graph.add_node("planner", planner_node)
    graph.add_node("clarification", clarification_node)
    graph.add_node("specialists", specialists_node)
    graph.add_node("budget", budget_node)
    graph.add_node("validator", validator_node)
    graph.add_node("repair", repair_node)
    graph.add_node("synthesizer", synthesizer_node)

    graph.add_edge(START, "planner")
    graph.add_conditional_edges(
        "planner",
        _route_after_planner,
        {"clarification": "clarification", "specialists": "specialists"},
    )
    graph.add_edge("clarification", END)
    graph.add_edge("specialists", "budget")
    graph.add_edge("budget", "validator")
    graph.add_conditional_edges(
        "validator",
        _route_after_validator,
        {"repair": "repair", "synthesizer": "synthesizer"},
    )
    graph.add_edge("repair", "validator")
    graph.add_edge("synthesizer", END)

    return graph.compile()
