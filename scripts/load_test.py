"""Load-test the operational constraints: 8-turn cap honored, every call
under the 30s timeout, and graceful handling when messages exceed 8 turns.

Usage: python scripts/load_test.py [--base-url http://localhost:8000]
"""

import argparse
import time

import requests


def timed_post(base_url: str, messages: list[dict]) -> tuple[dict, float]:
    start = time.monotonic()
    response = requests.post(f"{base_url}/chat", json={"messages": messages}, timeout=30)
    elapsed = time.monotonic() - start
    response.raise_for_status()
    return response.json(), elapsed


def test_eight_turn_cap(base_url: str) -> None:
    print("=== 8-turn cap: should close out by turn 8 ===")
    messages = []
    max_latency = 0.0
    for i in range(8):
        messages.append(
            {"role": "user", "content": f"Turn {i + 1}: still deciding on a Java backend developer role, mid-level."}
        )
        body, elapsed = timed_post(base_url, messages)
        max_latency = max(max_latency, elapsed)
        messages.append({"role": "assistant", "content": body["reply"]})
        print(f"  turn {i + 1}: {elapsed:.1f}s, recs={len(body['recommendations'])}, eoc={body['end_of_conversation']}")

    assert body["end_of_conversation"] is True, "expected end_of_conversation=True at turn cap"
    print(f"  PASS: closed at turn 8, max latency {max_latency:.1f}s")


def test_beyond_turn_cap(base_url: str) -> None:
    print("\n=== Beyond turn cap: 10 turns, should not error ===")
    messages = []
    for i in range(10):
        messages.append(
            {"role": "user", "content": f"Turn {i + 1}: considering a Python data engineer, senior level."}
        )
        body, elapsed = timed_post(base_url, messages)
        messages.append({"role": "assistant", "content": body["reply"]})
    print(f"  turn 10: {elapsed:.1f}s, recs={len(body['recommendations'])}, eoc={body['end_of_conversation']}")
    print("  PASS: no error past the turn cap")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()

    test_eight_turn_cap(args.base_url)
    test_beyond_turn_cap(args.base_url)


if __name__ == "__main__":
    main()
