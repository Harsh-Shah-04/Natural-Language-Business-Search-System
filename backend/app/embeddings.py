"""
Embedding pipeline (M1.3).

Loads BAAI/bge-small-en-v1.5 as a lazy singleton, guarded the same way as
app/db.py's MongoClient singleton. The model loads once per process and is
reused for both bulk ingestion (scripts/seed.py) and the FastAPI background
warm-up wired up in app/main.py.
"""

import threading

from sentence_transformers import SentenceTransformer

from app.constants import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL_NAME

_model: SentenceTransformer | None = None
_model_lock = threading.Lock()

_state_lock = threading.Lock()
_state = "not_started"  # not_started -> loading -> ready | error
_state_detail: str | None = None


def get_model_health() -> dict[str, str]:
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


def get_embedder() -> SentenceTransformer:
    """Return the loaded embedding model, loading it on first call.

    Blocks the calling thread until the model is ready. Callers that need a
    non-blocking startup (the FastAPI app) should call this from a
    background thread instead of the request path — see app/main.py.
    """
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                _set_state("loading")
                try:
                    model = SentenceTransformer(EMBEDDING_MODEL_NAME)
                    # sentence-transformers renamed this method in newer
                    # releases; support either without pinning an exact version.
                    get_dims = getattr(
                        model,
                        "get_embedding_dimension",
                        model.get_sentence_embedding_dimension,
                    )
                    actual_dims = get_dims()
                    if actual_dims != EMBEDDING_DIMENSIONS:
                        raise RuntimeError(
                            f"{EMBEDDING_MODEL_NAME} produced {actual_dims}-dim "
                            f"vectors, expected {EMBEDDING_DIMENSIONS} "
                            f"(app/constants.py, and the Atlas index's numDimensions)"
                        )
                except Exception as e:
                    _set_state("error", str(e))
                    raise
                _model = model
                _set_state("ready")
    return _model


def build_embedding_text(doc: dict) -> str:
    """Concatenate the fields carrying semantic signal, per design-doc-v2.md.

    `business_name` is included so exact/near name queries can match via
    vector search for registered businesses whose description does not
    repeat the name (seeded rows already get the name via description
    boilerplate; including it here is redundant for them but harmless).

    Contact fields (email/phone/website/contact_person) are excluded — they
    carry no semantic signal for search.
    """
    parts = [
        doc.get("business_name") or "",
        doc.get("business_description") or "",
        doc.get("products_services") or "",
        doc.get("keywords") or "",
        doc.get("specialties") or "",
        doc.get("sub_category") or "",
    ]
    return " ".join(p.strip() for p in parts if p.strip())


def embed_texts(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """Encode a batch of texts into normalized 384-dim vectors.

    normalize_embeddings=True L2-normalizes each vector (standard BGE
    convention; also keeps concatenated-text length from leaking into
    vector magnitude). .tolist() converts numpy floats to native Python
    floats so pymongo's BSON encoder accepts them directly.
    """
    model = get_embedder()
    vectors = model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return vectors.tolist()
