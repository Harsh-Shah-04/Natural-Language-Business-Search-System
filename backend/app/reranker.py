"""
Cross-encoder reranking (M4.2).

Loads cross-encoder/ms-marco-MiniLM-L-6-v2 as a lazy singleton, guarded the
same way as app/embeddings.py's embedder and app/db.py's MongoClient. The
model loads once per process and is reused across requests.

Runs *after* hybrid search, on a wider candidate pool than the final result
(see app/search.py): the cross-encoder rescores the fused top-N by full
attention over each (query, document) pair, so it judges semantic relevance
directly rather than via vector distance. This targets the exact failure
mode M4.1/M4.1.1 identified and couldn't fix at the retrieval layer — a
query and a document sharing a surface token in different senses (e.g.
"business trip" vs "business insurance") get a low cross-encoder score
because the model reads the whole phrase, not just token overlap.
"""

import threading

from sentence_transformers import CrossEncoder

from app.constants import RERANKER_MODEL_NAME
from app.embeddings import build_embedding_text

_model: CrossEncoder | None = None
_model_lock = threading.Lock()

_state_lock = threading.Lock()
_state = "not_started"  # not_started -> loading -> ready | error
_state_detail: str | None = None


def get_reranker_health() -> dict[str, str]:
    with _state_lock:
        health = {"status": _state}
        if _state_detail:
            health["detail"] = _state_detail
        return health


def _set_state(state: str, detail: str | None = None) -> None:
    global _state, _state_detail
    with _state_lock:
        _state = state
        _state_detail = detail


def get_reranker() -> CrossEncoder:
    """Return the loaded cross-encoder, loading it on first call. Blocks the
    calling thread until ready — callers needing a non-blocking startup
    should load from a background thread (see app/main.py)."""
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:  # re-check: another thread may have won the race
                _set_state("loading")
                try:
                    model = CrossEncoder(RERANKER_MODEL_NAME)
                except Exception as e:
                    _set_state("error", str(e))
                    raise
                _model = model
                _set_state("ready")
    return _model


def rerank_candidates(query: str, candidates: list[dict], top_n: int) -> list[dict]:
    """Rescore the top `top_n` candidates with the cross-encoder and re-sort
    them by that score; candidates beyond top_n keep their original order and
    stay after the reranked block.

    Each reranked candidate's `score` is replaced with the cross-encoder
    relevance score (the RRF score it carried in is no longer the ranking
    signal); `matched_via` is preserved from fusion so the caller can still
    see whether a result came from semantic / keyword / both. The document
    side reuses build_embedding_text() (same fields the embedder uses) so
    query- and document-time text construction stay consistent.
    """
    if not candidates:
        return candidates

    pool = candidates[:top_n]
    rest = candidates[top_n:]

    model = get_reranker()
    pairs = [(query, build_embedding_text(doc)) for doc in pool]
    scores = model.predict(pairs)

    for doc, score in zip(pool, scores):
        doc["score"] = float(score)

    pool_sorted = sorted(pool, key=lambda d: d["score"], reverse=True)
    return pool_sorted + rest
