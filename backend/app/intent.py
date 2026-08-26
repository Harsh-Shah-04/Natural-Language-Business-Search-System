"""
Query understanding / intent layer (M6.1).

Turns a raw user query into a structured QueryIntent -- what the person is
actually asking for -- before any retrieval runs. This is the stage the
architecture did not previously have: search_businesses() embedded the raw
string and went straight to Atlas, so no object anywhere in the system
represented what the user *meant*, and therefore the UI had nothing to show
them beyond a float and matched_via.

PROVIDERS
---------
The provider is swappable and QueryIntent is the contract. All of them return
exactly this shape, so swapping one changes no caller and no frontend code.

  auto       (default)         llm, then fixture, then embedding, then
                               nothing. Each step is tried only if the one
                               before it produced nothing.
  llm        (M6.2)            an LLM constrained to the same closed taxonomy.
                               Strict: no fallback, see infer_intent().
  embedding                    zero-shot classification over the trusted
                               40-category taxonomy using the bge-small model
                               already loaded in-process. No API key, no new
                               dependency, ~1ms after warm-up.
  fixture                      checked-in intents for known demo queries,
                               labelled as such in the response.
  off                          no intent panel; /api/search returns results
                               exactly as it did before this module existed.
                               Note that RERANK_POLICY="intent-gated" still
                               consults names_a_service() -- routing is a
                               retrieval concern, independent of whether an
                               intent is displayed.

WHAT THE EMBEDDING PROVIDER CAN AND CANNOT DO -- MEASURED, NOT ASSUMED
----------------------------------------------------------------------
scripts/measure_intent.py, against this corpus:

  queries that NAME a service ("cybersecurity firm for penetration testing",
  and all 15 keyword/semantic/synonym queries in the golden set)
      top-1 cosine similarity to the correct category profile: min 0.597

  queries that describe a SYMPTOM ("my company keeps getting suspicious
  emails..."), and outright gibberish ("asdfgh qwerty zxcvbn")
      top-1 cosine similarity:                                 max 0.560

Two things follow, and both matter.

First, the gate is absolute similarity, not softmax and not margin. An earlier
version of this module ranked categories by softmax over cosine and gated on
the top probability. That is a *relative* score: it renormalises whatever it is
given, so gibberish 0.005 away from its nearest neighbour still came out at
"0.263 confidence" and the panel confidently announced Cybersecurity for
"asdfgh qwerty zxcvbn". Margin fails too -- named-service queries go as low as
0.020 and symptom queries as high as 0.023, which overlap. Absolute similarity
is the only one of the three that separates the classes.

Second, and this is the finding that should drive M6.2: the bi-encoder cannot
tell a symptom query from gibberish. 0.543 versus 0.532. Not a tuning problem
-- there is no threshold in that gap. The category profile is written in
service vocabulary ("SOC, penetration testing, ISO27001") and the query is
written in symptom vocabulary ("employees falling for scams"); bridging them
needs world knowledge a 384-dim bi-encoder does not carry. So this provider is
deliberately SILENT on exactly the query class the reviewer raised, and that
silence is the honest, measured argument for an LLM rather than an assumed one.

WHY CLASSIFY THE QUERY, NOT THE RESULTS
---------------------------------------
Inferring intent from the top results would be cheaper and would score better
on any metric, because it would agree with retrieval by construction. It would
also be post-hoc rationalisation: when retrieval is wrong the panel would
confidently explain the wrong answer, which is worse than showing nothing.
Classification runs on the query alone, before retrieval, so the panel and the
results can visibly disagree -- and when they do, that is information.

FAILURE BEHAVIOUR
-----------------
Intent is a presentation and (later) routing layer, never a hard dependency.
Any failure -- taxonomy missing, model unavailable, provider unknown -- returns
None, and search proceeds exactly as it did before. Same rule the reranker
follows in app/search.py.
"""

import json
import os
import threading
import time
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app import llm
from app.embeddings import embed_texts
from app.taxonomy import (
    TaxonomyUnavailableError,
    category_names,
    describe_need,
    get_categories,
    is_known_category,
    profile_text,
)

