# Backend — M1.1 (Atlas + FastAPI spike)

Scope of this milestone only: prove the MongoDB Atlas index configuration
works before any real data or ML code depends on it. No business logic,
no ingestion, no embedding model yet — those are M1.2/M1.3.

## Setup

1. **Install dependencies:**
   ```
   cd backend
   uv sync
   ```

2. **Create a free MongoDB Atlas M0 cluster** (no credit card required):
   - Sign up / log in at https://cloud.mongodb.com
   - Create a new Project, then a new Cluster on the **M0 (Free)** tier
   - Database Access -> add a database user with a password
   - Network Access -> add your current IP (or `0.0.0.0/0` for local dev only)
   - Once the cluster is up: Connect -> Drivers -> Python -> copy the connection string

3. **Configure environment:**
   ```
   cp .env.example .env
   ```
   Paste your connection string into `MONGODB_URI`, and set `DB_NAME` (default `business_search` is fine).

4. **Create the two Atlas indexes** (Atlas Search index types aren't creatable via the
   standard pymongo driver — this is a one-time step in the Atlas UI):
   - In the cluster: Atlas Search tab -> Create Search Index -> JSON Editor
   - Select your `business_search` database, `businesses` collection (it will be created on first insert)
   - Paste `scripts/atlas_indexes/vector_index.json` for the **vectorSearch**-type index
   - Repeat, pasting `scripts/atlas_indexes/search_index.json` for the **search**-type index
   - Wait for both to show status "Active" (usually under a minute for an empty collection)

## Run

Start the API:
```
uv run uvicorn app.main:app --reload
```
Check it's up: `curl http://127.0.0.1:8000/health` -> `{"status":"ok"}`

Verify the Atlas spike (both indexes actually work end-to-end):
```
uv run python scripts/verify_atlas_spike.py
```
Expected output: `PASS: both $vectorSearch and $search found the test document`

## Field naming convention

The dataset's xlsx columns map to snake_case document fields going forward
(`business_description`, `products_services`, `keywords`, `specialties`, etc.) —
established here since the search index definition needs concrete field names,
and M1.2's ingestion script will follow the same convention.
