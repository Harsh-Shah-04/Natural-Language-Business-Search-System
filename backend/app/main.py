import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from app.embeddings import get_embedder, get_model_health
from app.filters import FilterValidationError, get_filter_allowlist
from app.schemas import SearchRequest, SearchResponse
from app.search import SearchUnavailableError, search_businesses


def _warm_up_embedder() -> None:
    # get_embedder() already records failures via get_model_health()'s
    # state, so swallow here rather than letting the daemon thread crash
    # with an unhandled traceback on every failed load.
    try:
        get_embedder()
    except Exception:
        pass


def _warm_up_filters() -> None:
    # Best-effort: a cache miss on first use just means the next call
    # queries Mongo directly (see app/filters.py) — no state to record here.
    try:
        get_filter_allowlist()
    except Exception:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the embedding model and the filter allow-list in the background
    # so the API is reachable instantly — no live request ever eats a cold
    # model-load or a cold allow-list query.
    threading.Thread(target=_warm_up_embedder, daemon=True).start()
    threading.Thread(target=_warm_up_filters, daemon=True).start()
    yield


app = FastAPI(title="Business Search Backend", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/model")
def health_model() -> dict[str, str]:
    return get_model_health()


@app.get("/api/filters/values")
def filters_values() -> dict[str, list[str]]:
    allowlist = get_filter_allowlist()
    return {field: sorted(values) for field, values in allowlist.items()}


@app.post("/api/search")
def search(request: SearchRequest) -> SearchResponse:
    filters_dict = request.filters.model_dump() if request.filters else None
    try:
        results = search_businesses(request.query, request.limit, filters_dict)
    except FilterValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except SearchUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return SearchResponse(query=request.query, results=results, filters=request.filters)
