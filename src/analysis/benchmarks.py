"""
Cross-protocol benchmarking: compare SUMR against revenue-share tokens.

Benchmark set (from validation plan section 3.5):
  AAVE, GMX, MKR/SKY, Morpho, Euler, Compound, Maple

Metrics: protocol fees, revenue, tokenholder revenue, revenue/TVL, revenue/mcap.
Data source: DeFiLlama fees/revenue dashboards.
"""

BENCHMARK_PROTOCOLS = [
    "aave",
    "gmx",
    "maker",
    "morpho",
    "euler",
    "compound-finance",
    "maple",
]


def fetch_benchmark_data(slugs: list[str] | None = None) -> "pd.DataFrame":
    """Pull fees/revenue data from DeFiLlama for benchmark protocols."""
    # TODO: Implement — fetch /summary/fees/{slug} for each protocol
    raise NotImplementedError
