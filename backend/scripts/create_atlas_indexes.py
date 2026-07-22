"""
Create or update Atlas Search indexes from scripts/atlas_indexes/*.json.

Safe to re-run. Creates missing indexes; for an existing search index whose
definition drifted (e.g. a newly mapped field), calls update_search_index so
$search can see the new field without a manual Atlas UI edit.

Requires MONGODB_URI in .env.

Run: uv run python scripts/create_atlas_indexes.py
"""

import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from pymongo.operations import SearchIndexModel

from app.db import get_db

INDEXES_DIR = Path(__file__).parent / "atlas_indexes"
INDEX_SPECS = [
    ("business_vector_index", "vectorSearch", INDEXES_DIR / "vector_index.json"),
    ("business_search_index", "search", INDEXES_DIR / "search_index.json"),
]
POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 180


def _wait_queryable(businesses, names: set[str]) -> int:
    if not names:
        return 0
    print(
        f"Waiting for {len(names)} index(es) to become queryable "
        f"(up to {POLL_TIMEOUT_SECONDS}s)..."
    )
    deadline = time.time() + POLL_TIMEOUT_SECONDS
    pending = set(names)
    while pending and time.time() < deadline:
        time.sleep(POLL_INTERVAL_SECONDS)
        for idx in businesses.list_search_indexes():
            if idx["name"] in pending and idx.get("queryable"):
                print(f"READY: {idx['name']}")
                pending.discard(idx["name"])
    if pending:
        print(f"FAIL: still not queryable after {POLL_TIMEOUT_SECONDS}s: {pending}")
        return 1
    return 0


def main() -> int:
    load_dotenv()
    db = get_db()
    businesses = db["businesses"]

    existing = {idx["name"]: idx for idx in businesses.list_search_indexes()}

    created_or_updated: set[str] = set()
    for name, index_type, definition_path in INDEX_SPECS:
        definition = json.loads(definition_path.read_text())
        if name not in existing:
            model = SearchIndexModel(
                definition=definition, name=name, type=index_type
            )
            businesses.create_search_index(model)
            print(f"CREATED (building): {name}")
            created_or_updated.add(name)
            continue

        # Vector indexes are rarely redefined here; only refresh the Lucene
        # search index when the on-disk definition adds/removes mapped fields
        # (minimal change for name-lookup: business_name).
        if index_type == "search":
            current = existing[name].get("latestDefinition") or existing[name].get(
                "definition"
            )
            if current != definition:
                businesses.update_search_index(name, definition)
                print(f"UPDATED (rebuilding): {name}")
                created_or_updated.add(name)
            else:
                print(f"SKIP: {name} already matches definition")
        else:
            print(f"SKIP: {name} already exists")

    if not created_or_updated:
        print("All indexes already exist and match — nothing to wait for.")
        return 0

    rc = _wait_queryable(businesses, created_or_updated)
    if rc == 0:
        print("PASS: all indexes created/updated and queryable")
    return rc


if __name__ == "__main__":
    sys.exit(main())
