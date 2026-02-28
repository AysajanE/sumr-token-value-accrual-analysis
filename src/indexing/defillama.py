"""
DeFiLlama API client for TVL, fees, and revenue time series.

Endpoints:
  - Protocol TVL:  GET /protocol/{slug}
  - Fees/Revenue:  GET /summary/fees/{slug}

Snapshots saved to data/snapshots/defillama/ with timestamps.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import requests

from src.config import DEFILLAMA_BASE_URL, DATA_DIR, LAZY_SUMMER_SLUG, SUMMERFI_SLUG

SNAPSHOT_DIR = DATA_DIR / "snapshots" / "defillama"


def fetch_protocol_tvl(slug: str) -> dict:
    """Fetch full protocol data including TVL history."""
    resp = requests.get(f"{DEFILLAMA_BASE_URL}/protocol/{slug}", timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_fees_summary(slug: str) -> dict:
    """Fetch fees/revenue summary."""
    resp = requests.get(f"{DEFILLAMA_BASE_URL}/summary/fees/{slug}", timeout=30)
    resp.raise_for_status()
    return resp.json()


def save_snapshot(data: dict, slug: str, kind: str) -> Path:
    """Save API response with timestamp for reproducibility."""
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = SNAPSHOT_DIR / f"{slug}_{kind}_{ts}.json"
    path.write_text(json.dumps(data, indent=2))
    return path


def pull_all_snapshots() -> None:
    """Pull and save current snapshots for both protocol slugs."""
    for slug in [LAZY_SUMMER_SLUG, SUMMERFI_SLUG]:
        tvl = fetch_protocol_tvl(slug)
        save_snapshot(tvl, slug, "tvl")
        print(f"Saved TVL snapshot for {slug}")

    fees = fetch_fees_summary(LAZY_SUMMER_SLUG)
    save_snapshot(fees, LAZY_SUMMER_SLUG, "fees")
    print(f"Saved fees snapshot for {LAZY_SUMMER_SLUG}")


if __name__ == "__main__":
    pull_all_snapshots()
