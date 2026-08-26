"""
Is BM25 helping or hurting once the query is intent-expanded? (M6.3, measurement only)

THE QUESTION
------------
One example (the reviewer's own query under expansion) showed the keyword arm
promoting Corporate Training over Cybersecurity, because the LLM's expansion
contained the token "training". That is a single anecdote. Removing a retrieval
arm on an anecdote is how the "never rerank" trap nearly happened: a change
that looks right on one class of query can quietly cost another.

So this measures the full matrix instead of acting on the anecdote.

ARMS
----
Two query forms crossed with two retrieval modes, plus the concatenation:

                    vector-only            hybrid (vector + BM25 + RRF)
  raw               Original Vector        Original Hybrid   <- production today
  expanded          Expanded Vector        Expanded Hybrid
  raw+expanded      Both Vector            Both Hybrid

"Original Vector" is a control and is the reason this matrix has four cells
instead of the three the question strictly needs. Without it, a jump from
Original Hybrid to Expanded Vector is unattributable -- it could be the
expansion, or it could be dropping BM25, and those imply completely different
architectural changes.

READING THE RESULT
------------------
  Expanded Hybrid ~= Expanded Vector  -> BM25 adds nothing after expansion
  Expanded Hybrid  >  Expanded Vector -> BM25 still earns its place; keep it
  Expanded Hybrid  <  Expanded Vector -> BM25 actively hurts expanded queries

RERANKING IS HELD OFF FOR EVERY ARM
-----------------------------------
Under the shipped RERANK_POLICY="intent-gated", all ten situational queries
route away from the cross-encoder anyway (names_a_service is false for every
one of them), so rerank=False *is* production behavior here. Holding it
constant keeps this measurement about one variable: the keyword arm.

COST AND SCOPE
--------------
Zero LLM calls -- intents come from scripts/intent_cache.py, already populated.
Run with INTENT_CACHE_OFFLINE=1 to prove it. Nothing in app/ is modified and no
production default changes; this script only reads.

Run:
  INTENT_CACHE_OFFLINE=1 LLM_MODEL=deepseek-v4-flash \
      uv run python scripts/measure_expansion_retrieval.py
"""

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv()

import intent_cache  # noqa: E402
from app.db import get_db  # noqa: E402
from app.embeddings import embed_texts  # noqa: E402
from app.search import (  # noqa: E402
    POOL_SIZE_DEFAULT,
    _vector_search,
    search_businesses,
)
from measure_situational_baseline import QUERIES as SITUATIONAL  # noqa: E402

LIMIT = 10

# (label, query form, retrieval mode). Order is the reading order of the report.
ARMS = [
    ("Original Hybrid", "raw", "hybrid"),          # production today
    ("Original Vector", "raw", "vector"),          # control
    ("Expanded Vector", "expanded", "vector"),
    ("Expanded Hybrid", "expanded", "hybrid"),
    ("Both Vector", "both", "vector"),
    ("Both Hybrid", "both", "hybrid"),
]


def _live_names(categories) -> set[str]:
    docs = get_db()["businesses"].find(
        {"sub_category": {"$in": list(categories)}}, {"business_name": 1, "_id": 0}
    )
    return {d["business_name"] for d in docs}


def _metrics(ranked: list[str], relevant: set[str]) -> dict:
    target = min(len(relevant), 3)
    hits3 = sum(1 for n in ranked[:3] if n in relevant)
    return {
        "success3": 1.0 if hits3 == target else 0.0,
        "recall3": hits3 / len(relevant),
        "p5": sum(1 for n in ranked[:5] if n in relevant) / 5,
        "first_rank": next((i + 1 for i, n in enumerate(ranked) if n in relevant), None),
    }


def _query_text(form: str, query: str, intent) -> str | None:
    if form == "raw":
        return query
    if intent is None or not intent.expanded_query:
        return None  # no expansion available: arm is undefined, not zero
    if form == "expanded":
        return intent.expanded_query
    return f"{query} {intent.expanded_query}"


def _retrieve(text: str, mode: str) -> list[str]:
    """Vector-only runs the same $vectorSearch stage the hybrid path uses, so
    the only difference between the two modes is whether BM25 + RRF run at all
    -- not a different index, embedding, or pool size."""
    if mode == "vector":
        businesses = get_db()["businesses"]
        docs = _vector_search(businesses, embed_texts([text])[0], POOL_SIZE_DEFAULT, {})
        return [d["business_name"] for d in docs][:LIMIT]
    # rerank=False: see the module docstring -- this is production behavior for
    # every query in this set under RERANK_POLICY="intent-gated".
    return [r["business_name"] for r in search_businesses(text, LIMIT, None, rerank=False)]


