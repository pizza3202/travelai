#!/usr/bin/env python3
"""
Debug LLM judge for one golden case — OpenRouter free tier.

  cd ~/Desktop/travelai
  backend/.venv/bin/python eval/debug_judge_one.py
  backend/.venv/bin/python eval/debug_judge_one.py --case-id tokyo_5day_budget
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BACKEND))

from eval.judge import load_golden, mock_judge, rule_based_judge  # noqa: E402
from eval.run_eval import run_case  # noqa: E402


def _hr(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Debug one-case LLM judge")
    parser.add_argument("--case-id", default="tokyo_5day_budget")
    parser.add_argument("--mode", choices=["optimized", "baseline"], default="optimized")
    args = parser.parse_args()

    cases = {c["id"]: c for c in load_golden(Path(__file__).parent / "golden.jsonl")}
    case = cases.get(args.case_id)
    if not case:
        print(f"Unknown case id: {args.case_id}")
        sys.exit(1)

    from app.config import get_settings
    from app.services.llm_client import (
        LLMUnavailableError,
        _parse_json_content,
        _resolve_provider,
        complete_json,
        complete_text,
        llm_available,
        max_tokens_for_agent,
        model_for_agent,
    )
    from pydantic import BaseModel, Field

    get_settings.cache_clear()
    settings = get_settings()

    _hr("CONFIG")
    print("LLM_PROVIDER:", settings.llm_provider)
    print("OPENROUTER_API_KEY set:", bool(settings.openrouter_api_key))
    print("llm_available():", llm_available())
    try:
        provider = _resolve_provider()
    except LLMUnavailableError as e:
        provider = f"UNAVAILABLE ({e})"
    print("resolved provider:", provider)

    model = model_for_agent("validator")
    print("judge model (validator):", model)

    _hr(f"PIPELINE OUTPUT ({args.mode})")
    state_output = await run_case(case, args.mode)
    print("agents_used:", state_output.get("agents_used"))
    print("itinerary days:", len(state_output.get("itinerary") or []))
    rules = rule_based_judge(case, state_output)
    print("rule_based passed:", rules.passed)

    class JudgeLLMOutput(BaseModel):
        passed: bool
        fact_scores: dict[str, bool] = Field(default_factory=dict)
        forbidden_violations: list[str] = Field(default_factory=list)
        reasoning: str = ""

    payload = {
        "case_id": case["id"],
        "input": case["input"],
        "expected_facts": case.get("expected_facts", []),
        "forbidden_facts": case.get("forbidden_facts", []),
        "output": {
            k: state_output.get(k)
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
    user = json.dumps(payload, indent=2)

    _hr("RAW HTTP (complete_text)")
    fallback_reason = None
    raw_content = None
    try:
        result = await complete_text(
            agent_name="eval_judge",
            model=model,
            system=system + "\nRespond with valid JSON only, no markdown.",
            user=user,
            max_tokens=max_tokens_for_agent("eval_judge"),
            temperature=0.1,
        )
        print("provider:", result.provider)
        print("model:", result.model)
        print("prompt_tokens:", result.prompt_tokens)
        print("completion_tokens:", result.completion_tokens)
        raw_content = result.content
        print("raw response (first 1200 chars):")
        print(raw_content[:1200] if raw_content else "(empty)")
        if raw_content and raw_content.strip().startswith("```"):
            print("\n>>> Likely MARKDOWN fence — _parse_json_content should strip this")
    except Exception as e:
        fallback_reason = f"complete_text failed: {type(e).__name__}: {e}"
        print("ERROR:", fallback_reason)
        traceback.print_exc()

    _hr("PARSE (_parse_json_content)")
    parsed = None
    if raw_content:
        try:
            parsed = _parse_json_content(raw_content)
            print("parsed JSON keys:", list(parsed.keys()))
            print("parsed:", json.dumps(parsed, indent=2)[:800])
        except Exception as e:
            fallback_reason = f"JSON parse failed: {type(e).__name__}: {e}"
            print("ERROR:", fallback_reason)

    _hr("PYDANTIC (complete_json)")
    try:
        validated = await complete_json(
            agent_name="eval_judge",
            model=model,
            system=system,
            user=user,
            max_tokens=max_tokens_for_agent("eval_judge"),
            output_model=JudgeLLMOutput,
        )
        print("parsed response (validated):")
        print(validated.model_dump_json(indent=2))
        print("fallback reason: NONE — judge would use", f"{provider}_judge")
    except Exception as e:
        if not fallback_reason:
            fallback_reason = f"complete_json failed: {type(e).__name__}: {e}"
        print("ERROR:", fallback_reason)
        traceback.print_exc()
        mock = mock_judge(case, state_output)
        print("\nWould fallback to mock_judge, passed:", mock.passed)

    _hr("FREE MODEL QUICK CHECK (OpenRouter)")
    import httpx

    key = settings.openrouter_api_key
    if not key:
        print("No OPENROUTER_API_KEY — skip")
        return
    test_models = [
        model,
        "poolside/laguna-xs.2:free",
        "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    ]
    async with httpx.AsyncClient(timeout=45) as client:
        for m in dict.fromkeys(test_models):
            r = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": m,
                    "messages": [{"role": "user", "content": 'Return JSON: {"ok":true}'}],
                    "max_tokens": 30,
                    "response_format": {"type": "json_object"},
                },
            )
            body = r.text[:200]
            print(f"  {m}: HTTP {r.status_code} — {body}")


if __name__ == "__main__":
    asyncio.run(main())
