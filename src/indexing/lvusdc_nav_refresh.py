"""
Refresh LVUSDC convertToAssets snapshots at relevant historical blocks.

Writes deterministic JSON snapshots to the selected snapshot directory.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timezone
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any

import requests
from web3 import Web3

from src.config import BASE_RPC_URL, DATA_DIR

getcontext().prec = 50

LVUSDC_TOKEN = "0x98c49e13bf99d7cad8069faa2a370933ec9ecf17"
SIP3131_TX = "0x30643401cafbc331687f312b4fab670470553419ea3c2cef510f48e00c488e54"
DEFAULT_FROM_BLOCK = 41932733

SELECTOR_CONVERT_TO_ASSETS = Web3.keccak(text="convertToAssets(uint256)").hex()[:10]
SELECTOR_ASSET = Web3.keccak(text="asset()").hex()[:10]
SELECTOR_DECIMALS = Web3.keccak(text="decimals()").hex()[:10]


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def rpc_call(
    rpc_url: str,
    method: str,
    params: list[Any],
    retries: int = 6,
    timeout: int = 90,
) -> Any:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = requests.post(rpc_url, json=payload, timeout=timeout)
            response.raise_for_status()
            body = response.json()
            if "error" in body:
                raise RuntimeError(str(body["error"]))
            return body["result"]
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(min(30, attempt * 3))
    raise RuntimeError(f"RPC call failed after retries for {method}: {last_error}") from last_error


def parse_hex_int(value: str | int | None) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    if value.startswith("0x"):
        return int(value, 16)
    return int(value)


def eth_call_hex(rpc_url: str, to: str, data: str, block: int) -> str:
    result = rpc_call(
        rpc_url,
        "eth_call",
        [{"to": to, "data": data}, hex(block)],
        retries=6,
        timeout=90,
    )
    if not isinstance(result, str):
        raise TypeError(f"Unexpected eth_call result type: {type(result).__name__}")
    return result


def decode_uint256(hex_value: str) -> int:
    if not hex_value or hex_value == "0x":
        return 0
    return int(hex_value, 16)


def decode_address(hex_value: str) -> str:
    if not hex_value or hex_value == "0x":
        return ""
    clean = hex_value[2:] if hex_value.startswith("0x") else hex_value
    return "0x" + clean[-40:]


def encode_uint256(value: int) -> str:
    return hex(value)[2:].rjust(64, "0")


def pick_claim_file(snapshot_dir: Path, from_block: int) -> Path:
    latest_alias = snapshot_dir / f"base_rpc_distributor_claimed_lvusdc_{from_block}_latest.json"
    if latest_alias.exists():
        return latest_alias

    candidates = sorted(snapshot_dir.glob(f"base_rpc_distributor_claimed_lvusdc_{from_block}_*.json"))
    if not candidates:
        raise FileNotFoundError(
            f"No LVUSDC claim snapshot found for from_block={from_block} in {snapshot_dir}"
        )

    def score(path: Path) -> tuple[int, int]:
        match = re.search(rf"_{from_block}_(\d+)\.json$", path.name)
        if match:
            return (1, int(match.group(1)))
        return (0, 0)

    return max(candidates, key=score)


def detect_funding_block(snapshot_dir: Path, rpc_url: str) -> int:
    tx_path = snapshot_dir / f"tx_{SIP3131_TX}.json"
    if tx_path.exists():
        tx_payload = load_json(tx_path)
        return int(tx_payload.get("block_number"))

    receipt_path = snapshot_dir / f"base_rpc_receipt_{SIP3131_TX}.json"
    if receipt_path.exists():
        receipt_payload = load_json(receipt_path)
        return parse_hex_int(receipt_payload.get("blockNumber"))

    receipt = rpc_call(rpc_url, "eth_getTransactionReceipt", [SIP3131_TX], retries=6, timeout=90)
    return parse_hex_int(receipt.get("blockNumber"))


def run(snapshot_dir: Path, rpc_url: str, from_block: int, to_block: int | None, shares_raw: int | None) -> None:
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    claim_file = pick_claim_file(snapshot_dir, from_block)
    claim_payload = load_json(claim_file)

    claim_from_block = int(claim_payload.get("from_block") or from_block)
    claim_to_block = int(claim_payload.get("to_block") or 0)
    if claim_to_block <= 0:
        claim_to_block = parse_hex_int(rpc_call(rpc_url, "eth_blockNumber", []))
    observation_block = int(to_block) if to_block is not None else claim_to_block

    funding_block = detect_funding_block(snapshot_dir, rpc_url)
    claim_blocks = sorted(
        {
            parse_hex_int(log.get("blockNumber"))
            for log in (claim_payload.get("logs") or [])
            if log.get("blockNumber") is not None
        }
    )

    lvusdc_decimals = decode_uint256(eth_call_hex(rpc_url, LVUSDC_TOKEN, SELECTOR_DECIMALS, observation_block))
    asset_address = decode_address(eth_call_hex(rpc_url, LVUSDC_TOKEN, SELECTOR_ASSET, observation_block))
    asset_decimals = (
        decode_uint256(eth_call_hex(rpc_url, asset_address, SELECTOR_DECIMALS, observation_block))
        if asset_address
        else 6
    )

    if shares_raw is None:
        shares_raw = 10 ** lvusdc_decimals

    blocks = sorted(set([claim_from_block, funding_block, observation_block, *claim_blocks]))

    snapshots = []
    assets_per_lvusdc_values: list[Decimal] = []
    shares_tokens = Decimal(shares_raw) / (Decimal(10) ** lvusdc_decimals) if lvusdc_decimals >= 0 else Decimal(0)
    if shares_tokens <= 0:
        raise ValueError("shares_raw must represent a positive LVUSDC share amount.")

    for block in blocks:
        data = SELECTOR_CONVERT_TO_ASSETS + encode_uint256(shares_raw)
        assets_raw = decode_uint256(eth_call_hex(rpc_url, LVUSDC_TOKEN, data, block))
        assets_tokens = Decimal(assets_raw) / (Decimal(10) ** asset_decimals)
        assets_per_lvusdc = assets_tokens / shares_tokens
        assets_per_lvusdc_values.append(assets_per_lvusdc)
        snapshots.append(
            {
                "block_number": int(block),
                "shares_raw": str(shares_raw),
                "assets_raw": str(assets_raw),
                "assets_tokens": str(assets_tokens),
                "assets_per_lvusdc": str(assets_per_lvusdc),
            }
        )

    latest_nav = snapshots[-1]["assets_per_lvusdc"] if snapshots else None
    funding_nav = None
    for row in snapshots:
        if row["block_number"] == funding_block:
            funding_nav = row["assets_per_lvusdc"]
            break

    payload = {
        "schema": "lvusdc_convertToAssets_snapshot_v1",
        "retrieved_utc": datetime.now(timezone.utc).isoformat(),
        "rpc_url": rpc_url,
        "contract": LVUSDC_TOKEN,
        "method": "convertToAssets(uint256)",
        "asset_address": asset_address,
        "lvusdc_decimals": lvusdc_decimals,
        "asset_decimals": asset_decimals,
        "shares_input_raw": str(shares_raw),
        "claim_source_file": claim_file.name,
        "claim_window_from_block": claim_from_block,
        "claim_window_to_block": claim_to_block,
        "funding_execute_block": funding_block,
        "observation_block": observation_block,
        "snapshot_count": len(snapshots),
        "snapshots": snapshots,
        "summary": {
            "block_min": min(blocks) if blocks else None,
            "block_max": max(blocks) if blocks else None,
            "funding_block_assets_per_lvusdc": funding_nav,
            "observation_block_assets_per_lvusdc": latest_nav,
            "assets_per_lvusdc_min": str(min(assets_per_lvusdc_values)) if assets_per_lvusdc_values else None,
            "assets_per_lvusdc_max": str(max(assets_per_lvusdc_values)) if assets_per_lvusdc_values else None,
        },
    }

    dated = snapshot_dir / f"base_rpc_lvusdc_convertToAssets_{claim_from_block}_{observation_block}.json"
    alias_latest = snapshot_dir / "base_rpc_lvusdc_convertToAssets_latest.json"
    alias_from_block = snapshot_dir / f"base_rpc_lvusdc_convertToAssets_{claim_from_block}_latest.json"

    write_json(dated, payload)
    write_json(alias_latest, payload)
    write_json(alias_from_block, payload)

    print("Refreshed LVUSDC convertToAssets snapshots")
    print(f"Blocks queried: {len(blocks)}")
    print(f"Window: {claim_from_block} -> {observation_block}")
    print(f"Files written: 3")


def main() -> None:
    default_snapshot_dir = DATA_DIR / "snapshots" / "external_review" / "2026-02-09-independent"
    parser = argparse.ArgumentParser(description="Refresh LVUSDC convertToAssets snapshots at historical blocks.")
    parser.add_argument("--snapshot-dir", type=Path, default=default_snapshot_dir)
    parser.add_argument("--rpc-url", type=str, default=BASE_RPC_URL or "https://base-rpc.publicnode.com")
    parser.add_argument("--from-block", type=int, default=DEFAULT_FROM_BLOCK)
    parser.add_argument("--to-block", type=int, default=None)
    parser.add_argument("--shares-raw", type=int, default=None, help="share amount for convertToAssets; default is 1 LVUSDC token in raw units")
    args = parser.parse_args()

    run(
        snapshot_dir=args.snapshot_dir,
        rpc_url=args.rpc_url,
        from_block=args.from_block,
        to_block=args.to_block,
        shares_raw=args.shares_raw,
    )


if __name__ == "__main__":
    main()
