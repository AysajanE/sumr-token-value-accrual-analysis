"""
Discrepancy detection between on-chain, DeFiLlama, and documentation sources.

Per validation plan section 2.3:
  1. Check scope (chains/vaults included)
  2. Check pricing (oracle source)
  3. Check strategy accounting (totalAssets vs external positions)
  4. Check timing (block vs timestamp cutoffs)
"""


def check_tvl_reconciliation(onchain_tvl: float, defillama_tvl: float, tolerance: float = 0.05) -> dict:
    """Compare on-chain computed TVL to DeFiLlama. Flag if >tolerance."""
    diff = abs(onchain_tvl - defillama_tvl)
    pct_diff = diff / defillama_tvl if defillama_tvl > 0 else float("inf")
    return {
        "onchain_tvl": onchain_tvl,
        "defillama_tvl": defillama_tvl,
        "absolute_diff": diff,
        "pct_diff": pct_diff,
        "passes": pct_diff <= tolerance,
        "tolerance": tolerance,
    }


def check_fee_rate_consistency(computed_rate: float, claimed_rate: float = 0.0066, tolerance: float = 0.002) -> dict:
    """Compare computed effective fee rate to claimed ~0.66%."""
    diff = abs(computed_rate - claimed_rate)
    return {
        "computed_rate": computed_rate,
        "claimed_rate": claimed_rate,
        "diff": diff,
        "passes": diff <= tolerance,
    }


def check_staker_share(computed_share: float, claimed_share: float = 0.20, tolerance: float = 0.03) -> dict:
    """Compare computed staker share of tips to claimed 20%."""
    diff = abs(computed_share - claimed_share)
    return {
        "computed_share": computed_share,
        "claimed_share": claimed_share,
        "diff": diff,
        "passes": diff <= tolerance,
    }
