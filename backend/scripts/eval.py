"""
Search evaluation framework (M4.1).

Runs the golden query set (scripts/eval_dataset.py) against two search
systems -- vector-only (M2 baseline) and hybrid+RRF (M3.1/M3.2, the current
default) -- and reports Precision@K, Recall@K, and MRR for each, overall
and broken down by query category. This is the evidence M4.2 will need:
"ship reranking only if it measurably improves precision@5 on this set"
(design-doc-v2.md) requires a baseline number to improve on, which is what
this script produces.

Extensibility for future reranking experiments: a "system" is just a
Callable[[str, int, dict | None], list[dict]] returning ranked result
dicts with a "business_name" key (see SYSTEMS below). Adding a third
system (e.g. hybrid + cross-encoder rerank, once M4.2 builds it) means
writing one more function with that signature and adding one line to
SYSTEMS -- no changes needed anywhere else in this file.

Run: uv run python scripts/eval.py
"""

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from app.db import get_db
from app.embeddings import embed_texts
from app.filters import validate_filters
from app.search import (
    POOL_SIZE_DEFAULT,
    POOL_SIZE_FILTERED,
    POOL_SIZE_MULTIPLIER,
    _keyword_search,
    _vector_search,
    search_businesses,
)
from eval_dataset import GOLDEN_QUERIES

K_VALUES = (5, 10)
REPORT_DIR = Path(__file__).parent.parent / "eval_reports"


# ---------------------------------------------------------------------------
# Systems under comparison. Each is Callable[[str, int, dict | None], list[dict]].
# Both reuse app.search's existing internals directly -- no retrieval logic
# is duplicated here.
# ---------------------------------------------------------------------------

def vector_only_search(query: str, limit: int, filters: dict | None = None) -> list[dict]:
    """M2's baseline: Atlas $vectorSearch alone, no keyword signal, no RRF."""
    query_vector = embed_texts([query])[0]
    active_filters = validate_filters(filters)
    pool_size = (
        POOL_SIZE_FILTERED
        if active_filters
        else max(POOL_SIZE_DEFAULT, limit * POOL_SIZE_MULTIPLIER)
    )
    businesses = get_db()["businesses"]
    results = _vector_search(businesses, query_vector, pool_size, active_filters)
    return results[:limit]


def hybrid_search(query: str, limit: int, filters: dict | None = None) -> list[dict]:
    """M3.1/M3.2's current default: hybrid $vectorSearch + $search fused
    with RRF, with filters applied to both retrieval paths."""
    return search_businesses(query, limit, filters)


SYSTEMS = {
    "vector-only": vector_only_search,
    "hybrid": hybrid_search,
}


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def precision_at_k(retrieved_names: list[str], relevant_names: set[str], k: int) -> float:
    top_k = retrieved_names[:k]
    if not top_k:
        return 0.0
    hits = sum(1 for name in top_k if name in relevant_names)
    return hits / len(top_k)


def recall_at_k(retrieved_names: list[str], relevant_names: set[str], k: int) -> float | None:
    """None (not 0.0) when there are zero relevant documents -- recall is
    mathematically undefined (0/0), not zero. Callers must exclude None
    values from any average rather than treating them as 0."""
    if not relevant_names:
        return None
    top_k = retrieved_names[:k]
    hits = sum(1 for name in top_k if name in relevant_names)
    return hits / len(relevant_names)


def reciprocal_rank(retrieved_names: list[str], relevant_names: set[str]) -> float | None:
    """MRR@max(K_VALUES): looks for the first relevant hit within the top
    max(K_VALUES) (10) retrieved results, not an unbounded ranked list --
    evaluate_system() only ever retrieves that many per query.

    None when there are zero relevant documents, for the same reason as
    recall_at_k -- there is no "correct rank" to reach for a query with no
    relevant answer, so 0.0 would misleadingly count as a bad score rather
    than an undefined one."""
    if not relevant_names:
        return None
    for rank, name in enumerate(retrieved_names, start=1):
        if name in relevant_names:
            return 1.0 / rank
    return 0.0