# Minimum cosine similarity between the query and a category profile before a
# category may be reported at all. 0.58 sits in the empty band between the
# lowest-scoring named-service query in the golden set (0.597) and the
# highest-scoring symptom/gibberish query (0.560) -- see the module docstring
# and scripts/measure_intent.py.
#
# Honest caveat: that band was measured on 15 positives and 6 negatives. It is
# a clean separation on the data available, not a calibrated threshold, and it
# should be re-derived if the corpus or the query mix changes.
MIN_SIMILARITY = 0.58

# A second (or third) category is reported only if it is within this much of
# the top category's similarity. Real queries do span two categories -- "a
# notice from the tax department" is genuinely both Chartered Accountants and
# GST Consultants -- so a hard top-1 would under-report, while an unbounded
# list would pad the panel with noise.
#
# 0.04 sits in the empty band between the two, measured over all 42 queries in
# the golden + situational + negative sets. Only six produce a secondary at
# all, and they separate cleanly:
#
#   gap     query                                            verdict
#   0.0148  multi-04 "both cold storage AND last-mile"       genuine multi-intent
#   0.0163  multi-03 "both GST filing AND tax audits"        genuine multi-intent
#   0.0203  sem-01   "help filing my business taxes"         genuine multi-intent
#   0.0343  multi-05 "both interiors AND electrical work"    genuine multi-intent
#   ------------------------------------------------------- 0.04 threshold
#   0.0432  syn-04   -> Digital Marketing, Advertising       false (truth: Branding only)
#   0.0493  whats-pos-> PR Agencies                          false ("ai agent" ~ "PR Agencies")
#
# The two rejected cases are lexical collisions, not meaning: "ai agent" is
# close to "PR Agencies" as strings, and that is exactly the M4.1 "business
# trip" / "business insurance" failure surfacing in the panel instead of the
# ranking. A panel asserting understanding it does not have is worse than a
# panel showing one category, so the threshold sits nearer the legitimate side
# of the band (0.0057 of headroom above the widest genuine gap).
#
# This affects DISPLAY and expanded_query only. names_a_service() reads
# MIN_SIMILARITY alone, so reranking routing and retrieval are untouched --
# verified before/after across all 42 queries.
SECONDARY_MARGIN = 0.04
MAX_CATEGORIES = 3

# Caps on model-authored text (M6.2). underlying_need and exclusions are
# rendered in the UI and expanded_query can reach retrieval, so none of them
# may be unbounded just because a model produced them. React escapes markup,
# so this is about size and control characters, not XSS.
LLM_MAX_NEED_CHARS = 200
LLM_MAX_EXPANDED_CHARS = 400
LLM_MAX_EXCLUSIONS = 5
LLM_MAX_EXCLUSION_CHARS = 80

INTENT_PROVIDER = os.environ.get("INTENT_PROVIDER", "auto").strip().lower()

# In-process LLM intent cache (M6.5). Two independent reasons, both measured:
#
# 1. REPRODUCIBILITY. scripts/measure_intent_determinism.py ran the same query
#    20 times at temperature=0 and got 0.05-0.25 exact agreement: the category
#    is stable (0.80-1.00, correct in 20/20) but underlying_need and
#    expanded_query are re-worded almost every call. Scoring each distinct
#    expansion through retrieval, the reviewer's own query passed 10 times and
#    failed 8. Caching does not make the first answer better -- it makes it
#    FIXED, so the same query cannot give a user two different answers.
# 2. LATENCY AND COST. p50 ~2.5s, max ~9s per call, and every call ships the
#    user's query to a third party.
#
# Deliberately small: a dict with an insertion-ordered FIFO bound and a TTL.
# No distributed cache, no persistence -- a process restart simply re-fetches.
# Only successful intents are stored; a None (model declined, or every category
# was hallucinated) is never cached, so a transient failure cannot pin a query
# to "no intent" for the whole TTL.
INTENT_CACHE_SIZE = int(os.environ.get("INTENT_CACHE_SIZE", "512"))
INTENT_CACHE_TTL_SECONDS = float(os.environ.get("INTENT_CACHE_TTL_SECONDS", "3600"))

