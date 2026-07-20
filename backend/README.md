# Backend — M1.1-M1.3 + M2 (Atlas spike, ingestion, embeddings, search API)

**M1.1** proved the MongoDB Atlas index configuration works before any real
data or ML code depends on it. **M1.2** added raw ingestion of the actual
120-business dataset. **M1.3** backfills real embeddings onto that data and
adds background model warm-up + a dedicated model health check. **M2** adds
`POST /api/search` — vector-only semantic search (naive baseline; hybrid
search + RRF + reranking are M3.1/M4.2, not implemented here).

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

## Search API (M2)

`POST /api/search` — vector-only semantic search, the naive baseline per
design-doc-v2.md. No keyword search, RRF, or reranking yet (M3.1/M4.2).

Request:
```json
{"query": "GST Expert", "limit": 10}
```
`query`: required, non-blank after stripping whitespace, max 500 chars.
`limit`: optional, default 10, bounded 1-50.

Response: `{"query": "...", "results": [{...business fields..., "id": "...", "score": 0.89}]}`.
`embedding` is never returned to the client. `score` is Atlas's `vectorSearchScore`
(cosine similarity, since vectors are normalized and the index uses `cosine`).

Error handling: invalid request body -> 422 (FastAPI/Pydantic). Embedding
model or Atlas unavailable -> 503 with a plain-language `detail` message
(never a raw 500 or leaked internals — `app/search.py`'s `SearchUnavailableError`
wraps both the embed-model-load path and the Mongo query path, including
`get_db()` failing before a query is even attempted).

`numCandidates` for `$vectorSearch` is `max(limit * 10, 100)` — standard Atlas
guidance is 10-20x `limit` for good recall; at this corpus size (120 docs)
that comfortably covers the whole collection regardless of `limit`.

Benchmarked against the live Atlas cluster (30 requests, warm model, real
HTTP + embed + Atlas roundtrip): **p50 ~60ms, p95 ~82ms, mean ~68ms** — well
under the design doc's <500ms p50 target for the eventual full hybrid+rerank
pipeline.

Verified against real queries: "GST Expert" -> GST Consultants top 3
(score ~0.86-0.89); "website design and development" -> Software
Development/Digital Marketing firms; "restaurant food packaging" -> Food
Packaging manufacturers.

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