def main() -> int:
    queries = [(qid, q, _live_names(cats)) for qid, q, cats in SITUATIONAL]
    cached, fetched = intent_cache.warm([q for _, q, _ in queries])
    print(f"intents: {cached} cached, {fetched} fetched   "
          f"(LLM calls so far: {intent_cache.calls_made()})")
    print()

    results: dict = {}       # arm -> qid -> metrics
    for label, form, mode in ARMS:
        results[label] = {}
        for qid, query, relevant in queries:
            intent = intent_cache.get_intent(query)
            text = _query_text(form, query, intent)
            if text is None:
                results[label][qid] = None
                continue
            results[label][qid] = _metrics(_retrieve(text, mode), relevant)

    labels = [a[0] for a in ARMS]

    print("=" * 100)
    print("PER-QUERY success@3   (1 = every relevant business that could fit in the top 3 is there)")
    print("=" * 100)
    def cell(label: str, qid: str) -> str:
        row = results[label][qid]
        return "-" if row is None else f"{row['success3']:.0f}"

    print(f"{'id':<9}" + "".join(f"{lbl:>17}" for lbl in labels))
    print("-" * 100)
    for qid, _query, _relevant in queries:
        print(f"{qid:<9}" + "".join(f"{cell(label, qid):>17}" for label in labels))
    print()
    print("query text for reference:")
    for qid, query, _ in queries:
        print(f"  {qid:<9} {query[:82]}")
    print()

    print("=" * 100)
    print("AGGREGATE over the 10 situational queries")
    print("=" * 100)
    print(f"{'arm':<20}{'success@3':>12}{'recall@3':>12}{'P@5':>10}{'mean first rank':>18}")
    print("-" * 100)
    # Average every arm over the SAME queries. Any query whose intent is
    # missing (a cached LLM failure) has no expanded form, so its expanded arms
    # are undefined -- averaging raw arms over 10 and expanded arms over 9 would
    # compare different denominators and flatter whichever arm dropped the
    # harder query. Excluded queries are listed below the table, never silently.
    common = [
        qid for qid, _, _ in queries
        if all(results[label][qid] is not None for label in labels)
    ]
    excluded = [qid for qid, _, _ in queries if qid not in common]
    if excluded:
        print(f"  excluded from all aggregates (no intent available): {excluded}")
        print(f"  every arm below is averaged over the same {len(common)} queries")
        print()

    agg = {}
    for label in labels:
        rows = [results[label][qid] for qid in common]
        ranks = [r["first_rank"] for r in rows if r["first_rank"]]
        agg[label] = {
            k: sum(r[k] for r in rows) / len(rows) for k in ("success3", "recall3", "p5")
        }
        agg[label]["mean_first_rank"] = sum(ranks) / len(ranks) if ranks else None
        a = agg[label]
        marker = "   <- production" if label == "Original Hybrid" else ""
        print(f"{label:<20}{a['success3']:>12.3f}{a['recall3']:>12.3f}{a['p5']:>10.3f}"
              f"{a['mean_first_rank']:>18.2f}{marker}")
    print()

    print("=" * 100)
    print("DOES BM25 STILL EARN ITS PLACE AFTER EXPANSION?")
    print("=" * 100)
    for form, vec_label, hyb_label in (
        ("raw", "Original Vector", "Original Hybrid"),
        ("expanded", "Expanded Vector", "Expanded Hybrid"),
        ("raw+expanded", "Both Vector", "Both Hybrid"),
    ):
        deltas = " ".join(
            f"{k}={agg[hyb_label][k] - agg[vec_label][k]:+.3f}"
            for k in ("success3", "recall3", "p5")
        )
        print(f"  {form:<14} hybrid minus vector-only:  {deltas}")
    print()
    print("  Positive = BM25 adds value for that query form. Negative = it costs.")
    print("  Decide on all three rows, not the middle one alone.")

    dest = Path(__file__).parent.parent / "eval_reports" / "expansion_retrieval.json"
    dest.write_text(json.dumps({"aggregate": agg, "per_query": results}, indent=2),
                    encoding="utf-8")
    print(f"\nwrote {dest}")
    print(f"LLM calls made this run: {intent_cache.calls_made()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