_intent_cache: "OrderedDict[str, tuple[float, QueryIntent]]" = OrderedDict()
_intent_cache_lock = threading.Lock()
_cache_hits = 0
_cache_misses = 0

FIXTURES_PATH = Path(__file__).resolve().parent / "intent_fixtures.json"

_profiles: tuple[list[str], list[list[float]]] | None = None
_profiles_lock = threading.Lock()

_fixtures: dict[str, dict] | None = None
_fixtures_lock = threading.Lock()

_state_lock = threading.Lock()
_state = "not_started"  # not_started -> loading -> ready | error | disabled
_state_detail: str | None = None
# Kept separately from _state because in "auto" a fallback provider answers
# after an LLM failure and would otherwise overwrite the state with "ready" --
# leaving a model that is down completely invisible, which is the silent
# degradation this module refuses to allow for INTENT_PROVIDER=llm.
_last_llm_error: str | None = None


@dataclass(frozen=True)
class QueryIntent:
    """What the user is actually asking for."""

    # Natural-language statement of the need, for display. Sourced from the
    # taxonomy or a fixture, never composed at request time.
    underlying_need: str
    # Categories from the TRUSTED taxonomy only. Never free text, never a value
    # sourced from the businesses collection -- see app/taxonomy.py.
    service_categories: list[str]
    # The user's words plus the inferred categories' service vocabulary.
    # Computed and returned; not yet used for retrieval (see app/search.py).
    expanded_query: str
    # Reserved for negation handling. No query in the measured situational set
    # contains a negation, so nothing populates this yet and nothing consumes
    # it -- the field exists so the contract does not change when it does.
    exclusions: list[str] = field(default_factory=list)
    # For the embedding provider this is the top-1 cosine similarity itself,
    # not a softmax probability. It is the number the MIN_SIMILARITY gate is
    # applied to, so what the client sees is the quantity actually being
    # trusted rather than a renormalised restatement of it.
    confidence: float = 0.0
    # Which provider produced this, so a reader -- and the UI -- can tell a
    # classifier result from a checked-in fixture without guessing.
    source: str = "unknown"

    def to_dict(self) -> dict:
        return asdict(self)


def get_intent_health() -> dict[str, str]:
    with _state_lock:
        health = {"status": _state, "provider": INTENT_PROVIDER}
        if _state_detail:
            health["detail"] = _state_detail
        if _last_llm_error:
            # Present even when status is "ready": under "auto" a healthy
            # fallback masks an unhealthy model, and an operator needs to see
            # that they are paying for an LLM that is not answering.
            health["llm_error"] = _last_llm_error
        return health


def _set_llm_error(detail: str | None) -> None:
    global _last_llm_error
    with _state_lock:
        _last_llm_error = detail


def _set_state(state: str, detail: str | None = None) -> None:
    global _state, _state_detail
    with _state_lock:
        _state = state
        _state_detail = detail


# ---- embedding provider ---------------------------------------------------


def _get_profiles() -> tuple[list[str], list[list[float]]]:
    """(category names, profile vectors), embedded once per process.

    40 vectors of 384 floats -- trivial to hold, and it means classification
    costs one query embedding plus 40 dot products, not 40 model calls.
    """
    global _profiles
    if _profiles is None:
        with _profiles_lock:
            if _profiles is None:  # re-check: another thread may have won the race
                _set_state("loading")
                try:
                    categories = get_categories()
                    names = list(categories.keys())
                    vectors = embed_texts([profile_text(categories[n]) for n in names])
                except Exception as e:
                    _set_state("error", str(e))
                    raise
                _profiles = (names, vectors)
                _set_state("ready")
    return _profiles


def classify(query: str) -> list[tuple[str, float]]:
    """Every taxonomy category scored against `query`, best first.

    Cosine similarity is a plain dot product here: embed_texts() L2-normalizes,
    and so did the vectors these profiles were built from.
    """
    names, profile_vectors = _get_profiles()
    query_vector = embed_texts([query])[0]
    similarities = [
        sum(q * p for q, p in zip(query_vector, profile_vector))
        for profile_vector in profile_vectors
    ]
    return sorted(zip(names, similarities), key=lambda pair: pair[1], reverse=True)


