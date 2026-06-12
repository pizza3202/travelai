"""POST /chat — Server-Sent Events streaming."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from uuid import UUID

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.graph.baseline import run_baseline_graph
from app.graph.workflow import run_optimized_graph
from app.models.schemas import (
    AgentState,
    CardType,
    ChatRequest,
    GraphMode,
    TravelPlanResponse,
    make_card,
    make_delta,
    make_error,
    make_final,
    make_trace,
)
from app.observability.langsmith_tracer import trace_run

router = APIRouter()


async def _stream_chat(request: ChatRequest, mode: GraphMode) -> AsyncGenerator[dict, None]:
    initial = AgentState(
        session_id=str(request.session_id),
        conversation_id=str(request.conversation_id),
        message=request.message,
        departure_city=request.departure_city,
        mode=mode,
    )

    yield make_trace("graph", "started", detail=mode.value).to_sse_line()

    try:
        with trace_run("travelai_chat", {"mode": mode.value}):
            if mode == GraphMode.BASELINE:
                result = await run_baseline_graph(initial)
            else:
                result = await run_optimized_graph(initial)

        if result.needs_clarification:
            msg = result.clarification_message or "More information needed."
            yield make_trace("clarification", "completed").to_sse_line()
            yield make_delta(msg).to_sse_line()
            yield make_final(
                TravelPlanResponse(
                    agents_used=result.agents_used,
                    mode=mode,
                    conversation_id=request.conversation_id,
                    session_id=request.session_id,
                )
            ).to_sse_line()
            return

        for agent in result.agents_used:
            yield make_trace(agent, "completed").to_sse_line()

        if result.budget_summary:
            budget_payload = (
                result.budget_summary
                if isinstance(result.budget_summary, dict)
                else result.budget_summary.model_dump(mode="json")
            )
            yield make_card(CardType.BUDGET, budget_payload).to_sse_line()

        plan_data = result.final_response
        if plan_data:
            plan = (
                TravelPlanResponse.model_validate(plan_data)
                if isinstance(plan_data, dict)
                else plan_data
            )
            yield make_delta("Your travel plan is ready.\n").to_sse_line()
            yield make_final(plan).to_sse_line()
        else:
            yield make_error("NO_PLAN", "Graph completed without final response").to_sse_line()

        yield make_trace("graph", "completed").to_sse_line()

    except Exception as e:
        yield make_error("INTERNAL_ERROR", str(e), recoverable=False).to_sse_line()
        yield make_trace("graph", "failed", detail=str(e)).to_sse_line()


def _parse_sse_line(line: str) -> dict:
    """Convert SSE data line to EventSourceResponse event."""
    if line.startswith("data: "):
        payload = json.loads(line[6:].strip())
        return {"event": payload.get("type", "message"), "data": json.dumps(payload)}
    return {"data": line}


@router.post("/chat")
async def chat_endpoint(request: ChatRequest) -> EventSourceResponse:
    async def event_generator() -> AsyncGenerator[dict, None]:
        async for line in _stream_chat(request, GraphMode.OPTIMIZED):
            parsed = _parse_sse_line(line) if line.startswith("data:") else {"data": line}
            yield parsed

    return EventSourceResponse(event_generator())


@router.post("/chat/baseline")
async def chat_baseline_endpoint(request: ChatRequest) -> EventSourceResponse:
    async def event_generator() -> AsyncGenerator[dict, None]:
        async for line in _stream_chat(request, GraphMode.BASELINE):
            parsed = _parse_sse_line(line) if line.startswith("data:") else {"data": line}
            yield parsed

    return EventSourceResponse(event_generator())
