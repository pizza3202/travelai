# TravelAI Eval Summary

Generated from `baseline_results.json` and `optimized_results.json`.

## Aggregate Metrics

| Metric | Baseline | Optimized | Delta |
|--------|----------|-----------|-------|
| Rule pass rate | 57.1% | 85.7% | +28.6pp |
| Budget satisfaction | 86.4% | 95.5% | +9.1pp |
| Valid day structure | 100.0% | 100.0% | +0.0pp |
| Interest match (avg) | 64.9% | 82.1% | +17.3pp |
| Forbidden violation rate | 25.0% | 10.7% | -14.3pp |
| Latency p50 (ms) | 1 | 436.5 | — |
| Est. cost / case (USD) | None | 0.010421428571428573 | — |
| RAGAS faithfulness (avg) | None | 0.5285714285714286 | — |
| RAGAS context recall (avg) | None | 1.0 | — |
| Cases with RAG context | 0 | 21 | — |

## Cohen's Kappa (rules vs LLM/mock judge)

- **κ = 0.7586** (target ≥ 0.6)
- Meets target: **True**
- Agreement rate: 0.9286
- Rater B: mock_judge (20/28)

## Failure Analysis (rule judge, optimized)

### missing_destination_clarify
- Tags: missing_info, clarification, multi_day, budget, interests
- Forbidden hits: ['full 5-day itinerary without destination']
- Failed expected facts: ['asks for destination or clarification', 'needs clarification']

### paris_hotel_focus
- Tags: hotel, paris, multi_day, budget, international_trip
- Forbidden hits: ['missing hotel estimate']
- Failed expected facts: ['itinerary has 5 days', 'has hotel estimate']

### barcelona_style_reject
- Tags: budget, multi_day, interests, international_trip
- Forbidden hits: []
- Failed expected facts: ['itinerary has 5 days']

## Quality / Latency / Cost Tradeoff

Optimized adds RAG grounding, specialist agents, budget validation, and repair — improving 
structure and interest alignment at the cost of higher latency and per-case LLM/tool spend. 
Baseline is faster and cheaper but misses multi-agent constraints and RAG context. 
For capstone demo, prefer **optimized** when quality matters; use **baseline** as ablation.
