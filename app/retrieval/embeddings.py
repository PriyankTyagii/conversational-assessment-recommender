from functools import lru_cache

_MODEL_NAME = "all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def _get_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(_MODEL_NAME)


def embed(texts: list[str]):
    """Embed a batch of texts. Raises ImportError if sentence-transformers
    is not installed, so callers can fall back to keyword search."""
    model = _get_model()
    return model.encode(texts, normalize_embeddings=True)
