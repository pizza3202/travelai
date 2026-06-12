"""Itinerary validation — day count, budget, duplicates, overload."""

from app.models.schemas import (
    ActivityPlan,
    BudgetSummary,
    DayPlan,
    TravelBrief,
    ValidationResult,
)


def validate_itinerary(
    brief: TravelBrief,
    itinerary: list[DayPlan],
    budget_summary: BudgetSummary | None,
    activities: list[ActivityPlan],
) -> ValidationResult:
    expected_days = brief.duration_days or 0
    valid_day_count = len(itinerary) == expected_days if expected_days else True

    within_budget = True
    if budget_summary:
        within_budget = budget_summary.within_budget

    titles: list[str] = []
    for day in itinerary:
        for item in day.items:
            titles.append(item.title.lower().strip())
    for act in activities:
        titles.append(act.name.lower().strip())
    no_duplicates = len(titles) == len(set(titles))

    days_not_overloaded = all(len(d.items) <= 8 for d in itinerary)

    issues: list[str] = []
    if not valid_day_count:
        issues.append(
            f"itinerary has {len(itinerary)} days, expected {expected_days}"
        )
    if not within_budget:
        issues.append("total cost exceeds budget")
    if not no_duplicates:
        issues.append("duplicate activities detected")
    if not days_not_overloaded:
        issues.append("one or more days are overloaded")

    valid = valid_day_count and within_budget and no_duplicates and days_not_overloaded
    return ValidationResult(
        valid=valid,
        valid_day_count=valid_day_count,
        within_budget=within_budget,
        no_duplicate_activities=no_duplicates,
        days_not_overloaded=days_not_overloaded,
        issues=issues,
        repair_suggested=not valid and (not within_budget or not no_duplicates),
    )
