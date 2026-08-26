"""
Measure the intent classifier (M6.1).

Two questions, both of which have to be answered before an "I understood you
need..." panel is allowed to ship, because a panel that is confidently wrong is
worse than no panel at all:

1. On symptom-only queries, does the classifier pick the right category?
2. Does MIN_SIMILARITY separate the queries it gets right from the ones it gets
   wrong -- i.e. is the number the gate trusts an honest one?

The classifier is measured in isolation (INTENT_PROVIDER is forced to
"embedding" below) so the checked-in fixtures cannot answer for the demo
queries and flatter the result.

Uses the same 10 queries and ground-truth categories as
scripts/measure_situational_baseline.py, so intent accuracy and retrieval
quality are measured against one shared labelling. Needs no database: the
taxonomy comes from the checked-in app/taxonomy.json.

Run: uv run python scripts/measure_intent.py
"""

import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv()

from app import intent as intent_module  # noqa: E402
from app.intent import classify, infer_intent  # noqa: E402
from eval_dataset import GOLDEN_QUERIES  # noqa: E402

# The provider is a parameter. Defaults to "embedding" so the classifier is
# measured on its own merits (fixtures would otherwise answer for three of the
# ten queries and flatter the result); override to measure a real provider:
#   INTENT_PROVIDER=llm uv run python scripts/measure_intent.py
PROVIDER = os.environ.get("INTENT_PROVIDER", "embedding").strip().lower()
intent_module.INTENT_PROVIDER = PROVIDER

# (id, query, ground-truth categories). Kept identical to the QUERIES list in
# measure_situational_baseline.py -- if that list changes, change this too.
QUERIES = [
    ("rev-01", "My company keeps getting suspicious emails and I want someone to make "
               "sure our employees don't fall for scams", {"Cybersecurity"}),
    ("sit-02", "We're opening a new office next month and the space is completely bare",
     {"Interior Design"}),
    ("sit-03", "Our vegetables keep spoiling before they reach the shops", {"Cold Chain"}),
    ("sit-04", "Nobody can find us when they search online", {"Digital Marketing"}),
    ("sit-05", "I got a notice from the tax department and I don't understand it",
     {"Chartered Accountants", "GST Consultants"}),
    ("sit-06", "Our machines on the shop floor keep breaking and we only find out when "
               "production stops", {"Industrial Automation"}),
    ("sit-07", "We have 200 staff and nobody knows how to handle an angry customer",
     {"Corporate Training"}),
    ("sit-08", "Customers keep telling us the product arrived damaged",
     {"Food Packaging", "Freight Transport"}),
    ("sit-09", "Our website goes down every time we get a rush of visitors",
     {"Cloud Services"}),
    ("sit-10", "We're moving to a new city and everything has to get there",
     {"Freight Transport", "Courier Services"}),
]

# Queries that must classify to NOTHING. The classifier always has a nearest
# category among 40, so without these the gate is untested and the panel would
# happily label gibberish.
NEGATIVES = [
    ("neg-01", "asdfgh qwerty zxcvbn"),
    ("neg-02", "what is the weather tomorrow"),
    ("neg-03", "how do I renew my passport"),
]


def separation() -> None:
    """Evidence for the gate being absolute cosine similarity.

    Shows where named-service queries sit, where symptom queries and gibberish
    sit, and whether a gap exists for MIN_SIMILARITY to live in. Margin is
    reported too because it was considered and rejected -- the two classes
    overlap on it.
    """
    named = [
        gq["query"]
        for gq in GOLDEN_QUERIES
        if gq["category"] in ("keyword", "semantic", "synonym")
    ]
    symptomatic = [q for _, q, _ in QUERIES] + [q for _, q in NEGATIVES]

    def stats(queries: list[str]) -> list[tuple[float, float]]:
        rows = []
        for query in queries:
            ranked = classify(query)
            rows.append((ranked[0][1], ranked[0][1] - ranked[1][1]))
        return rows

    print("=" * 78)
    print("GATE EVIDENCE -- classifier only, independent of the active provider")
    print("=" * 78)
    named_rows, symptom_rows = stats(named), stats(symptomatic)
    print(f"{'class':<32}{'n':>4}{'sim min':>10}{'sim max':>10}"
          f"{'marg min':>10}{'marg max':>10}")
    print("-" * 78)
    for label, rows in (
        ("names a service (golden set)", named_rows),
        ("symptom-only + gibberish", symptom_rows),
    ):
        print(f"{label:<32}{len(rows):>4}{min(r[0] for r in rows):>10.3f}"
              f"{max(r[0] for r in rows):>10.3f}{min(r[1] for r in rows):>10.3f}"
              f"{max(r[1] for r in rows):>10.3f}")
    gap = min(r[0] for r in named_rows) - max(r[0] for r in symptom_rows)
    print()
    print(f"  similarity gap between classes : {gap:+.3f}   "
          f"(MIN_SIMILARITY = {intent_module.MIN_SIMILARITY})")
    print(f"  margin overlaps                : named min "
          f"{min(r[1] for r in named_rows):.3f} <= symptom max "
          f"{max(r[1] for r in symptom_rows):.3f}  -> rejected as a gate")
    print()


