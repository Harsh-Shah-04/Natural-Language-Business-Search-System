"""
End-to-end contextual search checks, including negation (M6.4).

Traces the WHOLE pipeline for each query -- query -> intent -> resolved
exclusions -> retrieval -> fusion -> rerank -> final results -- and asserts on
the FINAL list, not on the intent. An intent that correctly says "exclude
Cybersecurity" while Cybersecurity businesses still rank 1-2-3 is a failure,
and that is exactly the bug this file exists to catch: before M6.4, exclusions
were produced, displayed, and ignored by retrieval.

Goes through app.search.search_with_intent(), the same entry point
/api/search uses, so nothing here can pass while the real endpoint fails.

Run:
  uv run python scripts/test_contextual_search.py
"""

import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv()

from app import intent as intent_module  # noqa: E402
from app.search import search_with_intent  # noqa: E402
from app.taxonomy import resolve_categories  # noqa: E402

# (id, query, must_appear, must_not_appear)
#   must_appear     : at least one result in the top 10 has this sub_category
#   must_not_appear : NO result may have this sub_category
CASES = [
    ("A-positive",
     "I want cybersecurity companies to protect my employees.",
     {"Cybersecurity"}, set()),
    ("B-negation",
     "I don't want cybersecurity companies. I need someone to train my "
     "employees so they don't fall for scams.",
     {"Corporate Training"}, {"Cybersecurity"}),
    ("C-negation-unmappable",
     "I don't want WhatsApp bot companies.",
     set(), set()),
    ("D-keyword",
     "I need help filing GST returns.",
     {"GST Consultants"}, set()),
    ("E-symptom",
     "My website keeps crashing whenever lots of customers visit.",
     {"Cloud Services"}, set()),
]


def main() -> int:
    print(f"INTENT_PROVIDER={intent_module.INTENT_PROVIDER}")
    print()
    failures = []

    for qid, query, must_appear, must_not in CASES:
        intent, results = search_with_intent(query, 10, None)
        categories = [r["sub_category"] for r in results]
        resolved = resolve_categories(intent.exclusions) if intent else []

        print("=" * 92)
        print(f"{qid}: {query}")
        print("=" * 92)
        if intent:
            print(f"  intent.need       : {intent.underlying_need}")
            print(f"  intent.include    : {intent.service_categories}")
            print(f"  intent.exclusions : {intent.exclusions}")
            print(f"  -> resolved to    : {resolved or '(nothing mappable -- filters nothing)'}")
            print(f"  intent.expanded   : {intent.expanded_query[:76]}")
            print(f"  source/confidence : {intent.source} / {intent.confidence}")
        else:
            print("  intent            : None (no panel)")

        print(f"  top 10 categories : {categories}")
        for n, r in enumerate(results[:5], 1):
            print(f"      {n}. {r['business_name']:<34} [{r['sub_category']}]")

        appeared = set(categories)
        missing = must_appear - appeared
        leaked = must_not & appeared
        ok = not missing and not leaked
        if missing:
            failures.append(f"{qid}: expected {sorted(missing)} in results, absent")
        if leaked:
            failures.append(f"{qid}: EXCLUDED {sorted(leaked)} still present")

        print()
        print(f"  expected present  : {sorted(must_appear) or '(none required)'}"
              f"   -> {'OK' if not missing else 'MISSING ' + str(sorted(missing))}")
        print(f"  must not appear   : {sorted(must_not) or '(none)'}"
              f"   -> {'OK' if not leaked else 'LEAKED ' + str(sorted(leaked))}")
        print(f"  VERDICT           : {'PASS' if ok else 'FAIL'}")
        print()

    print("=" * 92)
    if failures:
        print(f"FAIL — {len(failures)} of {len(CASES)} cases")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"PASS — all {len(CASES)} cases")
    return 0


if __name__ == "__main__":
    sys.exit(main())
