"""Test 6: validator detects duplicate activities."""

from app.models.schemas import ActivityPlan, DayPlan, ItineraryItem, TravelBrief
from app.services.validator_service import validate_itinerary


def test_detects_duplicate_activities():
    brief = TravelBrief(destination="Japan", duration_days=2, budget_usd=2500)
    itinerary = [
        DayPlan(
            day=1,
            theme="D1",
            items=[ItineraryItem(title="Senso-ji Temple", category="culture")],
        ),
        DayPlan(
            day=2,
            theme="D2",
            items=[ItineraryItem(title="Senso-ji Temple", category="culture")],
        ),
    ]
    activities = [ActivityPlan(name="Senso-ji Temple", category="culture", estimated_cost_usd=0)]
    result = validate_itinerary(brief, itinerary, None, activities)
    assert result.no_duplicate_activities is False
