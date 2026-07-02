"""For each trace's final turn, check whether the expected URLs are even
present in the top-K retrieved candidates (before LLM reranking), to tell
apart a retrieval failure (right items never surfaced) from an orchestration
failure (found but not selected).
"""

from app.catalog.loader import known_urls
from app.config import settings
from app.retrieval.store import get_store
from scripts.parse_traces import load_all_traces


def main() -> None:
    store = get_store()
    catalog_urls = known_urls()
    traces = load_all_traces()
    top_k = settings.retrieval_top_k

    for name, turns in traces.items():
        final_turn = turns[-1]
        if not final_turn.expected_urls:
            continue

        missing_from_catalog = [u for u in final_turn.expected_urls if u not in catalog_urls]

        query_text = " ".join(t.user_message for t in turns)
        retrieved = store.search(query_text, top_k=top_k)
        retrieved_urls = {e.url for e in retrieved}

        hits = len(set(final_turn.expected_urls) & retrieved_urls)
        recall_at_k = hits / len(final_turn.expected_urls)

        print(f"{name}: query_text={query_text!r}")
        print(f"  expected={len(final_turn.expected_urls)} in_top{top_k}={hits} recall@{top_k}={recall_at_k:.2f}")
        if missing_from_catalog:
            print(f"  NOT IN CATALOG AT ALL: {missing_from_catalog}")
        for url in final_turn.expected_urls:
            marker = "OK " if url in retrieved_urls else "MISS"
            print(f"    [{marker}] {url}")


if __name__ == "__main__":
    main()
