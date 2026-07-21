# Submission Checklist & Final QA (M5.5)

Verification run: 2026-07-21, against the live Atlas cluster and a clean build.

---

## Submission checklist

| Item | Status | Evidence |
|---|---|---|
| Repository ready | **Done** | Working tree clean; 51 commits; no secrets in history. |
| README complete | **Done** | Root `README.md`: overview, architecture (+2 Mermaid diagrams), API reference for all 6 endpoints, evaluation, performance, deployment. |
| Environment variables documented | **Done** | `backend/.env.example`, `frontend/.env.example`, and a table per file in the README. |
| Installation verified | **Done** | `uv sync` + `npm install` both documented and exercised. |
| Build verified | **Done** | `npm run build` (tsc -b + Vite) passes; `npm run lint` (oxlint) clean. |
| Backend starts clean | **Done** | `uvicorn app.main:app` boots, models warm in background, all 3 health endpoints 200. |
| End-to-end QA | **Done** | 10/10 automated checks passed, plus registration, empty-state and cross-encoder verification. See below. |
| No secrets committed | **Done** | 0 credentialed URIs across all 51 commits; `.env` gitignored and never tracked. |
| Demo script prepared | **Done** | [`docs/DEMO_SCRIPT.md`](DEMO_SCRIPT.md). |
| Project summary | **Done** | [`docs/PROJECT_SUMMARY.md`](PROJECT_SUMMARY.md). |
| **Screenshots captured** | **Not done** | Placeholders + capture instructions in [`docs/screenshots/`](screenshots/). Requires a human with a browser. |
| **Deployed** | **Not done** | Deployment guide written; nothing hosted. Out of scope for M5.5. |
| **Automated test suite** | **Not present** | Verified by the evaluation harness + live manual QA. No unit/integration tests. Biggest engineering gap; stated in the README. |

---

## Final QA results

All checks run against a live backend with both models loaded.

### Automated checks — 10/10 passed

| # | Check | Result |
|---|---|---|
| 1 | `GET /health` | 200 |
| 2 | `GET /health/model` | 200, `ready` |
| 3 | `GET /health/reranker` | 200, `ready` |
| 4 | `POST /api/search` | 200, ranked results |
| 5 | `GET /api/filters/values` | 200, all 5 fields |
| 6 | Blank query | 422 |
| 7 | Filter value outside allow-list | 422 |
| 8 | `limit` out of range (999) | 422 |
| 9 | Malformed email on registration | 422 |
| 10 | Missing required field on registration | 422 |

### Behavioural verification

| Scenario | Result |
|---|---|
| **Semantic / vocabulary mismatch** — "someone who can defend us against computer hacking" | Cybersecurity ranked 1-2-3, with zero shared keywords. |
| **Keyword + semantic** — "eco friendly packaging for restaurants" | Food-packaging manufacturers top-3, all `matched_via: both`. |
| **Filters narrow correctly** | `state=Maharashtra` → 10/10 results in Maharashtra, no leakage. |
| **Empty state** | `industry=Agriculture` + `city=Indore` (both valid values) → 0 results, HTTP 200, not an error. |
| **Registration** | 201 with `{id, business_name}`. |
| **Duplicate registration** | 409 with a clear message. |
| **Immediate searchability** | Registered business found by search **2s** after insert. |
| **Filter cache invalidation** | New `city=Nashik` and `sub_category=Hydroponics` became valid filter values immediately. |
| **Cross-encoder changes ranking** | Rerank **off**: AI Solutions ranks 1-3 for "computer hacking defense" (the documented token collision). Rerank **on**: Cybersecurity ranks 1-2-3. |
| **`RERANK_ENABLED=false`** | Reranker reports `not_started` — model is never loaded, saving its ~92MB. |

Test data created during QA was deleted; the collection is back to the seeded 120 documents.

### Code cleanup — clean

| Scan | Result |
|---|---|
| `TODO` / `FIXME` / `XXX` / `HACK` | none |
| `console.*` / `debugger` / `alert()` | none |
| `print()` / `pdb` / `breakpoint()` in `backend/app/` | none (scripts print intentionally) |
| Orphaned frontend source files | none — every file is imported |
| Frontend build | passes (33 modules, 64.6 kB gzip JS) |
| Frontend lint (oxlint) | clean |
| Unused imports / locals | impossible — `noUnusedLocals` + `noUnusedParameters` are on and the build passes |

---

## Finding raised and fixed

**The documented latency figures are not reproducible on demand.** The README
reported ~58ms p50 (rerank off) and ~463ms (rerank on). Re-measuring the
identical code in this session gave **~178ms** and **~2135ms** — 3-5x higher.

Diagnosis: not a regression. `git diff 222dabe HEAD` over `search.py`,
`reranker.py`, `embeddings.py` and `constants.py` is empty, so the search path
is byte-identical to the commit those numbers came from. Both paths degraded
proportionally, *including the rerank-off path that never invokes the
cross-encoder*, which points at machine state (CPU contention, thermal, Atlas
round-trip) rather than code.

Fix: both READMEs now carry a caveat stating these are point-in-time
single-machine numbers, giving the re-measured figures, and directing readers to
treat the **relative** cost of reranking as the durable finding.

---

## Known gaps (deliberate, documented)

1. **No automated test suite.** Correctness is established by the golden-query
   evaluation harness and live manual QA. This is the biggest engineering gap.
2. **No authentication.** Every endpoint is public, including
   `POST /api/businesses`. Needs auth + rate limiting before any public deploy.
3. **Screenshots not captured.** Needs a human with a browser.
4. **Not deployed.** Guide written, nothing hosted.
5. **Responsive layout verified by CSS analysis, not a real device/browser.**
6. **Residual ranking collision.** A query token matching a business's own
   discriminative field in a different sense can still mislead keyword
   retrieval; reranking recovers most but not all such cases.
