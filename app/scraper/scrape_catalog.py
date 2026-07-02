"""Fetch the official SHL product catalog JSON and transform it into the
shape app/catalog/loader.py consumes.

SHL provides the catalog as a stable JSON export (see the assignment PDF's
"SHL catalogue" link) rather than requiring us to scrape the rendered
listing page, so this is a straight fetch + transform, not a crawler.
Run with: `python -m app.scraper.scrape_catalog`.
"""

import json
import re
from datetime import datetime, timezone

import requests

from app.config import CATALOG_PATH

CATALOG_SOURCE_URL = (
    "https://tcp-us-prod-rnd.shl.com/voiceRater/shl-ai-hiring/shl_product_catalog.json"
)

# SHL's public test-type legend: https://www.shl.com/solutions/products/product-catalog/
# Each product's "keys" (job family / category tags) map 1:1 to a single-letter code.
CATEGORY_TO_TEST_TYPE = {
    "Ability & Aptitude": "A",
    "Biodata & Situational Judgment": "B",
    "Competencies": "C",
    "Development & 360": "D",
    "Assessment Exercises": "E",
    "Knowledge & Skills": "K",
    "Personality & Behavior": "P",
    "Simulations": "S",
}

_DURATION_PATTERN = re.compile(r"(\d+)")


def _parse_duration_minutes(duration: str) -> int | None:
    if not duration or duration.strip() == "-":
        return None
    match = _DURATION_PATTERN.search(duration)
    return int(match.group(1)) if match else None


def _test_type_string(keys: list[str]) -> str:
    codes = [CATEGORY_TO_TEST_TYPE.get(key, "") for key in keys]
    return ",".join(code for code in codes if code)


def fetch_raw_catalog() -> list[dict]:
    response = requests.get(CATALOG_SOURCE_URL, timeout=30)
    response.raise_for_status()
    # The source JSON contains literal control characters inside description
    # strings (e.g. \r left over from the source CMS), which is invalid per
    # the JSON spec but common in scraped text — parse leniently.
    return json.loads(response.text, strict=False)


def transform(raw_entries: list[dict]) -> list[dict]:
    transformed = []
    seen_urls: set[str] = set()

    for raw in raw_entries:
        url = raw["link"]
        if url in seen_urls:
            continue  # dedupe by canonical URL
        seen_urls.add(url)

        transformed.append(
            {
                "entity_id": raw.get("entity_id"),
                "name": raw["name"],
                "url": url,
                "description": raw.get("description", "").strip(),
                "keys": raw.get("keys", []),
                "test_type": _test_type_string(raw.get("keys", [])),
                "duration_minutes": _parse_duration_minutes(raw.get("duration", "")),
                "remote_testing": raw.get("remote") == "yes",
                "adaptive": raw.get("adaptive") == "yes",
                "job_levels": raw.get("job_levels", []),
                "languages": raw.get("languages", []),
            }
        )

    return transformed


def main() -> None:
    raw_entries = fetch_raw_catalog()
    entries = transform(raw_entries)

    payload = {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "source": CATALOG_SOURCE_URL,
        "entries": entries,
    }
    CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CATALOG_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"Wrote {len(entries)} catalog entries to {CATALOG_PATH}")


if __name__ == "__main__":
    main()
