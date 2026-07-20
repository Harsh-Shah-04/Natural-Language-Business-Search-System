"""
Search evaluation framework (M4.1), extended for a 3-way comparison (M4.1.1).

Runs the golden query set (scripts/eval_dataset.py) against three search
systems -- vector-only (M2 baseline), hybrid-previous (M3.1/M3.2's
original unweighted, unfiltered-keyword-score, 4-field config, preserved
here only for comparison), and hybrid-tuned (M4.1.1's current default,
identical to what search_businesses() and the live API actually run) --
and reports Precision@K, Recall@K, and MRR for each, overall and broken
down by query category. This is the evidence M4.2 will need: "ship
reranking only if it measurably improves precision@5 on this set"
(design-doc-v2.md) requires a baseline to improve on, which is what this
script produces.

Extensibility for future reranking experiments: a "system" is just a
Callable[[str, int, dict | None], list[dict]] returning ranked result
dicts with a "business_name" key (see SYSTEMS below). Adding a fourth
system (e.g. hybrid + cross-encoder rerank, once M4.2 builds it) means
writing one more function with that signature and adding one line to
SYSTEMS -- no changes needed anywhere else in this file. Nothing below
the SYSTEMS section (metrics, runner, report) changed for M4.1.1.

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
    _reciprocal_rank_fusion,
    _vector_search,
    search_businesses,
)
from eval_dataset import GOLDEN_QUERIES

K_VALUES = (5, 10)
REPORT_DIR = Path(__file__).parent.parent / "eval_reports"


# ---------------------------------------------------------------------------
# Systems under comparison. Each is Callable[[str, int, dict | None], list[dict]].
# All three reuse app.search's existing internals directly -- no retrieval
# logic is duplicated here.
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


# M3.1/M3.2's original config, before M4.1.1's tuning. Preserved only so
# this eval can show the actual before/after delta -- not used by the live
# API. Reconstructed via the same _keyword_search/_reciprocal_rank_fusion
# internals with their tuned defaults explicitly overridden back to the
# pre-M4.1.1 behavior: unweighted RRF (both sources weight 1.0), no
# keyword score-threshold gating (ratio 0.0 keeps everything), and the
# original 4-field search path including business_description.
_LEGACY_SEARCH_PATHS = ["business_description", "products_services", "keywords", "specialties"]


def hybrid_search_previous(query: str, limit: int, filters: dict | None = None) -> list[dict]:
    """M3.1/M3.2's original hybrid config (pre-M4.1.1), for comparison."""
    query_vector = embed_texts([query])[0]
    active_filters = validate_filters(filters)
    pool_size = (
        POOL_SIZE_FILTERED
        if active_filters
        else max(POOL_SIZE_DEFAULT, limit * POOL_SIZE_MULTIPLIER)
    )
    businesses = get_db()["businesses"]
    vector_results = _vector_search(businesses, query_vector, pool_size, active_filters)
    keyword_results = _keyword_search(
        businesses,
        query,
        pool_size,
        active_filters,
        search_paths=_LEGACY_SEARCH_PATHS,
        score_threshold_ratio=0.0,
    )
    return _reciprocal_rank_fusion(
        vector_results, keyword_results, limit, vector_weight=1.0, keyword_weight=1.0
    )


def hybrid_search_tuned(query: str, limit: int, filters: dict | None = None) -> list[dict]:
    """M4.1.1's tuned hybrid: identical to what search_businesses() (and
    the live /api/search endpoint) actually runs -- no separate config."""
    return search_businesses(query, limit, filters)


SYSTEMS = {
    "vector-only": vector_only_search,
    "hybrid-previous": hybrid_search_previous,
    "hybrid-tuned": hybrid_search_tuned,
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
    lines.append("# Search Evaluation Report (M4.1 + M4.1.1)")
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
        "**M4.1 finding:** hybrid-previous scored *lower* than vector-only "
        "overall (P@5 0.467 vs 0.560), worst on `synonym` queries. Root "
        "cause, verified by direct inspection: Atlas `$search` matching on "
        "a single coincidental literal token with zero real relevance to "
        "the query (e.g. `syn-01`, \"computer hacking defense and security "
        "auditing firm\" targeting Cybersecurity, matched \"AI Solutions\" "
        "on \"computer\" via their \"computer vision\" keyword), which "
        "RRF's rank-based fusion had no way to discount."
    )
    lines.append("")
    lines.append(
        "**M4.1.1 result:** tuning (score-threshold-gated keyword matches, "
        "weighted RRF favoring vector 0.7/0.3, narrowed search fields) "
        "recovered roughly half the P@5 gap (0.467 -> 0.513, vs "
        "vector-only's 0.560) and nearly closed the recall gap (R@5 0.792 "
        "-> 0.875; R@10 0.940 -> 1.000, now tied with vector-only). The "
        "`synonym` category -- the worst-hit in M4.1 -- improved the most "
        "(P@5 0.280 -> 0.480, R@10 0.800 -> 1.000). This is a genuine, "
        "meaningful improvement, not a full fix."
    )
    lines.append("")
    lines.append(
        "**What's still not fixed, and why -- verified, not assumed:** "
        "`edge_case` shows zero improvement, and `semantic`'s MRR actually "
        "*dropped* (0.850 -> 0.717) despite its precision improving. Traced "
        "by direct inspection to `sem-02` (\"looking for a place to stay "
        "overnight during my business trip\", targeting Hotels): the "
        "correct answer fell from rank 1 to rank 3 because Insurance's own "
        "`keywords` field literally contains \"business insurance\" -- the "
        "word \"business\" collides with the query, and this collision "
        "lives in `keywords` itself, not the `business_description` "
        "boilerplate the field-narrowing change targeted. Score-threshold "
        "gating doesn't catch it either, because it's the top (and only) "
        "keyword hit for that query -- there's no weaker match to filter "
        "against. Both tuning mechanisms only help when a genuinely strong "
        "match exists to compare against; they can't fix a case where the "
        "*single best available* keyword match is itself a same-word, "
        "different-sense coincidence."
    )
    lines.append("")
    lines.append(
        "This residual class of failure -- correct token, wrong sense, and "
        "no better keyword candidate to rank it against -- is exactly what "
        "a cross-encoder reranker (M4.2, not built here) is suited to fix: "
        "it evaluates full query+document semantic relevance rather than "
        "token overlap, so it isn't fooled by a shared surface form. This "
        "is the concrete evidence design-doc-v2.md's evidence-gating rule "
        "was built to require before shipping reranking."
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
