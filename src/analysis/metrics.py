"""
KPI computation for the validation scorecard.

Key metrics:
  - Effective fee rate (weighted avg + per vault)
  - Staker share of tips (per cycle)
  - Revenue yield on staked value / mcap / FDV
  - Emissions vs revenue ratio
  - Distribution reliability (days between deposits, payout variance)
"""


def revenue_yield_on_fdv(ttm_staker_revenue: float, max_supply: int, token_price: float) -> float:
    """TTM staker revenue / (max_supply * price)."""
    fdv = max_supply * token_price
    return ttm_staker_revenue / fdv if fdv > 0 else 0.0


def revenue_yield_on_mcap(ttm_staker_revenue: float, circ_supply: int, token_price: float) -> float:
    """TTM staker revenue / (circulating_supply * price)."""
    mcap = circ_supply * token_price
    return ttm_staker_revenue / mcap if mcap > 0 else 0.0


def emissions_vs_revenue_ratio(emission_rewards_usd: float, revenue_rewards_usd: float) -> float:
    """What fraction of total rewards is genuine revenue (not inflation)?"""
    total = emission_rewards_usd + revenue_rewards_usd
    return revenue_rewards_usd / total if total > 0 else 0.0
