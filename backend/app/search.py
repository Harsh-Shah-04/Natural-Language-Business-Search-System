"""
Hybrid semantic + keyword search with optional filters (M3.1 + M3.2),
tuned per M4.1's evaluation findings (M4.1.1).

Runs Atlas $vectorSearch and Atlas $search concurrently, fuses the two
candidate lists with Weighted Reciprocal Rank Fusion, and returns the top
N. Same endpoint contract as M2's vector-only baseline — extension, not
rewrite; search_businesses()'s signature is unchanged, and so is the
/api/search route.

Deliberately no cross-encoder reranking (gated on M4.1's eval showing it
actually helps — see design-doc-v2.md).

M4.1's golden-query evaluation (scripts/eval.py) found hybrid scoring
*below* vector-only overall, traced by direct inspection to two causes,
targeted (not fully eliminated -- see below) by this milestone's tuning:
1. business_description's templated boilerplate ("X is a [goods/services]
   business specializing in...") let near-universal words (e.g.
   "business") produce coincidental keyword matches with zero semantic
   relevance (SEARCH_TEXT_PATHS).
2. RRF's rank-based fusion had no way to tell a weak/coincidental keyword
   match from a genuine one, so it could still drag a correct vector
   ranking down (KEYWORD_SCORE_THRESHOLD_RATIO, RRF_WEIGHT_*).

Re-running the eval after these changes recovered roughly half the
precision@5 gap and most of the recall gap, but did not fully close it --
the same class of collision can still occur when the coincidental token
lives inside a business's own genuinely discriminative fields (not just
business_description's boilerplate) and is the *only* keyword match
available for that query, since neither field-narrowing nor relative
score-thresholding has anything stronger to compare it against in that
case. Full accounting in eval_reports/ and backend/README.md.
"""

from concurrent.futures import ThreadPoolExecutor

from pymongo.errors import PyMongoError

from app.db import get_db
from app.embeddings import embed_texts
from app.filters import FilterValidationError, validate_filters

VECTOR_INDEX_NAME = "business_vector_index"
SEARCH_INDEX_NAME = "business_search_index"

# M4.1.1: narrowed from the original 4 fields (business_description,
# products_services, keywords, specialties). business_description carries
# templated boilerplate ("...business specializing in...") repeated almost
# verbatim across all 120 documents, so dropping it reduces false matches
# without losing recall (keywords/specialties/products_services carry the
# same discriminative terms without that boilerplate).
#
# Confirmed NOT a complete fix, not oversold as one: re-running scripts/
# eval.py after this change still found a near-identical collision living
# INSIDE keywords itself -- Insurance's own keywords field literally
# contains "business insurance", so "business trip" still mismatches it.
# Field narrowing only removes the boilerplate-specific instances of this
# problem; a coincidental token shared by the query and a business's own
# genuinely discriminative fields isn't addressed by any of M4.1.1's three
# changes (see eval_reports/ and backend/README.md for the honest
# after-the-fact accounting, including what's still open).
SEARCH_TEXT_PATHS = ["keywords", "specialties", "products_services"]

# design-doc-v2.md: "top ~30" from each retrieval at the default limit=10.
# Generalized so a larger requested `limit` (up to 50) doesn't starve
# fusion of candidates: max(30, limit * 3) reduces to exactly 30 at the
# documented default.
POOL_SIZE_DEFAULT = 30
POOL_SIZE_MULTIPLIER = 3

# Atlas $vectorSearch truncates to its own `limit` INSIDE the stage, before
# any later $match can run — so a naive post-filter on the normal ~30-doc
# pool could correctly-but-uselessly filter down to near-zero results even
# when the full corpus has plenty of matches. When any filter is active,
# widen the pool past the current corpus size (120 docs) so filtering never
# starves the result set. At meaningfully larger corpora this would need
# Atlas's native filter-type index fields (pre-filtering before HNSW search)
# instead of over-fetching — out of scope at this dataset's actual size.
POOL_SIZE_FILTERED = 200

# Standard Atlas guidance: numCandidates should be well above the
# vectorSearch stage's own `limit` for good recall (commonly 10-20x). At
# this corpus size (120 docs) this comfortably covers the whole collection.
CANDIDATE_MULTIPLIER = 10
MIN_CANDIDATES = 100

