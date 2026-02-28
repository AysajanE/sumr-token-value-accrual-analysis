"""
Staker revenue flow computation.

Tracks:
  - Revenue reward deposits into staker module
  - Staker claims (RewardPaid events)
  - NAV conversion for LV-USDC tokens (convertToAssets at claim block)
  - Unclaimed accrual balance
"""


def compute_staker_revenue(reward_events, prices) -> "pd.DataFrame":
    """Compute staker revenue USD from reward deposit/claim events."""
    # TODO: Implement per validation plan section 1.2
    raise NotImplementedError


def staker_share_of_tips(staker_revenue_usd, total_tips_usd) -> float:
    """Ratio test: is the staker share ~20% of total tips?"""
    # TODO: Implement — should be ~0.20 across cycles
    raise NotImplementedError
