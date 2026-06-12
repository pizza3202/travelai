"""
Dual-judge evaluation: rule-based + LLM (any configured provider) or mock fallback.

Cohen's kappa between rule_based_judge and llm_judge pass labels.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class JudgeVerdict:
    case_id: str
    passed: bool
    fact_results: dict[str, bool]
    forbidden_violations: list[str]
    score: float
    rater: str  # rules | {provider}_judge | mock_judge


def load_golden(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            case = json.loads(line)
            if case.get("id", "").startswith("placeholder"):
                continue
            cases.append(case)
    return cases


def _blob(output: dict[str, Any]) -> str:
    return json.dumps(output, default=str).lower()


def _check_expected_fact(fact: str, output: dict[str, Any], case: dict[str, Any]) -> bool:
    fl = fact.lower()
    itin = output.get("itinerary") or []
    bs = output.get("budget_summary") or {}

    if "needs clarification" in fl or "asks for" in fl or "clarification" in fl:
        return bool(
            output.get("needs_clarification")
            or output.get("message")
            and not itin
        )

    m_days = re.search(r"itinerary has (\d+) days?", fl)
    if m_days:
        return len(itin) == int(m_days.group(1))

    if "at most 3" in fl or "weekend" in fl:
        return len(itin) <= 3

    if "under 2500" in fl:
        total = bs.get("total_estimated_cost", 0)
        return total <= 2500

    if "within budget" in fl:
        limit = case.get("budget_limit")
        total = bs.get("total_estimated_cost", 0)
        if limit:
            return total <= float(limit)
        return bs.get("within_budget", False)

    if "food" in fl and ("include" in fl or "related" in fl):
        return "food" in _blob(output)

    if "cultural" in fl or "culture" in fl:
        return "culture" in _blob(output)

    if "nature" in fl:
        return "nature" in _blob(output)

    if "hotel" in fl:
        return bool(output.get("hotels"))

    if "flight" in fl:
        return bool(output.get("flights"))

    if "transport" in fl:
        return bool(output.get("transport"))

    if "budget summary" in fl:
        return bool(bs)

    if "agents include" in fl:
        agents = output.get("agents_used") or []
        return any(a in agents for a in ("flight", "hotel"))

    return True


def _check_forbidden(forbidden: str, output: dict[str, Any], case: dict[str, Any]) -> bool:
    """Return True if forbidden fact is violated."""
    fl = forbidden.lower()
    blob = _blob(output)
    bs = output.get("budget_summary") or {}
    itin = output.get("itinerary") or []

    if "exceeds budget" in fl:
        limit = case.get("budget_limit") or bs.get("budget_limit")
        total = bs.get("total_estimated_cost", 0)
        return bool(limit and total > float(limit))

    if fl.strip() == "within budget":
        limit = case.get("budget_limit") or bs.get("budget_limit")
        total = bs.get("total_estimated_cost", 0)
        return bool(limit and total <= float(limit))

    if "duplicate" in fl:
        titles = []
        for day in itin:
            for item in day.get("items") or []:
                titles.append((item.get("title") or "").lower())
        return len(titles) != len(set(titles)) and len(titles) > 0

    if "booking" in fl or "purchase" in fl:
        return bool(re.search(r"booked|confirmed purchase|purchase completed", blob))

    if "missing hotel" in fl:
        return not output.get("hotels")

    if "missing transport" in fl:
        return not output.get("transport")

    if "missing budget" in fl:
        return not bs

    if "international flight" in fl or "flight estimate" in fl:
        if "no " in fl or "without" in fl:
            return bool(output.get("flights"))
        return False

    if "full itinerary" in fl or "complete 5-day" in fl or "without budget" in fl or "without duration" in fl or "without destination" in fl:
        if output.get("needs_clarification"):
            return False
        if "without budget" in fl and not case.get("budget_limit"):
            return len(itin) > 0 and bool(bs)
        if "without duration" in fl:
            return len(itin) > 0 and case.get("expected_days") is None
        if "without destination" in fl:
            return len(itin) > 0
        if "complete 5-day" in fl:
            return len(itin) >= 5
        return len(itin) > 3

    if "wrong day count" in fl:
        exp = case.get("expected_days")
        return exp is not None and len(itin) != exp

    return False


def rule_based_judge(case: dict[str, Any], output: dict[str, Any]) -> JudgeVerdict:
    fact_results = {
        fact: _check_expected_fact(fact, output, case)
        for fact in case.get("expected_facts", [])
    }
    forbidden_violations = [
        f for f in case.get("forbidden_facts", [])
        if _check_forbidden(f, output, case)
    ]
    n_facts = max(len(fact_results), 1)
    score = sum(fact_results.values()) / n_facts
    passed = all(fact_results.values()) and not forbidden_violations
    return JudgeVerdict(
        case_id=case["id"],
        passed=passed,
        fact_results=fact_results,
        forbidden_violations=forbidden_violations,
        score=round(score, 4),
        rater="rules",
    )


async def llm_judge(
    case: dict[str, Any], output: dict[str, Any], variant: str = "strict"
) -> JudgeVerdict:
    """Rater B: LLM rubric via configured provider, else mock_judge."""
    _ = variant
    try:
        import sys
        from pathlib import Path

        backend = Path(__file__).resolve().parents[1] / "backend"
        if str(backend) not in sys.path:
            sys.path.insert(0, str(backend))

        from app.services.llm_client import (
            complete_json,
            llm_available,
            llm_judge_rater_label,
            max_tokens_for_agent,
            model_for_agent,
        )
        from pydantic import BaseModel, Field

        class JudgeLLMOutput(BaseModel):
            passed: bool
            fact_scores: dict[str, bool] = Field(default_factory=dict)
            forbidden_violations: list[str] = Field(default_factory=list)
            reasoning: str = ""

        if not llm_available():
            return mock_judge(case, output)

        rater = llm_judge_rater_label()

        payload = {
            "case_id": case["id"],
            "input": case["input"],
            "expected_facts": case.get("expected_facts", []),
            "forbidden_facts": case.get("forbidden_facts", []),
            "output": {
                k: output.get(k)
                for k in (
                    "itinerary",
                    "budget_summary",
                    "hotels",
                    "flights",
                    "transport",
                    "activities",
                    "needs_clarification",
                    "agents_used",
                )
            },
        }
        system = (
            "You are an evaluation judge for travel plans. "
            "Score whether expected_facts are met and forbidden_facts are violated. "
            "Return JSON with passed (bool), fact_scores (map fact string to bool), "
            "forbidden_violations (list of triggered forbidden strings), reasoning (short)."
        )
        result = await complete_json(
            agent_name="eval_judge",
            model=model_for_agent("validator"),
            system=system,
            user=json.dumps(payload, indent=2),
            max_tokens=max_tokens_for_agent("eval_judge"),
            output_model=JudgeLLMOutput,
        )
        if not isinstance(result, JudgeLLMOutput):
            return mock_judge(case, output)

        fact_results = result.fact_scores or {
            f: result.passed for f in case.get("expected_facts", [])
        }
        score = (
            sum(1 for v in fact_results.values() if v) / max(len(fact_results), 1)
        )
        return JudgeVerdict(
            case_id=case["id"],
            passed=result.passed,
            fact_results=fact_results,
            forbidden_violations=result.forbidden_violations,
            score=round(score, 4),
            rater=rater,
        )
    except Exception as exc:
        logger.warning("LLM judge failed for %s: %s", case["id"], exc)
        return mock_judge(case, output)


def mock_judge(case: dict[str, Any], output: dict[str, Any]) -> JudgeVerdict:
    """Fallback rater when no LLM provider is available or the judge call fails."""
    rules = rule_based_judge(case, output)
    # Borderline: strict on forbidden, lenient on partial fact match
    passed = rules.score >= 0.75 and len(rules.forbidden_violations) == 0
    if rules.score >= 0.5 and rules.score < 0.75 and len(rules.forbidden_violations) == 0:
        passed = hash(case["id"]) % 2 == 0
    return JudgeVerdict(
        case_id=rules.case_id,
        passed=passed,
        fact_results=rules.fact_results,
        forbidden_violations=rules.forbidden_violations,
        score=rules.score,
        rater="mock_judge",
    )


def cohens_kappa(labels_a: list[bool], labels_b: list[bool]) -> float:
    if len(labels_a) != len(labels_b) or not labels_a:
        return 0.0
    n = len(labels_a)
    agree = sum(1 for a, b in zip(labels_a, labels_b) if a == b)
    po = agree / n
    p_a = sum(labels_a) / n
    p_b = sum(labels_b) / n
    pe = p_a * p_b + (1 - p_a) * (1 - p_b)
    if pe == 1.0:
        return 1.0
    return (po - pe) / (1 - pe)


def compute_kappa(
    verdicts_rules: list[JudgeVerdict], verdicts_llm: list[JudgeVerdict]
) -> dict[str, Any]:
    labels_a = [v.passed for v in verdicts_rules]
    labels_b = [v.passed for v in verdicts_llm]
    kappa = cohens_kappa(labels_a, labels_b)
    rater_counts: dict[str, int] = {}
    for v in verdicts_llm:
        rater_counts[v.rater] = rater_counts.get(v.rater, 0) + 1
    if rater_counts:
        rater_b, n_primary = max(rater_counts.items(), key=lambda x: x[1])
        if len(rater_counts) > 1:
            rater_b = f"{rater_b} ({n_primary}/{len(verdicts_llm)})"
    else:
        rater_b = "llm"
    return {
        "kappa": round(kappa, 4),
        "target": 0.6,
        "meets_target": kappa >= 0.6,
        "n_cases": len(labels_a),
        "agreement_rate": round(sum(1 for a, b in zip(labels_a, labels_b) if a == b) / max(n, 1), 4)
        if (n := len(labels_a))
        else 0,
        "rater_a": "rules",
        "rater_b": rater_b,
        "rater_counts": rater_counts,
    }
