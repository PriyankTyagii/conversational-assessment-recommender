"""Parse SHL's sample-conversation markdown traces (tests/traces/*.md) into
structured turns: {user, expected_urls, expected_end_of_conversation}.

Trace format (see tests/traces/C1.md for a full example):

    ### Turn 1
    **User**
    > <user message, possibly multi-line>
    **Agent**
    <agent reply text>
    | # | Name | Test Type | ... | URL |
    |---|------|-----------|-----|-----|
    | 1 | ... | ... | ... | <https://...> |
    _`end_of_conversation`: **false**_

Turn numbers in the source files are sometimes non-contiguous (e.g. Turn 2
then Turn 4) — we parse in document order and ignore the printed number.
"""

import re
from dataclasses import dataclass
from pathlib import Path

TRACES_DIR = Path(__file__).resolve().parent.parent / "tests" / "traces"

_TURN_SPLIT = re.compile(r"^### Turn \d+\s*$", re.MULTILINE)
_USER_BLOCK = re.compile(r"\*\*User\*\*\s*\n((?:>.*\n?)+)", re.MULTILINE)
_URL_IN_TABLE_ROW = re.compile(r"<(https://\S+?)>")
_END_OF_CONV = re.compile(r"end_of_conversation.*?\*\*(true|false)\*\*", re.IGNORECASE)
_NO_RECS_MARKER = re.compile(r"recommendations:\s*null", re.IGNORECASE)


@dataclass
class TraceTurn:
    user_message: str
    expected_urls: list[str]
    expected_end_of_conversation: bool


def _parse_user_message(block: str) -> str:
    lines = [line.strip() for line in block.strip().splitlines()]
    quoted = [line.lstrip(">").strip() for line in lines if line.startswith(">")]
    return " ".join(line for line in quoted if line)


def parse_trace(path: Path) -> list[TraceTurn]:
    text = path.read_text(encoding="utf-8")
    chunks = _TURN_SPLIT.split(text)[1:]  # drop preamble before first "### Turn"

    turns = []
    for chunk in chunks:
        user_match = _USER_BLOCK.search(chunk)
        if not user_match:
            continue
        user_message = _parse_user_message(user_match.group(1))

        expected_urls = [] if _NO_RECS_MARKER.search(chunk) else _URL_IN_TABLE_ROW.findall(chunk)

        eoc_match = _END_OF_CONV.search(chunk)
        expected_end_of_conversation = bool(eoc_match) and eoc_match.group(1).lower() == "true"

        turns.append(TraceTurn(user_message, expected_urls, expected_end_of_conversation))

    return turns


def load_all_traces() -> dict[str, list[TraceTurn]]:
    return {path.stem: parse_trace(path) for path in sorted(TRACES_DIR.glob("*.md"))}


if __name__ == "__main__":
    for name, turns in load_all_traces().items():
        print(f"{name}: {len(turns)} turns")
        for i, turn in enumerate(turns, 1):
            print(f"  turn {i}: user={turn.user_message[:60]!r} expected_urls={len(turn.expected_urls)} eoc={turn.expected_end_of_conversation}")