# design-doc-v2.md: "score = Σ 1/(60 + rank)" — k=60 is the standard
# IR-literature default, used as-is, not re-derived for this corpus size.
RRF_K = 60

# M4.1.1: Weighted RRF. M4.1's eval found keyword search never contributed
# a unique win anywhere in the golden set (vector-only already covers
# literal-keyword-heavy queries well, since the embedding text is built
# from the same keywords/products_services/specialties fields), while
# repeatedly diluting otherwise-correct vector rankings with noise.
# Weighting vector ~2.3x higher than keyword directly limits how much a
# weak keyword-side ranking can drag a query down, while still letting
# keyword search reinforce a ranking when it agrees with vector
# (contributes to matched_via="both"). Chosen as a reasoned starting point
# from the eval findings, not grid-searched; validated by re-running
# scripts/eval.py after this change (see backend/README.md).
RRF_WEIGHT_VECTOR = 0.7
RRF_WEIGHT_KEYWORD = 0.3

# M4.1.1: keyword score-threshold gating. RRF is rank-based and blind to
# score magnitude — a keyword hit at rank 30-of-30 with a near-zero
# searchScore previously contributed to fusion exactly as formulaically as
# a strong rank-1 hit. Atlas's searchScore has no fixed scale across
# queries, so the threshold is relative to each query's own top keyword
# score, not an absolute cutoff: a hit must score at least this fraction
# of the best keyword match for the same query to be included in fusion
# at all. 0.3 is a conservative starting point (discards clearly-weak tail
# matches, keeps legitimate partial multi-term matches); validated the
# same way as the RRF weights above.
KEYWORD_SCORE_THRESHOLD_RATIO = 0.3

# Fields returned to the client. Excludes `embedding` (384 floats, no
# reason to ship it) and `_id` is remapped to `id` after fusion.
RESULT_FIELDS = {
    "business_name": 1,
    "nature": 1,
    "industry": 1,
    "sub_category": 1,
    "city": 1,
    "state": 1,
    "contact_person": 1,
    "email": 1,
    "website": 1,
    "phone": 1,
    "business_description": 1,
    "products_services": 1,
    "keywords": 1,
    "specialties": 1,
}
_PROJECT_STAGE = {"_id": 1, **RESULT_FIELDS}
# Keyword search additionally projects Atlas's raw searchScore, needed for
# M4.1.1's score-threshold gating below. Overwritten by the real RRF score
# before any result reaches the client -- see _reciprocal_rank_fusion.
_KEYWORD_PROJECT_STAGE = {"_id": 1, "score": {"$meta": "searchScore"}, **RESULT_FIELDS}


class SearchUnavailableError(Exception):
    """Raised when the embedding model or Atlas is unavailable for search."""


def _vector_search(
    businesses, query_vector: list[float], pool_size: int, filters: dict[str, str]
) -> list[dict]:
    num_candidates = max(pool_size * CANDIDATE_MULTIPLIER, MIN_CANDIDATES)
    pipeline = [
        {
            "$vectorSearch": {
                "index": VECTOR_INDEX_NAME,
                "path": "embedding",
                "queryVector": query_vector,
                "numCandidates": num_candidates,
                "limit": pool_size,
            }
        },
    ]
    if filters:
        # $vectorSearch already truncated to `pool_size` above — filtering
        # here can only ever narrow further, never recover results outside
        # that pool. That's exactly why pool_size is widened by the caller
        # when filters are active.
        pipeline.append({"$match": filters})
    pipeline.append({"$project": _PROJECT_STAGE})
    return list(businesses.aggregate(pipeline))


