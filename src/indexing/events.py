"""
On-chain event indexing via eth_getLogs.

Fetches and decodes Transfer, TipAccrued, RewardAdded, RewardPaid,
Locked, Withdrawn, and penalty events from Lazy Summer contracts.

Outputs: data/indexed/{transfers,tip_events,staking_events,reward_events}/*.parquet
"""

from web3 import Web3

from src.config import BASE_RPC_URL


def get_web3() -> Web3:
    """Initialize Web3 connection to Base archive node."""
    w3 = Web3(Web3.HTTPProvider(BASE_RPC_URL))
    if not w3.is_connected():
        raise ConnectionError(f"Cannot connect to {BASE_RPC_URL}")
    return w3


def fetch_logs(
    w3: Web3,
    address: str,
    topics: list[str],
    from_block: int,
    to_block: int,
    batch_size: int = 2000,
) -> list[dict]:
    """Fetch logs in batches to avoid RPC limits."""
    # TODO: Implement batched eth_getLogs with retry logic
    raise NotImplementedError


def decode_event(log: dict, abi: dict) -> dict:
    """Decode a raw log entry using contract ABI."""
    # TODO: Implement using eth_abi or web3 contract
    raise NotImplementedError


if __name__ == "__main__":
    print("Event indexing — run from notebook 02-05 for interactive exploration")
