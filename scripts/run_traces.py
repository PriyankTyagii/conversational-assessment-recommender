"""Regression runner: replay tests/traces/*.md against a running server and
compute Recall@10 on each trace's final recommendation set (matching the
spec: "Mean Recall@10 across all conversation traces" is computed on final
recommendations, not every intermediate turn).

Usage: python scripts/run_traces.py [--base-url http://localhost:8000]
"""

import argparse
import time

import requests

from scripts.parse_traces import load_all_traces


def recall_at_k(returned_urls: list[str], expected_urls: list[str]) -> float | None:
    if not expected_urls:
        return None
    hits = len(set(returned_urls) & set(expected_urls))
    return hits / len(expected_urls)


def run_trace(base_url: str, name: str, turns) -> dict:
    messages: list[dict] = []
    print(f"\n=== {name} ({len(turns)} turns) ===")
    last_body = None
    latencies = []

    for i, turn in enumerate(turns, 1):
        messages.append({"role": "user", "content": turn.user_message})
        start = time.monotonic()
        try:
            response = requests.post(f"{base_url}/chat", json={"messages": messages}, timeout=30)
            latencies.append(time.monotonic() - start)
            response.raise_for_status()
            body = response.json()
        except requests.exceptions.RequestException as exc:
            latencies.append(time.monotonic() - start)
            print(f"  turn {i}: REQUEST FAILED ({exc.__class__.__name__}) ({latencies[-1]:.1f}s)")
            messages.pop()  # drop the user turn we couldn't get a reply for
            continue
        messages.append({"role": "assistant", "content": body["reply"]})
        last_body = body

        returned_urls = [r["url"] for r in body["recommendations"]]
        turn_recall = recall_at_k(returned_urls, turn.expected_urls)
        recall_note = f" recall@10={turn_recall:.2f}" if turn_recall is not None else ""
        print(
            f"  turn {i}: got {len(returned_urls)} rec(s), expected {len(turn.expected_urls)}"
            f"{recall_note} ({latencies[-1]:.1f}s)"
        )

    final_turn = turns[-1]
    final_urls = [r["url"] for r in last_body["recommendations"]] if last_body else []
    final_recall = recall_at_k(final_urls, final_turn.expected_urls)
    max_latency = max(latencies) if latencies else 0.0
    return {"name": name, "final_recall": final_recall, "max_latency": max_latency}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()

    traces = load_all_traces()
    if not traces:
        raise SystemExit("No trace files found in tests/traces/*.md")

    results = [run_trace(args.base_url, name, turns) for name, turns in traces.items()]

    print("\n=== Summary ===")
    recalls = [r["final_recall"] for r in results if r["final_recall"] is not None]
    for r in results:
        recall_str = f"{r['final_recall']:.2f}" if r["final_recall"] is not None else "n/a"
        print(f"  {r['name']}: final_recall={recall_str} max_latency={r['max_latency']:.1f}s")
    if recalls:
        print(f"\nMean Recall@10 across {len(recalls)} traces: {sum(recalls) / len(recalls):.3f}")
    print(f"Max latency observed: {max(r['max_latency'] for r in results):.1f}s")


if __name__ == "__main__":
    main()
