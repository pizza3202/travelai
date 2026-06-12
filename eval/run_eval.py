#!/usr/bin/env python3
"""
TravelAI evaluation harness.

  python eval/run_eval.py --mode baseline
  python eval/run_eval.py --mode r1
  python eval/run_eval.py --mode r2
  python eval/run_eval.py --mode optimized
  python eval/run_eval.py --mode all          # R0→R3 + iteration summary
  python eval/run_eval.py --mode summary      # compare saved JSON only
  python eval/run_eval.py --report            # alias for --mode summary
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Callable, Awaitable

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BACKEND))

from eval.judge import (  # noqa: E402
    compute_kappa,
    load_golden,
    llm_judge,
    rule_based_judge,
)
from eval.metrics import compute_case_metrics  # noqa: E402
from eval.ragas_eval import run_ragas_metrics  # noqa: E402

GOLDEN_PATH = Path(__file__).parent / "golden.jsonl"
RESULTS_DIR = Path(__file__).parent / "results"

# Eval round order for iteration log (R0 → R3)
ROUND_MODES = ["baseline", "r1", "r2", "optimized"]

RESULT_FILENAMES: dict[str, str] = {
    "baseline": "baseline_results.json",
    "r1": "r1_results.json",
    "r2": "r2_results.json",
    "optimized": "optimized_results.json",
}

ROUND_META: dict[str, tuple[str, str]] = {
    "baseline": ("R0", "Baseline: single-agent, no RAG/validator/repair"),
    "r1": ("R1", "+ specialist agents + budget (no RAG/validator/repair)"),
    "r2": ("R2", "+ RAG grounding (no validator/repair)"),
    "optimized": ("R3", "+ validator + repair loop"),
}


async def run_case(case: dict, mode: str) -> dict[str, Any]:
    from uuid import uuid4

    from app.graph.baseline import run_baseline_graph
    from app.graph.workflow import run_optimized_graph, run_r1_graph, run_r2_graph
    from app.models.schemas import AgentState, GraphMode, TravelPlanResponse

    graph_mode = {
        "baseline": GraphMode.BASELINE,
        "r1": GraphMode.R1,
        "r2": GraphMode.R2,
        "optimized": GraphMode.OPTIMIZED,
    }[mode]

    runners: dict[str, Callable[[AgentState], Awaitable[Any]]] = {
        "baseline": run_baseline_graph,
        "r1": run_r1_graph,
        "r2": run_r2_graph,
        "optimized": run_optimized_graph,
    }

    state = AgentState(
        session_id=str(uuid4()),
        conversation_id=str(uuid4()),
        message=case["input"],
        departure_city=case.get("departure_city"),
        mode=graph_mode,
    )

    start = time.perf_counter()
    result = await runners[mode](state)
    latency_ms = int((time.perf_counter() - start) * 1000)

    if result.needs_clarification:
        output: dict[str, Any] = {
            "needs_clarification": True,
            "message": result.clarification_message,
            "itinerary": [],
            "agents_used": result.agents_used,
        }
    elif result.final_response:
        fr = result.final_response
        plan = (
            TravelPlanResponse.model_validate(fr) if isinstance(fr, dict) else fr
        )
        output = plan.model_dump(mode="json")
        output["agents_used"] = result.agents_used
    else:
        output = {"error": "no final response", "agents_used": result.agents_used}

    output["latency_ms"] = latency_ms
    output["rag_context"] = list(result.rag_context or [])
    output["web_search_snippets"] = list(result.web_search_snippets or [])
    return output


def _aggregate(results: list[dict]) -> dict[str, Any]:
    ok = [r for r in results if "error" not in r]
    n = max(len(ok), 1)

    def rate(key: str) -> float | None:
        vals = [r["metrics"][key] for r in ok if r.get("metrics", {}).get(key) is not None]
        if not vals:
            return None
        if isinstance(vals[0], bool):
            return sum(vals) / len(vals)
        return sum(vals) / len(vals)

    latencies = [r["metrics"]["latency_ms"] for r in ok if r.get("metrics", {}).get("latency_ms")]
    costs = [r["metrics"]["estimated_cost_usd"] for r in ok if r.get("metrics", {}).get("estimated_cost_usd")]

    ragas_f = [r["ragas"]["faithfulness"] for r in ok if r.get("ragas", {}).get("faithfulness") is not None]
    ragas_c = [r["ragas"]["context_recall"] for r in ok if r.get("ragas", {}).get("context_recall") is not None]

    return {
        "total_cases": len(results),
        "successful_cases": len(ok),
        "error_cases": len(results) - len(ok),
        "rule_pass_rate": sum(1 for r in ok if r.get("passed_rules")) / n,
        "llm_pass_rate": sum(1 for r in ok if r.get("passed_llm")) / n,
        "budget_satisfaction_rate": rate("budget_satisfaction"),
        "valid_structure_rate": rate("valid_day_structure"),
        "interest_match_avg": rate("interest_match"),
        "forbidden_violation_rate": rate("forbidden_fact_violation"),
        "latency_ms_avg": statistics.mean(latencies) if latencies else None,
        "latency_ms_p50": statistics.median(latencies) if latencies else None,
        "estimated_cost_usd_avg": statistics.mean(costs) if costs else None,
        "ragas_faithfulness_avg": statistics.mean(ragas_f) if ragas_f else None,
        "ragas_context_recall_avg": statistics.mean(ragas_c) if ragas_c else None,
        "ragas_cases_with_context": sum(
            1 for r in ok if not r.get("ragas", {}).get("skipped", True)
        ),
    }


async def evaluate_mode(mode: str, cases: list[dict], *, compute_kappa_flag: bool) -> dict[str, Any]:
    results: list[dict] = []
    verdicts_rules = []
    verdicts_llm = []

    for i, case in enumerate(cases):
        print(f"[{i+1}/{len(cases)}] {mode} :: {case['id']}")
        try:
            output = await run_case(case, mode)
            metrics = compute_case_metrics(case, output, mode)
            ragas = run_ragas_metrics(case, output)
            vr = rule_based_judge(case, output)
            if compute_kappa_flag:
                vl = await llm_judge(case, output)
                verdicts_llm.append(vl)
                passed_llm = vl.passed
                judge_rater_b = vl.rater
            else:
                passed_llm = None
                judge_rater_b = "skipped"
            verdicts_rules.append(vr)
            results.append(
                {
                    "id": case["id"],
                    "tags": case.get("tags", []),
                    "mode": mode,
                    "passed_rules": vr.passed,
                    "passed_llm": passed_llm,
                    "judge_rater_b": judge_rater_b,
                    "metrics": metrics,
                    "ragas": ragas,
                    "fact_results": vr.fact_results,
                    "forbidden_violations": vr.forbidden_violations,
                }
            )
        except Exception as e:
            results.append(
                {"id": case["id"], "mode": mode, "error": str(e), "tags": case.get("tags", [])}
            )

    summary = _aggregate(results)
    summary["mode"] = mode

    kappa_data = None
    if compute_kappa_flag and verdicts_rules and verdicts_llm:
        kappa_data = compute_kappa(verdicts_rules, verdicts_llm)
        summary["kappa"] = kappa_data

    return {
        "summary": summary,
        "results": results,
        "kappa": kappa_data,
    }


def _write_mode_results(mode: str, payload: dict[str, Any]) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / RESULT_FILENAMES[mode]
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {path}")
    return path


def _load_results(mode: str) -> dict[str, Any] | None:
    path = RESULTS_DIR / RESULT_FILENAMES[mode]
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _load_all_round_results() -> dict[str, dict[str, Any]]:
    loaded: dict[str, dict[str, Any]] = {}
    for mode in ROUND_MODES:
        data = _load_results(mode)
        if data:
            loaded[mode] = data
    return loaded


def _load_kappa(optimized: dict[str, Any] | None) -> dict[str, Any] | None:
    kappa_path = RESULTS_DIR / "kappa.json"
    if kappa_path.exists():
        return json.loads(kappa_path.read_text(encoding="utf-8"))
    if optimized:
        return optimized.get("kappa") or optimized.get("summary", {}).get("kappa")
    return None


def _pct(v: float | None) -> str:
    if v is None:
        return "N/A"
    return f"{v * 100:.1f}%"


def _pp_delta(curr: float | None, prev: float | None) -> str:
    if curr is None or prev is None:
        return "—"
    return f"{(curr - prev) * 100:+.1f}pp"


def _format_metric_delta(summary: dict[str, Any], prev: dict[str, Any] | None) -> str:
    """Compact delta string vs previous round for iteration table."""
    parts: list[str] = []
    rp = summary.get("rule_pass_rate")
    if rp is not None:
        parts.append(f"rule pass {_pct(rp)} ({_pp_delta(rp, prev.get('rule_pass_rate') if prev else None)} vs prev)")
    rag = summary.get("ragas_cases_with_context")
    if rag is not None:
        prev_rag = prev.get("ragas_cases_with_context") if prev else None
        if prev_rag is not None and rag != prev_rag:
            parts.append(f"RAG cases {prev_rag}→{rag}/28")
        elif prev is None:
            parts.append(f"RAG cases {rag}/28")
    interest = summary.get("interest_match_avg")
    if interest is not None:
        parts.append(f"interest {_pct(interest)} ({_pp_delta(interest, prev.get('interest_match_avg') if prev else None)})")
    budget = summary.get("budget_satisfaction_rate")
    if budget is not None:
        parts.append(f"budget {_pct(budget)} ({_pp_delta(budget, prev.get('budget_satisfaction_rate') if prev else None)})")
    lat = summary.get("latency_ms_p50")
    if lat is not None:
        parts.append(f"latency p50 {lat:.0f}ms")
    return "; ".join(parts) if parts else "—"


def _round_conclusion(mode: str, summary: dict[str, Any], prev: dict[str, Any] | None) -> str:
    rp = summary.get("rule_pass_rate")
    if mode == "baseline":
        return "Starting point: fast, minimal constraints"
    if mode == "r1":
        delta = _pp_delta(rp, prev.get("rule_pass_rate") if prev else None)
        return f"Specialists add structure; rule pass {delta} vs R0"
    if mode == "r2":
        rag = summary.get("ragas_cases_with_context", 0)
        return f"RAG grounding on {rag}/28 cases; interest/budget vs R1"
    if mode == "optimized":
        delta = _pp_delta(rp, prev.get("rule_pass_rate") if prev else None)
        return f"Validator+repair; best rule pass {delta} vs R2 (trade: latency/cost)"
    return ""


def write_iteration_md(rounds: dict[str, dict[str, Any]]) -> None:
    lines = [
        "# TravelAI Iteration Log (R0 → R3)",
        "",
        "Formal ablation eval on the same 28-case golden set.",
        "",
        "| Round | Change | Metric delta (vs previous) | Conclusion |",
        "|-------|--------|----------------------------|------------|",
    ]
    prev_summary: dict[str, Any] | None = None
    for mode in ROUND_MODES:
        if mode not in rounds:
            continue
        label, change = ROUND_META[mode]
        s = rounds[mode]["summary"]
        lines.append(
            f"| {label} | {change} | {_format_metric_delta(s, prev_summary)} | {_round_conclusion(mode, s, prev_summary)} |"
        )
        prev_summary = s

    lines.extend(["", "## Per-round detail", ""])
    for mode in ROUND_MODES:
        if mode not in rounds:
            continue
        label, change = ROUND_META[mode]
        s = rounds[mode]["summary"]
        lines.extend(
            [
                f"### {label} — {change}",
                "",
                f"- Rule pass: {_pct(s.get('rule_pass_rate'))}",
                f"- Budget satisfaction: {_pct(s.get('budget_satisfaction_rate'))}",
                f"- Interest match: {_pct(s.get('interest_match_avg'))}",
                f"- Forbidden violation: {_pct(s.get('forbidden_violation_rate'))}",
                f"- RAG cases with context: {s.get('ragas_cases_with_context', 0)}/28",
                f"- Latency p50: {s.get('latency_ms_p50', 'N/A')} ms",
                f"- Est. cost/case: ${s.get('estimated_cost_usd_avg') or 'N/A'}",
                "",
            ]
        )

    path = RESULTS_DIR / "iteration.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {path}")


def write_readme_iteration_table(rounds: dict[str, dict[str, Any]]) -> None:
    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")

    rows: list[str] = []
    prev_summary: dict[str, Any] | None = None
    for mode in ROUND_MODES:
        if mode not in rounds:
            continue
        label, change = ROUND_META[mode]
        s = rounds[mode]["summary"]
        rows.append(
            f"| {label} | {change} | {_format_metric_delta(s, prev_summary)} | {_round_conclusion(mode, s, prev_summary)} |"
        )
        prev_summary = s

    table = (
        "| Round | Change | Metric delta (vs previous) | Conclusion |\n"
        "|-------|--------|----------------------------|------------|\n"
        + "\n".join(rows)
    )

    if "## Experiment Results" in text:
        parts = text.split("## Experiment Results", 1)
        tail = parts[1]
        for marker in ("**Cohen's κ target:**", "\n## "):
            if marker in tail:
                tail = tail[tail.index(marker) :]
                break
        else:
            tail = ""
        text = parts[0] + "## Experiment Results\n\n" + table + "\n\n" + tail.lstrip()
        readme.write_text(text, encoding="utf-8")
        print("Updated README iteration table")


def _failed_cases(results: list[dict], n: int = 3) -> list[dict]:
    failed = [r for r in results if not r.get("passed_rules") and "error" not in r]
    return failed[:n]


def write_summary_md(baseline: dict, optimized: dict, kappa: dict | None) -> None:
    b = baseline["summary"]
    o = optimized["summary"]

    def delta(bv: float | None, ov: float | None) -> str:
        if bv is None or ov is None:
            return "N/A"
        return f"{(ov - bv) * 100:+.1f}pp"

    lines = [
        "# TravelAI Eval Summary",
        "",
        "R0 (baseline) vs R3 (optimized) on the same golden set.",
        "",
        "## Aggregate Metrics",
        "",
        "| Metric | Baseline (R0) | Optimized (R3) | Delta |",
        "|--------|---------------|----------------|-------|",
        f"| Rule pass rate | {_pct(b.get('rule_pass_rate'))} | {_pct(o.get('rule_pass_rate'))} | {delta(b.get('rule_pass_rate'), o.get('rule_pass_rate'))} |",
        f"| Budget satisfaction | {_pct(b.get('budget_satisfaction_rate'))} | {_pct(o.get('budget_satisfaction_rate'))} | {delta(b.get('budget_satisfaction_rate'), o.get('budget_satisfaction_rate'))} |",
        f"| Valid day structure | {_pct(b.get('valid_structure_rate'))} | {_pct(o.get('valid_structure_rate'))} | {delta(b.get('valid_structure_rate'), o.get('valid_structure_rate'))} |",
        f"| Interest match (avg) | {_pct(b.get('interest_match_avg'))} | {_pct(o.get('interest_match_avg'))} | {delta(b.get('interest_match_avg'), o.get('interest_match_avg'))} |",
        f"| Forbidden violation rate | {_pct(b.get('forbidden_violation_rate'))} | {_pct(o.get('forbidden_violation_rate'))} | {delta(b.get('forbidden_violation_rate'), o.get('forbidden_violation_rate'))} |",
        f"| Latency p50 (ms) | {b.get('latency_ms_p50', 'N/A')} | {o.get('latency_ms_p50', 'N/A')} | — |",
        f"| Est. cost / case (USD) | {b.get('estimated_cost_usd_avg', 'N/A')} | {o.get('estimated_cost_usd_avg', 'N/A')} | — |",
        f"| RAGAS faithfulness (avg) | {b.get('ragas_faithfulness_avg', 'N/A')} | {o.get('ragas_faithfulness_avg', 'N/A')} | — |",
        f"| Cases with RAG context | {b.get('ragas_cases_with_context', 0)} | {o.get('ragas_cases_with_context', 0)} | — |",
        "",
        "Full R0→R3 ablation: [`eval/results/iteration.md`](results/iteration.md)",
        "",
        "## Cohen's Kappa (rules vs LLM judge, R3 run)",
        "",
    ]
    if kappa:
        lines.extend(
            [
                f"- **κ = {kappa.get('kappa')}** (target ≥ {kappa.get('target')})",
                f"- Meets target: **{kappa.get('meets_target')}**",
                f"- Agreement rate: {kappa.get('agreement_rate')}",
                f"- Rater B: {kappa.get('rater_b')}",
                "",
            ]
        )
    else:
        lines.append("- Kappa not computed.\n")

    lines.extend(["## Failure Analysis (rule judge, R3 optimized)", ""])
    for f in _failed_cases(optimized.get("results", [])):
        lines.append(f"### {f['id']}")
        lines.append(f"- Tags: {', '.join(f.get('tags', []))}")
        lines.append(f"- Forbidden hits: {f.get('forbidden_violations')}")
        bad_facts = [k for k, v in (f.get("fact_results") or {}).items() if not v]
        lines.append(f"- Failed expected facts: {bad_facts}")
        lines.append("")

    lines.extend(
        [
            "## Trade-off",
            "",
            "R3 trades higher latency and per-case LLM cost for +rule pass and RAG grounding vs R0. ",
            "See iteration log for step-wise R1/R2 deltas.",
            "",
        ]
    )

    path = RESULTS_DIR / "summary.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {path}")


def run_summary_from_saved(kappa: dict[str, Any] | None = None) -> bool:
    rounds = _load_all_round_results()
    baseline = rounds.get("baseline")
    optimized = rounds.get("optimized")
    if not baseline or not optimized:
        print(
            "Need baseline_results.json and optimized_results.json. "
            "Run --mode baseline and --mode optimized (or --mode all) first."
        )
        return False
    if kappa is None:
        kappa = _load_kappa(optimized)
    write_summary_md(baseline, optimized, kappa)
    if len(rounds) >= 2:
        write_iteration_md(rounds)
        write_readme_iteration_table(rounds)
    print("Summary generated from saved results (no models re-run).")
    return True


async def main() -> None:
    parser = argparse.ArgumentParser(description="TravelAI eval harness")
    eval_modes = ["baseline", "r1", "r2", "optimized", "both", "all", "summary"]
    parser.add_argument(
        "--mode",
        choices=eval_modes,
        default=None,
        help="all = R0→R3 ablation + summary; summary = JSON only",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Alias for --mode summary",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--no-kappa",
        action="store_true",
        help="Skip LLM judge/kappa (faster; use on r1/r2 if rate-limited)",
    )
    args = parser.parse_args()

    if args.report or args.mode == "summary":
        run_summary_from_saved()
        return

    if not args.mode:
        parser.error("Provide --mode baseline|r1|r2|optimized|both|all|summary")

    cases = load_golden(GOLDEN_PATH)
    if args.limit:
        cases = cases[: args.limit]

    if args.mode == "both":
        modes = ["baseline", "optimized"]
    elif args.mode == "all":
        modes = ROUND_MODES
    else:
        modes = [args.mode]

    last_kappa = None
    compute_kappa = not args.no_kappa

    for mode in modes:
        kappa_flag = compute_kappa and (
            mode == "optimized" if args.mode == "all" else True
        )
        payload = await evaluate_mode(mode, cases, compute_kappa_flag=kappa_flag)
        _write_mode_results(mode, payload)
        if payload.get("kappa"):
            last_kappa = payload["kappa"]
            kappa_path = RESULTS_DIR / "kappa.json"
            kappa_path.write_text(json.dumps(last_kappa, indent=2), encoding="utf-8")
            print(f"Wrote {kappa_path}")

    if args.mode in ("both", "all"):
        run_summary_from_saved(kappa=last_kappa)


if __name__ == "__main__":
    asyncio.run(main())
