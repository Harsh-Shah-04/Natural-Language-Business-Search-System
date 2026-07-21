# Demo Script — 3 to 5 minutes

A walkthrough for demoing the Natural Language Business Search System.
Timings are a guide, not a script to read aloud verbatim.

## Before you start

```bash
# terminal 1
cd backend && uv run uvicorn app.main:app --reload

# terminal 2
cd frontend && npm run dev
```

Wait until both models report ready — this matters, the first search is slow otherwise:

```bash
curl http://127.0.0.1:8000/health/model      # {"status":"ready"}
curl http://127.0.0.1:8000/health/reranker   # {"status":"ready"}
```

Open <http://localhost:5173>. Have a second tab on the repo's README (for the
architecture diagram) and a terminal ready.

---

## 0:00 — 0:30 · Introduction

> "This is a natural-language search system over a directory of 120 businesses.
> The goal isn't just to return results — it's that every ranking decision in it
> is backed by a measured evaluation, including the ones that didn't work."

Point at the search page. One sentence on the problem: users don't type the
words that appear in a business profile, so keyword search fails them.

---

## 0:30 — 1:30 · Search, and why it's not keyword matching

Search: **`someone who can defend us against computer hacking`**

> "Note there is no shared keyword here. No business profile says 'computer
> hacking'. The top three results are all Cybersecurity firms — matched on
> meaning, through a sentence-embedding model."

Point out on a card:
- the **Semantic + Keyword** badge (how the result was retrieved),
- the **highlighted terms** in the description,
- the **relevance score**.

Then search: **`eco friendly packaging for restaurants`**

> "Food-packaging manufacturers, all matched by both retrieval paths."

---

## 1:30 — 2:00 · Filters

With results on screen, set **State** to a real value (e.g. `Maharashtra`).

> "Filters re-scope the active query immediately. They're validated against a
> live allow-list pulled from the database — so an unknown value is rejected with
> a 422 rather than passed through as a raw query clause. That's what closes the
> injection-shaped gap in a filter API."

Optionally show the rejection:

```bash
curl -s -X POST http://127.0.0.1:8000/api/search -H 'Content-Type: application/json' \
  -d '{"query":"packaging","filters":{"city":"Atlantis"}}'
# {"detail":"invalid value for filter 'city': 'Atlantis' is not a known city"}
```

Click **Clear filters**.

---

## 2:00 — 2:45 · Registration, searchable immediately

Switch to the **Register** tab. Point out the three grouped sections and the
required markers. Fill in something memorable:

- Business Name: `Meridian Hydroponics`
- Industry: `Agriculture` · Nature: `Goods` · Sub Category: `Hydroponics`
- Description: `Meridian builds vertical hydroponic growing systems for urban farms.`
- Products / Services: `Vertical hydroponic racks, nutrient dosing, grow lights`
- City: `Nashik` · State: `Maharashtra`

Submit → success card → click **Search this business**.

> "The registration endpoint runs the new business through the same embedding
> pipeline as the original bulk ingest, so it's searchable through the normal
> search API within a second or two. Its new city also becomes a valid filter
> value straight away."

(If you want to show validation, type a bad email first and let it flag inline.)

---

## 2:45 — 3:45 · The cross-encoder, and the evidence for it

This is the most interesting part — lead with the failure, not the fix.

> "Adding keyword search to semantic search initially made results *worse*.
> Precision@5 dropped from 0.560 to 0.467."

Show the query that breaks it. With reranking **off**:

```
1. Vertex AI Industries      (AI Solutions)
2. Nova AI Solutions         (AI Solutions)
3. Blue AI Enterprises       (AI Solutions)
```

> "Query was 'computer hacking defense'. These AI firms matched on the single
> word 'computer' — from 'computer vision'. Rank-based fusion had no way to know
> that match was meaningless."

With reranking **on**:

```
1. Global Cybersecurity Solutions
2. Next Cybersecurity Industries
3. Prime Cybersecurity Enterprises
```

> "A cross-encoder rescores the top 20 by reading the query and the document
> together, so a shared word in a different sense no longer fools it."

Show the evaluation table (README):

| System | P@5 | R@5 | MRR |
|---|---|---|---|
| Vector-only | 0.560 | 0.946 | 0.958 |
| Previous Hybrid | 0.467 | 0.792 | 0.863 |
| Tuned Hybrid | 0.513 | 0.875 | 0.869 |
| Hybrid + Cross-Encoder | 0.560 | 0.946 | 0.929 |

> "Reranking ships enabled because it measurably beat the best non-reranked
> system on precision@5 — that bar was set before the measurement, not after.
> Honest caveat: on a corpus this small and clean, vector-only is already strong,
> so reranking reaches parity rather than beating it outright. And it costs real
> latency, which is why it's a toggle."

---

## 3:45 — 4:30 · Architecture

Show the Mermaid diagram in the README.

> "Query comes in, gets embedded. Vector search and keyword search run
> **concurrently** against Atlas, then weighted Reciprocal Rank Fusion combines
> them — weighted toward semantics, 0.7 to 0.3, because the evaluation showed
> keyword search was diluting good rankings. The fused top-20 goes to the
> cross-encoder, and we return the top N."

Worth naming:
- Both models run **locally on CPU** — no API keys, no per-query cost.
- Reranking is **additive**: if the cross-encoder fails, search degrades to
  un-reranked results instead of erroring.
- Fusion returns a **wider** pool than requested so reranking can promote a
  result from rank 15 into the top 10.

---

## 4:30 — 5:00 · Close: what's honest about it

> "What I'd flag if you were reviewing this: there's no automated test suite —
> correctness rests on the evaluation harness and manual QA. There's no auth, so
> it isn't deployable publicly as-is. And the residual ranking failure isn't
> fully solved, just mostly recovered by reranking. Those are written down in the
> README rather than left for you to find."

---

## If something goes wrong

| Symptom | Cause / fix |
|---|---|
| First search takes many seconds | Models still loading. Check `/health/model` and `/health/reranker`. |
| Search returns 503 | Embedder or Atlas unreachable. Check `MONGODB_URI` and Atlas network access. |
| Frontend can't reach the API | CORS. `CORS_ALLOW_ORIGINS` must include the frontend origin. |
| Every search is slow (~2s) | Expected under CPU contention with reranking on. `RERANK_ENABLED=false` gives the fast path. |
| Registration returns 409 | That business name already exists — names are unique. |
