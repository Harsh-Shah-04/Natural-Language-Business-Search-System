# Implementation Roadmap — Natural Language Business Search System

Source of truth: `design-doc-v2.md`. No code written. 5 phases, 15 milestones, each <1 day, each independently compilable/runnable/testable.

## Dependency graph

```
PHASE 1 (Data Foundation, backend-only)
  M1.1 Atlas+FastAPI spike ──┐
  M1.2 Raw ingestion ────────┼──> M1.3 Ingestion + embeddings
                              │
PHASE 2 (Core Search)         │
  M1.3 ──> M2.1 Read CRUD      │
  M1.3 + M1.1 ──> M2.2 Vector-only search ──> M2.3 React search page
                              │
PHASE 3 (Ranking Quality + Registration)
  M2.2 + M1.1(search idx) ──> M3.1 Hybrid+RRF
  M3.1 + M2.1 ──> M3.2 Filters (live allow-list)
  M1.3 + M3.2 ──> M3.3 POST /businesses (registration)
  M3.3 + M2.3 ──> M3.4 React registration + empty/error states
                              │
PHASE 4 (Ranking Evidence + Hardening)
  M3.1 ──> M4.1 Golden eval harness ──> M4.2 Cross-encoder rerank (gated)
  M4.2 ──> M4.3 Warm-up/health checks + README/docker-compose
                              │
PHASE 5 (Stretch — Deployment)
  M4.3 ──> M5.1 Deploy (Vercel + Render/Railway)
```

Each milestone in Phase N+1 extends what Phase N built — nothing is thrown away and rebuilt. The one place that looks like "rework" (M2.2's vector-only search becoming M3.1's hybrid search) is additive: the endpoint contract and every caller stay identical, only the internal ranking logic gains a fusion step.

---

## PHASE 1 — Data Foundation
**End state: a running FastAPI service, backed by a MongoDB Atlas cluster populated with 120 embedded businesses, fully verifiable via curl/Mongo shell. No UI yet — this phase's "working application" is a working backend service.**

| # | Milestone | Compiles & runs | Independently testable | Effort |
|---|---|---|---|---|
| M1.1 | Atlas + FastAPI spike: create free M0 cluster, define the two indexes (`vectorSearch` on `embedding`, `search` on the 4 text fields), FastAPI skeleton with `/health`. Insert one hand-embedded test doc; confirm both a `$vectorSearch` and a `$search` query return it. | `uvicorn` starts, `/health` returns 200 | `curl /health`; manual Mongo shell query returns the test doc via both index types | ~0.5 day |
| M1.2 | Ingestion script (raw): parse the provided `.xlsx`, insert all 14 fields per business into MongoDB — **no embeddings yet**, isolates data-pipeline bugs from ML bugs | `python scripts/seed.py` inserts 120 docs | `db.businesses.countDocuments() == 120`; no duplicate `Business Name` (already verified against the raw file, script now proves the pipeline does it too) | ~0.5 day |
| M1.3 | Extend M1.2's script: load `BAAI/bge-small-en-v1.5`, compute `embedding_text` per business, backfill the `embedding` field. Add background model warm-up + `/health/model` to the M1.1 FastAPI skeleton. | Re-run seed script, all 120 docs have a 384-dim `embedding` array; `/health/model` flips loading→ready | Spot-check vector length == 384; poll `/health/model` after startup | ~1 day |

**Risks:** Atlas index JSON syntax is new — front-loaded into M1.1 specifically so a wrong index definition is cheap to fix on day 1, not discovered mid-Phase-3. Model download/warm-up timing (bge-small ≈130MB, should be seconds) — low risk, but M1.3's dedicated health check exists precisely to catch this before it becomes an invisible startup hang later.

---

## PHASE 2 — Core Search
**End state: open a React page, type a natural-language query, see real ranked results from the live backend using Atlas Vector Search. First true end-to-end demo, using the actual recommended architecture (not a mock).**

| # | Milestone | Compiles & runs | Independently testable | Effort |
|---|---|---|---|---|
| M2.1 | `GET /api/businesses` (paginated list) + `GET /api/businesses/:id` | Endpoint serves real data from Mongo | `curl` returns 120 businesses paginated; unknown `:id` returns 404 | ~0.5 day |
| M2.2 | `POST /api/search` — **vector-only** (Atlas `$vectorSearch`, top-10 by cosine similarity). Explicitly the naive baseline the design doc says isn't sufficient alone — a deliberate stepping stone, not the final endpoint. | Endpoint returns ranked results for any query | Query "GST Expert" returns *something*; informal relevance check (hybrid arrives in Phase 3) | ~0.5 day |
| M2.3 | Minimal React search page: input box + results list, wired to M2.2 | `npm run dev` serves a working page | Manual e2e: type "restaurant packaging" → see results rendered from the live API | ~1 day |

**Risks:** CORS between the React dev server and FastAPI — common, cheap, worth calling out so it doesn't eat unplanned time. Vector-only relevance will visibly miss some of the assignment's own example queries at this stage — expected and by design (Premise 1 from the design doc), not a bug to chase in Phase 2.

---

## PHASE 3 — Ranking Quality + Registration
**End state: the assignment's full stated scope is met — register a business via the UI, search it with hybrid semantic+keyword ranking and filters, and get correct results on the assignment's own example queries. A legitimately submittable version.**

