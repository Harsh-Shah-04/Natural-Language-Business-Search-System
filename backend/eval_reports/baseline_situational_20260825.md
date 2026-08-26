# Situational baseline — measured 2026-08-25

Pre-work for M6. Two questions, answered before writing any feature code:

1. Does the shipped system already handle the reviewer's own example?
2. Is there a measurable ranking gap on symptom-only queries in general?

**Method.** `scripts/measure_situational_baseline.py`, against the live Atlas
cluster through `app.search.search_businesses()` — the exact pipeline `/api/search`
runs. Ten queries: the reviewer's verbatim example plus nine further symptom-only
queries, i.e. queries that describe a problem without naming a service. Two
configurations: `rerank=True` (what ships, since `RERANK_ENABLED` defaults true)
and `rerank=False`.

**Headline metric is success@3** (did every relevant business that could fit in the
top 3 actually land there) rather than P@5. See Finding 1 for why P@5 is unusable
here.

**Corpus correction applied first.** The live collection held 125 documents, not
120: five leftover registration-test records (`Demo Agent Labs`, `Jetflix AI`,
`Future AI Solutions Pvt Ltd`, `AI Solutions Pvt Ltd`, `Krishna Enterprise` with
`sub_category: "parlour"`). They were polluting 8 of 20 measured runs and one of
them outranked the correct answer on the reviewer's own query. Removed before the
numbers below. Reversible via `scripts/seed.py`.

---

## Finding 1 — the existing benchmark is saturated and cannot measure this work

`scripts/compute_metric_ceiling.py`. `precision_at_k` divides by `k=5`, while most
golden queries have 3 relevant documents, so per-query max P@5 is 0.6.

| category | n | max P@5 |
|---|---|---|
| edge_case | 5 | 0.3600 |
| filtered | 5 | 0.2800 |
| keyword | 5 | 0.6000 |
| multi_intent | 5 | 1.0000 |
| semantic | 5 | 0.6000 |
| synonym | 5 | 0.6000 |
| **overall** | **30** | **0.5733** |

`report_20260720_200803.md` records hybrid-rerank at **0.560**. That is **97.7% of
the mathematical ceiling**, leaving **0.0133** of headroom, and `R@10` is already
1.000. Any A/B run on this set measures noise.

Separately: `edge-02` and `edge-04` have zero relevant documents. `recall_at_k`
returns `None` for those and is excluded from the mean; `precision_at_k` returns
`0.0` and **is** averaged in. That asymmetry is why `edge_case` caps at 0.360, and
it will pin any future zero-relevant adversarial case at 0.0 whether it passes or
fails.

---

## Finding 2 — the reviewer's own example already scores perfectly

> *"My company keeps getting suspicious emails and I want someone to make sure our
> employees don't fall for scams"*

| config | top 3 | success@3 | recall@3 | P@5 |
|---|---|---|---|---|
| hybrid + rerank | Global Cybersecurity, Next Cybersecurity, Prime Cybersecurity | **1** | **1.00** | 0.60 / 0.60 (ceiling) |
| hybrid | Prime Cybersecurity, Global Cybersecurity, Next Cybersecurity | **1** | **1.00** | 0.60 / 0.60 (ceiling) |

All three correct businesses at ranks 1, 2, 3, at the metric ceiling, with no
changes to the system.

**On this query the system's ranking was never the problem.** It found the right
answer and gave the user no reason to believe it had understood them. That is a
presentation gap, not a retrieval gap.

Caveat worth stating in the meeting: before the corpus correction above, this same
query returned `AI Solutions Pvt Ltd` at rank 1 and scored success@3 = 0. If the
reviewer tested against the polluted database, a meaningless test record was
outranking the correct answers.

---

## Finding 3 — symptom-only queries are genuinely weak

Nine queries, none naming a service. Aggregate:

| config | success@3 | recall@3 | P@5 |
|---|---|---|---|
| hybrid + rerank (**ships today**) | 0.222 | 0.241 | **0.244** |
| hybrid (rerank off) | 0.222 | 0.278 | **0.378** |

Two of nine pass. The gap is real — just not on the reviewer's example.

---

## Finding 4 — the cross-encoder is a net negative on this query class

Reranking costs **0.133 P@5, a 35.3% relative decline**, and 0.037 recall@3.

| query | target | hybrid rank | +rerank rank | effect |
|---|---|---|---|---|
| `sit-02` new office, space bare | Interior Design | **1** | **6** | **destroyed** |
| `sit-05` tax department notice | Chartered / GST | **1** | **5** | **destroyed** |
| `sit-04` nobody finds us online | Digital Marketing | 3 | none | **destroyed** |
| `sit-07` staff can't handle angry customers | Corporate Training | 5 | none | worse |
| `sit-06` shop-floor machines | Industrial Automation | 2 | **1** | helps |
| `sit-08` product arrived damaged | Packaging / Freight | 5 | **2** | helps |
| `sit-09` site down under traffic | Cloud Services | 10 | **3** | helps |
| `sit-10` relocating, everything must arrive | Freight / Courier | 2 | **1** | helps |

Four helped, four hurt — but the damage is asymmetric. The wins move a result from
rank 2 to 1 or 5 to 2. The losses take a **perfect rank-1 result and bury it**.
`sit-05` is the clearest: hybrid alone returns the three GST businesses at ranks
1, 2, 3 for P@5 = 1.00, exactly at ceiling. With reranking they fall to rank 5 and
P@5 = 0.20.

### Why

`ms-marco-MiniLM-L-6-v2` is a 22M-parameter passage-relevance model. It scores
lexical-semantic overlap between query and document and has the same world-knowledge
ceiling as `bge-small-en-v1.5`. It cannot make the `suspicious emails → SOC,
penetration testing` hop either. Placed last and judging against the raw symptom
query, it is the one stage structurally guaranteed to score the correct answer low —
and it overrides a bi-encoder that had already found it.

### Scope correction to M4.2

M4.2 concluded "reranking measurably improves precision@5, so `RERANK_ENABLED`
defaults to true." That conclusion is sound **on queries that name their service**,
which is every query in the golden set. It **reverses** on queries that do not.
`RERANK_ENABLED` currently defaults to `true`, so the shipped system runs the worse
configuration for exactly the query class the reviewer raised.

Note also that the two configurations pass **different** queries — hybrid wins
`sit-02` and `sit-05`, reranking wins `sit-06` and `sit-10`. They are complementary,
which suggests query-conditional reranking rather than a global on/off.

---

## What this changes

1. **The visible-reasoning panel is the deliverable, not the ranking work.**
   Finding 2 settles it for the reviewer's own example.
2. **A real symptom-query gap exists** (success@3 = 0.222), so intent understanding
   still has a job — just not the one the plan assumed.
3. **The cheapest large win is a configuration change, not an LLM.** Measure
   query-conditional reranking, or reranking against an inferred need instead of the
   raw symptom, before committing to corpus enrichment.
4. **Never quote a P@5 delta from the existing golden set again without its
   ceiling beside it.**

## Reproduce

```
uv run python scripts/compute_metric_ceiling.py
uv run python scripts/measure_situational_baseline.py
```

Raw per-query output: `eval_reports/situational_baseline.json`.

## Limits of this measurement

- n = 9 situational queries. Small. One flipped ground-truth label moves the
  aggregate by ~0.11 on success@3.
- Ground-truth labels are first-pass and authored by the same process that wrote the
  queries. `sit-05`, `sit-08` and `sit-10` use multi-category relevant sets where two
  categories are genuinely both correct.
- The reviewer's query is the only genuinely held-out case here, because he wrote it.
- Latency was not measured in this run.
