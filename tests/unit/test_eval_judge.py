"""Eval judge and metrics — no API calls."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from eval.judge import load_golden, rule_based_judge, cohens_kappa, compute_kappa
from eval.metrics import compute_case_metrics, budget_satisfaction


def test_load_golden_at_least_25():
    cases = load_golden(ROOT / "eval" / "golden.jsonl")
    assert len(cases) >= 25


def test_rule_judge_tokyo_pass():
    case = {
        "id": "t",
        "expected_facts": ["itinerary has 5 days", "within budget"],
        "forbidden_facts": ["total cost exceeds budget"],
        "budget_limit": 2500,
    }
    output = {
        "itinerary": [{"day": i, "items": []} for i in range(1, 6)],
        "budget_summary": {
            "total_estimated_cost": 2000,
            "budget_limit": 2500,
            "within_budget": True,
        },
    }
    v = rule_based_judge(case, output)
    assert v.passed


def test_clarification_case():
    case = {
        "id": "c",
        "expected_facts": ["needs clarification"],
        "forbidden_facts": ["complete 5-day itinerary"],
    }
    output = {"needs_clarification": True, "message": "What is your budget?", "itinerary": []}
    v = rule_based_judge(case, output)
    assert v.passed


def test_cohens_kappa():
    assert cohens_kappa([True, True, False], [True, False, False]) >= 0


def test_llm_judge_rater_label_openrouter(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("USE_OLLAMA_FALLBACK", "false")
    from app.config import get_settings
    from app.services.llm_client import llm_judge_rater_label

    get_settings.cache_clear()
    assert llm_judge_rater_label() == "openrouter_judge"


def test_metrics_budget():
    case = {"budget_limit": 2500}
    out = {"budget_summary": {"total_estimated_cost": 2400, "within_budget": True}}
    assert budget_satisfaction(out, case) is True
