# Meeting Study Brief — Natural Language Business Search System

**Purpose:** Paste this whole file into ChatGPT (or read it yourself) to understand every decision, every alternative rejected, every milestone, and how each piece maps to the assignment criteria: **Embeddings, Vector databases, Semantic Search, NLP, Ranking**.

**Honesty rule for the interview:** You used AI assistance for implementation speed. What you must own in the meeting is *why* each architecture choice exists, what failed in eval, and what you would change at scale. This brief is written so you can defend that.

---

## 1. Assignment motive (what they are grading)

| Criterion | What they want to see | What you built |
|---|---|---|
| **Embeddings** | Text → vectors; same space for query and documents | Local bi-encoder `bge-small-en-v1.5`, 384-dim, L2-normalized |
| **Vector databases** | Real ANN / vector index, not only in-memory toy | MongoDB Atlas Vector Search (`$vectorSearch`, cosine, HNSW under the hood) |
| **Semantic Search** | Match meaning when words don’t overlap | Vector path finds “Cybersecurity” for “computer hacking defense” |
| **NLP** | Language understanding beyond string equality | Sentence embeddings + cross-encoder that reads full (query, doc) pairs |
| **Ranking** | Not raw cosine dump — a deliberate ranking pipeline | Hybrid retrieve → weighted RRF → cross-encoder rerank, gated by eval |

**Product requirement:** Businesses register via form → auto-embedded → searchable with natural language (not keyword-only).

**Example queries that define success:**
- “GST Expert” → Chartered Accountant (no shared literal phrase required)
- “someone who can help restaurants with packaging” → Food packaging firms

---

## 2. Problem framing (premises you accepted before coding)

1. **Vector-only will miss literal / near-literal queries** → hybrid (vector + keyword) is required.
2. **“Ranking” is a named grade** → raw top-k cosine is the baseline, not the final answer.
3. **120 rows is small** → don’t pretend you need 10M-scale infra; *do* say what changes at scale.
4. **Embeddings must be free/local** → no OpenAI/Voyage paid API for the take-home.
5. **New registrations must be searchable soon** → embed on write (sync), same pipeline as seed.

---

## 3. High-level architecture (one paragraph)

React UI talks to a FastAPI backend. On search, the backend embeds the query with a local sentence-transformer, runs **Atlas vector search** and **Atlas keyword search** in parallel, fuses ranks with **weighted Reciprocal Rank Fusion**, then **reranks the top ~20** with a local cross-encoder. On register, Pydantic validates the form, the same embedding text builder + embedder run, document is inserted into MongoDB Atlas, filter cache invalidates, and after Atlas index sync (~1–2s) the business is searchable.

```
User → React (Vite/TS)
        → FastAPI
            → embed query (bge-small)
            → parallel: $vectorSearch + $search
            → weighted RRF (0.7 vector / 0.3 keyword)
            → cross-encoder rerank (top-20)
            → top-N results + matched_via tags
```

---

## 4. Decision log — WHY this, WHY NOT that

### 4.1 Storage / vector DB: Atlas Vector Search vs Qdrant vs FAISS-in-process

| Option | Idea | Why rejected / accepted |
|---|---|---|
| **A — MongoDB Atlas Vector Search (CHOSEN)** | One Atlas cluster holds documents + vector index + keyword index | Matches required DB; no dual-write; free M0; same URI for local demo and any future deploy; directly shows “vector databases” |
| **B — MongoDB + self-hosted Qdrant** | Mongo = source of truth; Qdrant = vectors | Textbook pattern, but dual-write consistency for 120 rows wastes time; more moving parts in a live demo |
| **C — Mongo + NumPy/FAISS in RAM** | Load 120×384 floats in process; brute-force cosine | Fastest & honest at this scale (~180KB), but skips the graded “vector databases” line; weak “what at 50k?” story (you’d migrate later) |

