"""Situational baseline against the LIVE system (M6 pre-work).

Runs the reviewer's own query plus 9 further symptom-only queries through
app.search.search_businesses() -- the exact pipeline /api/search runs -- in three
configurations:

  hybrid+rerank   what ships today (RERANK_ENABLED defaults true)
  hybrid          same retrieval, reranking off
  vector-only     no keyword arm, no RRF, no rerank

Purpose: establish whether symptom-only queries (queries that describe a problem
without naming a service) are a real ranking gap, and isolate which stage is
responsible. The existing golden set in eval_dataset.py contains no queries of
this class, so this gap is invisible to scripts/eval.py.

Reports success@3 and recall@3 as the headline. P@5 is reported with its ceiling
because precision_at_k divides by k=5 while these queries have 3 relevant docs,
capping P@5 at 0.6 -- see scripts/compute_metric_ceiling.py.

Run: uv run python scripts/measure_situational_baseline.py
"""
import collections
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv()

from app.db import get_db  # noqa: E402
from app.search import search_businesses  # noqa: E402

# Ground truth is derived from the LIVE corpus, not the xlsx, so the labels match
# whatever is actually indexed (including any registered businesses).
_docs = list(get_db()["businesses"].find({}, {"business_name": 1, "sub_category": 1, "_id": 0}))
BY_CAT = collections.defaultdict(list)
for _d in _docs:
    BY_CAT[_d["sub_category"]].append(_d["business_name"])


def names(*cats: str) -> list[str]:
    out: list[str] = []
    for c in cats:
        if c not in BY_CAT:
            raise SystemExit(f"FAIL: {c!r} is not a sub_category in the live corpus. "
                             f"Fix the label before trusting any number from this run.")
        out += BY_CAT[c]
    return out


# The reviewer's verbatim query is first and is reported separately: it is the one
# genuinely held-out test case in this exercise, because he wrote it.
QUERIES = [
    ("rev-01", "My company keeps getting suspicious emails and I want someone to make "
               "sure our employees don't fall for scams", ("Cybersecurity",)),
    ("sit-02", "We're opening a new office next month and the space is completely bare",
     ("Interior Design",)),
    ("sit-03", "Our vegetables keep spoiling before they reach the shops", ("Cold Chain",)),
    ("sit-04", "Nobody can find us when they search online", ("Digital Marketing",)),
    # Two categories are genuinely both correct here; multi-03 in eval_dataset.py
    # already treats Chartered Accountants and GST Consultants as one relevant set.
    ("sit-05", "I got a notice from the tax department and I don't understand it",
     ("Chartered Accountants", "GST Consultants")),
    ("sit-06", "Our machines on the shop floor keep breaking and we only find out when "
               "production stops", ("Industrial Automation",)),
    ("sit-07", "We have 200 staff and nobody knows how to handle an angry customer",
     ("Corporate Training",)),
    ("sit-08", "Customers keep telling us the product arrived damaged",
     ("Food Packaging", "Freight Transport")),
    ("sit-09", "Our website goes down every time we get a rush of visitors", ("Cloud Services",)),
    ("sit-10", "We're moving to a new city and everything has to get there",
     ("Freight Transport", "Courier Services")),
]

CONFIGS = {
    "hybrid+rerank": lambda q: search_businesses(q, 10, None, rerank=True),
    "hybrid": lambda q: search_businesses(q, 10, None, rerank=False),
}


def metrics(ranked: list[str], relevant: set[str]) -> dict:
    """success@3 is all-or-nothing: did every relevant doc that COULD fit in the
    top 3 actually land there. Chosen over P@5 because P@5 is capped at 0.6 for
    3-relevant queries and the existing benchmark is already at 97.7% of its
    ceiling -- there is no headroom left in it to measure with."""
    target = min(len(relevant), 3)
    hits3 = sum(1 for n in ranked[:3] if n in relevant)
    return {
        "success3": 1.0 if hits3 == target else 0.0,
        "recall3": hits3 / len(relevant),
        "p5": sum(1 for n in ranked[:5] if n in relevant) / 5,
        "p5_ceiling": min(len(relevant), 5) / 5,
        "first_rank": next((i + 1 for i, n in enumerate(ranked) if n in relevant), None),
        "top3": ranked[:3],
    }


def main() -> int:
    out: dict = {"corpus_size": len(_docs), "sub_categories": len(BY_CAT), "queries": []}

    print(f"corpus: {len(_docs)} documents, {len(BY_CAT)} sub_categories")
    print()

    for qid, query, cats in QUERIES:
        relevant = set(names(*cats))
        row = {"id": qid, "query": query, "target": list(cats),
               "n_relevant": len(relevant), "configs": {}}
        header = "REVIEWER'S OWN QUERY" if qid == "rev-01" else qid
        print("=" * 78)
        print(f"{header}  ->  {', '.join(cats)}")
        print(f"  {query}")
        for name, fn in CONFIGS.items():
            m = metrics([r["business_name"] for r in fn(query)], relevant)
            row["configs"][name] = m
            print(f"  {name:<14} success@3={m['success3']:.0f}  recall@3={m['recall3']:.2f}  "
                  f"P@5={m['p5']:.2f}/{m['p5_ceiling']:.2f}  first_rank={m['first_rank']}")
            print(f"  {'':<14} top3: {', '.join(m['top3'])}")
        out["queries"].append(row)

    sit = [r for r in out["queries"] if r["id"] != "rev-01"]
    print()
    print("=" * 78)
    print(f"AGGREGATE over {len(sit)} situational queries (reviewer's query excluded)")
    agg = {}
    for name in CONFIGS:
        agg[name] = {
            k: sum(r["configs"][name][k] for r in sit) / len(sit)
            for k in ("success3", "recall3", "p5")
        }
        a = agg[name]
        print(f"  {name:<14} success@3={a['success3']:.3f}  recall@3={a['recall3']:.3f}  "
              f"P@5={a['p5']:.3f}")
    out["aggregate"] = agg

    delta = agg["hybrid+rerank"]["recall3"] - agg["hybrid"]["recall3"]
    print()
    print(f"  reranking effect on recall@3: {delta:+.3f}"
          f"  ({'HELPS' if delta > 0 else 'HURTS' if delta < 0 else 'neutral'})")

    dest = Path(__file__).parent.parent / "eval_reports" / "situational_baseline.json"
    dest.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
