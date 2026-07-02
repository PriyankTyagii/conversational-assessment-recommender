import re
from functools import lru_cache

from app.catalog.loader import CatalogEntry, load_catalog


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


class CatalogStore:
    """Retrieval over the catalog.

    Tries semantic search (sentence-transformers + cosine similarity) and
    falls back to keyword overlap if the embedding stack isn't installed or
    the catalog is empty. Keeping a fallback means the API stays bootable
    before the ML dependencies / scraped data are in place.
    """

    def __init__(self, entries: list[CatalogEntry]):
        self.entries = entries
        self._vectors = None
        try:
            if entries:
                from app.retrieval.embeddings import embed

                texts = [
                    f"{e.name}. {e.description} "
                    f"Categories: {', '.join(e.keys)}. "
                    f"Job levels: {', '.join(e.job_levels)}."
                    for e in entries
                ]
                self._vectors = embed(texts)
        except ImportError:
            self._vectors = None

    def search(self, query: str, top_k: int) -> list[CatalogEntry]:
        if not self.entries:
            return []

        if self._vectors is not None:
            from app.retrieval.embeddings import embed

            query_vec = embed([query])[0]
            scores = self._vectors @ query_vec
            ranked = sorted(
                range(len(self.entries)), key=lambda i: scores[i], reverse=True
            )
            return [self.entries[i] for i in ranked[:top_k]]

        query_tokens = _tokenize(query)
        scored = []
        for entry in self.entries:
            entry_tokens = _tokenize(f"{entry.name} {entry.description} {entry.test_type}")
            overlap = len(query_tokens & entry_tokens)
            if overlap:
                scored.append((overlap, entry))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [entry for _, entry in scored[:top_k]]


@lru_cache(maxsize=1)
def get_store() -> CatalogStore:
    return CatalogStore(load_catalog())