def _select(ranked: list[tuple[str, float]]) -> list[tuple[str, float]]:
    top_name, top_similarity = ranked[0]
    if top_similarity < MIN_SIMILARITY:
        return []  # below the gate: the classifier does not know, so say nothing
    selected = [(top_name, top_similarity)]
    for name, similarity in ranked[1:MAX_CATEGORIES]:
        if similarity >= top_similarity - SECONDARY_MARGIN:
            selected.append((name, similarity))
    return selected


def names_a_service(query: str) -> bool:
    """Whether the query names the service it wants, rather than describing a
    symptom. Never raises; unknown means False.

    This is the signal RERANK_POLICY="intent-gated" routes on, and it is
    deliberately NOT "did some provider return an intent". Those were the same
    thing while the classifier was the only provider, and they stop being the
    same thing the moment the LLM provider exists: the LLM answers symptom
    queries too, which is precisely the class where the cross-encoder was
    measured to hurt. Gating on "an intent exists" would therefore switch
    reranking ON for the queries it damages and OFF for the queries it helps --
    exactly backwards.

    So routing keeps asking the original question, which the classifier's
    similarity gate is a measured proxy for (named-service min 0.597 vs
    symptom/gibberish max 0.563), regardless of which provider is displaying
    an intent to the user.
    """
    try:
        return classify(query)[0][1] >= MIN_SIMILARITY
    except Exception:
        return False


def _build_expansion(chosen: list[str], query: str) -> str:
    """The user's words plus the chosen categories' service vocabulary.

    This is the bridge from symptom language to service language that a bare
    embedding of the raw query cannot make. Returned but NOT yet used for
    retrieval -- see INTENT_EXPANSION_ENABLED in app/search.py.
    """
    categories = get_categories()
    vocabulary = " ".join(
        profile_text(categories[name]) for name in chosen if is_known_category(name)
    )
    return f"{query.strip()} {vocabulary}".strip()


def _embedding_intent(query: str) -> QueryIntent | None:
    selected = _select(classify(query))
    if not selected:
        return None

    # Defensive, and cheap: only names still in the trusted taxonomy may leave
    # this function. classify() can only produce taxonomy names today, but this
    # is the gate that must hold if that ever changes.
    chosen = [name for name, _ in selected if is_known_category(name)]
    if not chosen:
        return None

    categories = get_categories()
    needs = [describe_need(categories[name]) for name in chosen]

    return QueryIntent(
        underlying_need="; ".join(n for n in needs if n),
        service_categories=chosen,
        expanded_query=_build_expansion(chosen, query),
        exclusions=[],
        confidence=round(float(selected[0][1]), 4),
        source="embedding-taxonomy",
    )


# ---- llm provider (M6.2) --------------------------------------------------

