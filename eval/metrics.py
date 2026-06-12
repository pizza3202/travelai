"""Per-case evaluation metrics for TravelAI golden harness."""

from __future__ import annotations

import json
import re
from typing import Any


def _text_blob(output: dict[str, Any]) -> str:
    return json.dumps(output, default=str).lower()


def _expected_days(case: dict[str, Any]) -> int | None:
    if case.get("expected_days") is not None:
        return int(case["expected_days"])
    for fact in case.get("expected_facts", []):
        m = re.search(r"(\d+)\s*days?", fact, re.I)
        if m and "itinerary has" in fact.lower():
            return int(m.group(1))
        if "at most 3" in fact.lower() or "weekend" in fact.lower():
            return 3
    return None


def budget_satisfaction(output: dict[str, Any], case: dict[str, Any]) -> bool | None:
    """True if within budget; None if clarification or no budget data."""
    if output.get("needs_clarification"):
        return None
    bs = output.get("budget_summary") or {}
    if not bs:
        return None
    limit = case.get("budget_limit") or bs.get("budget_limit")
    if limit is None:
        return bs.get("within_budget")
    total = bs.get("total_estimated_cost", 0)
    return total <= float(limit)


def valid_day_structure(output: dict[str, Any], case: dict[str, Any]) -> bool | None:
    if output.get("needs_clarification"):
        # Clarification cases should NOT have full itinerary
        itin = output.get("itinerary") or []
        expected = _expected_days(case)
        if expected and len(itin) == expected:
            return False
        return True
    expected = _expected_days(case)
    if expected is None:
        itin = output.get("itinerary") or []
        return len(itin) > 0
    itin = output.get("itinerary") or []
    if "at most 3" in " ".join(case.get("expected_facts", [])).lower():
        return len(itin) <= 3
    return len(itin) == expected


def interest_match(output: dict[str, Any], case: dict[str, Any]) -> float:
    """Fraction of requested interests reflected in output (0-1)."""
    interests = [i.lower() for i in case.get("interests", [])]
    if not interests:
        for fact in case.get("expected_facts", []):
            if "food" in fact.lower():
                interests.append("food")
            if "culture" in fact.lower():
                interests.append("culture")
            if "nature" in fact.lower():
                interests.append("nature")
    if not interests:
        return 1.0
    blob = _text_blob(output)
    hits = sum(1 for i in interests if i in blob)
    return hits / len(interests)


def forbidden_fact_violation(output: dict[str, Any], case: dict[str, Any]) -> bool:
    """True if any forbidden fact triggered."""
    blob = _text_blob(output)
    for forbidden in case.get("forbidden_facts", []):
        fl = forbidden.lower()
        if "exceeds budget" in fl or fl == "within budget":
            bs = output.get("budget_summary") or {}
            within = bs.get("within_budget", True)
            total = bs.get("total_estimated_cost", 0)
            limit = case.get("budget_limit") or bs.get("budget_limit") or 0
            if "exceeds" in fl and limit and total > limit:
                return True
            if fl.strip() == "within budget" and within:
                return True
        if "duplicate" in fl:
            titles = []
            for day in output.get("itinerary") or []:
                for item in day.get("items") or []:
                    titles.append((item.get("title") or "").lower())
            if len(titles) != len(set(titles)) and titles:
                return True
        if "booking" in fl or "purchase" in fl:
            if re.search(r"booked|confirmed purchase|purchase completed", blob):
                return True
        if "missing hotel" in fl and not (output.get("hotels") or []):
            return True
        if "missing transport" in fl and not (output.get("transport") or []):
            return True
        if "missing budget" in fl and not output.get("budget_summary"):
            return True
        if "flight estimate" in fl and (output.get("flights") or []):
            if "no " in fl or "without" in fl or "international flight" in fl:
                return True
        if "complete 5-day" in fl or "full itinerary" in fl:
            if output.get("needs_clarification"):
                continue
            exp = _expected_days(case)
            if exp and len(output.get("itinerary") or []) >= exp:
                if "without budget" in fl or "without duration" in fl or "without destination" in fl:
                    return True
                if "complete 5-day" in fl and exp == 5:
                    return True
        if "wrong day count" in fl:
            exp = _expected_days(case)
            if exp and len(output.get("itinerary") or []) != exp:
                return True
    return False


def estimate_run_cost_usd(output: dict[str, Any], mode: str) -> float:
    """Heuristic API cost per eval case (USD)."""
    agents = output.get("agents_used") or []
    cost = 0.0
    if "planner" in agents:
        cost += 0.0008
    if "synthesizer" in agents:
        cost += 0.008 if mode == "optimized" else 0.003
    if "validator" in agents:
        cost += 0.0005
    for a in agents:
        if a in ("flight", "hotel", "activity", "transport"):
            cost += 0.0003
    if mode == "optimized":
        cost += 0.002  # RAG + extra agents
    return round(cost, 6)


def compute_case_metrics(
    case: dict[str, Any], output: dict[str, Any], mode: str
) -> dict[str, Any]:
    return {
        "budget_satisfaction": budget_satisfaction(output, case),
        "valid_day_structure": valid_day_structure(output, case),
        "interest_match": round(interest_match(output, case), 4),
        "forbidden_fact_violation": forbidden_fact_violation(output, case),
        "latency_ms": output.get("latency_ms"),
        "estimated_cost_usd": estimate_run_cost_usd(output, mode),
    }
