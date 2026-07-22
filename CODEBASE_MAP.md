# Codebase Map

One-page guide to this take-home: **what each part does**, **which feature it supports**, and **where to look first**.

> Start here if you are reviewing the repo. For setup and eval numbers, use `README.md`. For deep design rationale, use `design-doc-v2.md`.

---

## Product features → code

| Feature | What the user gets | Primary code |
|---|---|---|
| **Natural-language search** | Type a query → ranked businesses | `backend/app/search.py`, `frontend/src/pages/SearchPage.tsx` |
| **Semantic (vector) retrieval** | Match by meaning, not shared keywords | `embeddings.py` + Atlas `$vectorSearch` in `search.py` |
| **Keyword retrieval** | Exact / near-term Lucene matches | Atlas `$search` in `search.py` + `scripts/atlas_indexes/search_index.json` |
| **Hybrid fusion (RRF)** | Merge vector + keyword lists | `_reciprocal_rank_fusion()` in `search.py` |
| **Cross-encoder rerank** | Rescore top candidates for precision | `reranker.py` (toggle: `RERANK_ENABLED`) |
| **Filters** | Industry / City / State / Nature / Sub Category | `filters.py`, `FilterPanel.tsx` |
| **Business registration** | Add a business → immediately searchable | `registration.py`, `RegisterPage.tsx` |
| **Exact name lookup** | Find a business by its registered name | `business_name` in embed text + keyword paths + Atlas mapping |
| **Evaluation** | Prove ranking changes with metrics | `scripts/eval.py`, `scripts/eval_dataset.py`, `eval_reports/` |
| **API** | HTTP contract for search / filters / register | `main.py`, `schemas.py` |

---

## Repository layout (top level)

```
Intern_assignment/
├── README.md                 # Setup, architecture, eval results, deploy notes
├── CODEBASE_MAP.md           # This file — navigation map
├── design-doc.md             # Early design notes
├── design-doc-v2.md          # Final design (evidence-gated decisions)
├── roadmap.md                # Milestone plan (M1–M5)
├── Business_Matchmaking_…xlsx # Source dataset (120 companies)
├── docs/                     # Submission / demo extras
├── backend/                  # FastAPI + ML + MongoDB Atlas
└── frontend/                 # React + TypeScript + Vite UI
```

---

## Backend map (`backend/`)

### App package — `backend/app/`

| File | Role | Features |
|---|---|---|
| `main.py` | FastAPI app, CORS, lifespan warm-up, routes | Wires search, filters, registration, health |
| `schemas.py` | Pydantic request/response models | Validates search + registration (Nature = Goods/Services) |
| `db.py` | MongoDB client singleton | Shared DB access |
| `constants.py` | Model names + embedding dims | Single source for ML config |
| `embeddings.py` | Load BGE bi-encoder; `build_embedding_text`; `embed_texts` | Semantic search + registration embeddings |
| `search.py` | Hybrid search pipeline (vector ∥ keyword → RRF → optional rerank) | Core ranking feature |
| `reranker.py` | Cross-encoder load + `rerank_candidates` | Precision boost after fusion |
| `filters.py` | Cached allow-list; validate filter values | Safe, dynamic filters |
| `registration.py` | Embed + insert new business; invalidate filter cache | Registration → searchable |

### HTTP routes (in `main.py`)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Process up |
| `GET` | `/health/model` | Embedder status |
| `GET` | `/health/reranker` | Reranker status |
| `GET` | `/api/filters/values` | Dropdown options |
| `POST` | `/api/search` | Hybrid search |
| `POST` | `/api/businesses` | Register business |

### Scripts — `backend/scripts/`

| File | Role |
|---|---|
| `seed.py` | Ingest Excel → Mongo + embeddings |
| `create_atlas_indexes.py` | Create/update Atlas vector + search indexes |
| `atlas_indexes/vector_index.json` | Vector Search index definition |
| `atlas_indexes/search_index.json` | Lucene search fields (includes `business_name`) |
| `reembed_businesses.py` | Recompute embeddings after embed-text changes |
| `eval.py` | Run golden-query evaluation (P@K, R@K, MRR) |
| `eval_dataset.py` | 30 labeled queries across 6 categories |
| `verify_atlas_spike.py` | Early Atlas connectivity / index smoke check |

### Other backend files

| Path | Role |
|---|---|
| `pyproject.toml` / `uv.lock` | Python deps (`uv`) |
| `.env.example` | `MONGODB_URI`, `DB_NAME`, optional `RERANK_ENABLED`, CORS |
| `README.md` | Backend-focused setup and milestone notes |
| `eval_reports/` | Saved eval reports (evidence for ranking choices) |

---