def measure_accuracy() -> tuple[int, int]:
    print("=" * 78)
    print(f"PER-QUERY INTENT -- provider={PROVIDER}  "
          f"(classifier MIN_SIMILARITY={intent_module.MIN_SIMILARITY})")
    print("=" * 78)

    top1_hits = 0
    reported_hits = 0
    silent = 0
    latencies = []
    for qid, query, truth in QUERIES:
        ranked = classify(query)
        top_name, top_similarity = ranked[0]
        top1_hits += top_name in truth

        started = time.perf_counter()
        result = infer_intent(query)
        elapsed_ms = (time.perf_counter() - started) * 1000
        latencies.append(elapsed_ms)

        reported = result.service_categories if result else []
        silent += not reported
        # A "hit" for the panel means at least one reported category is
        # correct -- that is what the user actually sees.
        reported_hit = any(c in truth for c in reported)
        reported_hits += reported_hit

        flag = ("HIT" if reported_hit else "WRONG") if reported else "quiet"
        label = "REVIEWER" if qid == "rev-01" else qid
        print(f"[{flag:<5}] {label:<9} {elapsed_ms:6.0f} ms   "
              f"src={result.source if result else '-'}  "
              f"conf={result.confidence if result else '-'}")
        print(f"          query : {query[:88]}")
        if result:
            print(f"          need  : {result.underlying_need}")
            print(f"          cats  : {result.service_categories}")
            print(f"          expq  : {result.expanded_query[:88]}")
            if result.exclusions:
                print(f"          excl  : {result.exclusions}")
        else:
            print("          need  : (no intent -- panel hidden)")
        print(f"          EXPECT: {sorted(truth)}"
              f"    [classifier sim={top_similarity:.3f} -> {top_name!r}]")
        print()

    print(f"top-1 classifier category correct : {top1_hits}/{len(QUERIES)}")
    print(f"panel shown AND correct           : {reported_hits}/{len(QUERIES)}")
    print(f"panel stayed silent               : {silent}/{len(QUERIES)}")
    if latencies:
        ordered = sorted(latencies)
        print(f"infer_intent latency              : p50 {ordered[len(ordered)//2]:.0f} ms"
              f"   max {ordered[-1]:.0f} ms")
    print()
    return top1_hits, reported_hits


def measure_negatives() -> int:
    print("=" * 78)
    print("NEGATIVES -- these must produce NO intent panel")
    print("=" * 78)
    suppressed = 0
    for qid, query in NEGATIVES:
        result = infer_intent(query)
        top_name, top_similarity = classify(query)[0]
        ok = result is None
        suppressed += ok
        verdict = "suppressed" if ok else f"SHOWN {result.service_categories}"
        print(f"[{'PASS' if ok else 'FAIL'}] {qid}  sim={top_similarity:.3f}  "
              f"nearest={top_name!r}  -> {verdict}")
        print(f"       {query!r}")
    print()
    print(f"correctly suppressed: {suppressed}/{len(NEGATIVES)}")
    print()
    return suppressed


def _render(result) -> None:
    if result is None:
        print("    (no intent -- panel hidden)")
        return
    print(f"    I understood you need: {result.underlying_need}")
    print(f"    categories : {result.service_categories}")
    print(f"    confidence : {result.confidence}")
    print(f"    source     : {result.source}")
    print(f"    expanded   : {result.expanded_query[:96]}...")


def main() -> int:
    separation()
    _, reported_hits = measure_accuracy()
    suppressed = measure_negatives()

    reviewer_query = QUERIES[0][1]
    print("=" * 78)
    print("REVIEWER'S QUERY -- what the panel renders")
    print("=" * 78)
    print(f"  provider={PROVIDER}:")
    _render(infer_intent(reviewer_query))

    print()
    print(f"SUMMARY  provider={PROVIDER}   shown-and-correct "
          f"{reported_hits}/{len(QUERIES)}   negatives-suppressed "
          f"{suppressed}/{len(NEGATIVES)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