**Talking point (own the tension):**  
“At 120 rows a dedicated vector DB is overkill technically. I still used Atlas Vector Search because MongoDB was required, M0 is free, and I get a real HNSW vector index without a second service. At 10k–100k I wouldn’t change the architecture — Atlas already scales; I’d change ingestion (bulkWrite, async embed queue), not the retrieval idea.”

---

### 4.2 Backend: FastAPI vs Node

| Choice | Why |
|---|---|
| **FastAPI (CHOSEN)** | Embeddings and cross-encoder run via Python `sentence-transformers`. One language = no Node→Python inference hop |
| Node | Fine for CRUD UI APIs; awkward for local ML without a second Python service |

---

### 4.3 Frontend: React + Vite + TypeScript (minimal stack)

| Choice | Why |
|---|---|
| React + Vite | Assignment expects a web UI; Vite is fast for demo |
| TypeScript | Catches API shape mistakes |
| No UI kit / Redux / axios | Keep focus on search quality; `fetch` + CSS enough |

---

### 4.4 Embedding model: bge-small vs e5-small vs OpenAI

| Model | Why not / why yes |
|---|---|
| **BAAI/bge-small-en-v1.5 (CHOSEN)** | 384-dim, strong MTEB for size, CPU-friendly, **no** mandatory `query:`/`passage:` prefixes |
| intfloat/e5-small-v2 | Similar quality but prefix convention — forget it and quality silently dies |
| OpenAI text-embedding-3-* | Better sometimes, but paid API keys / quota — out of take-home constraints |
| Larger bge / LLM embeddings | Overkill latency/RAM for 120 docs |

**How embedding text is built (NLP decision):**  
Concatenate only semantic fields:

`Business Description + Products/Services + Keywords + Specialties + Sub Category`

**Excluded:** Contact Person, Email, Phone, Website — no semantic signal; noise.  
**Also not stuffed into vectors as primary signal:** City/Industry as repeated category labels can dilute meaning — those are **filters**, not embedding bulk.

---

### 4.5 Bi-encoder vs Cross-encoder (two different NLP roles)

| Role | Model | What it does | Cost |
|---|---|---|---|
| **Retrieve (bi-encoder)** | bge-small | Encodes query and docs *separately* into vectors; fast ANN lookup | ~ms per query encode |
| **Rerank (cross-encoder)** | ms-marco-MiniLM-L-6-v2 | Reads full `(query, document)` together with attention | Slow → only on top ~20 |

**Why not cross-encoder over all 120?** Too slow for interactive search; retrieve-then-rerank is standard IR practice.

**Why not only bi-encoder?** Fast but coarse; fails some sense-collision cases (token “computer” matching wrong industry).

---

### 4.6 Semantic-only vs Hybrid (vector + keyword)

| Approach | Result |
|---|---|
| Vector-only | Strong semantic (P@5 0.560, MRR 0.958) but weaker on literal keyword needs |
| Keyword-only | Fails paraphrases (“defend against hacking” ≠ “cybersecurity”) |
| **Hybrid (CHOSEN)** | Assignment examples need both meaning and exact-ish terms |

Industry backing: embeddings + BM25-style keyword usually beats either alone (contextual retrieval literature).

---

### 4.7 Fusion: RRF vs averaging scores

| Method | Why |
|---|---|
| **Weighted RRF (CHOSEN)** | `score = Σ weight / (60 + rank)`. Rank-based → **scale-free**. Vector cosine and Lucene `searchScore` are incomparable — averaging them is wrong |
| Average / weighted sum of raw scores | Simpler but mixes incompatible numeric scales |
| Atlas `$rankFusion` | Valid alternative; RRF is portable and easy to explain |

**k=60:** Standard IR default from the RRF paper / industry practice — **not** re-tuned for 120 docs. Say that honestly.

**Weights:** vector **0.7**, keyword **0.3** — chosen after naive equal hybrid *hurt* quality (see eval story).

---

### 4.8 Tuned hybrid (the most important story for Ranking)

