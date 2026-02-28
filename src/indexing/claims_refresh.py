"""
Refresh post-execution distributor claim snapshots and receipt proofs.

This script is deterministic for a fixed block window and writes hash-pinned
manifest entries for all produced files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from web3 import Web3

from src.config import BASE_RPC_URL, DATA_DIR

DISTRIBUTOR = "0x3ef3d8ba38ebe18db133cec108f4d14ce00dd9ae"
DEFAULT_FROM_BLOCK = 41932733

TOKENS = {
    "usdc": {"address": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913", "decimals": 6},
    "lvusdc": {"address": "0x98c49e13bf99d7cad8069faa2a370933ec9ecf17", "decimals": 6},
    "abasusdc": {"address": "0x4e65fe4dba92790696d040ac24aa414708f5c0ab", "decimals": 6},
}

SIP_TXS = [
    "0x5aa10ad32d3d6a3d15d614954dbbe960da2f4376301e28b39b063d485dc15941",
    "0x30643401cafbc331687f312b4fab670470553419ea3c2cef510f48e00c488e54",
    "0xd7cc4ae7ca3f8d3855c7c4d79f7c94745a95b96c0ac883078c1536d08d11616d",
]

CLAIMED_TOPIC = Web3.keccak(text="Claimed(address,address,uint256)").hex()


def normalize_addr(address: str) -> str:
    return address.lower()


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
            wait = min(30, attempt * 3)
            time.sleep(wait)
    raise RuntimeError(f"RPC call failed after retries for {method}: {last_error}") from last_error


def topic_for_address(address: str) -> str:
    return "0x" + ("0" * 24) + normalize_addr(address)[2:]


def fetch_claimed_logs(
    rpc_url: str,
    token_address: str,
    from_block: int,
    to_block: int,
    chunk_size: int,
) -> tuple[list[dict[str, Any]], list[dict[str, int]]]:
    logs: list[dict[str, Any]] = []
    chunks: list[dict[str, int]] = []
    token_topic = topic_for_address(token_address)
    for start in range(from_block, to_block + 1, chunk_size):
        end = min(start + chunk_size - 1, to_block)
        params = [
            {
                "fromBlock": hex(start),
                "toBlock": hex(end),
                "address": DISTRIBUTOR,
                "topics": [CLAIMED_TOPIC, None, token_topic],
            }
        ]
        batch = rpc_call(rpc_url, "eth_getLogs", params=params)
        if batch is None:
            batch = []
        if not isinstance(batch, list):
            raise TypeError(f"Unexpected eth_getLogs result type: {type(batch).__name__}")
        logs.extend(batch)
        chunks.append({"from_block": start, "to_block": end, "count": len(batch)})
    logs.sort(key=lambda row: (int(row["blockNumber"], 16), int(row["logIndex"], 16)))
    return logs, chunks


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1 << 20)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def fetch_and_save_receipts(rpc_url: str, snapshot_dir: Path) -> list[Path]:
    files: list[Path] = []
    for tx_hash in SIP_TXS:
        receipt = rpc_call(rpc_url, "eth_getTransactionReceipt", [tx_hash], retries=6, timeout=90)
        out = snapshot_dir / f"base_rpc_receipt_{tx_hash}.json"
        write_json(out, receipt)
        files.append(out)
    return files


def refresh_claim_files(
    rpc_url: str,
    snapshot_dir: Path,
    from_block: int,
    to_block: int,
    chunk_size: int,
    token_keys: list[str],
) -> list[Path]:
    files: list[Path] = []
    retrieved_utc = datetime.now(timezone.utc).isoformat()

    for key in token_keys:
        token_meta = TOKENS[key]
        logs, chunks = fetch_claimed_logs(
            rpc_url=rpc_url,
            token_address=token_meta["address"],
            from_block=from_block,
            to_block=to_block,
            chunk_size=chunk_size,
        )
        payload = {
            "address": DISTRIBUTOR,
            "event": "Claimed(address,address,uint256)",
            "topic": CLAIMED_TOPIC,
            "token": token_meta["address"],
            "token_key": key,
            "decimals": token_meta["decimals"],
            "from_block": from_block,
            "to_block": to_block,
            "latest_block": to_block,
            "rpc_url": rpc_url,
            "retrieved_utc": retrieved_utc,
            "chunks": chunks,
            "logs": logs,
            "count": len(logs),
        }
        dated = snapshot_dir / f"base_rpc_distributor_claimed_{key}_{from_block}_{to_block}.json"
        alias = snapshot_dir / f"base_rpc_distributor_claimed_{key}_{from_block}_latest.json"
        write_json(dated, payload)
        write_json(alias, payload)
        files.extend([dated, alias])
    return files


def update_manifest(
    snapshot_dir: Path,
    manifest_filename: str,
    rpc_url: str,
    from_block: int,
    to_block: int,
    files: list[Path],
) -> Path:
    manifest_path = snapshot_dir / manifest_filename
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {"schema": "claim_refresh_manifest_v1", "runs": []}

    run = {
        "run_utc": datetime.now(timezone.utc).isoformat(),
        "rpc_url": rpc_url,
        "from_block": from_block,
        "to_block": to_block,
        "files": [],
    }
    for path in files:
        run["files"].append(
            {
                "file": path.name,
                "sha256": sha256_of_file(path),
                "bytes": path.stat().st_size,
            }
        )

    manifest["latest_run_utc"] = run["run_utc"]
    manifest["runs"].append(run)
    write_json(manifest_path, manifest)
    return manifest_path


def parse_token_keys(value: str) -> list[str]:
    keys = [v.strip().lower() for v in value.split(",") if v.strip()]
    unknown = [k for k in keys if k not in TOKENS]
    if unknown:
        raise ValueError(f"Unknown token keys: {unknown}. Allowed: {sorted(TOKENS)}")
    return keys


def main() -> None:
    default_snapshot_dir = DATA_DIR / "snapshots" / "external_review" / "2026-02-09-independent"
    parser = argparse.ArgumentParser(description="Refresh distributor claim snapshots and receipt proofs.")
    parser.add_argument("--snapshot-dir", type=Path, default=default_snapshot_dir)
    parser.add_argument("--from-block", type=int, default=DEFAULT_FROM_BLOCK)
    parser.add_argument("--to-block", type=int, default=None)
    parser.add_argument("--chunk-size", type=int, default=20_000)
    parser.add_argument("--tokens", type=str, default="usdc,lvusdc,abasusdc")
    parser.add_argument(
        "--rpc-url",
        type=str,
        default=BASE_RPC_URL or "https://base-rpc.publicnode.com",
    )
    parser.add_argument("--manifest-file", type=str, default="manifest_claim_refresh_latest.json")
    parser.add_argument("--skip-receipts", action="store_true")
    args = parser.parse_args()

    snapshot_dir: Path = args.snapshot_dir
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    token_keys = parse_token_keys(args.tokens)
    latest_block = int(rpc_call(args.rpc_url, "eth_blockNumber", []), 16)
    to_block = args.to_block if args.to_block is not None else latest_block
    if to_block < args.from_block:
        raise ValueError(f"to-block ({to_block}) is smaller than from-block ({args.from_block})")

    produced_files: list[Path] = []

    claim_files = refresh_claim_files(
        rpc_url=args.rpc_url,
        snapshot_dir=snapshot_dir,
        from_block=args.from_block,
        to_block=to_block,
        chunk_size=args.chunk_size,
        token_keys=token_keys,
    )
    produced_files.extend(claim_files)

    if not args.skip_receipts:
        produced_files.extend(fetch_and_save_receipts(args.rpc_url, snapshot_dir))

    manifest_path = update_manifest(
        snapshot_dir=snapshot_dir,
        manifest_filename=args.manifest_file,
        rpc_url=args.rpc_url,
        from_block=args.from_block,
        to_block=to_block,
        files=produced_files,
    )

    print(f"Refreshed claim snapshots for tokens: {', '.join(token_keys)}")
    print(f"Window: {args.from_block} -> {to_block}")
    print(f"Files written: {len(produced_files)}")
    print(f"Manifest updated: {manifest_path}")


if __name__ == "__main__":
    main()
