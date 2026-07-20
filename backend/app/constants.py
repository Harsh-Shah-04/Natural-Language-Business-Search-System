EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"

# Must match "numDimensions" in scripts/atlas_indexes/vector_index.json —
# JSON can't import this, so keep both in sync by hand if it ever changes.
EMBEDDING_DIMENSIONS = 384

# M4.2: cross-encoder reranker. design-doc-v2.md's named choice — lightweight
# (~80MB), CPU-friendly, the standard MS MARCO reranker. Unlike the bi-encoder
# embedder (which encodes query and document separately), a cross-encoder runs
# full attention over the concatenated (query, document) pair, so it judges
# semantic relevance directly instead of via vector distance — which is what
# the M4.1/M4.1.1 evals identified as the remaining failure mode.
RERANKER_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"
