"""
Measure query-conditional reranking (M6.1, step 4).

THE QUESTION
------------
eval_reports/baseline_situational_20260825.md measured the cross-encoder as a
net negative on symptom-only queries (P@5 0.244 with reranking vs 0.378
without, -35.3% relative), while M4.2 measured it as a net positive on the
golden set. Both hold: the golden set names its services and the situational
set does not.

RERANK_POLICY="intent-gated" (app/search.py) proposes using the intent
classifier as the switch -- rerank when it recognised the query, skip when it
did not -- because scripts/measure_intent.py shows it separates exactly those
two classes (named-service similarity min 0.597, symptom/gibberish max 0.563).

That is a plausible proxy, and a plausible proxy is not evidence. This script
is the evidence. It runs BOTH query classes through all three policies, so a
policy that helps symptom queries by wrecking named-service queries cannot
hide -- which is the failure mode a situational-set-only measurement would
have missed entirely.

  always        rerank everything          (the shipped default)
  never         rerank nothing
  intent-gated  rerank iff the CLASSIFIER recognised the query

Run: uv run python scripts/measure_rerank_policy.py
"""

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv()

from app import intent as intent_module  # noqa: E402
from app import search as search_module  # noqa: E402
from app.db import get_db  # noqa: E402
from app.search import search_businesses  # noqa: E402
from eval_dataset import GOLDEN_QUERIES  # noqa: E402
from measure_situational_baseline import QUERIES as SITUATIONAL  # noqa: E402

POLICIES = ("always", "never", "intent-gated")

# The intent provider is a parameter of this measurement, not a constant, and
# it matters: M6.2 made the displayed intent and the routing signal two
# different things, so a policy verified under one provider is not verified
# under another. Defaults to "auto" -- the shipped configuration -- rather than
# to whatever is convenient.
#
#   INTENT_PROVIDER=auto      uv run python scripts/measure_rerank_policy.py
#   INTENT_PROVIDER=llm       (needs LLM_API_KEY)
#   INTENT_PROVIDER=embedding classifier alone
PROVIDER = os.environ.get("INTENT_PROVIDER", "auto").strip().lower()
intent_module.INTENT_PROVIDER = PROVIDER


def _live_names(categories: tuple[str, ...]) -> set[str]:
    docs = get_db()["businesses"].find({"sub_category": {"$in": list(categories)}},
                                       {"business_name": 1, "_id": 0})
    return {d["business_name"] for d in docs}


def _metrics(ranked: list[str], relevant: set[str]) -> dict:
    target = min(len(relevant), 3)
    hits3 = sum(1 for n in ranked[:3] if n in relevant)
    return {
        "success3": 1.0 if hits3 == target else 0.0,
        "recall3": hits3 / len(relevant),
        "p5": sum(1 for n in ranked[:5] if n in relevant) / 5,
    }


def _run(query: str, relevant: set[str], policy: str, filters=None) -> dict:
    """One query under one policy, through the real pipeline.

    Calls search.py's own _should_rerank() rather than restating the rule. An
    earlier version of this script reimplemented the decision inline; that made
    it possible for the measured policy and the shipped policy to drift apart
    silently, which is the one failure a measurement script must not have.
    Only the policy constant is swapped, and it is restored afterwards.

    search_businesses() is called directly rather than search_with_intent() so
    that INTENT_EXPANSION_ENABLED cannot change what is being measured here --
    this script is about reranking, not about expansion.
    """
    intent = intent_module.infer_intent(query)
    previous = search_module.RERANK_POLICY
    search_module.RERANK_POLICY = policy
    try:
        rerank = search_module._should_rerank(query, intent)
    finally:
        search_module.RERANK_POLICY = previous

    results = search_businesses(query, 10, filters, rerank=rerank)
    row = _metrics([r["business_name"] for r in results], relevant)
    row["reranked"] = rerank
    row["intent_source"] = intent.source if intent else None
    return row


def main() -> int:
    # Symptom-only queries. Ground truth resolved from the live corpus, the
    # same way measure_situational_baseline.py does it.
    situational = [(qid, q, _live_names(cats)) for qid, q, cats in SITUATIONAL]

    # Named-service queries. Restricted to the unfiltered keyword/semantic/
    # synonym rows: those are the class M4.2's "reranking helps" conclusion
    # came from, and dropping the filtered rows keeps filter behavior out of a
    # measurement that is about reranking.
    named = [
        (gq["id"], gq["query"], set(gq["expected_relevant"]))
        for gq in GOLDEN_QUERIES
        if gq["category"] in ("keyword", "semantic", "synonym")
        and not gq.get("filters")
        and gq["expected_relevant"]
    ]

    suites = {"symptom-only (situational)": situational, "names a service (golden)": named}
    table: dict = defaultdict(dict)
    reranked_counts: dict = defaultdict(dict)

    for suite_name, queries in suites.items():
        for policy in POLICIES:
            rows = [_run(q, rel, policy) for _, q, rel in queries]
            table[suite_name][policy] = {
                key: sum(r[key] for r in rows) / len(rows)
                for key in ("success3", "recall3", "p5")
            }
            reranked_counts[suite_name][policy] = (
                sum(r["reranked"] for r in rows), len(rows)
            )

    print(f"INTENT_PROVIDER={PROVIDER}   "
          f"(routing signal: app.intent.names_a_service)")
    print()
    for suite_name, queries in suites.items():
        print("=" * 78)
        print(f"{suite_name}  (n={len(queries)})")
        print("=" * 78)
        print(f"{'policy':<14}{'success@3':>11}{'recall@3':>11}{'P@5':>9}{'reranked':>11}")
        print("-" * 78)
        for policy in POLICIES:
            m = table[suite_name][policy]
            done, total = reranked_counts[suite_name][policy]
            print(f"{policy:<14}{m['success3']:>11.3f}{m['recall3']:>11.3f}"
                  f"{m['p5']:>9.3f}{f'{done}/{total}':>11}")
        print()

    print("=" * 78)
    print("VERDICT")
    print("=" * 78)
    for suite_name in suites:
        base = table[suite_name]["always"]
        gated = table[suite_name]["intent-gated"]
        print(f"  {suite_name}")
        for key in ("success3", "recall3", "p5"):
            delta = gated[key] - base[key]
            direction = "better" if delta > 0 else "worse" if delta < 0 else "same"
            print(f"    {key:<9} intent-gated vs always: {delta:+.3f}  ({direction})")
    print()
    print("  A policy change is only justified if it does not lose ground on the")
    print("  named-service suite. Both numbers above, together, decide it.")

    dest = Path(__file__).parent.parent / "eval_reports" / "rerank_policy.json"
    dest.write_text(json.dumps(
        {"intent_provider": PROVIDER,
         "suites": {k: dict(v) for k, v in table.items()},
         "reranked_counts": {k: dict(v) for k, v in reranked_counts.items()}},
        indent=2), encoding="utf-8")
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
