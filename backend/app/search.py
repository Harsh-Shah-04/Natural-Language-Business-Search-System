"""
Hybrid semantic + keyword search (M3.1).

Runs Atlas $vectorSearch and Atlas $search concurrently, fuses the two
candidate lists with Reciprocal Rank Fusion, and returns the top N. Same
endpoint contract as M2's vector-only baseline — extension, not rewrite.

Deliberately no `filters` param (M3.2) and no cross-encoder reranking
(gated on M4.1's eval showing it actually helps — see design-doc-v2.md).
"""

from concurrent.futures import ThreadPoolExecutor

from pymongo.errors import PyMongoError

from app.db import get_db
from app.embeddings import embed_texts

VECTOR_INDEX_NAME = "business_vector_index"
SEARCH_INDEX_NAME = "business_search_index"
SEARCH_TEXT_PATHS = ["business_description", "products_services", "keywords", "specialties"]

# design-doc-v2.md: "top ~30" from each retrieval at the default limit=10.
# Generalized so a larger requested `limit` (up to 50) doesn't starve
# fusion of candidates: max(30, limit * 3) reduces to exactly 30 at the
# documented default.
POOL_SIZE_DEFAULT = 30
POOL_SIZE_MULTIPLIER = 3

# Standard Atlas guidance: numCandidates should be well above the
# vectorSearch stage's own `limit` for good recall (commonly 10-20x). At
# this corpus size (120 docs) this comfortably covers the whole collection.
CANDIDATE_MULTIPLIER = 10
MIN_CANDIDATES = 100

# design-doc-v2.md: "score = Σ 1/(60 + rank)" — k=60 is the standard
# IR-literature default, used as-is, not re-derived for this corpus size.
RRF_K = 60

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


class SearchUnavailableError(Exception):
    """Raised when the embedding model or Atlas is unavailable for search."""


def _vector_search(businesses, query_vector: list[float], pool_size: int) -> list[dict]:
    num_candidates = max(pool_size * CANDIDATE_MULTIPLIER, MIN_CANDIDATES)
    return list(
        businesses.aggregate(
            [
                {
                    "$vectorSearch": {
                        "index": VECTOR_INDEX_NAME,
                        "path": "embedding",
                        "queryVector": query_vector,
                        "numCandidates": num_candidates,
                        "limit": pool_size,
                    }
                },
                {"$project": _PROJECT_STAGE},
            ]
        )
    )


def _keyword_search(businesses, query: str, pool_size: int) -> list[dict]:
    return list(
        businesses.aggregate(
            [
                {
                    "$search": {
                        "index": SEARCH_INDEX_NAME,
                        "text": {"query": query, "path": SEARCH_TEXT_PATHS},
                    }
                },
                {"$limit": pool_size},
                {"$project": _PROJECT_STAGE},
            ]
        )
    )


def _reciprocal_rank_fusion(
    vector_results: list[dict], keyword_results: list[dict], limit: int
) -> list[dict]:
    fused: dict = {}  # _id -> {"doc": dict, "rrf_score": float, "sources": set[str]}

    for source_name, ranked_docs in (("semantic", vector_results), ("keyword", keyword_results)):
        for rank, doc in enumerate(ranked_docs, start=1):
            entry = fused.setdefault(
                doc["_id"], {"doc": doc, "rrf_score": 0.0, "sources": set()}
            )
            entry["rrf_score"] += 1 / (RRF_K + rank)
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


def search_businesses(query: str, limit: int) -> list[dict]:
    try:
        query_vector = embed_texts([query])[0]
    except Exception as e:
        raise SearchUnavailableError(f"embedding model unavailable: {e}") from e

    pool_size = max(POOL_SIZE_DEFAULT, limit * POOL_SIZE_MULTIPLIER)

    try:
        businesses = get_db()["businesses"]
        with ThreadPoolExecutor(max_workers=2) as executor:
            vector_future = executor.submit(_vector_search, businesses, query_vector, pool_size)
            keyword_future = executor.submit(_keyword_search, businesses, query, pool_size)
            vector_results = vector_future.result()
            keyword_results = keyword_future.result()
    except (PyMongoError, RuntimeError) as e:
        # RuntimeError covers get_db() failing before a query is even
        # attempted (e.g. MONGODB_URI unset) — that's a backend-unavailable
        # condition too, not just PyMongoError from the query itself.
        raise SearchUnavailableError(f"search backend unavailable: {e}") from e

    return _reciprocal_rank_fusion(vector_results, keyword_results, limit)
