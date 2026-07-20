"""
M1.1 spike verification.

Inserts one test business with a synthetic 384-dim vector (not a real
embedding — that's M1.3's job), then confirms both Atlas index types
defined in atlas_indexes/ can find it: a $vectorSearch query and a
$search (keyword) query. This proves the index configuration works
before any real ingestion or ML code depends on it.

Requires: MONGODB_URI in .env, and both indexes from atlas_indexes/*.json
already created in the Atlas UI (Atlas Search doesn't support creating
search-type or vectorSearch-type indexes via the standard driver API).

Run: uv run python scripts/verify_atlas_spike.py
"""

import math
import sys

from dotenv import load_dotenv

from app.db import get_db

TEST_DOC_ID = "m1.1-spike-test-doc"


def synthetic_vector(dims: int = 384) -> list[float]:
    """Deterministic, non-degenerate stand-in for a real embedding."""
    return [math.sin(i) for i in range(dims)]


def main() -> int:
    load_dotenv()
    db = get_db()
    businesses = db["businesses"]

    businesses.delete_one({"_id": TEST_DOC_ID})
    businesses.insert_one(
        {
            "_id": TEST_DOC_ID,
            "business_description": "Spike test business for Atlas index verification",
            "products_services": "atlas index verification",
            "keywords": "spike, verification, m1.1",
            "specialties": "index configuration testing",
            "embedding": synthetic_vector(),
        }
    )

    vector_ok = _check_vector_search(businesses)
    search_ok = _check_text_search(businesses)

    businesses.delete_one({"_id": TEST_DOC_ID})

    if vector_ok and search_ok:
        print("PASS: both $vectorSearch and $search found the test document")
        return 0

    print("FAIL: vector_search=%s text_search=%s" % (vector_ok, search_ok))
    return 1


def _check_vector_search(businesses) -> bool:
    results = list(
        businesses.aggregate(
            [
                {
                    "$vectorSearch": {
                        "index": "business_vector_index",
                        "path": "embedding",
                        "queryVector": synthetic_vector(),
                        "numCandidates": 10,
                        "limit": 5,
                    }
                },
                {"$project": {"_id": 1}},
            ]
        )
    )
    return any(doc["_id"] == TEST_DOC_ID for doc in results)


def _check_text_search(businesses) -> bool:
    results = list(
        businesses.aggregate(
            [
                {
                    "$search": {
                        "index": "business_search_index",
                        "text": {
                            "query": "verification",
                            "path": ["business_description", "keywords"],
                        },
                    }
                },
                {"$project": {"_id": 1}},
            ]
        )
    )
    return any(doc["_id"] == TEST_DOC_ID for doc in results)


if __name__ == "__main__":
    sys.exit(main())
