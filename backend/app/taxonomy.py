"""
Trusted service taxonomy (M6.1).

The closed set of service categories the query-intent layer is allowed to
classify into. Loaded from app/taxonomy.json, which scripts/build_taxonomy.py
generates from the checked-in seed dataset.

WHY THIS IS NOT app/filters.py's ALLOW-LIST
-------------------------------------------
Both modules answer a question shaped like "what sub_categories exist?", and
they must answer it from *different* sources, because they are trusted
differently:

  filters.py   -> businesses.distinct("sub_category"), live from the
                  collection. Correct there: a business registered in a new
                  city/category must become filterable immediately
                  (design-doc-v2.md), and a bad value can only ever cause an
                  over-permissive $match on a field the user already chose.

  taxonomy.py  -> the seed dataset, fixed at build time. Correct here because
                  POST /api/businesses is UNAUTHENTICATED and `sub_category`
                  is free text (app/schemas.py). Any stranger can put a string
                  into the collection. Today the live corpus already carries
                  the evidence: a QA registration introduced the sub_category
                  "parlour", which is not a service category by any definition.

The distinction matters the moment intent classification exists, and matters
much more when its LLM provider lands (M6.2), because the taxonomy is what
goes into the prompt as trusted, closed-set content. If the taxonomy came from
the collection, an unauthenticated POST would place attacker-authored text
inside every user's intent prompt -- stored prompt injection, with the write
primitive already publicly reachable. Sourcing from the dataset removes the
write primitive entirely rather than trying to sanitise its contents, which
is why this is a build step and not a validator: a blocklist over free text is
a losing position, an unreachable source is not.

Consequence, and it is intentional: a business registered in a category the
seed dataset never had is still stored, still searchable, and still
filterable -- it simply cannot become a *classification target* for intent
until someone regenerates the taxonomy and reviews the diff.
"""

import json
import threading
from pathlib import Path

TAXONOMY_PATH = Path(__file__).resolve().parent / "taxonomy.json"

_taxonomy: dict | None = None
_lock = threading.Lock()


class TaxonomyUnavailableError(Exception):
    """Raised when app/taxonomy.json is missing or malformed."""


def _load() -> dict:
    try:
        data = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise TaxonomyUnavailableError(
            f"{TAXONOMY_PATH.name} not found -- run scripts/build_taxonomy.py"
        ) from e
    except json.JSONDecodeError as e:
        raise TaxonomyUnavailableError(f"{TAXONOMY_PATH.name} is not valid JSON: {e}") from e

    categories = data.get("categories")
    if not isinstance(categories, dict) or not categories:
        raise TaxonomyUnavailableError(f"{TAXONOMY_PATH.name} has no categories")
    return data


def get_taxonomy() -> dict:
    """The whole taxonomy document, loaded once per process."""
    global _taxonomy
    if _taxonomy is None:
        with _lock:
            if _taxonomy is None:  # re-check: another thread may have won the race
                _taxonomy = _load()
    return _taxonomy


def get_categories() -> dict[str, dict]:
    """category name -> profile. Same ordering every call (JSON insertion
    order, which the generator writes sorted)."""
    return get_taxonomy()["categories"]


def category_names() -> list[str]:
    return list(get_categories().keys())


def is_known_category(name: str) -> bool:
    """Whether `name` is a trusted category. The only gate any caller should
    use before treating a category string as taxonomy content."""
    return name in get_categories()


def resolve_category(text: str) -> str | None:
    """Map free text onto a trusted category name, or None if it cannot be
    mapped safely.

    This is how a model-authored exclusion ("cybersecurity firm") becomes a
    filterable sub_category ("Cybersecurity"). It matches against the TRUSTED
    TAXONOMY'S OWN NAMES -- never against business descriptions, and never as a
    loose substring of arbitrary document text. "cybersecurity" appearing in
    some company's description must never cause filtering; only the taxonomy
    label itself may.

    Deliberately conservative, because the failure modes are asymmetric. A
    missed mapping means an exclusion is ignored and the user sees a result
    they did not want -- annoying. A wrong mapping silently deletes a whole
    category from the results -- much worse, and invisible to the user. So:

      - exact match on the normalised name wins outright;
      - otherwise the category name must appear as a whole phrase in the text
        ("cybersecurity firm" contains "cybersecurity");
      - ambiguity resolves to the LONGEST matching name, so "Food Packaging"
        beats a hypothetical "Packaging" rather than both applying;
      - anything unmatched returns None and filters nothing.

    Free text that names no taxonomy category -- "WhatsApp bot companies",
    or a hallucinated value -- therefore has no effect at all, which is the
    required behaviour for unknown exclusions.
    """
    normalized = " ".join(text.lower().split())
    if not normalized:
        return None

    categories = get_categories()
    for name in categories:
        if normalized == name.lower():
            return name

    matches = [name for name in categories if name.lower() in normalized]
    if not matches:
        return None
    return max(matches, key=len)


def resolve_categories(texts: list[str]) -> list[str]:
    """Every trusted category the given free-text values map to, de-duplicated
    and order-preserving. Values that map to nothing are dropped silently --
    see resolve_category for why that is the safe direction."""
    resolved: list[str] = []
    for text in texts:
        name = resolve_category(text)
        if name and name not in resolved:
            resolved.append(name)
    return resolved


def profile_text(category: dict) -> str:
    """The text representing a category to the embedding model.

    Deliberately built from the same fields app/embeddings.build_embedding_text
    reads (name, products/services, keywords, specialties) so a query is
    compared against categories in the same vocabulary the documents were
    indexed in. business_description is excluded for the reason M4.1.1
    excluded it from keyword search: its templated boilerplate is near-identical
    across all 120 rows and carries no discriminative signal.
    """
    parts = [
        category.get("sub_category") or "",
        category.get("industry") or "",
        category.get("products_services") or "",
        category.get("keywords") or "",
        category.get("specialties") or "",
    ]
    return " ".join(p.strip() for p in parts if p and p.strip())


def describe_need(category: dict) -> str:
    """The human-readable "what you need" phrase for a category.

    Prefers the `need` paraphrase when present -- that field is reserved for
    the LLM provider (M6.2), which can write "phishing protection and employee
    security awareness" because it has world knowledge this corpus does not.
    Until then, falls back to the category's own specialties, which is a claim
    the dataset actually supports. Nothing here is hand-authored: the panel can
    never assert more understanding than its source provides.
    """
    need = (category.get("need") or "").strip()
    if need:
        return need
    return (category.get("specialties") or category.get("sub_category") or "").strip()
