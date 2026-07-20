import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from app.embeddings import get_embedder, get_model_health
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the embedding model in the background so the API is reachable
    # instantly — no live request ever eats a cold model-load.
    threading.Thread(target=_warm_up_embedder, daemon=True).start()
    yield


app = FastAPI(title="Business Search Backend", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/model")
def health_model() -> dict[str, str]:
    return get_model_health()


@app.post("/api/search")
def search(request: SearchRequest) -> SearchResponse:
    try:
        results = search_businesses(request.query, request.limit)
    except SearchUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return SearchResponse(query=request.query, results=results)