def _mean(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    if not present:
        return None
    return sum(present) / len(present)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def evaluate_system(system_fn, golden_queries: list[dict]) -> list[dict]:
    """Returns one result row per golden query: metrics at every K in
    K_VALUES plus MRR, tagged with the query's id and category for the
    per-category breakdown in the report."""
    max_k = max(K_VALUES)
    rows = []
    for gq in golden_queries:
        retrieved = system_fn(gq["query"], max_k, gq.get("filters"))
        retrieved_names = [r["business_name"] for r in retrieved]
        relevant = set(gq["expected_relevant"])

        row = {
            "id": gq["id"],
            "category": gq["category"],
            "reciprocal_rank": reciprocal_rank(retrieved_names, relevant),
        }
        for k in K_VALUES:
            row[f"precision_at_{k}"] = precision_at_k(retrieved_names, relevant, k)
            row[f"recall_at_{k}"] = recall_at_k(retrieved_names, relevant, k)
        rows.append(row)
    return rows


def aggregate(rows: list[dict], category: str | None = None) -> dict:
    """Aggregate metrics across rows, optionally filtered to one category."""
    subset = [r for r in rows if category is None or r["category"] == category]
    agg = {"n": len(subset)}
    for k in K_VALUES:
        agg[f"precision_at_{k}"] = _mean([r[f"precision_at_{k}"] for r in subset])
        agg[f"recall_at_{k}"] = _mean([r[f"recall_at_{k}"] for r in subset])
    agg["mrr"] = _mean([r["reciprocal_rank"] for r in subset])
    return agg


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _fmt(value: float | None) -> str:
    return f"{value:.3f}" if value is not None else "n/a"


def render_report(results_by_system: dict[str, list[dict]], categories: list[str]) -> str:
    lines = []
    lines.append("# Search Evaluation Report (M4.1)")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"Golden queries: {len(GOLDEN_QUERIES)} across {len(categories)} categories")
    lines.append("")

    lines.append("## Overall")
    lines.append("")
    header = "| System | N | P@5 | P@10 | R@5 | R@10 | MRR |"
    sep = "|---|---|---|---|---|---|---|"
    lines.append(header)
    lines.append(sep)
    for system_name, rows in results_by_system.items():
        agg = aggregate(rows)
        lines.append(
            f"| {system_name} | {agg['n']} | {_fmt(agg['precision_at_5'])} | "
            f"{_fmt(agg['precision_at_10'])} | {_fmt(agg['recall_at_5'])} | "
            f"{_fmt(agg['recall_at_10'])} | {_fmt(agg['mrr'])} |"
        )
    lines.append("")

    lines.append("## By category")
    lines.append("")
    for category in categories:
        lines.append(f"### {category}")
        lines.append("")
        lines.append(header)
        lines.append(sep)
        for system_name, rows in results_by_system.items():
            agg = aggregate(rows, category=category)
            lines.append(
                f"| {system_name} | {agg['n']} | {_fmt(agg['precision_at_5'])} | "
                f"{_fmt(agg['precision_at_10'])} | {_fmt(agg['recall_at_5'])} | "
                f"{_fmt(agg['recall_at_10'])} | {_fmt(agg['mrr'])} |"
            )
        lines.append("")

    lines.append(
        "Note: recall@K and MRR are `n/a` for queries with zero expected "
        "relevant businesses (edge-02, edge-04) -- both metrics are "
        "mathematically undefined (0/0) for those, not zero, and are "
        "excluded from every average above rather than counted as failures."
    )
    lines.append("")

    lines.append("## Analysis")
    lines.append("")
    lines.append(
        "On this golden set, hybrid scores *lower* than vector-only overall "
        "(P@5 drops, most sharply on `synonym` queries). This is real signal, "
        "not a bug in this harness -- verified by direct inspection: for "
        "`syn-01` (\"computer hacking defense and security auditing firm\", "
        "targeting Cybersecurity), Atlas `$search` matches \"AI Solutions\" "
        "businesses on the single literal token \"computer\" (present in "
        "their keywords as \"computer vision\") -- a coincidental, irrelevant "
        "overlap. RRF has no way to tell a spurious single-word keyword hit "
        "from a genuine one, so it folds this into `matched_via: both` and "
        "wrongly outranks the correct Cybersecurity results. Vector-only, "
        "with no keyword signal to dilute its ranking, doesn't have this "
        "failure mode on these queries."
    )
    lines.append("")
    lines.append(
        "This is exactly the kind of gap a cross-encoder reranker could "
        "close (M4.2, not built here) -- a reranker sees full query+document "
        "semantic relevance, not just token overlap, so it could down-rank "
        "a document that only coincidentally shares one word with the "
        "query. It's also exactly why design-doc-v2.md gates reranking on "
        "evidence from this eval set rather than shipping it by assertion."
    )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    load_dotenv()

    categories = sorted({gq["category"] for gq in GOLDEN_QUERIES})

    results_by_system = {}
    for system_name, system_fn in SYSTEMS.items():
        print(f"Evaluating {system_name} ({len(GOLDEN_QUERIES)} queries)...")
        t0 = time.perf_counter()
        try:
            results_by_system[system_name] = evaluate_system(system_fn, GOLDEN_QUERIES)
        except Exception as e:
            print(
                f"FAIL: evaluating {system_name!r} raised — most likely the "
                f"embedding model or Atlas is unavailable. Check MONGODB_URI "
                f"and that both Atlas indexes are queryable. "
                f"Underlying error: {e}"
            )
            return 1
        elapsed = time.perf_counter() - t0
        print(f"  done in {elapsed:.1f}s")

    report = render_report(results_by_system, categories)
    print()
    print(report)

    REPORT_DIR.mkdir(exist_ok=True)
    report_path = REPORT_DIR / f"report_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"Report written to {report_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