**What happened:**
1. Vector-only: P@5 = **0.560**
2. Naive hybrid (add keyword + plain RRF): P@5 fell to **0.467** ← regression
3. Root cause (inspected): query “computer hacking defense” — keyword hit an AI firm on the single token “computer”
4. Fixes:
   - Narrow `$search` fields to discriminative ones (`keywords`, `specialties`, `products_services`) — not long boilerplate `business_description`
   - **Score-gate** weak keyword hits (must be ≥ ~30% of that query’s top keyword score)
   - Weight RRF toward semantics (0.7 / 0.3)
5. Tuned hybrid: P@5 = **0.513** (partial recovery)

**Say in meeting:**  
“I didn’t assume hybrid is always better. Eval showed naive hybrid was worse. I diagnosed a token collision, tuned retrieval, then added reranking only after measuring again.”

---

### 4.9 Cross-encoder reranking — evidence-gated

| Decision | Detail |
|---|---|
| Candidate pool | Rerank fused top **20** (wider than final 10 so #15 can promote) |
| Ship rule | Only if eval improves vs best non-reranked system |
| Outcome | P@5 0.513 → **0.560**, R@5 0.875 → **0.946**, MRR 0.869 → **0.929** |
| Toggle | `RERANK_ENABLED` — latency ~+400ms p50; ~92MB extra RAM |
| Failure mode | If reranker down → degrade to hybrid results, don’t crash |

**Honest caveat:** On this clean 120-doc set, vector-only MRR (0.958) still slightly beats hybrid+rerank MRR (0.929). Hybrid+rerank wins the *product* goal: keyword recall **and** semantic precision together. On messier real data that combo usually pulls ahead more clearly.

---

### 4.10 Indexes: two Atlas indexes (vector + search)

| Index | Operator | Purpose |
|---|---|---|
| Vector index on `embedding` (384, cosine) | `$vectorSearch` | Semantic ANN |
| Search index (Lucene) on text fields | `$search` | Keyword / BM25-style |

**Why two?** Different query operators and field configs. Day-1 spike verified both work before FastAPI/React depended on them.

**Why not Mongo `$text` only?** Weaker relevance tooling; Atlas Search is the native full-text path once Atlas is chosen.

---

### 4.11 Filters: live allow-list vs free-form pass-through

| Choice | Why |
|---|---|
| **Allow-list from live DB (CHOSEN)** | Unknown `city=Atlantis` → **422**, never injected into Mongo query |
| Static allow-list at seed time | Breaks when user registers a new city |
| Free-form filters | NoSQL-injection-shaped risk; silent empty results |

Cache invalidated on successful registration so new values appear quickly.

---

### 4.12 Registration design

| Decision | Why |
|---|---|
| Same `build_embedding_text` + `embed_texts` as seed | One quality path — no “UI businesses rank differently” |
| Sync embed on `POST /api/businesses` | Immediately searchable after Atlas near-real-time index sync (~1–2s) |
| Unique Business Name → 409 | Dataset verified unique; prevents duplicates |
| Pydantic required fields | Empty profile has nothing meaningful to embed |
| No auth (deliberate) | Out of assignment scope; document as known limitation |

---

### 4.13 Model warm-up + health endpoints

| Decision | Why |
|---|---|
| Background thread warm-up | First user request must not pay ~6–8s model load |
| Separate `/health`, `/health/model`, `/health/reranker` | API can be up while models still loading; isolate failures |

---

### 4.14 Eval harness before claiming ranking quality

| Decision | Why |
|---|---|
| ~30 golden queries, 6 categories | Enough that one lucky flip doesn’t dominate P@5 |
| Metrics: P@K, R@K, MRR | Standard IR; comparable across vector / hybrid / rerank |
| Gate features on numbers | Prevents cargo-cult “add rerank because blogs say so” |

---

### 4.15 What you deliberately did NOT build

| Skip | Reason |
|---|---|
| Auth / rate limits | Not required; stated limitation |
| Full unit/integration test suite | Biggest engineering gap — eval harness + manual QA instead |
| Public deploy | Optional; not required for grading motive |
| NL filter extraction (“in Mumbai” from query) | UI dropdowns satisfy filter requirement |
| RRF k sensitivity sweep | Prefer honest default over fake precision |

---

## 5. Implementation plan (roadmap phases) — what you did in order

### Phase 1 — Data foundation
| Milestone | What | Why that order |
|---|---|---|
| **M1.1** | Atlas M0 + both indexes + FastAPI `/health` + one hand-embedded spike doc proving `$vectorSearch` and `$search` | Kill the riskiest unknown (index JSON) on day 1 |
| **M1.2** | Seed 120 rows **without** embeddings | Isolate Excel/Mongo bugs from ML bugs |
| **M1.3** | Backfill embeddings with bge-small; `/health/model` | Only then attach ML |

### Phase 2 — Core search
| Milestone | What | Why |
|---|---|---|
| **M2.1** | Read CRUD | Browse confirms data |
| **M2.2** | `POST /api/search` **vector-only** | Naive baseline on purpose — proves semantic path |
| **M2.3** | React search page | First end-to-end demo |

### Phase 3 — Ranking quality + registration
| Milestone | What | Why |
|---|---|---|
| **M3.1** | Hybrid + RRF (same API contract) | Fixes Premise 1 (literal queries) |
| **M3.2** | Filters + live allow-list | Product + safety |
| **M3.3** | `POST /api/businesses` embed-on-write | Assignment core |
| **M3.4** | Registration UI + empty/error states | Full UX |

### Phase 4 — Evidence + hardening
| Milestone | What | Why |
|---|---|---|
| **M4.1** | Golden eval | Measure before claiming |
| **M4.2** | Cross-encoder **if** eval helps | Evidence-gated ranking |
| **M4.3** | Warm-up, dual health, README | Demo reliability |

### Phase 5 — Deploy (stretch)
Planned Vercel+Railway; **not required**; later reverted from repo when you chose not to host.

### Mid-project discovery (important narrative)
After M3.1, eval showed **naive hybrid < vector-only**. That forced “tuned hybrid” work (field narrowing, score gating, weights) **before** trusting rerank. This is your strongest Ranking story.

---

## 6. End-to-end search pipeline (memorize for whiteboard)

1. **Embed query** → 384-dim L2-normalized vector (same model as docs).
2. **Validate filters** against live allow-list → else 422.
3. **Retrieve in parallel**
   - `$vectorSearch` top ~30 (cosine)
   - `$search` top ~30 (narrow fields + relative score gate)
4. **Weighted RRF** fuse → tag `matched_via`: semantic | keyword | both.
5. **Cross-encoder** rescore top 20 (if enabled).
6. **Return top N** (empty list = 200 + `[]`, not an error).

Registration path: validate → same embed text → embed → insert → invalidate filter cache → Atlas sync → searchable.

---

## 7. Eval numbers (memorize)

| System | P@5 | R@5 | MRR | Story |
|---|---|---|---|---|
| Vector-only | 0.560 | 0.946 | **0.958** | Strong semantics |
| Previous (naive) Hybrid | **0.467** | 0.792 | 0.863 | **Regression** |
| Tuned Hybrid | 0.513 | 0.875 | 0.869 | Partial fix |
| **Hybrid + Cross-Encoder** | **0.560** | **0.946** | 0.929 | Ships enabled |

Latency (order-of-magnitude, machine-dependent): hybrid alone tens–hundreds ms; +rerank roughly +400ms class on CPU. Absolute numbers vary; **relative** finding is durable: rerank dominates latency.

---

## 8. Map each criterion → exact system piece (for “explain your understanding”)

### Embeddings
- Model: bge-small-en-v1.5  
- Dims: 384, cosine via normalized vectors  
- When computed: seed batch + every registration  
- Text construction choices (include/exclude fields)

### Vector databases
- Atlas Vector Search index on `embedding`  
- `$vectorSearch` ANN (HNSW)  
- Why Atlas vs FAISS vs Qdrant (section 4.1)

### Semantic Search
- Query and docs in same vector space  
- Demo query: “someone who can defend us against computer hacking” → Cybersecurity with little/no lexical overlap  
- UI: `matched_via: semantic` / `both`

### NLP
- Sentence-level meaning via transformers (not bag-of-words alone)  
- Cross-encoder as deeper pairwise relevance judgment  
- Keyword path as complementary lexical NLP (tokenization/Lucene), not the only path

### Ranking
- Multi-stage: retrieve → fuse (RRF) → rerank  
- Eval-gated decisions  
- Tuned hybrid after measured failure  
- `matched_via` + scores for explainability

---

## 9. Likely interview questions + short answers

**Q: Why not just FAISS in memory for 120 docs?**  
A: Technically fine; assignment grades vector DBs; Atlas gives real vector index + same store as Mongo with zero dual-write.

**Q: Why hybrid if vector-only MRR is higher?**  
A: Product needs exact and semantic. Naive hybrid hurt P@5; tuned+rerank recovers P@5 to 0.560 while keeping keyword path. MRR caveat is stated honestly.

**Q: Why RRF?**  
A: Incompatible score scales; rank fusion is correct. Averaging cosine and Lucene scores is a bug dressed as math.

**Q: Why rerank only top 20?**  
A: Cross-encoder cost is O(candidates). Retrieve cheaply, refine a shortlist.

**Q: What changes at 100k businesses?**  
A: Keep Atlas vector+search. Move embedding off request path to a queue; bulkWrite ingest; use Atlas native pre-filters on vector search; maybe raise candidate pool; keep eval harness.

**Q: Biggest weakness?**  
A: No automated unit/integration test suite; public endpoints unauthenticated; residual token-sense collisions; small golden set (directional, not huge CI).

**Q: Did AI write this?**  
A: “I used AI to move faster on boilerplate and docs. Architecture choices, eval failures, and tuning were driven by measured results — I can walk the pipeline and the regression story without the tools.”

---

## 10. Demo script cues (meeting / video)

1. Intro: NL search over 120 businesses; ranking is measured.  
2. Query: `someone who can defend us against computer hacking` → semantic.  
3. Query: `eco friendly packaging for restaurants` → hybrid / both.  
4. Filters + invalid city → 422 allow-list story.  
5. Register → search within ~2s → same embedding pipeline.  
6. Optional: rerank off vs on for the “computer” collision story.  
7. Close: naive hybrid failed → tuned → rerank shipped on evidence.

---

## 11. Files to open if they ask “show me”

| Topic | File |
|---|---|
| Decisions / alternatives | `design-doc.md`, `design-doc-v2.md` |
| Milestone plan | `roadmap.md` |
| Pipeline + eval table | `README.md` |
| Short summary | `docs/PROJECT_SUMMARY.md` |
| Demo steps | `docs/DEMO_SCRIPT.md` |
| Search code | `backend/app/search.py` |
| Embeddings | `backend/app/embeddings.py` |
| Reranker | `backend/app/reranker.py` |
| Eval | `backend/scripts/eval.py`, `backend/eval_reports/` |

---

## 12. One-minute closing speech (memorize)

“I built a hybrid semantic search system on MongoDB Atlas. Businesses are embedded with a local bge-small model into a 384-d vector index, and queries hit vector search and keyword search in parallel. I fuse with weighted RRF because the score scales don’t match. Eval showed naive hybrid actually hurt precision, so I tuned keyword fields and gating, then added a cross-encoder reranker only after it improved Precision@5. Registration uses the same embedding pipeline so new businesses are searchable in about a second. The point of the project isn’t that I stacked every buzzword — it’s that each ranking stage earned its place with numbers.”

---

*End of brief. Paste this entire document into ChatGPT and ask: “Quiz me as the interviewer grading embeddings, vector DBs, semantic search, NLP, and ranking. Challenge every decision.”*
