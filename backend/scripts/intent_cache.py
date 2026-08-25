"""
Persistent cache for LLM intents (M6.2 measurement support).

WHY THIS EXISTS
---------------
Measuring retrieval takes many runs; inferring intent does not. Without a cache,
every re-run of an experiment re-pays for identical LLM calls -- 75 calls just
to compare three reranking policies over 25 queries, none of which change the
intent. That is wasteful in money, in time, and in exposure: each call sends the
query to a third party, so re-running an experiment re-sends everything.

So intents are fetched ONCE per unique query and stored in
eval_reports/intent_cache.json. Every later measurement reads from disk. A run
that adds no new queries makes zero network calls, and scripts can be re-run
freely without spending anything.

CACHE INVALIDATION
------------------
The key is (normalised query, prompt fingerprint, model). The fingerprint is a
hash of the system prompt, so editing the prompt or switching models
automatically misses the cache rather than silently serving intents the current
configuration would never have produced. That is the failure this design has to
avoid: a stale cache would make a measurement look reproducible while
describing a system that no longer exists.

OFFLINE MODE
------------
INTENT_CACHE_OFFLINE=1 refuses to make any call and fails loudly on a miss.
Use it to prove a measurement spent nothing.
"""

import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import intent as intent_module  # noqa: E402
from app import llm  # noqa: E402
from app.intent import QueryIntent  # noqa: E402
from app.taxonomy import category_names  # noqa: E402

CACHE_PATH = Path(__file__).parent.parent / "eval_reports" / "intent_cache.json"

_calls_made = 0
_cache: dict | None = None


def calls_made() -> int:
    """How many live LLM calls this process has made. Printed by every script
    that uses the cache, so the cost of a run is never a guess."""
    return _calls_made


def _fingerprint() -> str:
    prompt = intent_module._LLM_SYSTEM_PROMPT.format(
        categories="\n".join(f"- {n}" for n in category_names())
    )
    digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12]
    model = os.environ.get("LLM_MODEL", "").strip() or "default"
    return f"{digest}:{model}"


def _load() -> dict:
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            _cache = {"_note": "LLM intents, fetched once per query. See scripts/intent_cache.py.",
                      "entries": {}}
    return _cache


def _save() -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(
        json.dumps(_load(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def get_intent(query: str) -> QueryIntent | None:
    """Cached LLM intent for `query`. Calls the API only on a miss.

    A cached `None` is a real result (the model declined, or every category it
    returned was outside the trusted taxonomy) and is preserved as such -- it
    must not be retried on every run, or negatives would cost calls forever.
    """
    global _calls_made
    cache = _load()
    key = f"{_fingerprint()}|{' '.join(query.lower().split())}"

    if key in cache["entries"]:
        stored = cache["entries"][key]
        return QueryIntent(**stored) if stored else None

    if os.environ.get("INTENT_CACHE_OFFLINE", "").strip() in ("1", "true", "yes"):
        raise SystemExit(
            f"OFFLINE: no cached intent for {query!r}.\n"
            f"Re-run without INTENT_CACHE_OFFLINE to fetch it (one LLM call)."
        )
    if not llm.is_configured():
        raise SystemExit(
            "No cached intent and no LLM configured. Set LLM_API_KEY (plus "
            "LLM_PROVIDER/LLM_BASE_URL/LLM_MODEL) to populate the cache."
        )

    previous = intent_module.INTENT_PROVIDER
    intent_module.INTENT_PROVIDER = "llm"  # strict: never cache a fallback as an LLM result
    try:
        result = intent_module.infer_intent(query)
    finally:
        intent_module.INTENT_PROVIDER = previous
    _calls_made += 1

    cache["entries"][key] = result.to_dict() if result else None
    _save()
    return result


def warm(queries: list[str]) -> tuple[int, int]:
    """Ensure every query is cached. Returns (already cached, newly fetched)."""
    before = _calls_made
    for query in queries:
        get_intent(query)
    fetched = _calls_made - before
    return len(queries) - fetched, fetched
