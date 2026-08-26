"""
Is the LLM intent layer reproducible? (measurement only, M6.2)

THE QUESTION
------------
Earlier runs produced different intents for the same query -- the reviewer's
query returned ['Cybersecurity'] once and ['Cybersecurity', 'Corporate
Training'] another time, and that second category changed a retrieval metric.
That was two anecdotes. This repeats each query N times and measures the
actual agreement rate before anyone calls the system nondeterministic.

WHY THERE IS ONLY ONE ARM
-------------------------
The obvious hypothesis is sampling temperature. It is already ruled out by
inspection, not assumption: app/llm.py sends temperature=0 on every request
today. top_p, seed and response_format are all absent (provider defaults), the
system prompt is a fixed string, and category ordering comes from
taxonomy.json sorted, identical on every call. So a "temperature=0 arm" would
be byte-identical to the current arm, and running it would spend another N*Q
calls proving 0 == 0. If variation shows up here, temperature is not the cause
-- which is the finding, not a limitation.

RAW OUTPUT IS CAPTURED PRE-VALIDATION
-------------------------------------
This calls llm.complete() and parses the payload itself rather than going
through infer_intent(), because _llm_intent() drops unknown categories via
is_known_category() before returning. Going through it would make hallucinated
categories invisible -- and "did the model ever emit a category outside the
trusted taxonomy" is precisely one of the questions being asked.

MAX TOKENS
----------
Run with LLM_MAX_TOKENS=1500. The code default of 400 is known to fail on
reasoning models (deepseek-v4-flash spends the whole budget on reasoning_tokens
and returns content=""), and a budget failure is not "variation" -- it would
confound the measurement with a different defect.

Nothing in app/ is modified and no production default changes.

Run:
  LLM_API_KEY=... LLM_PROVIDER=openai LLM_BASE_URL=https://api.deepseek.com \
  LLM_MODEL=deepseek-v4-flash LLM_MAX_TOKENS=1500 LLM_TIMEOUT_SECONDS=45 \
      uv run python scripts/measure_intent_determinism.py [reps]
"""

import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv()

from app import intent as intent_module  # noqa: E402
from app import llm  # noqa: E402
from app.taxonomy import category_names, is_known_category  # noqa: E402

REPS = int(sys.argv[1]) if len(sys.argv) > 1 else 20

# (id, query, categories a correct answer should contain, expects_negation)
QUERIES = [
    ("Q1-phishing", "My company keeps getting suspicious emails and I want someone "
                    "to make sure our employees don't fall for scams.",
     {"Cybersecurity"}, False),
    ("Q2-traffic", "My website keeps crashing whenever we get a lot of visitors.",
     {"Cloud Services"}, False),
    ("Q3-spoiling", "Our vegetables keep spoiling before they reach customers.",
     {"Cold Chain"}, False),
    ("Q4-money", "I need someone to help us manage our money and investments.",
     {"Investment Advisors"}, False),
    ("Q5-negation", "I don't want WhatsApp bot companies.",
     set(), True),
]


def _prompt() -> str:
    return intent_module._LLM_SYSTEM_PROMPT.format(
        categories="\n".join(f"- {n}" for n in category_names())
    )


def one_call(query: str) -> dict:
    """One raw round-trip. Returns the parsed payload plus timing, or an error
    record -- an error is a real outcome for a reliability study, not something
    to retry away."""
    started = time.perf_counter()
    try:
        completion = llm.complete(_prompt(), f"Situation: {query.strip()}", prefill="{")
        elapsed = (time.perf_counter() - started) * 1000
        payload = intent_module._parse_llm_json(completion, prefill="{")
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}",
                "latency_ms": (time.perf_counter() - started) * 1000}

    raw_categories = payload.get("service_categories")
    if not isinstance(raw_categories, list):
        raw_categories = []
    raw_categories = [c for c in raw_categories if isinstance(c, str)]
    raw_exclusions = payload.get("exclusions")
    if not isinstance(raw_exclusions, list):
        raw_exclusions = []

    return {
        "ok": True,
        "latency_ms": elapsed,
        "underlying_need": str(payload.get("underlying_need", "")),
        # PRE-validation: exactly what the model emitted.
        "categories_raw": raw_categories,
        # POST-validation: what would survive is_known_category().
        "categories_valid": [c for c in raw_categories if is_known_category(c)],
        "hallucinated": [c for c in raw_categories if not is_known_category(c)],
        "expanded_query": str(payload.get("expanded_query", "")),
        "exclusions": [str(e) for e in raw_exclusions],
        "confidence": payload.get("confidence"),
    }


