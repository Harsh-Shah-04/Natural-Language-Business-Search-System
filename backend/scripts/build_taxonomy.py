"""
Build the trusted service taxonomy from the seed dataset (M6.1).

WHY THIS IS A BUILD STEP AND NOT A RUNTIME QUERY
------------------------------------------------
The obvious way to get the list of service categories is
`businesses.distinct("sub_category")` -- app/filters.py already does exactly
that for the filter allow-list. That source is correct for filters and wrong
for the taxonomy, because POST /api/businesses is unauthenticated and
`sub_category` is free text. Anything reaching the collection through that
route would become "the taxonomy", and the taxonomy is what the query-intent
layer treats as trusted closed-set content (and, once the LLM provider lands,
what goes into a prompt). See app/taxonomy.py for the full argument.

So the taxonomy is derived from the checked-in .xlsx -- the same file
scripts/seed.py reads -- and committed as app/taxonomy.json. Regenerating it
is a deliberate act that shows up in a diff and gets reviewed. Registration
cannot reach it.

WHY CATEGORY-LEVEL PROFILES ARE LOSSLESS HERE
---------------------------------------------
Measured, not assumed: in all 40 sub-categories, `keywords`, `specialties`
and `products_services` are byte-identical across all three member
businesses -- only `business_description` varies. This script asserts that and
fails loudly if it ever stops being true. One profile per category therefore
carries the full discriminative vocabulary of its three businesses, so the
taxonomy is 40 entries rather than 120 with no loss. (This is also why any
future doc2query enrichment should be 40 calls, not 120.)

Run: uv run python scripts/build_taxonomy.py [path/to/dataset.xlsx]
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

# Same contract seed.py uses to read the dataset, imported rather than
# duplicated so the two can never drift on column order.
from seed import DEFAULT_DATASET_PATH, parse_rows

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "app" / "taxonomy.json"

# Fields that must be identical across a category's members for the
# category-level profile to be lossless. Asserted below, never assumed.
INVARIANT_FIELDS = ["keywords", "specialties", "products_services"]


def _clean(value) -> str:
    return str(value).strip() if value is not None else ""


def build(documents: list[dict]) -> dict:
    by_category: dict[str, list[dict]] = defaultdict(list)
    for doc in documents:
        by_category[_clean(doc["sub_category"])].append(doc)

    violations = []
    categories = {}
    for name in sorted(by_category):
        members = by_category[name]
        for field in INVARIANT_FIELDS:
            distinct = {_clean(m.get(field)) for m in members}
            if len(distinct) != 1:
                violations.append(f"{name}.{field}: {len(distinct)} distinct values")

        head = members[0]
        categories[name] = {
            "sub_category": name,
            "industry": _clean(head["industry"]),
            "nature": _clean(head["nature"]),
            # The category's own discriminative vocabulary, straight from the
            # dataset. This is the text the intent classifier embeds, and the
            # text the UI shows as the inferred need -- nothing is authored
            # here, so the panel can never claim more than the corpus says.
            "specialties": _clean(head.get("specialties")),
            "keywords": _clean(head.get("keywords")),
            "products_services": _clean(head.get("products_services")),
            # Reserved for the LLM provider (M6.2): a natural-language
            # paraphrase of the underlying need, e.g. "phishing protection and
            # employee security awareness". Deliberately null -- that phrasing
            # is world knowledge, absent from this corpus, and hand-authoring
            # it here would be hardcoding the demo.
            "need": None,
            "member_count": len(members),
        }

    if violations:
        raise SystemExit(
            "FAIL: category-level profiles would lose information.\n  "
            + "\n  ".join(violations)
            + "\n\nA category-level taxonomy is only valid while these fields are "
            "uniform within a category. Switch to per-business profiles, or "
            "aggregate the distinct values, before regenerating."
        )

    return {
        "_source": "Business_Matchmaking_Test_Dataset_V2_120_Companies.xlsx",
        "_generator": "scripts/build_taxonomy.py",
        "_note": (
            "TRUSTED, CODE-OWNED DATA. Generated from the checked-in seed dataset, "
            "never from the businesses collection -- POST /api/businesses is "
            "unauthenticated, so collection-derived values are attacker-influenced. "
            "Do not hand-edit; re-run the generator."
        ),
        "business_count": len(documents),
        "category_count": len(categories),
        "categories": categories,
    }


def main() -> int:
    xlsx_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DATASET_PATH
    if not xlsx_path.exists():
        print(f"FAIL: dataset not found at {xlsx_path}")
        return 1

    documents = parse_rows(xlsx_path)
    taxonomy = build(documents)

    OUTPUT_PATH.write_text(
        json.dumps(taxonomy, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        f"PASS: {taxonomy['category_count']} categories from "
        f"{taxonomy['business_count']} businesses -> app/{OUTPUT_PATH.name}"
    )
    print(f"      invariant within every category: {', '.join(INVARIANT_FIELDS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
