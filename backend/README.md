# Backend — M1.1-M1.3 + M2 + M3.1 + M3.2 + M4.1 + M4.1.1 + M4.2 (Atlas, ingestion, embeddings, reranked hybrid search, evaluation)

**M1.1** proved the MongoDB Atlas index configuration works before any real
data or ML code depends on it. **M1.2** added raw ingestion of the actual
120-business dataset. **M1.3** backfills real embeddings onto that data and
adds background model warm-up + a dedicated model health check. **M2** added
`POST /api/search` as vector-only semantic search (naive baseline). **M3.1**
upgraded it to hybrid: Atlas `$vectorSearch` + `$search` fused with
Reciprocal Rank Fusion — same route, same request shape. **M3.2** adds
optional `filters` (industry/city/state/nature/sub_category), validated
against a live, cached DB allow-list — closes the NoSQL-injection-shaped gap
the architecture review flagged. **M4.1** adds a golden-query evaluation
framework (Precision@K, Recall@K, MRR) that found hybrid scoring *below*
vector-only. **M4.1.1** tunes hybrid based on that finding (score-threshold
keyword gating, weighted RRF, narrowed search fields) — recovers roughly
half the gap. **M4.2** adds an optional cross-encoder reranking stage after
hybrid, which the eval shows closes the rest of the gap to vector-only — so
it ships enabled, on that evidence, per design-doc-v2.md's evidence-gating
rule. Same API, same filters, same eval framework throughout. **M5.2** adds
business registration (`POST /api/businesses`), which reuses this embedding
pipeline so a registered business is immediately searchable — see "Business
registration" below. The React frontend lives in `../frontend`.

## Setup

1. **Install dependencies:**
   ```
   cd backend
   uv sync
   ```

2. **Create a free MongoDB Atlas M0 cluster** (no credit card required):
   - Sign up / log in at https://cloud.mongodb.com
   - Create a new Project, then a new Cluster on the **M0 (Free)** tier
   - Database Access -> add a database user with a password
   - Network Access -> add your current IP (or `0.0.0.0/0` for local dev only)
   - Once the cluster is up: Connect -> Drivers -> Python -> copy the connection string

3. **Configure environment:**
   ```
   cp .env.example .env
   ```
   Paste your connection string into `MONGODB_URI`, and set `DB_NAME` (default `business_search` is fine).