# The task is classification into a closed set plus a short paraphrase -- not
# free generation. Everything the model may choose from is listed in the
# prompt, and everything it returns is re-checked against the same list on the
# way back (_llm_intent), because a prompt instruction is not an access
# control: a model can always emit a string it was told not to.
#
# The examples deliberately avoid every query in the measured sets
# (scripts/measure_intent.py) so the evaluation is not being answered in the
# prompt. The second one exists to teach the negation rule by demonstration,
# since stating it in prose is reliably not enough.
_LLM_SYSTEM_PROMPT = """\
You map a described business situation to service categories from a fixed list.

The person describes a PROBLEM or a SITUATION, usually without naming the \
service that solves it. Your job is to infer the underlying need and choose \
the categories that address it. Do not wait to be told the service name.

ALLOWED CATEGORIES -- you may only choose from these exact strings:
{categories}

RULES
1. service_categories contains only strings copied exactly from the list \
above. If nothing in the list addresses the need, return an empty array. \
Never invent a category, never adapt one, never return a near-miss spelling.
2. Infer only from what the person actually wrote. Do not invent facts about \
them -- not their industry, size, budget, location, or urgency.
3. underlying_need is a short phrase naming the SERVICE NEED you inferred, \
not a restatement of the situation. "Our vans keep breaking down" becomes \
"fleet maintenance", not "vans that keep breaking down".
4. NEGATION: if the person says they do NOT want something, that thing goes \
in exclusions and must NOT appear in service_categories. Wanting to avoid \
something is never a reason to recommend it.
5. expanded_query is the vocabulary a business directory would use for this \
need: a few words, lowercase, no punctuation, no sentence.
6. confidence is 0.0-1.0 for how sure you are that the chosen categories \
address the need. Use a low value when you are guessing, and do not inflate it.

Reply with ONE JSON object and nothing else -- no prose, no markdown fence:
{{"underlying_need": string, "service_categories": [string], \
"expanded_query": string, "exclusions": [string], "confidence": number}}

EXAMPLES

Situation: "Half our stock goes missing somewhere between the factory and the \
shop every quarter."
{{"underlying_need": "inventory tracking and managed storage", \
"service_categories": ["Warehousing"], "expanded_query": "inventory \
management fulfillment storage stock control", "exclusions": [], \
"confidence": 0.82}}

Situation: "We need someone to build our internal tools, but I don't want \
WhatsApp bot companies."
{{"underlying_need": "custom internal software development", \
"service_categories": ["Software Development"], "expanded_query": "custom \
software internal tools web applications", "exclusions": ["WhatsApp bot \
companies"], "confidence": 0.78}}"""


def _clean_text(value, limit: int) -> str:
    """Model output on its way to a UI: single line, bounded, stripped."""
    if not isinstance(value, str):
        return ""
    collapsed = " ".join(value.split())  # also removes newlines / control runs
    return collapsed[:limit].strip()


def _parse_llm_json(completion: str, prefill: str = "{") -> dict:
    """Parse the model's reply, tolerating the usual envelope noise.

    The assistant turn is prefilled with "{" so a well-behaved reply continues
    from inside the object and needs the prefill put back. A model that ignores
    the prefill and emits a whole fenced object instead must not be broken by
    that concatenation, so the prefill is only restored when the completion
    does not already open its own object. Anything still unparseable degrades
    to a ValueError -- never to a crash on the search path.
    """
    text = completion.strip()
    if not text.startswith(("{", "```")):
        text = prefill + completion
    text = text.strip()
    if text.startswith("```"):
        # ```json\n{...}\n```  ->  {...}
        fenced = text[3:].split("```", 1)[0]
        text = fenced.removeprefix("json").strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in response")
    parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("response JSON was not an object")
    return parsed


