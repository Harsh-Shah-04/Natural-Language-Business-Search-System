# Project Summary

Natural Language Business Search System — semantic search over a 120-business
directory, built as an AI Engineer take-home.

The distinguishing property is not the feature list. It is that **every ranking
decision is gated on a measured evaluation**, and the milestone where the
obvious idea made results *worse* is documented rather than quietly dropped.

---

## Features implemented

| Feature | Summary |
|---|---|
| Semantic search | Query and corpus embedded into a shared 384-dim space; matches on meaning, not tokens. |
| Hybrid search | Atlas vector search + Atlas keyword search run concurrently, fused with Reciprocal Rank Fusion. |
| Tuned hybrid | Score-threshold gating on weak keyword hits, weighted RRF (0.7 semantic / 0.3 keyword), keyword search narrowed to discriminative fields. |
| Cross-encoder reranking | Rescores the fused top-20 by full (query, document) attention. Toggle-able; enabled on evaluation evidence. |
| Dynamic filters | Industry / City / State / Nature / Sub Category, validated against a live DB-derived allow-list. |
| Evaluation framework | 30 golden queries, 6 categories, Precision@K / Recall@K / MRR; the gate for every ranking change. |
| Business registration | `POST /api/businesses` runs new businesses through the same embedding pipeline; searchable in ~1-2s. |
| React interface | Search with keyword highlighting, filters, grouped registration form, full loading / empty / error states, responsive, keyboard-accessible. |

---

## Technologies used

**Backend** — Python 3.11+, FastAPI, Pydantic v2, PyMongo, `uv`.

**Search / ML** — MongoDB Atlas Vector Search (`$vectorSearch`, cosine) and
Atlas Search (`$search`, Lucene); `BAAI/bge-small-en-v1.5` bi-encoder (384-dim,
L2-normalized) and `cross-encoder/ms-marco-MiniLM-L-6-v2` reranker, both local
on CPU — no API keys, no per-query cost.

**Frontend** — React 19, TypeScript, Vite. No UI kit, no state library, no HTTP
client; `fetch` and plain CSS.

---

## Evaluation results

30 golden queries across semantic, keyword-heavy, synonym, multi-intent,
filtered and edge-case categories, with hand-verified relevance judgments.

| System | P@5 | P@10 | R@5 | R@10 | MRR |
|---|---|---|---|---|---|
| Vector-only | 0.560 | 0.303 | 0.946 | 1.000 | **0.958** |
| Previous Hybrid | 0.467 | 0.283 | 0.792 | 0.940 | 0.863 |
| Tuned Hybrid | 0.513 | 0.303 | 0.875 | 1.000 | 0.869 |
| **Hybrid + Cross-Encoder** | **0.560** | **0.303** | **0.946** | **1.000** | 0.929 |

The arc that matters:

1. **Naive hybrid was a regression.** Adding keyword search dropped P@5 from
   0.560 to 0.467. Cause, verified by inspection: Atlas `$search` matching a
   single coincidental token ("computer" in a query about hacking matched an
   AI-vision firm), which rank-based fusion could not discount.
2. **Tuning recovered about half.** P@5 to 0.513, R@10 back to 1.000.
3. **Reranking closed the rest.** P@5 to 0.560 and R@5 to 0.946, both equal to
   vector-only; MRR 0.869 → 0.929. The categories tuning could not fix improved
   as predicted (`synonym` P@5 0.480 → 0.560; `edge_case` MRR 0.722 → 1.000).

**Caveat, stated plainly:** on a corpus this small and templated, vector-only is
already strong, so reranking reaches *parity* rather than beating it everywhere
— vector-only's MRR (0.958) still edges the reranked pipeline (0.929). The win
is having keyword-exact recall and semantic precision simultaneously; a messier
corpus is where that combination would pull clearly ahead.

---

## Performance

| Config | p50 | p95 |
|---|---|---|
| Hybrid (rerank off) | ~58ms | ~800ms |
| Hybrid + cross-encoder | ~463ms | ~830ms |

Filtering is effectively free at this corpus size (~67-72ms regardless).
Embedding: model load ~6.4s, 120 documents ~3.8s (~31 docs/sec), single query
~37ms. Memory: embedder ~135MB, cross-encoder ~92MB / 22.7M params — a
rerank-enabled process holds both, which is the binding constraint on small
hosts.

**These absolute figures are point-in-time and single-machine.** Re-measuring
the identical code later gave ~178ms and ~2135ms — 3-5x higher on both paths,
including the path that never touches the cross-encoder, so it reflects machine
state rather than a regression. The durable finding is relative: **reranking
dominates search latency**, which is exactly why it is a toggle.

---

## Known limitations

1. **No automated test suite.** Correctness rests on the golden-query evaluation
   harness plus live manual QA. The biggest engineering gap.
2. **No authentication or rate limiting.** Every endpoint is public, including
   the write endpoint. Not publicly deployable as-is.
3. **Residual ranking collision.** When a query token matches a business's own
   discriminative field in a *different sense*, and it is the only keyword hit,
   neither field-narrowing nor score-gating helps. Reranking recovers most such
   cases, not all.
4. **Small evaluation set.** 30 queries over 120 documents supports directional
   calls, not tight confidence intervals.
5. **Filtering over-fetches.** `$vectorSearch` truncates internally before
   `$match`, so filtered searches widen the candidate pool to 200. Fine at 120
   documents; needs Atlas native filter fields at scale.
6. **Latency headroom is thin** with reranking on, and the numbers vary by
   machine.
7. **Not deployed; screenshots not captured.** Both documented, neither done.
8. **Responsive layout verified by CSS analysis**, not on real devices.

---

## Future improvements

- Add unit and integration tests — the clearest next investment.
- Auth + rate limiting, prerequisites for any public deployment.
- Query-side sense disambiguation to attack the residual collision at its cause.
- Atlas native filter fields to pre-filter before HNSW traversal.
- Pagination (the API caps at 50 results, no cursor).
- Grow the golden set and add multiple judges to harden every conclusion above.
- Deploy per the guide in the root README.
