# Backend — M1.1-M1.3 + M2 + M3.1 (Atlas, ingestion, embeddings, hybrid search)

**M1.1** proved the MongoDB Atlas index configuration works before any real
data or ML code depends on it. **M1.2** added raw ingestion of the actual
120-business dataset. **M1.3** backfills real embeddings onto that data and
adds background model warm-up + a dedicated model health check. **M2** added
`POST /api/search` as vector-only semantic search (naive baseline). **M3.1**
upgrades it to hybrid: Atlas `$vectorSearch` + `$search` fused with
Reciprocal Rank Fusion — same route, same request shape. Cross-encoder
reranking is still deferred (M4.2, gated on M4.1's eval showing it helps);
`filters` are still deferred (M3.2).

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

The embedding model loads in a background thread on startup, so `/health`
is up instantly regardless of model load state. Poll model readiness:
```
curl http://127.0.0.1:8000/health/model
```
Cycles `{"status":"not_started"}` -> `{"status":"loading"}` -> `{"status":"ready"}`
(or `{"status":"error","detail":"..."}` if the model fails to load).

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

## Search API (M2 + M3.1 hybrid)

`POST /api/search` — hybrid semantic + keyword search. Runs Atlas
`$vectorSearch` and Atlas `$search` (on `business_description`,
`products_services`, `keywords`, `specialties`) **concurrently** (2-worker
`ThreadPoolExecutor` — pymongo's `MongoClient` is thread-safe), fuses the two
ranked candidate lists with Reciprocal Rank Fusion (`score = Σ 1/(60 + rank)`,
k=60 — standard IR-literature default, used as-is per design-doc-v2.md), and
returns the top N. Same route and request shape as M2's vector-only baseline
— extension, not rewrite. Still no `filters` param (M3.2) and no
cross-encoder reranking (gated on M4.1's eval showing it actually helps).

Request: unchanged from M2.
```json
{"query": "GST Expert", "limit": 10}
```
`query`: required, non-blank after stripping whitespace, max 500 chars.
`limit`: optional, default 10, bounded 1-50. Candidate pool per retrieval
source is `max(30, limit * 3)` — design-doc-v2.md's documented "top ~30" at
the default `limit=10`, generalized so a larger `limit` doesn't starve fusion.

Response: `{"query": "...", "results": [{...business fields..., "id": "...",
"score": 0.033, "matched_via": "both"}]}`. `matched_via` is `"semantic"`,
`"keyword"`, or `"both"`. **`score` is now the RRF-fused value, not raw
cosine similarity** — small numbers (max ~0.033 if ranked #1 by both
sources), not M2's ~0.7-0.9 range. `embedding` is never returned.

Error handling: unchanged from M2 — invalid request body -> 422; embedding
model or Atlas unavailable -> 503 with a plain-language `detail` message,
never a raw 500 or leaked internals.

Benchmarked against the live Atlas cluster (30 requests, warm model, real
HTTP + parallel embed/Atlas roundtrip): **p50 ~62ms, p95 ~80ms, mean ~71ms**
— nearly identical to M2's vector-only baseline (p50 ~60ms), confirming the
parallel retrieval didn't cost meaningful latency. Well under the design
doc's <500ms p50 target for the eventual hybrid+rerank pipeline.

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
