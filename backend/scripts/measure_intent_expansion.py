"""
Does searching the LLM's expanded_query beat searching the raw query? (M6.3)

THE QUESTION
------------
M6.2 fixed the panel, not retrieval. The LLM now identifies the right category
for 10/10 symptom queries, but retrieval still runs on the user's raw words, so
symptom queries sit at success@3 = 0.300 -- the panel can say "Cold Chain"
while the results show farms. INTENT_EXPANSION_ENABLED exists to close that gap
and has been off since it was written, because it was never measured.

The LLM returns the bridge:

  "Our vegetables keep spoiling before they reach the shops"
    -> expanded_query: "cold chain logistics perishable vegetables transportation"

Symptom vocabulary in, service vocabulary out -- the same vocabulary the
documents are indexed in. This measures whether searching that actually helps.

THREE ARMS, ONE SET OF INTENTS
------------------------------
  raw            the user's words          (what ships today)
  expanded       the LLM's expanded_query only
  raw+expanded   both, concatenated

The third costs no extra LLM call and guards against a real risk in the second:
expanded_query is a short service phrase, so it can drop specifics the user
gave (a city, a product, a constraint). Concatenation keeps the original signal
and adds the bridge.

BOTH QUERY CLASSES, ALWAYS
--------------------------
Symptom-only AND named-service. Measuring expansion on symptom queries alone
would repeat the mistake that once made "never rerank" look good: a change that
helps one class can quietly wreck the other, and only measuring both can see it.

COST
----
Intents come from scripts/intent_cache.py -- one LLM call per unique query, ever.
Re-runs make zero calls. The call count is printed at the end of every run.

Run:
  LLM_API_KEY=... LLM_PROVIDER=openai LLM_BASE_URL=... LLM_MODEL=... \
      uv run python scripts/measure_intent_expansion.py
  INTENT_CACHE_OFFLINE=1 uv run python scripts/measure_intent_expansion.py   # free
"""

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv()

import intent_cache  # noqa: E402
from app import search as search_module  # noqa: E402
from app.db import get_db  # noqa: E402
from app.search import search_businesses  # noqa: E402
from app.taxonomy import (  # noqa: E402
    get_categories,
    is_known_category,
    profile_text,
)
from eval_dataset import GOLDEN_QUERIES  # noqa: E402
from measure_situational_baseline import QUERIES as SITUATIONAL  # noqa: E402

# "taxonomy" is the stable alternative to the model's prose: the SAME chosen
# categories, but the expansion text comes from app/taxonomy.json instead of
# from free generation. measure_intent_determinism.py showed categories agree
# 0.80-1.00 across identical calls while expanded_query varies 17-19 distinct
# values in 20 -- so this arm is deterministic given the categories, and the
# free-text arms are not.
ARMS = ("raw", "expanded", "raw+expanded", "taxonomy", "raw+taxonomy")


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
    }


def _taxonomy_expansion(intent) -> str:
    """The chosen categories' own vocabulary, straight from taxonomy.json."""
    if intent is None or not intent.service_categories:
        return ""
    categories = get_categories()
    return " ".join(
        profile_text(categories[name])
        for name in intent.service_categories
        if is_known_category(name)
    )


def _retrieval_query(arm: str, query: str, intent) -> str:
    if arm == "raw" or intent is None:
        return query
    if arm in ("taxonomy", "raw+taxonomy"):
        vocabulary = _taxonomy_expansion(intent)
        if not vocabulary:
            return None
        return vocabulary if arm == "taxonomy" else f"{query} {vocabulary}"
    if not intent.expanded_query:
        return None
    if arm == "expanded":
        return intent.expanded_query
    return f"{query} {intent.expanded_query}"