4. **Create the two Atlas indexes:**
   ```
   uv run python scripts/create_atlas_indexes.py
   ```
   Reads `scripts/atlas_indexes/*.json`, creates `business_vector_index` (Vector Search)
   and `business_search_index` (Search) via the pymongo driver, and waits until both
   are queryable. Safe to re-run — skips indexes that already exist.

   **Manual fallback** (if you'd rather use the Atlas UI): Atlas Search tab -> Create
   Search Index -> JSON Editor. The JSON Editor only wants the index *definition* —
   Index Name, Database, Collection, and Index Type are separate UI fields, not part
   of the pasted JSON. Select `business_search` / `businesses`, then create Index 1
   (Type = Vector Search, Name = `business_vector_index` — exact name, the app looks
   it up by this string) pasting `vector_index.json`, and Index 2 (Type = Search, Name
   = `business_search_index`) pasting `search_index.json`.

## Seed the dataset + embeddings (M1.2 + M1.3)

Parses `Business_Matchmaking_Test_Dataset_V2_120_Companies.xlsx` (expected at
the repo root, one level above `backend/`), computes a `BAAI/bge-small-en-v1.5`
embedding per business, and inserts all 14 raw fields plus the 384-dim
`embedding` field into the `businesses` collection. Safe to re-run: clears
and reinserts the collection each time, so it always converges on exactly
120 fully-embedded documents.

```
uv run python scripts/seed.py
```

Expected output ends with:
```
Embedded 120 businesses in ~Ns (~X docs/sec, model load included)
PASS: seeded 120 businesses from Business_Matchmaking_Test_Dataset_V2_120_Companies.xlsx
```

First run downloads the model (~130MB) from Hugging Face, so it's slower than
subsequent runs, which reuse the local HF cache.

To seed from a different file path: `uv run python scripts/seed.py path/to/dataset.xlsx`

## Run

Start the API:
```
uv run uvicorn app.main:app --reload
```
Check it's up: `curl http://127.0.0.1:8000/health` -> `{"status":"ok"}`

The models load in background threads on startup, so `/health` is up
instantly regardless of model load state. Poll model readiness:
```
curl http://127.0.0.1:8000/health/model      # embedder (bge-small)
curl http://127.0.0.1:8000/health/reranker   # cross-encoder (M4.2, if RERANK_ENABLED)
```
Each cycles `{"status":"not_started"}` -> `{"status":"loading"}` ->
`{"status":"ready"}` (or `{"status":"error","detail":"..."}` on load
failure). The two are independent — search still works (un-reranked) if the
reranker is down.

Verify the Atlas spike (both indexes actually work end-to-end):
```
uv run python scripts/verify_atlas_spike.py
```
Expected output: `PASS: both $vectorSearch and $search found the test document`

Search (once seeded — see above):
```
curl -X POST http://127.0.0.1:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "GST Expert", "limit": 5}'
```

Register a business (M5.2):
```
curl -X POST http://127.0.0.1:8000/api/businesses \
  -H "Content-Type: application/json" \
  -d '{"business_name":"Acme Cold Chain","industry":"Logistics",
       "nature":"Services","sub_category":"Cold Storage",
       "business_description":"Refrigerated warehousing and last-mile cold delivery.",
       "products_services":"Cold storage, refrigerated transport","city":"Pune","state":"Maharashtra"}'
```

## Business registration (M5.2)

`POST /api/businesses` adds a new business through the same pipeline as the bulk
seed, so it becomes searchable via `/api/search` immediately — no separate
indexing step:

- **Reuses the embedding pipeline** — `app/registration.py` calls the same
  `build_embedding_text()` + `embed_texts()` as `scripts/seed.py`; embeddings
  are produced in exactly one place.
- **Same document shape** as a seeded business (the 14 fields), so search reads
  it back unchanged. The form's optional `address` is stored as an extra field
  (not part of the search projection); `contact_person`/`specialties` aren't
  collected and are stored as `None` for shape uniformity.
- **Filters stay correct** — a successful insert calls
  `invalidate_filter_cache()` (the seam `app/filters.py` was built for), so a
  business registered in a new city/industry/sub_category becomes a valid filter
  value on the next request.
- **Validation** — Pydantic (`BusinessRegistration`) rejects missing required
  fields, and malformed email / website with `422`; a duplicate `business_name`
  (unique index) returns `409`; an embedding-model or DB outage returns `503`.
  Response is `201` with `{id, business_name}`.
- The search API, its request/response contract, and the search pipeline are
  unchanged — registration only adds a schema, `app/registration.py`, and this
  one route.

## Field naming convention

The dataset's 14 xlsx columns map to snake_case document fields: `business_name`,
`nature`, `industry`, `sub_category`, `city`, `state`, `contact_person`, `email`,
`website`, `phone`, `business_description`, `products_services`, `keywords`,
`specialties`. Established in M1.1 (the search index needs concrete field names)
and applied to all 14 fields by M1.2's ingestion script.

## Embedding pipeline (M1.3)

- Model: `BAAI/bge-small-en-v1.5` via `sentence-transformers`, loaded lazily
  as a singleton in `app/embeddings.py` (same double-checked-locking pattern
  as `app/db.py`'s MongoClient). Free, local, no GPU required.
- `embedding_text` = `business_description + products_services + keywords +
  specialties + sub_category`, space-joined. Contact fields (email, phone,
  website, contact_person) are excluded — no semantic signal.
- Vectors are L2-normalized (`normalize_embeddings=True`) — standard BGE
  convention, keeps concatenated-text length from leaking into vector
  magnitude, and stays compatible with `dotProduct` similarity if that's
  ever revisited (today's index uses `cosine`, which is scale-invariant
  regardless).
- Dimension is asserted at model-load time against `EMBEDDING_DIMENSIONS`
  (384) — a model swap that changes output size fails fast instead of
  silently producing vectors Atlas's index will reject.
- Benchmarked on this machine (CPU, warm HF cache): model load ~6.4s,
  encoding 120 business docs ~3.8s (~31 docs/sec), single-query encode
  ~37ms — well under the design doc's <500ms p50 end-to-end search target.
- Live vector search sanity check: querying `$vectorSearch` with a real
  encoded query for "GST Expert" surfaces GST Consultants as the top
  matches (score ~0.86-0.89); "restaurant food packaging" surfaces Food
  Packaging manufacturers — confirms the assignment's own example queries
  work end-to-end with real embeddings, not just the synthetic spike vector
  from M1.1.

## Search API (M2 + M3.1 hybrid + M3.2 filters + M4.1.1 tuning)

`POST /api/search` — hybrid semantic + keyword search with optional filters.
Runs Atlas `$vectorSearch` and Atlas `$search` (on `keywords`, `specialties`,
`products_services` — narrowed from the original 4 fields, see M4.1.1 below)
**concurrently** (2-worker `ThreadPoolExecutor` — pymongo's `MongoClient` is
thread-safe), fuses the two ranked candidate lists with **Weighted**
Reciprocal Rank Fusion (`score = Σ weight/(60 + rank)`, vector weight 0.7 /
keyword weight 0.3, k=60 — see M4.1.1 below for why), and returns the top N.
Same route and request shape as M2's vector-only baseline — extension, not
rewrite. Still no cross-encoder reranking (gated on M4.1's eval showing it
actually helps).

Request:
```json
{"query": "GST Expert", "limit": 10, "filters": {"city": "Mumbai"}}
```
`query`: required, non-blank after stripping whitespace, max 500 chars.
`limit`: optional, default 10, bounded 1-50. Candidate pool per retrieval
source is `max(30, limit * 3)` — design-doc-v2.md's documented "top ~30" at
the default `limit=10`, generalized so a larger `limit` doesn't starve fusion.
`filters`: optional, all 5 fields optional — `industry`, `city`, `state`,
`nature`, `sub_category`. Omit entirely, or omit individual fields, for no
filtering on that dimension.

Response: `{"query": "...", "results": [{...business fields..., "id": "...",
"score": 0.033, "matched_via": "both"}], "filters": {...}}`. `matched_via` is
`"semantic"`, `"keyword"`, or `"both"`. **`score` is the RRF-fused value, not
raw cosine similarity** — small numbers (max ~0.033 if ranked #1 by both
sources). `embedding` is never returned.

Error handling: invalid request body -> 422. A filter value not in the live
allow-list -> 422 with a plain message (e.g. `"invalid value for filter
'city': 'FakeCity' is not a known city"`) — never passed through as a raw
query clause, closing the NoSQL-injection-shaped gap the architecture review
flagged. Embedding model or Atlas unavailable -> 503, never a raw 500.

**`GET /api/filters/values`** — returns the live, cached allow-list per
field: `{"industry": [...], "city": [...], "state": [...], "nature": [...],
"sub_category": [...]}`. Backs the 422 validation above and the frontend
filter dropdowns. Cached in-process, warmed in the background on startup
(same pattern as the embedding model); `app/filters.py` exposes
`invalidate_filter_cache()`, which the M5.2 registration endpoint now calls
after each insert so a newly registered business's field values become valid
filters immediately.

**Why filtering doesn't just bolt a `$match` onto the existing pipeline:**
Atlas's `$vectorSearch` truncates to its own `limit` *inside* the stage,
before any later pipeline stage runs. Filtering the normal ~30-doc candidate
pool after the fact could correctly-but-uselessly return far fewer results
than actually exist, if the matching businesses didn't happen to rank in the
top 30 by similarity alone. Fix: when any filter is active, the candidate
pool widens to 200 (`POOL_SIZE_FILTERED` in `app/search.py`) — safely above
the current 120-doc corpus — before filtering runs. No Atlas index changes
needed. At meaningfully larger corpora, this would need Atlas's native
filter-type index fields (pre-filtering before the HNSW search itself)
instead of over-fetching; explicitly out of scope at this dataset's size.

Benchmarked against the live Atlas cluster (30 requests each, warm model):
unfiltered p50 ~72ms, filtered-by-city p50 ~68ms, filtered-by-2-fields p50
~67ms — filtering costs no meaningful latency at this corpus size, confirming
the pool-widening approach is cheap here.

Verified against the live cluster:
- `GET /api/filters/values` returns the real current values (10 industries,
  10 cities, 9 states, 2 natures, 40 sub-categories) — all 120 documents have
  every one of the 5 filterable fields populated (verified via
  `count_documents` for missing/null), so the allow-list is complete.
- `filters: {"city": "Mumbai"}` -> all 10 returned results are in Mumbai.
- `filters: {"city": "FakeCity"}` -> `422`, exactly per roadmap.md's stated
  test criterion.
- `filters: {"industry": "Finance", "city": "Mumbai"}` (a narrow, real
  combination) -> exactly the 2 matching businesses, both tagged correctly
  — a naturally-occurring rare combination that wasn't truncated, evidence
  the pool-widening fix actually works, not just passes a synthetic test.

Verified against the live cluster:
- "GST Expert" -> all 3 GST Consultants rank first, tagged `matched_via:
  "both"`; the two vector-only false-positive "Coaching Institutes" matches
  (semantically similar, no literal overlap) correctly demote and tag
  `matched_via: "semantic"`.
- "ISO27001 compliance" -> vector-only and keyword-only disagree on result
  order; RRF fusion re-ranks based on combined evidence from both.
- "HNSW indexing vector database" (out-of-domain jargon) -> keyword search
  returns zero hits, hybrid gracefully falls back to semantic-only results
  instead of erroring.

## Tuned Hybrid Search (M4.1.1)

M4.1's eval found hybrid scoring *below* vector-only overall (P@5 0.467 vs
0.560), traced to Atlas `$search` producing coincidental single-token
matches with zero real relevance that RRF's rank-based fusion couldn't
discount. Three tuning changes target this, all in `app/search.py`, all
configurable via module-level constants (documented inline with the
reasoning) and *not* exposed as new request fields — the API, filters, and
eval framework are all unchanged:

1. **Keyword score-threshold gating** (`KEYWORD_SCORE_THRESHOLD_RATIO =
   0.3`) — a keyword hit must score at least 30% of that query's own top
   keyword match to survive into fusion. Atlas's `searchScore` has no
   fixed scale across queries, so the threshold is relative per-query, not
   an absolute cutoff.
2. **Weighted RRF** (`RRF_WEIGHT_VECTOR = 0.7`, `RRF_WEIGHT_KEYWORD =
   0.3`) — vector weighted ~2.3x higher, since M4.1's eval found keyword
   search never contributed a unique win in the golden set while
   repeatedly diluting correct vector rankings with noise.
3. **Narrowed search fields** (`keywords`, `specialties`,
   `products_services` — dropped `business_description`) — the dropped
   field carries near-identical templated boilerplate ("...business
   specializing in...") across all 120 documents, which produced false
   matches like "business trip" -> "business insurance".

All three are reasoned starting points from the M4.1 investigation, not
grid-searched — validated by re-running the same golden eval (below), not
asserted.

**Result — a genuine, partial improvement, reported honestly:**

| System | P@5 | P@10 | R@5 | R@10 | MRR |
|---|---|---|---|---|---|
| Vector-only | 0.560 | 0.303 | 0.946 | 1.000 | 0.958 |
| Previous Hybrid (M3.1/M3.2) | 0.467 | 0.283 | 0.792 | 0.940 | 0.863 |
| Tuned Hybrid (M4.1.1) | 0.513 | 0.303 | 0.875 | 1.000 | 0.869 |

Recovered roughly half the P@5 gap and nearly closed the recall gap (R@10
now ties vector-only). The `synonym` category — worst-hit in M4.1 —
improved the most (P@5 0.280 -> 0.480, R@10 0.800 -> 1.000).

**What's still not fixed, verified by direct inspection, not assumed:**
`edge_case` shows zero improvement, and `semantic`'s MRR actually *dropped*
(0.850 -> 0.717). Traced to `sem-02` ("...business trip", targeting
Hotels): the correct answer fell from rank 1 to rank 3 because **Insurance's
own `keywords` field literally contains "business insurance"** — the
collision lives inside a genuinely discriminative field, not the boilerplate
field-narrowing targeted. Score-threshold gating doesn't catch this either,
because it's the *only* keyword hit for that query — there's no weaker
match to compare it against and discard. Both tuning mechanisms only help
when a stronger match exists to judge a weak one against; neither can fix a
case where the single best available keyword match is itself a same-word,
different-sense coincidence. This residual failure class is exactly what a
cross-encoder reranker (M4.2, not built here) is suited for — it judges
full semantic relevance, not token overlap — and is the concrete evidence
design-doc-v2.md's evidence-gating rule requires before shipping it.

Full report with per-category breakdown: `eval_reports/report_*.md` (run
`uv run python scripts/eval.py` to regenerate).

## Cross-Encoder Reranking (M4.2)

M4.1.1 left a residual failure class it couldn't fix at the retrieval
layer: a query and a business sharing a surface token in *different senses*
(e.g. "business trip" colliding with "business insurance"), where that
collision is the only keyword match available. M4.2 adds an optional
cross-encoder reranking stage after hybrid to fix exactly that.

**How it works.** A bi-encoder (the `bge-small` embedder) encodes query and
document separately into vectors and compares by distance — it can't tell
apart two different senses of the same token. A cross-encoder
(`cross-encoder/ms-marco-MiniLM-L-6-v2`, ~92MB, 22.7M params) instead runs
full attention over the concatenated `(query, document)` pair and outputs a
relevance score, so it reads "business trip" and "business insurance" as the
different things they are. After hybrid fusion, the fused **top-20**
(`RERANK_TOP_N`) are rescored by the cross-encoder and re-sorted, then the
top-`limit` is returned. Reranking a pool *wider* than the final limit is
the point: a business hybrid ranked #15 can climb into the top-10 if it's
genuinely more relevant — reranking only the already-cut top-10 could never
recover it.

**The hybrid pipeline is untouched.** `_vector_search`, `_keyword_search`,
and `_reciprocal_rank_fusion` are byte-for-byte unchanged; reranking is a
strictly additive stage layered on top of their output (`app/reranker.py`).

**Configurable.** `RERANK_ENABLED` in `app/search.py` (also settable via the
`RERANK_ENABLED` env var) toggles it; `search_businesses(..., rerank=...)`
overrides per call (that's how the eval measures hybrid vs hybrid+rerank).
The reranker loads as a lazy singleton with independent background warm-up
and its own health endpoint, `GET /health/reranker` — separate from
`/health/model` (the embedder), which is unchanged. When rerank is disabled,
the reranker never loads, so a rerank-off deployment pays none of its cost.

**Graceful degradation, not a hard dependency.** If the cross-encoder fails
to load or infer, search returns the un-reranked (still-good) hybrid results
rather than erroring — reranking is a quality layer, and design-doc-v2.md
calls for reranker failure to mean "search degrades, not a crash." Persistent
failures stay visible via `/health/reranker`.

**API contract preserved.** Same route, same request/response shape. `score`
becomes the cross-encoder relevance score when reranking is on (MS MARCO
logits, unbounded — can exceed 1; still a `float`, same field). `matched_via`
is carried through from fusion unchanged.

**Quality — reranking clears the evidence gate** (full 4-way eval, live
Atlas):

| System | P@5 | P@10 | R@5 | R@10 | MRR |
|---|---|---|---|---|---|
| Vector-only | 0.560 | 0.303 | 0.946 | 1.000 | 0.958 |
| Previous Hybrid (M3.1/M3.2) | 0.467 | 0.283 | 0.792 | 0.940 | 0.863 |
| Tuned Hybrid (M4.1.1) | 0.513 | 0.303 | 0.875 | 1.000 | 0.869 |
| **Hybrid + Cross-Encoder (M4.2)** | **0.560** | **0.303** | **0.946** | **1.000** | **0.929** |

Reranking closes the rest of the gap: P@5 0.513 → 0.560 and R@5 0.875 →
0.946 (both now equal vector-only), MRR 0.869 → 0.929. The two categories
tuning couldn't fix improve exactly as predicted — `synonym` P@5 0.480 →
0.560, `edge_case` P@5 0.240 → 0.360 / MRR 0.722 → 1.000. Verified live:
"computer hacking..." now ranks the 3 Cybersecurity businesses first (was AI
Solutions), and "...business trip" ranks Hotels first (was Insurance).

**Honest caveat.** On this small, clean, templated 120-doc set vector-only
is already very strong, so reranking brings hybrid *to parity* with it on
P@5/R@5/R@10 rather than strictly beating it everywhere (vector-only's MRR
0.958 still edges rerank's 0.929). The win is that hybrid+rerank gets
keyword-exact recall (which pure vector search lacks) *and* semantic
precision together; on a messier real-world corpus that combination is where
it would pull clearly ahead. Reranking *does* measurably beat the best
non-reranked system (precision@5 0.513 → 0.560), which is the specific bar
design-doc-v2.md set for shipping it — hence `RERANK_ENABLED` defaults on.

**Latency cost** (benchmarked on this machine, CPU, warm models, live Atlas):

| Config | p50 | p95 |
|---|---|---|
| Hybrid (rerank off) | ~58ms | ~800ms |
| Hybrid + rerank | ~463ms | ~830ms |

Reranking adds **~+405ms p50** — the cost of running the cross-encoder over
~20 `(query, document)` pairs per query on CPU. That lands just under the
design doc's <500ms p50 target, but with little headroom; on a latency-
sensitive deployment `RERANK_ENABLED=false` gives back the tuned-hybrid
numbers instantly. (The ~800ms p95 on both rows is occasional
cold-cache/Atlas-roundtrip noise, not reranking — it's present with rerank
off too.)

**Memory.** Cross-encoder: ~92MB on disk, 22.7M params (~90MB of float32
weights resident, plus PyTorch overhead). Cold load ~8.5s. This is *in
addition* to the embedder (`bge-small`, ~135MB on disk) — so a
rerank-enabled process holds both models. Relevant for the M5 deploy target:
Render's free 512MB tier would be tight with both loaded, which is partly
why reranking is toggle-able.

## Evaluation Framework (M4.1)

Golden-query evaluation harness comparing search systems on real,
verified relevance judgments — the evidence M4.2's reranking decision
(and any future ranking change) should be gated on, not an assertion.

**Run it:**
```
uv run python scripts/eval.py
```
Requires a seeded, embedded DB (M1.2/M1.3) and both Atlas indexes queryable
(M1.1) — same prerequisites as the app itself. Prints a full report to the
console and writes a timestamped copy to `eval_reports/report_<UTC
timestamp>.md`. Takes a few seconds (mostly model load, cached after the
first request).

**The golden dataset** (`scripts/eval_dataset.py`): 30 hand-labeled queries
across the 6 categories required for M4.1 — `semantic`, `keyword`,
`synonym`, `multi_intent`, `filtered`, `edge_case` (5 each). Every expected
relevant business was verified against the live dataset before being
written down, not guessed: the 120-business corpus is exactly 3 businesses
per sub-category (40 x 3), so "all 3 businesses in sub-category X" is a
clean, defensible ground truth for any query targeting that category.
Multi-intent queries expect the union of two categories; filtered queries
expect the intersection of a category and a real city/industry value
pulled from the live DB; two edge cases expect zero relevant results
(verified empty, not assumed) to exercise the framework's handling of
that case.

**Metrics** (`scripts/eval.py`): Precision@5, Precision@10, Recall@5,
Recall@10, MRR@10. Recall and MRR are `None` (not `0.0`) for the two
zero-relevant edge cases — mathematically undefined (0/0), not a failure
— and excluded from every average rather than silently counted as zero.

**Systems compared** (4-way): `vector-only` (M2's baseline),
`hybrid-previous` (M3.1/M3.2's original unweighted/unfiltered/4-field
config, kept only for comparison), `hybrid-tuned` (M4.1.1's tuning, rerank
off), and `hybrid-rerank` (M4.2: tuned hybrid + cross-encoder, what the
live API runs when `RERANK_ENABLED`). All four apply filters identically for
a fair comparison, and all four reuse `app.search`'s actual retrieval
internals directly (`_vector_search`, `_keyword_search`,
`_reciprocal_rank_fusion`, `rerank_candidates`, `search_businesses`) — no
duplicated retrieval logic between the live API and the eval harness. The
`rerank` toggle on `search_businesses()` is what lets the eval force
reranking on/off per system without a separate code path.

**Extensible:** a "system" is just
`Callable[[str, int, dict | None], list[dict]]` returning ranked results
with a `business_name` key (see `SYSTEMS` in `scripts/eval.py`). Each new
milestone's variant (M4.1.1's tuned, M4.2's reranked) was one more function
of that signature plus one line in `SYSTEMS` — nothing below the SYSTEMS
section (metrics, runner, report) has had to change.

**Findings from this run:** see "Tuned Hybrid Search (M4.1.1)" above for
the full before/after comparison table and honest accounting of what
tuning fixed and what it didn't. Full per-category breakdown and analysis
in the generated report (`eval_reports/report_*.md`).

## Notes

- Embedding dimensionality (384) is defined once in `app/constants.py`. The
  Atlas vector index's `numDimensions` in `scripts/atlas_indexes/vector_index.json`
  can't import that constant (it's plain JSON) — keep them in sync by hand if
  the embedding model ever changes.
- `verify_atlas_spike.py` retries each index query briefly before failing, since
  Atlas Search/Vector Search indexes update asynchronously after a write — an
  immediate query can miss a just-inserted document even with a correctly
  configured index.
- Common first-run failure: `bad auth : Authentication failed` usually means the
  connection string's username is still the literal `<db_username>` placeholder
  from Atlas's template — check Database Access in the Atlas UI for the actual
  username and swap it in.
