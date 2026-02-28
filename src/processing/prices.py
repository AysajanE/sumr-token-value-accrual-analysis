"""
Asset pricing: Chainlink feeds, DeFiLlama price API, DEX TWAP.

Convention: stablecoins = $1.00 unless depeg evidence exists.
Primary: Chainlink (if available). Secondary: DeFiLlama coins API.
"""

import requests

from src.config import DEFILLAMA_BASE_URL


def get_defillama_price(chain: str, address: str, timestamp: int | None = None) -> float:
    """Fetch token price from DeFiLlama. Current or historical."""
    coin_id = f"{chain}:{address}"
    if timestamp:
        url = f"{DEFILLAMA_BASE_URL}/coins/prices/historical/{timestamp}/{coin_id}"
    else:
        url = f"{DEFILLAMA_BASE_URL}/coins/prices/current/{coin_id}"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return data.get("coins", {}).get(coin_id, {}).get("price", 0.0)