def analyse(qid: str, query: str, expected: set, expects_negation: bool,
            runs: list[dict]) -> dict:
    ok = [r for r in runs if r["ok"]]
    errors = len(runs) - len(ok)
    if not ok:
        return {"id": qid, "runs": len(runs), "errors": errors, "all_failed": True}

    def modal(values):
        return Counter(values).most_common(1)[0]

    cats = [tuple(r["categories_valid"]) for r in ok]
    needs = [r["underlying_need"] for r in ok]
    expqs = [r["expanded_query"] for r in ok]
    excls = [tuple(r["exclusions"]) for r in ok]
    confs = [r["confidence"] for r in ok if isinstance(r["confidence"], (int, float))]
    # "Exact intent" = every semantic field identical.
    exact = [(c, n, e, x) for c, n, e, x in zip(cats, needs, expqs, excls)]

    top_cat, top_cat_n = modal(cats)
    top_exact, top_exact_n = modal(exact)

    correct = [set(c) & expected != set() for c in cats] if expected else []
    hallucinated = [h for r in ok for h in r["hallucinated"]]
    negation_present = [len(x) > 0 for x in excls]
    positive_on_negation = [len(c) > 0 for c in cats] if expects_negation else []

    return {
        "id": qid, "query": query, "runs": len(runs), "errors": errors,
        "exact_agreement": top_exact_n / len(ok),
        "category_agreement": top_cat_n / len(ok),
        "modal_categories": list(top_cat),
        "distinct_category_sets": len(set(cats)),
        "category_sets": {str(list(k)): v for k, v in Counter(cats).items()},
        "distinct_needs": len(set(needs)),
        "sample_needs": sorted(set(needs))[:6],
        "distinct_expanded": len(set(expqs)),
        "sample_expanded": sorted(set(expqs))[:4],
        "confidence_values": dict(Counter(confs)),
        "confidence_min": min(confs) if confs else None,
        "confidence_max": max(confs) if confs else None,
        "correct_rate": (sum(correct) / len(correct)) if correct else None,
        "hallucinated_categories": dict(Counter(hallucinated)),
        "negation_kept_rate": (sum(negation_present) / len(ok)) if expects_negation else None,
        "negation_flipped_positive": (sum(positive_on_negation)) if expects_negation else None,
        "distinct_exclusion_sets": len(set(excls)) if expects_negation else None,
        "exclusion_sets": ({str(list(k)): v for k, v in Counter(excls).items()}
                           if expects_negation else None),
        "latency_p50": statistics.median(r["latency_ms"] for r in ok),
        "latency_max": max(r["latency_ms"] for r in ok),
    }


def main() -> int:
    if not llm.is_configured():
        raise SystemExit("LLM not configured. Set LLM_API_KEY / LLM_PROVIDER / LLM_MODEL.")

    print(f"model={llm.describe()}  reps={REPS}  queries={len(QUERIES)}  "
          f"total calls={REPS * len(QUERIES)}")
    print(f"sampling: temperature=0 (already), top_p/seed/response_format absent")
    print()

    out = {"model": llm.describe(), "reps": REPS, "queries": []}
    for qid, query, expected, negates in QUERIES:
        print(f"{qid}: ", end="", flush=True)
        runs = []
        for _ in range(REPS):
            r = one_call(query)
            runs.append(r)
            print("." if r["ok"] else "x", end="", flush=True)
        print()
        summary = analyse(qid, query, expected, negates, runs)
        summary["runs_detail"] = runs
        out["queries"].append(summary)

    print()
    print("=" * 100)
    print(f"AGREEMENT OVER {REPS} IDENTICAL REQUESTS PER QUERY")
    print("=" * 100)
    print(f"{'query':<14}{'exact':>8}{'category':>10}{'needs':>8}{'expq':>7}"
          f"{'conf':>7}{'correct':>9}{'halluc':>8}{'err':>5}{'p50 ms':>9}")
    print("-" * 100)
    for s in out["queries"]:
        if s.get("all_failed"):
            print(f"{s['id']:<14}  ALL {s['runs']} CALLS FAILED")
            continue
        rate = s["correct_rate"]
        correct = "n/a" if rate is None else f"{rate:.2f}"
        print(f"{s['id']:<14}{s['exact_agreement']:>8.2f}{s['category_agreement']:>10.2f}"
              f"{s['distinct_needs']:>8}{s['distinct_expanded']:>7}"
              f"{len(s['confidence_values']):>7}{correct:>9}"
              f"{len(s['hallucinated_categories']):>8}{s['errors']:>5}"
              f"{s['latency_p50']:>9.0f}")
    print()
    print("  exact    = fraction of runs sharing the single most common "
          "(categories, need, expanded_query, exclusions)")
    print("  category = fraction sharing the most common validated category set")
    print("  needs/expq/conf = number of DISTINCT values seen across the runs (1 = stable)")
    print()

    for s in out["queries"]:
        if s.get("all_failed"):
            continue
        print("=" * 100)
        print(f"{s['id']}  {s['query']}")
        print("=" * 100)
        print(f"  category sets seen : {s['category_sets']}")
        print(f"  confidence values  : {s['confidence_values']}")
        print(f"  distinct needs ({s['distinct_needs']}):")
        for n in s["sample_needs"]:
            print(f"      {n!r}")
        print(f"  distinct expanded_query ({s['distinct_expanded']}):")
        for e in s["sample_expanded"]:
            print(f"      {e!r}")
        if s["hallucinated_categories"]:
            print(f"  !! HALLUCINATED (dropped by is_known_category): "
                  f"{s['hallucinated_categories']}")
        if s["negation_kept_rate"] is not None:
            print(f"  negation kept in exclusions : {s['negation_kept_rate']:.2f} of runs")
            print(f"  runs that returned a POSITIVE category: "
                  f"{s['negation_flipped_positive']} of {s['runs'] - s['errors']}")
            print(f"  exclusion sets : {s['exclusion_sets']}")
        print(f"  latency p50/max : {s['latency_p50']:.0f} / {s['latency_max']:.0f} ms")
        print()

    dest = Path(__file__).parent.parent / "eval_reports" / "intent_determinism.json"
    dest.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