def _keyword_search(
    businesses,
    query: str,
    pool_size: int,
    filters: dict[str, str],
    search_paths: list[str] | None = None,
    score_threshold_ratio: float | None = None,
) -> list[dict]:
    """search_paths and score_threshold_ratio default to the module-level
    tuned constants (SEARCH_TEXT_PATHS, KEYWORD_SCORE_THRESHOLD_RATIO).
    Overridable so scripts/eval.py can reconstruct the pre-M4.1.1 config
    for a genuine before/after comparison without duplicating this
    function -- not exposed on search_businesses() or the HTTP API."""
    if search_paths is None:
        search_paths = SEARCH_TEXT_PATHS
    if score_threshold_ratio is None:
        score_threshold_ratio = KEYWORD_SCORE_THRESHOLD_RATIO

    pipeline = [
        {
            "$search": {
                "index": SEARCH_INDEX_NAME,
                "text": {"query": query, "path": search_paths},
            }
        },
    ]
    if filters:
        # $match before $limit here (unlike $vectorSearch's internal
        # truncation): $search itself doesn't cap results, so filtering
        # before the $limit stage means pool_size counts filtered results,
        # not raw hits that might get discarded before filtering ever runs.
        pipeline.append({"$match": filters})
    pipeline.append({"$limit": pool_size})
    pipeline.append({"$project": _KEYWORD_PROJECT_STAGE})
    results = list(businesses.aggregate(pipeline))

    if not results or score_threshold_ratio <= 0:
        return results
    # Atlas $search ranks by descending searchScore, so results[0] is the
    # true top score among all matches (not just among the pool_size kept).
    threshold = results[0]["score"] * score_threshold_ratio
    return [r for r in results if r["score"] >= threshold]


def _reciprocal_rank_fusion(
    vector_results: list[dict],
    keyword_results: list[dict],
    limit: int,
    vector_weight: float | None = None,
    keyword_weight: float | None = None,
) -> list[dict]:
    """vector_weight/keyword_weight default to the module-level tuned
    constants (RRF_WEIGHT_VECTOR, RRF_WEIGHT_KEYWORD). Overridable so
    scripts/eval.py can reconstruct the pre-M4.1.1 unweighted config
    (both 1.0) for comparison -- not exposed on search_businesses()."""
    if vector_weight is None:
        vector_weight = RRF_WEIGHT_VECTOR
    if keyword_weight is None:
        keyword_weight = RRF_WEIGHT_KEYWORD

    fused: dict = {}  # _id -> {"doc": dict, "rrf_score": float, "sources": set[str]}
    weights = {"semantic": vector_weight, "keyword": keyword_weight}

    for source_name, ranked_docs in (("semantic", vector_results), ("keyword", keyword_results)):
        weight = weights[source_name]
        for rank, doc in enumerate(ranked_docs, start=1):
            entry = fused.setdefault(
                doc["_id"], {"doc": doc, "rrf_score": 0.0, "sources": set()}
            )
            entry["rrf_score"] += weight / (RRF_K + rank)
            entry["sources"].add(source_name)

    ranked = sorted(fused.values(), key=lambda e: e["rrf_score"], reverse=True)[:limit]

    results = []
    for entry in ranked:
        doc = dict(entry["doc"])
        doc["id"] = str(doc.pop("_id"))
        doc["score"] = entry["rrf_score"]
        doc["matched_via"] = "both" if len(entry["sources"]) == 2 else next(iter(entry["sources"]))
        results.append(doc)
    return results


def search_businesses(
    query: str, limit: int, filters: dict[str, str | None] | None = None
) -> list[dict]:
    try:
        query_vector = embed_texts([query])[0]
    except Exception as e:
        raise SearchUnavailableError(f"embedding model unavailable: {e}") from e

    try:
        active_filters = validate_filters(filters)
    except FilterValidationError:
        raise
    except (PyMongoError, RuntimeError) as e:
        # The allow-list itself is DB-backed (cached, but a cache miss
        # queries Mongo) — its own backend failures are a 503 condition,
        # distinct from a validation failure (422).
        raise SearchUnavailableError(f"filter allow-list unavailable: {e}") from e

    pool_size = (
        POOL_SIZE_FILTERED
        if active_filters
        else max(POOL_SIZE_DEFAULT, limit * POOL_SIZE_MULTIPLIER)
    )

    try:
        businesses = get_db()["businesses"]
        with ThreadPoolExecutor(max_workers=2) as executor:
            vector_future = executor.submit(
                _vector_search, businesses, query_vector, pool_size, active_filters
            )
            keyword_future = executor.submit(
                _keyword_search, businesses, query, pool_size, active_filters
            )
            vector_results = vector_future.result()
            keyword_results = keyword_future.result()
    except (PyMongoError, RuntimeError) as e:
        # RuntimeError covers get_db() failing before a query is even
        # attempted (e.g. MONGODB_URI unset) — that's a backend-unavailable
        # condition too, not just PyMongoError from the query itself.
        raise SearchUnavailableError(f"search backend unavailable: {e}") from e

    return _reciprocal_rank_fusion(vector_results, keyword_results, limit)
