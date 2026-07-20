"""
Filter allow-list (M3.2).

Filter values (city, industry, etc.) are validated against an allow-list of
actual current values pulled from the live database — not a static
seed-time snapshot — so newly registered businesses stay filterable
(design-doc-v2.md). Any value outside the allow-list is rejected (422),
never passed through as a raw query clause — this is what closes the
NoSQL-injection-shaped gap the architecture review flagged.

Cached in-process; call invalidate_filter_cache() after any write that
could add a new distinct value. No caller does this yet — business
registration (M3.3) isn't implemented in this milestone — but the seam is
ready for it.
"""

import threading

from app.db import get_db

FILTERABLE_FIELDS = ["industry", "city", "state", "nature", "sub_category"]

_cache: dict[str, set] | None = None
_cache_lock = threading.Lock()


class FilterValidationError(Exception):
    """Raised when a filter value isn't in the live allow-list for that field."""


def _load_allowlist() -> dict[str, set]:
    businesses = get_db()["businesses"]
    return {field: set(businesses.distinct(field)) for field in FILTERABLE_FIELDS}


def get_filter_allowlist() -> dict[str, set]:
    global _cache
    if _cache is None:
        with _cache_lock:
            if _cache is None:
                _cache = _load_allowlist()
    return _cache


def invalidate_filter_cache() -> None:
    """Force the next get_filter_allowlist() call to re-query the DB."""
    global _cache
    with _cache_lock:
        _cache = None


def validate_filters(filters: dict[str, str | None] | None) -> dict[str, str]:
    """Return only the non-None filters, after checking each value against
    the live allow-list. Raises FilterValidationError on any invalid value."""
    if not filters:
        return {}

    allowlist = get_filter_allowlist()
    active = {k: v for k, v in filters.items() if v is not None}

    for field, value in active.items():
        if value not in allowlist.get(field, set()):
            raise FilterValidationError(
                f"invalid value for filter '{field}': {value!r} is not a known {field}"
            )
    return active
