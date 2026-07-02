import json
from dataclasses import dataclass, field
from functools import lru_cache

from app.config import CATALOG_PATH


@dataclass(frozen=True)
class CatalogEntry:
    name: str
    url: str
    description: str = ""
    test_type: str = ""  # comma-separated SHL codes, e.g. "P,C"
    keys: tuple[str, ...] = field(default_factory=tuple)  # category names, e.g. ("Personality & Behavior",)
    duration_minutes: int | None = None
    remote_testing: bool | None = None
    adaptive: bool | None = None
    job_levels: tuple[str, ...] = field(default_factory=tuple)
    languages: tuple[str, ...] = field(default_factory=tuple)


@lru_cache(maxsize=1)
def load_catalog() -> list[CatalogEntry]:
    """Load the fetched catalog from disk.

    Cached in-process since the service is stateless per-request but the
    catalog file itself only changes when the scraper is re-run.
    """
    with open(CATALOG_PATH, encoding="utf-8") as f:
        data = json.load(f)

    return [
        CatalogEntry(
            name=e["name"],
            url=e["url"],
            description=e.get("description", ""),
            test_type=e.get("test_type", ""),
            keys=tuple(e.get("keys", [])),
            duration_minutes=e.get("duration_minutes"),
            remote_testing=e.get("remote_testing"),
            adaptive=e.get("adaptive"),
            job_levels=tuple(e.get("job_levels", [])),
            languages=tuple(e.get("languages", [])),
        )
        for e in data.get("entries", [])
    ]


def known_urls() -> set[str]:
    return {entry.url for entry in load_catalog()}


def find_by_name(name: str) -> CatalogEntry | None:
    name_lower = name.lower()
    for entry in load_catalog():
        if entry.name.lower() == name_lower:
            return entry
    return None
