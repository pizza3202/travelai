"""Synthesizer helpers — LLM itinerary narrative with deterministic fallback."""

from __future__ import annotations

import json
import logging

from app.models.schemas import (
    ActivityPlan,
    DayPlan,
    ItineraryItem,
    TravelBrief,
)
from app.services.llm_client import complete_json, llm_available, max_tokens_for_agent, model_for_agent
from app.services.llm_schemas import SynthesizerLLMOutput

logger = logging.getLogger(__name__)


def _json_ready_list(items: list) -> list[dict]:
    """Normalize Pydantic models or dicts for json.dumps."""
    out: list[dict] = []
    for item in items:
        if hasattr(item, "model_dump"):
            out.append(item.model_dump(mode="json"))
        elif isinstance(item, dict):
            out.append(item)
        else:
            out.append(dict(item))
    return out


SYNTHESIZER_SYSTEM = """You are TravelAI synthesizer. Build a day-by-day itinerary from the provided data.
- Use ONLY activities and facts given; do not invent bookings or confirm purchases.
- Mark costs as estimates. Match the requested number of days exactly.
- Themes should be specific and varied. Spread activities across days when possible.
"""


async def build_itinerary_with_llm(
    brief: TravelBrief,
    activities: list[ActivityPlan],
    rag_context: list[str],
    web_snippets: list[str],
    flights: list[dict],
    hotels: list[dict],
    transport: list[dict],
    *,
    session_id: str | None = None,
    conversation_id: str | None = None,
) -> list[DayPlan] | None:
    if not llm_available():
        return None

    days = brief.duration_days or 5
    payload = {
        "destination": brief.destination,
        "duration_days": days,
        "budget_usd": brief.budget_usd,
        "interests": brief.interests,
        "activities": [a.model_dump(mode="json") for a in activities],
        "flights": _json_ready_list(flights),
        "hotels": _json_ready_list(hotels),
        "transport": _json_ready_list(transport),
        "rag_context": rag_context[:5],
        "web_search": web_snippets[:3],
    }
    user = f"Create a {days}-day itinerary JSON.\n\nData:\n{json.dumps(payload, indent=2)}"

    try:
        out = await complete_json(
            agent_name="synthesizer",
            model=model_for_agent("synthesizer"),
            system=SYNTHESIZER_SYSTEM,
            user=user,
            max_tokens=max_tokens_for_agent("synthesizer"),
            output_model=SynthesizerLLMOutput,
            session_id=session_id,
            conversation_id=conversation_id,
        )
    except Exception as exc:
        logger.warning("Synthesizer LLM failed: %s", exc)
        return None

    if not isinstance(out, SynthesizerLLMOutput) or not out.days:
        return None

    itinerary: list[DayPlan] = []
    for day in out.days[:days]:
        items = [
            ItineraryItem(
                title=item.title,
                description=item.description,
                category=item.category,
                estimated_cost_usd=item.estimated_cost_usd,
            )
            for item in day.items
        ]
        itinerary.append(DayPlan(day=day.day, theme=day.theme, items=items))

    while len(itinerary) < days:
        n = len(itinerary) + 1
        itinerary.append(DayPlan(day=n, theme=f"Day {n}", items=[]))

    return itinerary[:days]


def build_itinerary_deterministic(
    brief: TravelBrief,
    activities: list[ActivityPlan],
    rag_extra: list[str],
) -> list[DayPlan]:
    days = brief.duration_days or 5
    themes = [
        "Arrival and light exploration",
        "Culture and neighborhoods",
        "Nature and outdoors",
        "Food-focused day",
        "Highlights and departure prep",
    ]
    per_day = max(len(activities) // days, 1) if activities else 0
    itinerary: list[DayPlan] = []

    for d in range(1, days + 1):
        start = (d - 1) * per_day
        chunk = activities[start : start + per_day] if activities else []
        items = [
            ItineraryItem(
                title=a.name,
                description=f"{a.category} activity (estimate)",
                estimated_cost_usd=a.estimated_cost_usd,
                category=a.category,
            )
            for a in chunk
        ]
        if d == 1 and rag_extra:
            items.insert(
                0,
                ItineraryItem(
                    title="Orientation",
                    description=rag_extra[0][:200],
                    category="culture",
                ),
            )
        itinerary.append(
            DayPlan(day=d, theme=themes[(d - 1) % len(themes)], items=items)
        )
    return itinerary