def _llm_intent(query: str) -> QueryIntent | None:
    """Cached at this level, not around infer_intent(), because only the LLM
    path is expensive and nondeterministic. The classifier is ~10ms and returns
    the same answer for the same input; caching it would add a code path for no
    gain."""
    global _cache_hits, _cache_misses

    if not llm.is_configured():
        _set_state("disabled", "LLM_API_KEY is not set")
        return None

    # Keyed on the normalised query plus the model, so switching LLM_MODEL does
    # not serve answers the current model never produced.
    cache_key = f"{llm.describe()}|{_normalize(query)}"
    cached = _cache_get(cache_key)
    if cached is not None:
        with _intent_cache_lock:
            _cache_hits += 1
        _set_state("ready", f"{llm.describe()}; cache hit")
        return cached
    with _intent_cache_lock:
        _cache_misses += 1

    prompt = _LLM_SYSTEM_PROMPT.format(
        categories="\n".join(f"- {name}" for name in category_names())
    )
    # Prefill "{" so the reply starts inside the JSON object; _parse_llm_json
    # restores it, since complete() returns only the generated part.
    completion = llm.complete(prompt, f"Situation: {query.strip()}", prefill="{")
    payload = _parse_llm_json(completion, prefill="{")

    # THE SECURITY GATE. Categories are re-validated against the trusted
    # taxonomy here, not trusted because the prompt said so. Unknown values are
    # discarded silently rather than rejected wholesale: a model that returns
    # two good categories and one hallucinated one should still be useful, and
    # dropping the bad one is strictly safer than keeping it. Nothing that
    # fails is_known_category() can reach the response, the UI, or a filter.
    raw_categories = payload.get("service_categories")
    if not isinstance(raw_categories, list):
        raw_categories = []
    chosen, dropped = [], 0
    for value in raw_categories:
        if isinstance(value, str) and is_known_category(value):
            if value not in chosen:
                chosen.append(value)
        else:
            dropped += 1
    chosen = chosen[:MAX_CATEGORIES]

    underlying_need = _clean_text(payload.get("underlying_need"), LLM_MAX_NEED_CHARS)

    # Must be a list. A bare string here would otherwise be iterated one
    # character at a time and turn into a list of single-letter "exclusions".
    raw_exclusions = payload.get("exclusions")
    if not isinstance(raw_exclusions, list):
        raw_exclusions = []
    exclusions = [
        cleaned
        for cleaned in (
            _clean_text(e, LLM_MAX_EXCLUSION_CHARS) for e in raw_exclusions
        )
        if cleaned
    ][:LLM_MAX_EXCLUSIONS]

    # Nothing usable to show. An exclusion-only reply IS usable -- "I don't
    # want WhatsApp bot companies" legitimately has no positive category -- so
    # the test is whether anything at all was understood, not whether a
    # category was chosen.
    if not chosen and not exclusions:
        detail = "model returned no usable categories or exclusions"
        _set_state("error", detail)
        _set_llm_error(detail)
        return None
    # A pure-negation query legitimately has no positive need -- "I don't want
    # WhatsApp bot companies" is a complete intent consisting only of an
    # exclusion, and scripts/measure_intent_determinism.py showed the model
    # returns "" for underlying_need on some of those runs. Dropping the intent
    # there would throw away the exclusion, which is the only thing the user
    # actually told us. Nothing is invented to fill the gap: the field stays
    # empty and the UI omits that line.
    if not underlying_need and not exclusions:
        detail = "model returned no underlying_need"
        _set_state("error", detail)
        _set_llm_error(detail)
        return None

    try:
        confidence = float(payload.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = min(max(confidence, 0.0), 1.0)

    # Prefer the model's expansion, fall back to the taxonomy's own vocabulary.
    # Only ever a retrieval input when INTENT_EXPANSION_ENABLED is on, which it
    # is not by default -- see app/search.py.
    expanded = _clean_text(payload.get("expanded_query"), LLM_MAX_EXPANDED_CHARS)
    if not expanded:
        expanded = _build_expansion(chosen, query) if chosen else query.strip()

    _set_state("ready", llm.describe() + (f"; dropped {dropped} unknown" if dropped else ""))
    _set_llm_error(None)
    result = QueryIntent(
        underlying_need=underlying_need,
        service_categories=chosen,
        expanded_query=expanded,
        exclusions=exclusions,
        confidence=round(confidence, 4),
        source="llm",
    )
    # Only successes are cached: a None must stay retryable, or one bad minute
    # would pin a query to "no intent" for the whole TTL.
    _cache_put(cache_key, result)
    return result


# ---- fixture provider -----------------------------------------------------


def _normalize(query: str) -> str:
    return " ".join(query.lower().split())


# ---- llm intent cache -----------------------------------------------------


def _cache_get(key: str) -> QueryIntent | None:
    """Never raises: a cache fault must degrade to a live call, not an error."""
    try:
        with _intent_cache_lock:
            entry = _intent_cache.get(key)
            if entry is None:
                return None
            stored_at, intent = entry
            if time.monotonic() - stored_at > INTENT_CACHE_TTL_SECONDS:
                _intent_cache.pop(key, None)
                return None
            _intent_cache.move_to_end(key)  # keep hot entries away from eviction
            return intent
    except Exception:
        return None


def _cache_put(key: str, intent: QueryIntent) -> None:
    try:
        with _intent_cache_lock:
            _intent_cache[key] = (time.monotonic(), intent)
            _intent_cache.move_to_end(key)
            while len(_intent_cache) > max(INTENT_CACHE_SIZE, 1):
                _intent_cache.popitem(last=False)  # evict least recently used
    except Exception:
        pass


def get_cache_stats() -> dict[str, int]:
    with _intent_cache_lock:
        return {"entries": len(_intent_cache), "hits": _cache_hits, "misses": _cache_misses}


def clear_intent_cache() -> None:
    """Drop every cached intent. Used by tests and measurement scripts that
    need a guaranteed cold call; not wired to any endpoint."""
    global _cache_hits, _cache_misses
    with _intent_cache_lock:
        _intent_cache.clear()
        _cache_hits = 0
        _cache_misses = 0


def _get_fixtures() -> dict[str, dict]:
    global _fixtures
    if _fixtures is None:
        with _fixtures_lock:
            if _fixtures is None:
                try:
                    raw = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))
                    entries = raw.get("intents", [])
                except (OSError, json.JSONDecodeError):
                    entries = []
                _fixtures = {_normalize(e["query"]): e for e in entries if e.get("query")}
    return _fixtures


