"""
Fee/tip accrual computation per vault.

Computes:
  - Daily fees (USD) from TipAccrued events or share mints to fee addresses
  - Effective fee rate = fees / AUM, annualized
  - Weighted average fee rate across all vaults
"""


def compute_daily_fees(tip_events, vault_snapshots, prices) -> "pd.DataFrame":
    """Compute daily fee USD from tip events and vault state."""
    # TODO: Implement per validation plan section 1.1
    raise NotImplementedError


def effective_fee_rate(daily_fees, daily_aum, period_days: int = 365) -> float:
    """Annualized effective fee rate = (sum fees / avg AUM) * (365/days)."""
    # TODO: Implement per validation plan section 1.1.5
    raise NotImplementedError
