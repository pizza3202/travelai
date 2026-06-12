"""Test 1: router extracts destination/budget/duration."""

from app.services.planner_service import extract_travel_brief


def test_extracts_destination_budget_duration():
    msg = "Plan a 5-day Japan trip under $2500. I like food, nature, and culture."
    brief = extract_travel_brief(msg, departure_city="San Francisco")
    assert brief.destination is not None
    assert "japan" in brief.destination.lower() or brief.destination == "Japan"
    assert brief.duration_days == 5
    assert brief.budget_usd == 2500.0
    assert "food" in brief.interests
