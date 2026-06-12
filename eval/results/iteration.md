# TravelAI Iteration Log (R0 → R3)

Formal ablation eval on the same 28-case golden set.

| Round | Change | Metric delta (vs previous) | Conclusion |
|-------|--------|----------------------------|------------|
| R0 | Baseline: single-agent, no RAG/validator/repair | rule pass 60.7% (— vs prev); RAG cases 0/28; interest 68.5% (—); budget 86.4% (—); latency p50 2622ms | Starting point: fast, minimal constraints |
| R1 | + specialist agents + budget (no RAG/validator/repair) | rule pass 60.7% (+0.0pp vs prev); interest 85.7% (+17.3pp); budget 63.6% (-22.7pp); latency p50 44784ms | Specialists add structure; rule pass +0.0pp vs R0 |
| R2 | + RAG grounding (no validator/repair) | rule pass 64.3% (+3.6pp vs prev); RAG cases 0→20/28; interest 82.1% (-3.6pp); budget 63.6% (+0.0pp); latency p50 49788ms | RAG grounding on 20/28 cases; interest/budget vs R1 |
| R3 | + validator + repair loop | rule pass 82.1% (+17.9pp vs prev); RAG cases 20→18/28; interest 75.0% (-7.1pp); budget 94.7% (+31.1pp); latency p50 50556ms | Validator+repair; best rule pass +17.9pp vs R2 (trade: latency/cost) |

## Per-round detail

### R0 — Baseline: single-agent, no RAG/validator/repair

- Rule pass: 60.7%
- Budget satisfaction: 86.4%
- Interest match: 68.5%
- Forbidden violation: 25.0%
- RAG cases with context: 0/28
- Latency p50: 2621.5 ms
- Est. cost/case: $N/A

### R1 — + specialist agents + budget (no RAG/validator/repair)

- Rule pass: 60.7%
- Budget satisfaction: 63.6%
- Interest match: 85.7%
- Forbidden violation: 28.6%
- RAG cases with context: 0/28
- Latency p50: 44784.0 ms
- Est. cost/case: $0.004057142857142857

### R2 — + RAG grounding (no validator/repair)

- Rule pass: 64.3%
- Budget satisfaction: 63.6%
- Interest match: 82.1%
- Forbidden violation: 28.6%
- RAG cases with context: 20/28
- Latency p50: 49787.5 ms
- Est. cost/case: $0.004057142857142857

### R3 — + validator + repair loop

- Rule pass: 82.1%
- Budget satisfaction: 94.7%
- Interest match: 75.0%
- Forbidden violation: 17.9%
- RAG cases with context: 18/28
- Latency p50: 50556.0 ms
- Est. cost/case: $0.009382142857142858