def _run(query: str, relevant: set[str], arm: str, intent) -> dict:
    # Reranking is decided on the ORIGINAL query under the shipped policy --
    # whether a user named their service is a property of what they typed, not
    # of what the expansion turned it into. Calling search.py's own
    # _should_rerank keeps this measurement tied to shipped behavior.
    text = _retrieval_query(arm, query, intent)
    if text is None:
        return None  # this arm is undefined for this query (no intent / no expansion)
    rerank = search_module._should_rerank(query, intent)
    results = search_businesses(text, 10, None, rerank=rerank)
    row = _metrics([r["business_name"] for r in results], relevant)
    row["reranked"] = rerank
    return row


def main() -> int:
    situational = [(qid, q, _live_names(cats)) for qid, q, cats in SITUATIONAL]
    named = [
        (gq["id"], gq["query"], set(gq["expected_relevant"]))
        for gq in GOLDEN_QUERIES
        if gq["category"] in ("keyword", "semantic", "synonym")
        and not gq.get("filters")
        and gq["expected_relevant"]
    ]
    suites = {"symptom-only": situational, "names a service": named}

    every_query = [q for _, q, _ in situational] + [q for _, q, _ in named]
    cached, fetched = intent_cache.warm(every_query)
    print(f"intents: {cached} from cache, {fetched} fetched "
          f"({len(every_query)} unique queries)")
    print()

    table: dict = {}
    per_query: dict = {}
    for suite_name, queries in suites.items():
        table[suite_name] = {}
        for arm in ARMS:
            rows = []
            for qid, query, relevant in queries:
                intent = intent_cache.get_intent(query)
                row = _run(query, relevant, arm, intent)
                rows.append(row)
                per_query.setdefault(qid, {"query": query})[arm] = (
                    None if row is None else row["success3"]
                )
            defined = [r for r in rows if r is not None]
            table[suite_name][arm] = {
                k: (sum(r[k] for r in defined) / len(defined)) if defined else None
                for k in ("success3", "recall3", "p5")
            }
            table[suite_name][arm]["n"] = len(defined)

    for suite_name, queries in suites.items():
        print("=" * 78)
        print(f"{suite_name}  (n={len(queries)})")
        print("=" * 78)
        print(f"{'arm':<16}{'success@3':>11}{'recall@3':>11}{'P@5':>9}{'n':>5}")
        print("-" * 78)
        for arm in ARMS:
            m = table[suite_name][arm]
            if m["success3"] is None:
                print(f"{arm:<16}{'n/a':>11}")
                continue
            print(f"{arm:<16}{m['success3']:>11.3f}{m['recall3']:>11.3f}"
                  f"{m['p5']:>9.3f}{m['n']:>5}")
        print()

    print("=" * 78)
    print("PER-QUERY success@3  (symptom-only)")
    print("=" * 78)
    print(f"{'id':<9}" + "".join(f"{a[:12]:>14}" for a in ARMS) + "   query")
    print("-" * 100)
    for qid, _, _ in situational:
        row = per_query[qid]
        cells = "".join(
            f"{('-' if row[a] is None else f'{row[a]:.0f}'):>14}" for a in ARMS
        )
        print(f"{qid:<9}{cells}   {row['query'][:34]}")
    print()

    print("=" * 78)
    print("VERDICT")
    print("=" * 78)
    for suite_name in suites:
        base = table[suite_name]["raw"]
        print(f"  {suite_name}")
        for arm in ARMS[1:]:
            if table[suite_name][arm]["success3"] is None:
                continue
            deltas = " ".join(
                f"{k}={table[suite_name][arm][k] - base[k]:+.3f}"
                for k in ("success3", "recall3", "p5")
            )
            print(f"    {arm:<14} vs raw:  {deltas}")
    print()
    print("  Expansion is only worth shipping if it does not lose ground on the")
    print("  named-service suite. Both blocks above, together, decide it.")

    dest = Path(__file__).parent.parent / "eval_reports" / "intent_expansion.json"
    dest.write_text(json.dumps({"suites": table, "per_query": per_query}, indent=2),
                    encoding="utf-8")
    print(f"\nwrote {dest}")
    print(f"LLM calls made this run: {intent_cache.calls_made()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
