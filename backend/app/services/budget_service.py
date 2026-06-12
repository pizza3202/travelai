"""Budget aggregation and violation detection."""

from app.models.schemas import (
    ActivityPlan,
    BudgetLineItem,
    BudgetSummary,
    FlightEstimate,
    HotelEstimate,
    TransportPlan,
    TravelBrief,
)


def compute_budget_summary(
    brief: TravelBrief,
    flights: list[FlightEstimate],
    hotels: list[HotelEstimate],
    activities: list[ActivityPlan],
    transport: list[TransportPlan],
) -> BudgetSummary:
    limit = brief.budget_usd or 0.0
    line_items: list[BudgetLineItem] = []

    flight_total = sum(f.estimated_cost_usd for f in flights)
    if flight_total:
        line_items.append(
            BudgetLineItem(category="flights", estimated_cost_usd=flight_total)
        )

    hotel_total = sum(h.estimated_total_usd for h in hotels)
    if hotel_total:
        line_items.append(
            BudgetLineItem(category="hotels", estimated_cost_usd=hotel_total)
        )

    activity_total = sum(a.estimated_cost_usd for a in activities)
    if activity_total:
        line_items.append(
            BudgetLineItem(category="activities", estimated_cost_usd=activity_total)
        )

    transport_total = sum(t.estimated_cost_usd for t in transport)
    if transport_total:
        line_items.append(
            BudgetLineItem(category="transport", estimated_cost_usd=transport_total)
        )

    # Daily misc estimate
    days = brief.duration_days or 1
    misc = days * 40.0
    line_items.append(BudgetLineItem(category="daily_misc", estimated_cost_usd=misc))

    total = sum(li.estimated_cost_usd for li in line_items)
    return BudgetSummary(
        total_estimated_cost=round(total, 2),
        budget_limit=limit,
        within_budget=total <= limit if limit else True,
        line_items=line_items,
    )


def is_over_budget(summary: BudgetSummary) -> bool:
    return not summary.within_budget
