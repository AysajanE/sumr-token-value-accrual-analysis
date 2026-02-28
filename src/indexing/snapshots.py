"""
Historical state reads via eth_call at specific blocks.

Used for daily vault snapshots: totalAssets(), totalSupply(),
convertToAssets(), and staking contract state.
"""

from web3 import Web3


def read_at_block(w3: Web3, contract, function_name: str, block: int, *args):
    """Call a view function at a specific historical block."""
    func = getattr(contract.functions, function_name)
    return func(*args).call(block_identifier=block)


def get_end_of_day_block(w3: Web3, timestamp: int) -> int:
    """Binary search for the last block before a given UTC timestamp."""
    # TODO: Implement binary search over block timestamps
    raise NotImplementedError


def snapshot_vault(w3: Web3, vault_contract, block: int) -> dict:
    """Read vault state at a specific block."""
    return {
        "block": block,
        "totalAssets": read_at_block(w3, vault_contract, "totalAssets", block),
        "totalSupply": read_at_block(w3, vault_contract, "totalSupply", block),
    }
