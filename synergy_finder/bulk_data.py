"""Download and cache Scryfall's `oracle_cards` bulk data file.

Scryfall asks API consumers to avoid per-card lookups when bulk data will
do (https://scryfall.com/docs/api/bulk-data). This module fetches the bulk
data index once, downloads the `oracle_cards` file if the cache is missing
or stale, and stores everything under `data/`.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

import requests

BULK_DATA_INDEX_URL = "https://api.scryfall.com/bulk-data"
BULK_DATA_TYPE = "oracle_cards"

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CARDS_PATH = DATA_DIR / "oracle_cards.json"
META_PATH = DATA_DIR / "bulk_meta.json"

# Scryfall's guidance is to not re-request bulk data more than once a day.
DEFAULT_MAX_AGE_SECONDS = 24 * 60 * 60

# Scryfall asks bulk-data consumers to identify their application.
USER_AGENT = "commander-synergy-finder/0.1 (+https://github.com/steven-robert-eddy/commander-synergy)"
REQUEST_HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json;q=0.9,*/*;q=0.8"}


@dataclass
class BulkDataInfo:
    download_uri: str
    updated_at: str
    size: int


class BulkDataError(RuntimeError):
    pass


def _get_json(url: str) -> dict:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_bulk_data_info(bulk_type: str = BULK_DATA_TYPE) -> BulkDataInfo:
    """Look up the current download URI for a bulk data type from Scryfall's index."""
    index = _get_json(BULK_DATA_INDEX_URL)
    for entry in index.get("data", []):
        if entry.get("type") == bulk_type:
            return BulkDataInfo(
                download_uri=entry["download_uri"],
                updated_at=entry["updated_at"],
                size=entry.get("size", 0),
            )
    raise BulkDataError(f"No bulk data entry of type {bulk_type!r} found")


def _read_meta() -> dict | None:
    if not META_PATH.exists():
        return None
    try:
        return json.loads(META_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _write_meta(info: BulkDataInfo) -> None:
    META_PATH.write_text(
        json.dumps(
            {
                "download_uri": info.download_uri,
                "updated_at": info.updated_at,
                "size": info.size,
                "fetched_at": time.time(),
            },
            indent=2,
        )
    )


def _cache_is_fresh(max_age_seconds: int) -> bool:
    if not CARDS_PATH.exists():
        return False
    meta = _read_meta()
    if meta is None:
        return False
    return (time.time() - meta.get("fetched_at", 0)) < max_age_seconds


def download_oracle_cards(
    force: bool = False,
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
) -> Path:
    """Ensure `data/oracle_cards.json` exists and is reasonably fresh.

    Returns the path to the cached file. Skips the network entirely if the
    cache is fresh and `force` is False.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not force and _cache_is_fresh(max_age_seconds):
        return CARDS_PATH

    info = fetch_bulk_data_info()

    meta = _read_meta()
    if not force and meta is not None and meta.get("updated_at") == info.updated_at and CARDS_PATH.exists():
        # Upstream file hasn't changed since our last download; just refresh
        # the fetched_at timestamp so we don't re-check for another day.
        _write_meta(info)
        return CARDS_PATH

    tmp_path = CARDS_PATH.with_suffix(".json.part")
    with requests.get(info.download_uri, headers=REQUEST_HEADERS, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        with open(tmp_path, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                if chunk:
                    fh.write(chunk)
    tmp_path.replace(CARDS_PATH)

    _write_meta(info)
    return CARDS_PATH


def load_cards(path: Path = CARDS_PATH) -> list[dict]:
    """Load the cached oracle_cards JSON into memory as a list of card dicts."""
    if not path.exists():
        raise BulkDataError(
            f"{path} does not exist yet. Run `synergy-finder update-data` first."
        )
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)
