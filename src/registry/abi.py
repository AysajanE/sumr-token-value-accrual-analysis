"""
ABI fetching, caching, and hashing.

Fetches verified ABIs from BaseScan. Caches as JSON in data/contracts/abis/.
Computes SHA-256 hash for reproducibility tracking in registry.csv.
"""

import hashlib
import json
from pathlib import Path

import requests

from src.config import BASESCAN_API_KEY, DATA_DIR

ABI_DIR = DATA_DIR / "contracts" / "abis"


def fetch_abi(address: str, chain: str = "base") -> dict | None:
    """Fetch verified ABI from BaseScan API."""
    url = "https://api.basescan.org/api"
    params = {
        "module": "contract",
        "action": "getabi",
        "address": address,
        "apikey": BASESCAN_API_KEY,
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") == "1" and data.get("result"):
        return json.loads(data["result"])
    return None


def cache_abi(address: str, abi: dict) -> Path:
    """Save ABI JSON to disk and return file path."""
    ABI_DIR.mkdir(parents=True, exist_ok=True)
    path = ABI_DIR / f"{address.lower()}.json"
    path.write_text(json.dumps(abi, indent=2))
    return path


def abi_hash(abi: dict) -> str:
    """Compute SHA-256 hash of canonical ABI JSON."""
    canonical = json.dumps(abi, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def load_abi(address: str) -> dict | None:
    """Load cached ABI from disk."""
    path = ABI_DIR / f"{address.lower()}.json"
    if path.exists():
        return json.loads(path.read_text())
    return None
