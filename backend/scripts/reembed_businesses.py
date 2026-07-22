"""
Re-embed every business with the current build_embedding_text().

Required after adding business_name to the embedding text so existing
documents (especially registrations whose description omits the name) become
findable via vector search. Also repairs Nature values that are not
Goods/Services so the filter allow-list stays clean.

Run: uv run python scripts/reembed_businesses.py
"""

from dotenv import load_dotenv

from app.embeddings import build_embedding_text, embed_texts
from app.filters import invalidate_filter_cache
from app.db import get_db

ALLOWED_NATURE = {"Goods", "Services"}


def main() -> int:
    load_dotenv()
    businesses = get_db()["businesses"]
    docs = list(businesses.find({}))
    if not docs:
        print("FAIL: no businesses found")
        return 1

    nature_fixed = 0
    for doc in docs:
        nature = doc.get("nature")
        if nature not in ALLOWED_NATURE:
            # Registrations that stuffed service lists into nature. Prefer
            # Services when the row looks service-like; otherwise Services is
            # still the safer directory default for filter hygiene.
            businesses.update_one(
                {"_id": doc["_id"]}, {"$set": {"nature": "Services"}}
            )
            doc["nature"] = "Services"
            nature_fixed += 1

    texts = [build_embedding_text(doc) for doc in docs]
    vectors = embed_texts(texts)
    for doc, vector in zip(docs, vectors):
        businesses.update_one({"_id": doc["_id"]}, {"$set": {"embedding": vector}})

    invalidate_filter_cache()
    print(f"PASS: re-embedded {len(docs)} businesses; nature repaired {nature_fixed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