## Frontend map (`frontend/`)

### Entry & shell

| File | Role |
|---|---|
| `index.html` | HTML shell |
| `src/main.tsx` | React mount |
| `src/App.tsx` | Search ↔ Register view switch (no router) |
| `src/index.css` | All styles |

### Pages

| File | Feature |
|---|---|
| `src/pages/SearchPage.tsx` | Search UI: query, filters, results |
| `src/pages/RegisterPage.tsx` | Registration form + success actions |

### API client

| File | Role |
|---|---|
| `src/api/client.ts` | Base URL, `fetch`, error normalization |
| `src/api/search.ts` | `POST /api/search`, filter values |
| `src/api/businesses.ts` | `POST /api/businesses` |
| `src/types/api.ts` | TypeScript types mirroring backend schemas |

### Hooks

| File | Role |
|---|---|
| `src/hooks/useSearch.ts` | Search state, run query, loading/error |
| `src/hooks/useFilterOptions.ts` | Load filter dropdowns |
| `src/hooks/useRegistrationForm.ts` | Form values, validation, submit |

### Components

| File | Role |
|---|---|
| `SearchBar.tsx` | Query input + submit |
| `FilterPanel.tsx` / `FilterSelect.tsx` | Filter dropdowns |
| `ResultsList.tsx` / `ResultCard.tsx` | Result cards, scores, matched_via |
| `StatusMessage.tsx` | Empty / loading / error messages |
| `FormField.tsx` | Text / textarea / select for registration |
| `utils/highlight.tsx` | Highlight query terms in results |

### Frontend config

| File | Role |
|---|---|
| `package.json` | Scripts: `dev`, `build`, `lint` |
| `vite.config.ts` | Vite + React plugin |
| `.env.example` | `VITE_API_BASE_URL` (points at backend) |

---

## Docs map (`docs/` + design)

| File | Audience | Contents |
|---|---|---|
| `README.md` | Reviewer / engineer | Full project guide |
| `design-doc-v2.md` | Reviewer | Final architecture + evidence gates |
| `design-doc.md` | Context | Earlier design iteration |
| `roadmap.md` | Context | Milestone checklist |
| `docs/SUBMISSION.md` | Submission checklist | What to turn in |
| `docs/DEMO_SCRIPT.md` | Demo walkthrough | Live demo steps |
| `docs/PROJECT_SUMMARY.md` | Short overview | Elevator + stack |
| `docs/screenshots/README.md` | Screenshot capture guide | UI evidence |

---

## Search pipeline (mental model)

```
Query
  ├─→ embed (bge-small) ──→ Atlas $vectorSearch ──┐
  │                                                ├─→ Weighted RRF fusion
  └─→ Atlas $search (name + keywords + …) ─────────┘
                         │
                         ▼
              optional cross-encoder rerank (top 20)
                         │
                         ▼
                   top N results (+ filters if set)
```

**Name lookup note:** `business_name` is in embedding text, keyword paths, and the Atlas search index so registered businesses are findable by exact name even when the description does not repeat the name.

---

## Config a reviewer should know

| Variable | Where | Meaning |
|---|---|---|
| `MONGODB_URI` / `DB_NAME` | `backend/.env` | Atlas connection |
| `RERANK_ENABLED` | `backend/.env` (optional, default true) | Turn cross-encoder on/off |
| `CORS_ALLOW_ORIGINS` | `backend/.env` (optional) | Frontend origins |
| `VITE_API_BASE_URL` | `frontend/.env` | Backend URL for the UI |

---

## What is intentionally *not* in the repo

| Item | Why excluded |
|---|---|
| `.env` / secrets | Local only (gitignored) |
| `node_modules/`, `.venv/` | Installable deps |
| `.gstack/`, QA screenshots | Local agent/QA tooling, not assignment deliverables |
| Excel lock files (`~$*`) | Transient Office locks |

---

## Suggested reading order (15–20 min)

1. This file (`CODEBASE_MAP.md`) — orientation  
2. `README.md` — features, architecture diagram, how to run  
3. `backend/app/search.py` — ranking heart  
4. `backend/app/embeddings.py` + `reranker.py` — ML pieces  
5. `frontend/src/pages/SearchPage.tsx` + `RegisterPage.tsx` — UI  
6. `eval_reports/` + `scripts/eval_dataset.py` — evidence for ranking choices  
7. `design-doc-v2.md` — why hybrid + rerank shipped  

---

## Quick run (local)

```powershell
# Backend (from backend/)
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8001

# Frontend (from frontend/)
# set VITE_API_BASE_URL=http://127.0.0.1:8001 in frontend/.env
npm run dev
```

Open http://localhost:5173 — search and register.
