import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from app.embeddings import get_embedder, get_model_health
from app.filters import FilterValidationError, get_filter_allowlist
from app.reranker import get_reranker, get_reranker_health
from app.schemas import SearchRequest, SearchResponse
from app.search import RERANK_ENABLED, SearchUnavailableError, search_businesses


def _warm_up_embedder() -> None:
    # get_embedder() already records failures via get_model_health()'s
    # state, so swallow here rather than letting the daemon thread crash
    # with an unhandled traceback on every failed load.
    try:
        get_embedder()
    except Exception:
        pass


def _warm_up_reranker() -> None:
    # get_reranker() records failures via get_reranker_health(); swallow
    # here so a failed load doesn't crash the daemon thread with a traceback.
    try:
        get_reranker()
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
    # Load the models and the filter allow-list in the background so the API
    # is reachable instantly — no live request ever eats a cold model-load or
    # a cold allow-list query. The reranker only warms up when reranking is
    # enabled, so a rerank-off deployment doesn't pay its ~80MB / load time.
    threading.Thread(target=_warm_up_embedder, daemon=True).start()
    threading.Thread(target=_warm_up_filters, daemon=True).start()
    if RERANK_ENABLED:
        threading.Thread(target=_warm_up_reranker, daemon=True).start()
    yield


app = FastAPI(title="Business Search Backend", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/model")
def health_model() -> dict[str, str]:
    return get_model_health()


@app.get("/health/reranker")
def health_reranker() -> dict[str, str]:
    # Independent from /health/model (the embedder): the two models load
    # separately, and search still works if the reranker is down (results
    # just aren't reranked). Reports "not_started" when reranking is disabled
    # and nothing has triggered a lazy load.
    return get_reranker_health()


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
