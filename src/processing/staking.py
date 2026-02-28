"""
Staking state computation: lock distribution, penalties, effective weight.

Computes:
  - Total staked SUMR by lock duration bucket
  - Early exit penalties and penalty rates
  - Lock-weighted stake (multiplier-adjusted)
"""


def compute_staking_state(staking_events) -> "pd.DataFrame":
    """Build daily staking state from Locked/Withdrawn/EarlyExit events."""
    # TODO: Implement per validation plan section 1.3
    raise NotImplementedError


def validate_penalty_rate(early_exit_events) -> "pd.DataFrame":
    """For each early exit, compute implied penalty rate and compare to linear decay."""
    # TODO: Implement — penalty_rate = penalty_amount / principal
    # Expected: max 20%, linearly decaying to 0% at lock expiry
    raise NotImplementedError
