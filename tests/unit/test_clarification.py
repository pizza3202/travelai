"""Test 3: missing destination asks clarification."""

from app.graph.workflow import _route_after_planner
from app.services.planner_service import extract_travel_brief


def test_missing_budget_triggers_clarification():
    brief = extract_travel_brief("I want to visit Japan for a week.")
    assert brief.needs_clarification
    assert brief.budget_usd is None
    assert len(brief.clarification_questions) >= 1


def test_route_clarification_when_incomplete():
    brief = extract_travel_brief("I want to visit Japan for a week.")
    state = {"brief": brief.model_dump(mode="json")}
    assert _route_after_planner(state) == "clarification"
