# TravelAI Eval Summary

R0 (baseline) vs R3 (optimized) on the same golden set.

## Aggregate Metrics

| Metric | Baseline (R0) | Optimized (R3) | Delta |
|--------|---------------|----------------|-------|
| Rule pass rate | 60.7% | 82.1% | +21.4pp |
| Budget satisfaction | 86.4% | 94.7% | +8.4pp |
| Valid day structure | 100.0% | 100.0% | +0.0pp |
| Interest match (avg) | 68.5% | 75.0% | +6.5pp |
| Forbidden violation rate | 25.0% | 17.9% | -7.1pp |
| Latency p50 (ms) | 2621.5 | 50556.0 | — |
| Est. cost / case (USD) | None | 0.009382142857142858 | — |
| RAGAS faithfulness (avg) | None | 0.5645061728395062 | — |
| Cases with RAG context | 0 | 18 | — |

Full R0→R3 ablation: [`eval/results/iteration.md`](results/iteration.md)

## Cohen's Kappa (rules vs LLM judge, R3 run)

- **κ = 0.7042** (target ≥ 0.6)
- Meets target: **True**
- Agreement rate: 0.8929
- Rater B: openrouter_judge

## Failure Analysis (rule judge, R3 optimized)

### japan_transport_focus
- Tags: transportation, japan, multi_day, budget, international_trip
- Forbidden hits: ['missing transport plan']
- Failed expected facts: ['itinerary has 6 days', 'has transport plan']

### paris_art_culture
- Tags: interests, culture, international_trip, multi_day, budget
- Forbidden hits: ['missing budget summary']
- Failed expected facts: ['itinerary has 5 days', 'includes cultural activities']

### london_5day_international
- Tags: international_trip, multi_day, budget, interests
- Forbidden hits: []
- Failed expected facts: ['itinerary has 5 days', 'has flight estimate']

## Trade-off

R3 trades higher latency and per-case LLM cost for +rule pass and RAG grounding vs R0. 
See iteration log for step-wise R1/R2 deltas.
