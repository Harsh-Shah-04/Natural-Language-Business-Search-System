"""
Business registration (M5.2).

Turns a validated registration payload into a stored, immediately searchable
business document — reusing the exact embedding pipeline the bulk seed uses
(app/embeddings.build_embedding_text + embed_texts), so there is one and only
one place embeddings are produced.

The written document has the same shape as a seeded one (see scripts/seed.py's
COLUMNS) plus the optional `address` field the form adds, so the search
pipeline reads it back with no changes. After a successful insert we invalidate
the filter allow-list cache (app/filters.py) so a business registered in a new
city / industry / sub_category becomes a valid filter value right away — the
caller that seam was built for.
"""

from pymongo.errors import DuplicateKeyError, PyMongoError

from app.db import get_db
from app.embeddings import build_embedding_text, embed_texts
from app.filters import invalidate_filter_cache


class BusinessConflictError(Exception):
    """Raised when a business with the same (unique) name already exists."""


class RegistrationUnavailableError(Exception):
    """Raised when the embedding model or the database is unavailable."""


def register_business(data: dict) -> dict:
    """Embed, insert, and return {id, business_name}. `data` is a validated
    BusinessRegistration dump. Raises BusinessConflictError on a duplicate
    name and RegistrationUnavailableError on a backend failure."""
    # Build the stored document explicitly, in the seeded field order, so its
    # shape matches existing documents. contact_person/specialties aren't
    # collected by the form; store them as None to keep the collection uniform
    # (build_embedding_text tolerates the None specialties).
    doc = {
        "business_name": data["business_name"],
        "nature": data["nature"],
        "industry": data["industry"],
        "sub_category": data["sub_category"],
        "city": data["city"],
        "state": data["state"],
        "contact_person": None,
        "email": data.get("email"),
        "website": data.get("website"),
        "phone": data.get("phone"),
        "business_description": data["business_description"],
        "products_services": data["products_services"],
        "keywords": data.get("keywords"),
        "specialties": None,
        "address": data.get("address"),
    }

    # Embed before insert (same order as seed.py): if embedding fails we never
    # write a document without its vector.
    try:
        doc["embedding"] = embed_texts([build_embedding_text(doc)])[0]
    except Exception as e:
        raise RegistrationUnavailableError(f"embedding model unavailable: {e}") from e

    try:
        businesses = get_db()["businesses"]
        result = businesses.insert_one(doc)
    except DuplicateKeyError as e:
        raise BusinessConflictError(
            f"a business named {doc['business_name']!r} is already registered"
        ) from e
    except (PyMongoError, RuntimeError) as e:
        # RuntimeError covers get_db() failing before the write is attempted
        # (e.g. MONGODB_URI unset) — a backend-unavailable condition (503).
        raise RegistrationUnavailableError(
            f"registration backend unavailable: {e}"
        ) from e

    # A newly introduced industry/city/state/nature/sub_category must become a
    # valid filter value immediately (design-doc-v2.md); this is the write the
    # invalidate_filter_cache() seam was waiting for.
    invalidate_filter_cache()

    return {"id": str(result.inserted_id), "business_name": doc["business_name"]}
