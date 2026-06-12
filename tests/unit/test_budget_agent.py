"""Test 4: budget agent detects over-budget."""

from app.models.schemas import BudgetLineItem, BudgetSummary, TravelBrief
from app.services.budget_service import is_over_budget


def test_detects_over_budget():
    summary = BudgetSummary(
        total_estimated_cost=3000,
        budget_limit=2500,
        within_budget=False,
        line_items=[BudgetLineItem(category="total", estimated_cost_usd=3000)],
    )
    assert is_over_budget(summary) is True


def test_within_budget():
    summary = BudgetSummary(
        total_estimated_cost=2000,
        budget_limit=2500,
        within_budget=True,
        line_items=[],
    )
    assert is_over_budget(summary) is False
