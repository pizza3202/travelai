"""Test 5: validator checks day count."""

from app.models.schemas import DayPlan, TravelBrief
from app.services.validator_service import validate_itinerary


def test_validator_day_count_mismatch():
    brief = TravelBrief(destination="Japan", duration_days=5, budget_usd=2500)
    itinerary = [DayPlan(day=i, theme=f"Day {i}", items=[]) for i in range(1, 4)]
    result = validate_itinerary(brief, itinerary, None, [])
    assert result.valid_day_count is False
    assert result.valid is False


def test_validator_day_count_match():
    brief = TravelBrief(destination="Japan", duration_days=3, budget_usd=2500)
    itinerary = [DayPlan(day=i, theme=f"Day {i}", items=[]) for i in range(1, 4)]
    result = validate_itinerary(brief, itinerary, None, [])
    assert result.valid_day_count is True