def _fixture_intent(query: str) -> QueryIntent | None:
    """Checked-in intent for a known query, matched on exact normalised text.

    Exact-match only, deliberately. A fuzzy fixture would fire on queries it
    was never written for and would be indistinguishable from a working intent
    layer -- which is the exact illusion this milestone exists to remove. The
    returned intent carries source="fixture", and the UI renders that
    provenance, so a fixture can never be mistaken for inference.
    """
    entry = _get_fixtures().get(_normalize(query))
    if not entry:
        return None

    # Fixtures are checked-in data, but they are still data: a category is only
    # honoured if it is in the trusted taxonomy, exactly as for the classifier.
    chosen = [c for c in entry.get("service_categories", []) if is_known_category(c)]
    if not chosen:
        return None

    return QueryIntent(
        underlying_need=entry.get("underlying_need", ""),
        service_categories=chosen,
        expanded_query=entry.get("expanded_query") or _build_expansion(chosen, query),
        exclusions=entry.get("exclusions", []),
        confidence=float(entry.get("confidence", 0.0)),
        source="fixture",
    )


# ---- dispatch -------------------------------------------------------------


def infer_intent(query: str) -> QueryIntent | None:
    """Structured intent for `query`, or None if unavailable or inconclusive.

    Never raises. Callers treat None as "no intent panel, search as normal" --
    intent is additive, and a failure here must not cost the user their
    results.
    """
    provider = INTENT_PROVIDER

    if provider in ("off", "none", "disabled"):
        _set_state("disabled")
        return None

    if provider not in ("auto", "llm", "embedding", "fixture"):
        _set_state("error", f"unknown INTENT_PROVIDER {provider!r}")
        return None

    try:
        if provider in ("auto", "llm"):
            # Every LLM failure mode -- no key, timeout, HTTP error, bad JSON,
            # missing fields, every category hallucinated -- lands here as
            # either None or an exception, and neither is allowed to cost the
            # user their results.
            try:
                result = _llm_intent(query)
            except Exception as e:
                detail = f"{type(e).__name__}: {e}"
                _set_state("error", f"llm: {detail}")
                _set_llm_error(detail)
                result = None
            if result is not None:
                _set_llm_error(None)  # recovered
                return result
            if provider == "llm":
                # Strict on purpose. An operator who asked for LLM intent and
                # silently got classifier intent instead would have no way to
                # notice the model was down. In "auto" the chain continues.
                return None

        if provider in ("auto", "fixture"):
            fixture = _fixture_intent(query)
            if fixture is not None:
                _set_state("ready")
                return fixture
            if provider == "fixture":
                return None

        return _embedding_intent(query)
    except TaxonomyUnavailableError as e:
        _set_state("error", str(e))
        return None
    except Exception as e:
        _set_state("error", str(e))
        return None


def warm_up() -> None:
    """Precompute the profile vectors so no live request pays for them.

    Warms under every provider, including "off" and "llm": names_a_service()
    needs the same vectors for RERANK_POLICY="intent-gated", and that routing
    runs whether or not an intent is being displayed.

    Failures are already recorded in the health state; swallow here so a
    background warm-up thread cannot crash with a traceback (app/main.py).
    """
    try:
        _get_profiles()
    except Exception:
        pass