| # | Milestone | Compiles & runs | Independently testable | Effort |
|---|---|---|---|---|
| M3.1 | Upgrade M2.2's search internals: add Atlas `$search` + Reciprocal Rank Fusion. **Same endpoint contract as M2.2** — extension, not rewrite. | Same `/api/search` route, now hybrid-fused results | Re-run the assignment's own examples ("GST Expert" → Chartered Accountant, etc.) and confirm literal-term-adjacent matches now surface | ~1 day |
| M3.2 | City/Industry filters — allow-list derived from live DB values (cached), wired into `/api/search` + a new `GET /api/filters/values`, plus dropdowns in the React page | Filter dropdowns populate live; selecting one narrows results | Filter by a known city, confirm scoping; submit a value NOT in the allow-list, confirm 422 (closes the injection-shaped gap from the eng review) | ~1 day |
| M3.3 | `POST /api/businesses` — validation, duplicate check (409), synchronous embedding, insert | Endpoint accepts valid payloads, rejects bad ones correctly | **Highest-integration-risk milestone in the roadmap:** register a business in a brand-new city → confirm it appears in `GET /api/businesses` immediately → confirm it appears in the filter allow-list within the cache refresh window (M3.2's dependency) → confirm it's findable via `/api/search` | ~1 day |
| M3.4 | React registration form (wired to M3.3) + empty-state/error-state UI for search | Form submits with visible success/error states | Submit invalid form → see field-level error; submit valid form → immediately search for it (the literal assignment requirement) | ~0.5 day |

**Risks:** M3.3 is called out explicitly because it's where three separately-built pieces (embedding pipeline, filter allow-list, hybrid search) intersect for the first time — budget the full day even though each piece individually is simple. Near-real-time Atlas index lag (registered business searchable within ~1 second, not instantly) — the design doc's mitigation (confirm registration via plain `GET`, not search) is what M3.4's success state validates.

---

## PHASE 4 — Ranking Evidence + Hardening
**End state: the full V2 architecture as designed — hybrid search with a *measured* (not asserted) reranking decision, resilient dual-model loading, and a clean 10-minute onboarding. This is the version that goes in front of an interviewer.**

| # | Milestone | Compiles & runs | Independently testable | Effort |
|---|---|---|---|---|
| M4.1 | Golden eval harness: 30-40 hand-labeled queries + expected business IDs, `scripts/eval.py` computing precision@5 (vector-only vs hybrid) | `python scripts/eval.py` prints a table | The numbers themselves are the test — deterministic against the fixed dataset | ~1 day (mostly labeling, not coding) |
| M4.2 | Cross-encoder rerank behind a flag; extend `eval.py` to add a third column (hybrid+rerank). **Ship rerank only if the eval shows it helps** — per the design doc's evidence-gating decision. | Eval script reports 3 numbers; search behavior reflects whichever the numbers justify | Eval table is the test; also confirm `<500ms p50` latency holds with rerank on | ~0.5 day |
| M4.3 | Background warm-up + independent health checks for both models (embedder + reranker); duplicate-registration UX polish; README + `docker-compose` | Fresh clone → `docker-compose up` → seed → working app, <10 min | Literally follow the README on a clean checkout — the design doc's own success criterion | ~1 day |

**Risks:** M4.1's bottleneck is human judgment (writing good eval queries), not engineering — flagged so it isn't scheduled like a coding task. M4.2 has an unusual "risk": the eval might show reranking doesn't help, meaning the "fix" is cutting a feature you already built — a good outcome per the design doc, not a failure to plan around. M4.3's environment-drift risk (works on dev machine, breaks on fresh clone) is the single most common last-mile failure — hence a dedicated milestone instead of an afterthought.

---

## PHASE 5 — Deployment (stretch, optional)
**End state: same application, reachable on a public URL. Atlas is already cloud-hosted, so this is env-var/CORS wiring, not a data-layer change.**

| # | Milestone | Compiles & runs | Independently testable | Effort |
|---|---|---|---|---|
| M5.1 | Deploy frontend (Vercel) + backend (Render/Railway); wire env vars and CORS | Public URL serves the same app | Re-run M4.3's exact test suite against the public URL instead of localhost | ~0.5 day |

**Risk:** CORS/env-var misconfiguration between the two hosts — common and cheap to fix, but budget for one iteration.

---

## Risk register (cross-cutting, not tied to a single milestone)

| Risk | First surfaces | Mitigation already in the roadmap |
|---|---|---|
| Atlas index config wrong | M1.1 | Validated in isolation on day 1, before any app code depends on it |
| Embedding/filter/search integration bugs | M3.3 | Full day budgeted specifically because 3 independent pieces meet here first |
| Reranking doesn't earn its complexity | M4.2 | Evidence-gated by design — "cut it" is a valid, planned outcome |
| Works locally, breaks on fresh clone | M4.3 | Dedicated milestone, tested by literally following the README |
| Index near-real-time lag visible in demo | M3.3/M3.4 | UX mitigation (confirm via plain GET) built into the milestone, not bolted on after |

## Total: 15 milestones, ~10.5 days effort, 4 required phases + 1 optional. Every phase boundary is a working, demoable application — not just a passing test suite.
