"""
Multi-method contract address discovery.

Three independent sources:
  1. Official docs / config (scrape for 0x... patterns)
  2. DeFiLlama protocol adapters (API + GitHub adapter repo)
  3. On-chain factory events / deployer tx history

Outputs: data/contracts/registry.csv
"""

import csv
from pathlib import Path
from src.config import DATA_DIR, SUMR_TOKEN, ST_SUMR

REGISTRY_PATH = DATA_DIR / "contracts" / "registry.csv"
REGISTRY_COLUMNS = [
    "chain", "address", "label", "abi_source", "abi_hash",
    "discovered_by", "first_seen_block", "notes",
]


def seed_registry() -> None:
    """Write seed addresses (known from docs) to registry.csv."""
    rows = [
        {
            "chain": "base",
            "address": SUMR_TOKEN,
            "label": "SUMR Token",
            "abi_source": "basescan",
            "abi_hash": "",
            "discovered_by": "docs",
            "first_seen_block": "",
            "notes": "ERC-20, max supply 1B",
        },
        {
            "chain": "base",
            "address": ST_SUMR,
            "label": "stSUMR (Staking V2)",
            "abi_source": "basescan",
            "abi_hash": "",
            "discovered_by": "docs",
            "first_seen_block": "",
            "notes": "Staking contract from Summer.fi token docs",
        },
    ]
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REGISTRY_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=REGISTRY_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Seeded registry with {len(rows)} addresses → {REGISTRY_PATH}")


def discover_from_docs() -> list[dict]:
    """Scrape Summer.fi docs pages for contract addresses."""
    # TODO: Implement — fetch docs HTML, regex for 0x[a-fA-F0-9]{40}
    raise NotImplementedError


def discover_from_defillama() -> list[dict]:
    """Pull addresses from DeFiLlama adapter configs."""
    # TODO: Implement — check DeFiLlama GitHub adapter or API metadata
    raise NotImplementedError


def discover_from_chain() -> list[dict]:
    """Trace deployer addresses and factory events on-chain."""
    # TODO: Implement — BaseScan contract creator API + getLogs for factory events
    raise NotImplementedError


if __name__ == "__main__":
    seed_registry()
