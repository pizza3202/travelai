"""Test 2: router routes to required agents."""

from app.models.schemas import SpecialistAgent
from app.services.planner_service import extract_travel_brief


def test_routes_to_all_specialists_when_complete():
    brief = extract_travel_brief("Plan a 5-day Japan trip under $2500.")
    assert not brief.needs_clarification
    assert SpecialistAgent.FLIGHT in brief.agents_to_run
    assert SpecialistAgent.HOTEL in brief.agents_to_run
    assert SpecialistAgent.ACTIVITY in brief.agents_to_run
    assert SpecialistAgent.TRANSPORT in brief.agents_to_run
