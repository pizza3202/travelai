import json
import logging

from app.agents.base import mark_agent_used, state_patch
from app.models.schemas import (
    ActivityPlan,
    AgentState,
    BudgetSummary,
    DayPlan,
    TravelBrief,
    ValidationResult,
)
from app.services.llm_client import complete_json, llm_available, max_tokens_for_agent, model_for_agent
from app.services.llm_schemas import ValidatorLLMOutput
from app.services.validator_service import validate_itinerary

logger = logging.getLogger(__name__)

VALIDATOR_SYSTEM = """You review a travel plan for constraint violations.
Return JSON with issues (short bullets) and optional repair_hint (one sentence).
Do not suggest booking or purchasing anything."""


async def run_validator(state: AgentState) -> dict:
    brief = TravelBrief.model_validate(state.brief) if state.brief else None
    if not brief:
        return state_patch(state)
    budget = (
        BudgetSummary.model_validate(state.budget_summary)
        if state.budget_summary
        else None
    )
    itinerary = [DayPlan.model_validate(d) for d in state.itinerary]
    activities = [ActivityPlan.model_validate(a) for a in state.activities]
    validation = validate_itinerary(brief, itinerary, budget, activities)

    if not validation.valid and llm_available():
        validation = await _enrich_validation_with_llm(
            validation,
            brief,
            itinerary,
            budget,
            session_id=state.session_id,
            conversation_id=state.conversation_id,
        )

    return state_patch(
        state,
        validation=validation.model_dump(mode="json"),
        agents_used=mark_agent_used(state, "validator"),
    )


async def _enrich_validation_with_llm(
    validation: ValidationResult,
    brief: TravelBrief,
    itinerary: list[DayPlan],
    budget: BudgetSummary | None,
    *,
    session_id: str | None,
    conversation_id: str | None,
) -> ValidationResult:
    try:
        user = json.dumps(
            {
                "rule_issues": validation.issues,
                "destination": brief.destination,
                "duration_days": brief.duration_days,
                "budget_usd": brief.budget_usd,
                "day_count": len(itinerary),
                "within_budget": validation.within_budget,
            }
        )
        out = await complete_json(
            agent_name="validator",
            model=model_for_agent("validator"),
            system=VALIDATOR_SYSTEM,
            user=user,
            max_tokens=max_tokens_for_agent("validator"),
            output_model=ValidatorLLMOutput,
            session_id=session_id,
            conversation_id=conversation_id,
        )
        if isinstance(out, ValidatorLLMOutput):
            issues = list(validation.issues)
            for item in out.issues:
                if item not in issues:
                    issues.append(item)
            if out.repair_hint and out.repair_hint not in issues:
                issues.append(out.repair_hint)
            return validation.model_copy(
                update={"issues": issues, "repair_suggested": validation.repair_suggested}
            )
    except Exception as exc:
        logger.warning("Validator LLM enrich failed: %s", exc)
    return validation
