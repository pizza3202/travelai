"""Test 8: repair loop reduces cost."""

import pytest

from app.agents.repair import run_repair
from app.models.schemas import ActivityPlan, AgentState, BudgetSummary


@pytest.mark.asyncio
async def test_repair_reduces_cost():
    state = AgentState(
        session_id="s",
        conversation_id="c",
        message="test",
        activities=[
            ActivityPlan(name="A", category="food", estimated_cost_usd=200).model_dump(
                mode="json"
            ),
            ActivityPlan(name="B", category="culture", estimated_cost_usd=100).model_dump(
                mode="json"
            ),
        ],
        budget_summary=BudgetSummary(
            total_estimated_cost=3000,
            budget_limit=2500,
            within_budget=False,
        ).model_dump(mode="json"),
        repair_round=0,
    )
    activities_before = [ActivityPlan.model_validate(a) for a in state.activities]
    before = max(a.estimated_cost_usd for a in activities_before)
    patch = await run_repair(state)
    new_state = AgentState.from_graph_dict({**state.to_graph_dict(), **patch})
    activities = [
        ActivityPlan.model_validate(a) for a in new_state.activities
    ]
    after_max = max(a.estimated_cost_usd for a in activities)
    assert after_max < before or (
        new_state.budget_summary
        and BudgetSummary.model_validate(new_state.budget_summary).total_estimated_cost
        < 3000
    )
