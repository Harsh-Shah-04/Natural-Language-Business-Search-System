"""
Create the two Atlas Search indexes for M1.1 programmatically, via the
pymongo driver, instead of manually pasting JSON into the Atlas UI.
Reproducible and avoids manual-entry mistakes (e.g. a mistyped index name
or username, which is exactly what happened during this milestone's
initial setup). Safe to re-run — skips indexes that already exist.

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
POLL_TIMEOUT_SECONDS = 120


def main() -> int:
    load_dotenv()
    db = get_db()
    businesses = db["businesses"]

    existing = {idx["name"] for idx in businesses.list_search_indexes()}

    created = []
    for name, index_type, definition_path in INDEX_SPECS:
        if name in existing:
            print(f"SKIP: {name} already exists")
            continue
        definition = json.loads(definition_path.read_text())
        model = SearchIndexModel(definition=definition, name=name, type=index_type)
        businesses.create_search_index(model)
        print(f"CREATED (building): {name}")
        created.append(name)

    if not created:
        print("All indexes already exist — nothing to wait for.")
        return 0

    print(f"Waiting for {len(created)} index(es) to become queryable (up to {POLL_TIMEOUT_SECONDS}s)...")
    deadline = time.time() + POLL_TIMEOUT_SECONDS
    pending = set(created)
    while pending and time.time() < deadline:
        time.sleep(POLL_INTERVAL_SECONDS)
        for idx in businesses.list_search_indexes():
            if idx["name"] in pending and idx.get("queryable"):
                print(f"READY: {idx['name']}")
                pending.discard(idx["name"])

    if pending:
        print(f"FAIL: still not queryable after {POLL_TIMEOUT_SECONDS}s: {pending}")
        return 1

    print("PASS: all indexes created and queryable")
    return 0


if __name__ == "__main__":
    sys.exit(main())
