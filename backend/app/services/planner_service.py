"""Planner: extract TravelBrief — LLM when configured, else rules."""

from __future__ import annotations

import logging
import re

from app.config import get_settings
from app.models.schemas import SpecialistAgent, TravelBrief
from app.services.llm_client import complete_json, llm_available, max_tokens_for_agent, model_for_agent
from app.services.llm_schemas import PlannerLLMOutput

logger = logging.getLogger(__name__)

PLANNER_SYSTEM = """You are the TravelAI planner. Extract structured trip constraints from the user message.
- Do not book anything. Estimates only.
- If destination, trip length in days, or total budget USD is missing, set needs_clarification true and list clear questions.
- agents_to_run must be a subset of: flight, hotel, activity, transport (all four when trip is complete).
"""


async def extract_travel_brief_async(
    message: str,
    departure_city: str | None = None,
    *,
    session_id: str | None = None,
    conversation_id: str | None = None,
) -> TravelBrief:
    if llm_available():
        try:
            return await _extract_via_llm(
                message,
                departure_city,
                session_id=session_id,
                conversation_id=conversation_id,
            )
        except Exception as exc:
            logger.warning("Planner LLM failed, using rules: %s", exc)
    return extract_travel_brief(message, departure_city)


async def _extract_via_llm(
    message: str,
    departure_city: str | None,
    *,
    session_id: str | None,
    conversation_id: str | None,
) -> TravelBrief:
    user = f"User message:\n{message}\n"
    if departure_city:
        user += f"Departure city: {departure_city}\n"

    out = await complete_json(
        agent_name="planner",
        model=model_for_agent("planner"),
        system=PLANNER_SYSTEM,
        user=user,
        max_tokens=max_tokens_for_agent("planner"),
        output_model=PlannerLLMOutput,
        session_id=session_id,
        conversation_id=conversation_id,
    )
    assert isinstance(out, PlannerLLMOutput)
    return _planner_output_to_brief(out, message, departure_city)


def _planner_output_to_brief(
    out: PlannerLLMOutput, message: str, departure_city: str | None
) -> TravelBrief:
    agents: list[SpecialistAgent] = []
    for name in out.agents_to_run:
        try:
            agents.append(SpecialistAgent(name.lower().strip()))
        except ValueError:
            continue

    brief = TravelBrief(
        destination=out.destination,
        duration_days=out.duration_days,
        budget_usd=out.budget_usd,
        travelers=out.travelers,
        interests=out.interests,
        departure_city=departure_city,
        raw_message=message,
        needs_clarification=out.needs_clarification,
        clarification_questions=out.clarification_questions,
        agents_to_run=agents,
    )

    if not brief.has_required_fields:
        brief.needs_clarification = True
        brief.clarification_questions = (
            out.clarification_questions or _clarification_questions(brief)
        )
        brief.agents_to_run = []
    elif not brief.agents_to_run:
        brief.agents_to_run = [
            SpecialistAgent.FLIGHT,
            SpecialistAgent.HOTEL,
            SpecialistAgent.ACTIVITY,
            SpecialistAgent.TRANSPORT,
        ]
        brief.needs_clarification = False

    return brief


def extract_travel_brief(message: str, departure_city: str | None = None) -> TravelBrief:
    """Rule-based fallback when LLM is off or fails."""
    dest = _extract_destination(message)
    duration = _extract_duration(message)
    budget = _extract_budget(message)
    interests = _extract_interests(message)

    brief = TravelBrief(
        destination=dest,
        duration_days=duration,
        budget_usd=budget,
        interests=interests,
        departure_city=departure_city,
        raw_message=message,
    )

    if not brief.has_required_fields:
        brief.needs_clarification = True
        brief.clarification_questions = _clarification_questions(brief)
        brief.agents_to_run = []
    else:
        brief.needs_clarification = False
        brief.agents_to_run = [
            SpecialistAgent.FLIGHT,
            SpecialistAgent.HOTEL,
            SpecialistAgent.ACTIVITY,
            SpecialistAgent.TRANSPORT,
        ]

    return brief


def _clarification_questions(brief: TravelBrief) -> list[str]:
    qs: list[str] = []
    if not brief.destination:
        qs.append("Which city or country would you like to visit?")
    if brief.duration_days is None:
        qs.append("How many days is your trip?")
    if brief.budget_usd is None:
        qs.append("What is your total budget in USD?")
    return qs


def _extract_destination(msg: str) -> str | None:
    patterns = [
        r"(?:trip to|visit|travel to|going to)\s+([A-Za-z\s]+?)(?:\s+trip|\s+under|\s+for|\.|,|$)",
        r"(\d+-day)\s+([A-Za-z\s]+?)\s+trip",
        r"([A-Za-z\s]+?)\s+trip\s+under",
    ]
    for p in patterns:
        m = re.search(p, msg, re.I)
        if m:
            groups = [g for g in m.groups() if g and not re.match(r"\d+-day", g, re.I)]
            if groups:
                return groups[-1].strip().title()
    for name in ("Japan", "Tokyo", "Paris", "London", "New York", "San Francisco"):
        if name.lower() in msg.lower():
            return name
    return None


def _extract_duration(msg: str) -> int | None:
    m = re.search(r"(\d+)\s*-?\s*day", msg, re.I)
    return int(m.group(1)) if m else None


def _extract_budget(msg: str) -> float | None:
    patterns = [
        r"under\s*\$?\s*([\d,]+)",
        r"budget\s*(?:of)?\s*\$?\s*([\d,]+)",
        r"\$\s*([\d,]+)\s*(?:usd|total|budget)?",
    ]
    for p in patterns:
        m = re.search(p, msg, re.I)
        if m:
            val = float(m.group(1).replace(",", ""))
            if val >= 50:
                return val
    return None


def _extract_interests(msg: str) -> list[str]:
    found: list[str] = []
    for word in ("food", "nature", "culture", "art", "history", "shopping", "nightlife"):
        if word in msg.lower():
            found.append(word)
    return found
