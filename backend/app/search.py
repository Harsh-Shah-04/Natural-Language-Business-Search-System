"""
Vector-only semantic search (M2).

Deliberately the naive baseline per design-doc-v2.md / roadmap.md: Atlas
$vectorSearch only, no keyword search, no RRF, no reranking — those are
M3.1/M4.2. The endpoint contract here is meant to stay stable when hybrid
search replaces the internals in M3.1.
"""

from pymongo.errors import PyMongoError

from app.db import get_db
from app.embeddings import embed_texts

VECTOR_INDEX_NAME = "business_vector_index"

# Standard Atlas guidance: numCandidates should be well above `limit` for
# good recall (commonly 10-20x). At this corpus size (120 docs) this
# comfortably covers the whole collection regardless of `limit`.
CANDIDATE_MULTIPLIER = 10
MIN_CANDIDATES = 100

# Fields returned to the client. Excludes `embedding` (384 floats, no
# reason to ship it) and `_id` is remapped to `id` below.
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


class SearchUnavailableError(Exception):
    """Raised when the embedding model or Atlas is unavailable for search."""


def search_businesses(query: str, limit: int) -> list[dict]:
    try:
        query_vector = embed_texts([query])[0]
    except Exception as e:
        raise SearchUnavailableError(f"embedding model unavailable: {e}") from e

    num_candidates = max(limit * CANDIDATE_MULTIPLIER, MIN_CANDIDATES)

    project_stage = {"_id": 1, "score": {"$meta": "vectorSearchScore"}}
    project_stage.update(RESULT_FIELDS)

    try:
        businesses = get_db()["businesses"]
        results = list(
            businesses.aggregate(
                [
                    {
                        "$vectorSearch": {
                            "index": VECTOR_INDEX_NAME,
                            "path": "embedding",
                            "queryVector": query_vector,
                            "numCandidates": num_candidates,
                            "limit": limit,
                        }
                    },
                    {"$project": project_stage},
                ]
            )
        )
    except (PyMongoError, RuntimeError) as e:
        # RuntimeError covers get_db() failing before a query is even
        # attempted (e.g. MONGODB_URI unset) — that's a backend-unavailable
        # condition too, not just PyMongoError from the query itself.
        raise SearchUnavailableError(f"search backend unavailable: {e}") from e

    for doc in results:
        doc["id"] = str(doc.pop("_id"))

    return results
