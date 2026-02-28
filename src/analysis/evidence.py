"""
Deterministic evidence artifact builder.

Reads frozen JSON snapshots and generates reproducible evidence tables in
`results/proofs/evidence_*`.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any

from eth_abi import decode

from src.config import DATA_DIR, RESULTS_DIR

getcontext().prec = 50

TREASURY = "0x447bf9d1485abdc4c1778025dfdfbe8b894c3796"
FOUNDATION_TIPSTREAM = "0xb0f53fc4e15301147de9b3e49c3db942e3f118f2"
DISTRIBUTOR = "0x3ef3d8ba38ebe18db133cec108f4d14ce00dd9ae"
MERKL_FEE_RECIPIENT = "0xeac6a75e19beb1283352d24c0311de865a867dab"

FEE_TOKEN_SYMBOLS = {"USDC", "EURC", "USDT", "WETH"}

SIP313_TX = "0x5aa10ad32d3d6a3d15d614954dbbe960da2f4376301e28b39b063d485dc15941"
SIP3131_TX = "0x30643401cafbc331687f312b4fab670470553419ea3c2cef510f48e00c488e54"
NEW_CAMPAIGN_TOPIC = "0x6e3c6fa6d4815a856783888c5c3ea2ad7e7303ac0cca66c99f5bd93502c44299"

KNOWN_SAMPLE_TXS = [
    "0xfb6877c5b85275982707f52d83a595092d1ddd98799cc65da05daf618be14f2d",
    "0xc16d8c1b1c2d5767b078f52fe9aad7f50018782b2b66e56f43f8f003a5e1eaa7",
    "0xbffa7e0b7852bb7521b5e664eab3358ebc64a1ec700c51563e0374fbb8652684",
    "0x214ad55d65fd936af8082992101b0998891d1f25d80516e668f139a846f0e955",
]

USDC_TOKEN = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
LVUSDC_TOKEN = "0x98c49e13bf99d7cad8069faa2a370933ec9ecf17"
ABASUSDC_TOKEN = "0x4e65fe4dba92790696d040ac24aa414708f5c0ab"

CLAIM_TOKEN_REGISTRY = {
    "usdc": {"address": USDC_TOKEN, "symbol": "USDC", "decimals": 6},
    "lvusdc": {"address": LVUSDC_TOKEN, "symbol": "LVUSDC", "decimals": 6},
    "abasusdc": {"address": ABASUSDC_TOKEN, "symbol": "aBasUSDC", "decimals": 6},
}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def normalize_addr(value: str | None) -> str:
    if not value:
        return ""
    return value.lower()


def parse_decimal(value: str | int | float | None) -> Decimal:
    if value is None:
        return Decimal(0)
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    return Decimal(value.replace(",", ""))


def raw_to_amount(raw: str | int | None, decimals: str | int | None) -> Decimal:
    raw_v = parse_decimal(raw)
    dec_v = int(decimals or 0)
    return raw_v / (Decimal(10) ** dec_v)


def strip_html(text: str) -> str:
    stripped = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(stripped)).strip()


def find_number(text: str, patterns: list[str]) -> Decimal | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return parse_decimal(match.group(1))
    return None


def pick_existing(snapshot_dir: Path, candidates: list[str]) -> Path:
    for candidate in candidates:
        path = snapshot_dir / candidate
        if path.exists():
            return path
    raise FileNotFoundError(f"Missing required snapshot file: one of {candidates}")


def optional_existing(snapshot_dir: Path, candidates: list[str]) -> Path | None:
    for candidate in candidates:
        path = snapshot_dir / candidate
        if path.exists():
            return path
    return None


def epoch_to_date(epoch: int | float) -> str:
    return datetime.fromtimestamp(int(epoch), tz=timezone.utc).strftime("%Y-%m-%d")


def extract_tvl_series(protocol: dict[str, Any]) -> list[dict[str, Any]]:
    series = protocol.get("tvl", []) or []
    rows = []
    for point in series:
        rows.append(
            {
                "date_epoch": int(point["date"]),
                "date": epoch_to_date(point["date"]),
                "tvl_usd": Decimal(str(point["totalLiquidityUSD"])),
            }
        )
    rows.sort(key=lambda r: r["date_epoch"])
    return rows


def extract_fee_series(fees_payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for point in fees_payload.get("totalDataChart", []) or []:
        if not isinstance(point, list) or len(point) < 2:
            continue
        rows.append(
            {
                "date_epoch": int(point[0]),
                "date": epoch_to_date(point[0]),
                "fee_usd": Decimal(str(point[1])),
            }
        )
    rows.sort(key=lambda r: r["date_epoch"])
    return rows


def parse_manifest_as_of(snapshot_dir: Path) -> str | None:
    candidates = [
        snapshot_dir / "manifest.json",
        snapshot_dir / "manifest_paginated.json",
        snapshot_dir / "manifest_paginated_core.json",
    ]
    seen: list[datetime] = []
    for path in candidates:
        if not path.exists():
            continue
        payload = load_json(path)
        if isinstance(payload, dict) and payload.get("as_of_utc"):
            seen.append(datetime.fromisoformat(payload["as_of_utc"].replace("Z", "+00:00")))
        if isinstance(payload, list):
            for row in payload:
                if row.get("retrieved_utc"):
                    seen.append(datetime.fromisoformat(row["retrieved_utc"].replace("Z", "+00:00")))
    if not seen:
        return None
    return max(seen).isoformat()


def build_kpi_summary(snapshot_dir: Path) -> dict[str, Any]:
    lazy = load_json(snapshot_dir / "defillama_protocol_lazy_summer.json")
    summer = load_json(snapshot_dir / "defillama_protocol_summer_fi.json")
    fees = load_json(snapshot_dir / "defillama_fees_dailyFees_lazy_summer.json")

    lazy_series = extract_tvl_series(lazy)
    summer_series = extract_tvl_series(summer)
    fee_series = extract_fee_series(fees)
    fee_chart = [row["fee_usd"] for row in fee_series]
    fee_window = fee_series[-90:]

    lazy_first = lazy_series[0]
    lazy_peak = max(lazy_series, key=lambda r: r["tvl_usd"])
    lazy_latest = lazy_series[-1]

    summer_first = summer_series[0]
    summer_peak = max(summer_series, key=lambda r: r["tvl_usd"])
    summer_latest = summer_series[-1]

    fees_30d = sum(fee_chart[-30:]) if fee_chart else Decimal(0)
    fees_90d = sum(row["fee_usd"] for row in fee_window)
    fee_window_days = len(fee_window)
    annualization_factor = (Decimal(365) / Decimal(fee_window_days)) if fee_window_days else Decimal(0)
    fees_annualized = fees_90d * annualization_factor if fee_window_days else Decimal(0)

    lazy_tvl_window: list[dict[str, Any]] = []
    if fee_window:
        start_epoch = fee_window[0]["date_epoch"]
        end_epoch = fee_window[-1]["date_epoch"]
        lazy_tvl_window = [row for row in lazy_series if start_epoch <= row["date_epoch"] <= end_epoch]
        if not lazy_tvl_window:
            lazy_tvl_window = lazy_series[-fee_window_days:]
    lazy_tvl_window_avg = (
        sum(row["tvl_usd"] for row in lazy_tvl_window) / Decimal(len(lazy_tvl_window))
        if lazy_tvl_window
        else Decimal(0)
    )
    implied_fee_rate_vs_window_tvl = (fees_annualized / lazy_tvl_window_avg) if lazy_tvl_window_avg > 0 else Decimal(0)

    return {
        "as_of_utc": parse_manifest_as_of(snapshot_dir),
        "lazy_first_date": lazy_first["date"],
        "lazy_first_tvl_usd": float(lazy_first["tvl_usd"]),
        "lazy_peak_date": lazy_peak["date"],
        "lazy_peak_tvl_usd": float(lazy_peak["tvl_usd"]),
        "lazy_latest_date": lazy_latest["date"],
        "lazy_latest_tvl_usd": float(lazy_latest["tvl_usd"]),
        "summer_first_date": summer_first["date"],
        "summer_peak_date": summer_peak["date"],
        "summer_peak_tvl_usd": float(summer_peak["tvl_usd"]),
        "summer_latest_date": summer_latest["date"],
        "summer_latest_tvl_usd": float(summer_latest["tvl_usd"]),
        "fees_api_total24h": float(parse_decimal(fees.get("total24h"))),
        "fees_api_total7d": float(parse_decimal(fees.get("total7d"))),
        "fees_api_total30d": float(parse_decimal(fees.get("total30d"))),
        "fees_api_totalAllTime": float(parse_decimal(fees.get("totalAllTime"))),
        "fees_derived_30d": float(fees_30d),
        "fees_derived_90d": float(fees_90d),
        "fees_derived_90d_annualized": float(fees_annualized),
        "fees_window_start_date": fee_window[0]["date"] if fee_window else None,
        "fees_window_end_date": fee_window[-1]["date"] if fee_window else None,
        "fees_window_days": fee_window_days,
        "fees_annualization_factor": float(annualization_factor),
        "lazy_tvl_window_avg_usd": float(lazy_tvl_window_avg),
        "lazy_tvl_window_points": len(lazy_tvl_window),
        "implied_fee_rate_vs_window_avg_tvl": float(implied_fee_rate_vs_window_tvl),
    }


def build_defillama_context(snapshot_dir: Path) -> dict[str, Any]:
    lazy = load_json(snapshot_dir / "defillama_protocol_lazy_summer.json")
    summer = load_json(snapshot_dir / "defillama_protocol_summer_fi.json")

    lazy_series = extract_tvl_series(lazy)
    summer_series = extract_tvl_series(summer)

    lazy_first = lazy_series[0]
    lazy_peak = max(lazy_series, key=lambda r: r["tvl_usd"])
    lazy_latest = lazy_series[-1]

    target_epoch = int(datetime(2024, 11, 1).timestamp())
    summer_nearest = min(summer_series, key=lambda r: abs(r["date_epoch"] - target_epoch))
    summer_peak = max(summer_series, key=lambda r: r["tvl_usd"])

    keys = sorted((lazy.get("chainTvls") or {}).keys())

    return {
        "lazy_first_date": lazy_first["date"],
        "lazy_peak_date": lazy_peak["date"],
        "lazy_peak_tvl_usd": float(lazy_peak["tvl_usd"]),
        "lazy_latest_date": lazy_latest["date"],
        "lazy_latest_tvl_usd": float(lazy_latest["tvl_usd"]),
        "summer_nearest_2024_11_01_date": summer_nearest["date"],
        "summer_nearest_2024_11_01_tvl_usd": float(summer_nearest["tvl_usd"]),
        "summer_peak_date": summer_peak["date"],
        "summer_peak_tvl_usd": float(summer_peak["tvl_usd"]),
        "lazy_chainTvls_keys": keys,
    }


def parse_tipjar_methods(items: list[dict[str, Any]], chain_label: str) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for item in items:
        method = item.get("method")
        if method:
            counts[method] += 1
            continue
        raw_input = (item.get("raw_input") or "").lower()
        if chain_label == "arbitrum_tipjar" and raw_input.startswith("0xfffa445e"):
            counts["0xfffa445e"] += 1
        else:
            counts["unknown"] += 1
    rows = [{"chain": chain_label, "method": method, "count": count} for method, count in sorted(counts.items())]
    return rows


def get_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return payload.get("items", []) or []


def parse_month_utc(timestamp: str | None) -> str:
    if not timestamp:
        return ""
    try:
        dt = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
    except ValueError:
        return str(timestamp)[:7] if len(str(timestamp)) >= 7 else ""
    return dt.astimezone(timezone.utc).strftime("%Y-%m")


def extract_outflow_rows(
    payload: dict[str, Any],
    from_address: str,
    allowed_symbols: set[str],
    include_name: bool = True,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in get_items(payload):
        from_hash = normalize_addr((item.get("from") or {}).get("hash"))
        if from_hash != from_address:
            continue
        token = item.get("token") or {}
        symbol = (token.get("symbol") or "").upper()
        if symbol not in allowed_symbols:
            continue
        total = item.get("total") or {}
        amount = raw_to_amount(total.get("value"), total.get("decimals"))
        row = {
            "block_number": item.get("block_number"),
            "timestamp": item.get("timestamp"),
            "tx_hash": item.get("transaction_hash"),
            "token_symbol": symbol,
            "raw_value": str(total.get("value")),
            "amount": float(amount),
            "to_address": normalize_addr((item.get("to") or {}).get("hash")),
        }
        if include_name:
            row["token_name"] = token.get("name")
        rows.append(row)
    rows.sort(key=lambda r: (int(r["block_number"]), r["tx_hash"]), reverse=True)
    return rows


def extract_inflow_rows(
    payload: dict[str, Any],
    to_address: str,
    allowed_symbols: set[str],
    include_name: bool = True,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in get_items(payload):
        to_hash = normalize_addr((item.get("to") or {}).get("hash"))
        if to_hash != to_address:
            continue
        token = item.get("token") or {}
        symbol = (token.get("symbol") or "").upper()
        if symbol not in allowed_symbols:
            continue
        total = item.get("total") or {}
        amount = raw_to_amount(total.get("value"), total.get("decimals"))
        row = {
            "block_number": item.get("block_number"),
            "timestamp": item.get("timestamp"),
            "tx_hash": item.get("transaction_hash"),
            "token_symbol": symbol,
            "raw_value": str(total.get("value")),
            "amount": float(amount),
            "from_address": normalize_addr((item.get("from") or {}).get("hash")),
        }
        if include_name:
            row["token_name"] = token.get("name")
        rows.append(row)
    rows.sort(key=lambda r: (int(r["block_number"]), r["tx_hash"]), reverse=True)
    return rows


def summarize_token_totals_decimal(rows: list[dict[str, Any]]) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = {}
    for row in rows:
        symbol = row["token_symbol"]
        totals[symbol] = totals.get(symbol, Decimal(0)) + parse_decimal(row["amount"])
    return totals


def summarize_token_totals(rows: list[dict[str, Any]]) -> dict[str, float]:
    totals = summarize_token_totals_decimal(rows)
    return {symbol: float(amount) for symbol, amount in totals.items()}


def build_monthly_net_flow_rows(
    chain: str,
    inflow_rows: list[dict[str, Any]],
    outflow_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    monthly: dict[tuple[str, str], dict[str, Any]] = {}

    def get_bucket(month_utc: str, token_symbol: str) -> dict[str, Any]:
        key = (month_utc, token_symbol)
        if key not in monthly:
            monthly[key] = {
                "chain": chain,
                "month_utc": month_utc,
                "token_symbol": token_symbol,
                "inflow_count": 0,
                "inflow_amount": Decimal(0),
                "outflow_count": 0,
                "outflow_amount": Decimal(0),
            }
        return monthly[key]

    for row in inflow_rows:
        month_utc = parse_month_utc(row.get("timestamp"))
        if not month_utc:
            continue
        bucket = get_bucket(month_utc, row["token_symbol"])
        bucket["inflow_count"] += 1
        bucket["inflow_amount"] += parse_decimal(row["amount"])

    for row in outflow_rows:
        month_utc = parse_month_utc(row.get("timestamp"))
        if not month_utc:
            continue
        bucket = get_bucket(month_utc, row["token_symbol"])
        bucket["outflow_count"] += 1
        bucket["outflow_amount"] += parse_decimal(row["amount"])

    result_rows = []
    for (month_utc, token_symbol) in sorted(monthly.keys()):
        bucket = monthly[(month_utc, token_symbol)]
        inflow_amount = bucket["inflow_amount"]
        outflow_amount = bucket["outflow_amount"]
        result_rows.append(
            {
                "chain": chain,
                "month_utc": month_utc,
                "token_symbol": token_symbol,
                "inflow_count": bucket["inflow_count"],
                "inflow_amount": float(inflow_amount),
                "outflow_count": bucket["outflow_count"],
                "outflow_amount": float(outflow_amount),
                "net_amount": float(inflow_amount - outflow_amount),
            }
        )
    return result_rows


def parse_forum_claim(path: Path, label: str) -> dict[str, Any]:
    payload = load_json(path)
    topic_id = payload.get("id")
    title = payload.get("title")
    cooked = ((payload.get("post_stream") or {}).get("posts") or [{}])[0].get("cooked", "")
    text = strip_html(cooked)

    revenue = find_number(
        text,
        [
            r"made\s+\$?([0-9][0-9,]*(?:\.[0-9]+)?)\s+of revenue",
            r"revenue\s+\(.*?\)\s+.*?\$?([0-9][0-9,]*(?:\.[0-9]+)?)",
        ],
    )
    payout = find_number(
        text,
        [
            r"payout[^0-9]{0,90}([0-9][0-9,]*(?:\.[0-9]+)?)\s*USDC",
            r"Reward amount paid out:\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*USDC",
        ],
    )
    treasury_transfer = find_number(
        text,
        [
            r"actual total being transferred from the DAO Treasury is\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*USDC",
            r"Total being paid:\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*USDC",
        ],
    )

    return {
        "label": label,
        "topic_id": topic_id,
        "title": title,
        "url": f"https://forum.summer.fi/t/{topic_id}",
        "protocol_revenue_usd": float(revenue) if revenue is not None else None,
        "staker_payout_usdc": float(payout) if payout is not None else None,
        "treasury_transfer_usdc": float(treasury_transfer) if treasury_transfer is not None else None,
    }


def build_forum_tables(snapshot_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    claims = [
        parse_forum_claim(snapshot_dir / "summer_forum_sip3_13.json", "SIP3.13"),
        parse_forum_claim(snapshot_dir / "summer_forum_sip3_13_1.json", "SIP3.13.1"),
    ]
    ratios = []
    for row in claims:
        payout = parse_decimal(row["staker_payout_usdc"])
        revenue = parse_decimal(row["protocol_revenue_usd"])
        transfer = parse_decimal(row["treasury_transfer_usdc"])
        staker_share = (payout / revenue * Decimal(100)) if revenue else Decimal(0)
        merkl_fee = ((transfer - payout) / payout * Decimal(100)) if payout else Decimal(0)
        ratios.append(
            {
                "label": row["label"],
                "protocol_revenue_usd": row["protocol_revenue_usd"],
                "staker_payout_usdc": row["staker_payout_usdc"],
                "staker_share_pct": float(staker_share),
                "merkl_fee_pct_of_payout": float(merkl_fee),
            }
        )
    return claims, ratios


def build_reward_added_rows(snapshot_dir: Path) -> list[dict[str, Any]]:
    payload = load_json(snapshot_dir / "base_blockscout_grm_rewardAdded_all.json")
    rows = []
    for item in get_items(payload):
        decoded = item.get("decoded") or {}
        params = decoded.get("parameters") or []
        reward_token = ""
        reward_raw = ""
        for p in params:
            if p.get("name") == "rewardToken":
                reward_token = p.get("value", "")
            if p.get("name") == "reward":
                reward_raw = p.get("value", "")
        rows.append(
            {
                "tx_hash": item.get("transaction_hash"),
                "block_number": item.get("block_number"),
                "event": decoded.get("method_call"),
                "reward_token": reward_token,
                "reward_raw": reward_raw,
            }
        )
    rows.sort(key=lambda r: int(r["block_number"]), reverse=True)
    return rows


def build_contract_source_checks(snapshot_dir: Path) -> dict[str, Any]:
    stsumr = load_json(snapshot_dir / "base_blockscout_stsumr_contract.json")
    staking = load_json(snapshot_dir / "base_blockscout_summerstaking_contract.json")

    st_source = stsumr.get("source_code", "")
    ss_source = staking.get("source_code", "")

    return {
        "stsumr_contract_name": stsumr.get("name"),
        "stsumr_has_canTransfer": "_canTransfer" in st_source,
        "stsumr_revert_transfer_not_allowed": "xSumr_TransferNotAllowed" in st_source,
        "stsumr_mint_or_burn_only_rule": "from == address(0) || to == address(0)" in st_source,
        "summerstaking_contract_name": staking.get("name"),
        "summerstaking_has_MAX_LOCKUP_PERIOD": "MAX_LOCKUP_PERIOD" in ss_source,
        "summerstaking_has_MIN_PENALTY_2pct": "MIN_PENALTY" in ss_source and "2" in ss_source,
        "summerstaking_has_MAX_PENALTY_20pct": "MAX_PENALTY" in ss_source and "20" in ss_source,
        "summerstaking_has_FIXED_PENALTY_110d": "FIXED_PENALTY_PERIOD" in ss_source and "110 days" in ss_source,
        "summerstaking_has_WEIGHTED_COEFF_700": "COEFFICIENT" in ss_source and "700" in ss_source,
    }


def build_sumr_supply(snapshot_dir: Path) -> dict[str, Any] | None:
    rpc_path = optional_existing(snapshot_dir, ["base_rpc_supply_and_receipts.json"])
    if rpc_path is None:
        return None
    payload = load_json(rpc_path)
    sumr = payload.get("sumr") or {}
    decimals = int(sumr.get("decimals", 18))
    total = parse_decimal(sumr.get("totalSupply_raw"))
    cap = parse_decimal(sumr.get("cap_raw"))
    return {
        "retrieved_utc": parse_manifest_as_of(snapshot_dir),
        "chain": "base",
        "contract": "0x194f360D130F2393a5E9F3117A6a1B78aBEa1624",
        "decimals": decimals,
        "totalSupply_raw": str(int(total)),
        "cap_raw": str(int(cap)),
        "totalSupply_tokens": float(total / (Decimal(10) ** decimals)),
        "cap_tokens": float(cap / (Decimal(10) ** decimals)),
    }


def parse_tx_transfers(tx_payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for transfer in tx_payload.get("token_transfers") or []:
        total = transfer.get("total") or {}
        token = transfer.get("token") or {}
        amount = raw_to_amount(total.get("value"), total.get("decimals"))
        rows.append(
            {
                "tx_hash": transfer.get("transaction_hash"),
                "block_number": transfer.get("block_number"),
                "log_index": transfer.get("log_index"),
                "token": token.get("symbol"),
                "token_address": token.get("address_hash"),
                "from": normalize_addr((transfer.get("from") or {}).get("hash")),
                "to": normalize_addr((transfer.get("to") or {}).get("hash")),
                "raw_value": str(total.get("value")),
                "amount": float(amount),
            }
        )
    rows.sort(key=lambda r: (int(r["block_number"]), int(r["log_index"])))
    return rows


def build_sample_tx_transfer_rows(snapshot_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for tx_hash in KNOWN_SAMPLE_TXS:
        path = snapshot_dir / f"tx_{tx_hash}.json"
        if not path.exists():
            continue
        tx_payload = load_json(path)
        rows.extend(parse_tx_transfers(tx_payload))
    return rows


def decode_create_campaign(tx_payload: dict[str, Any]) -> dict[str, Any] | None:
    decoded_input = tx_payload.get("decoded_input") or {}
    params = decoded_input.get("parameters") or []
    if len(params) < 3:
        return None
    calldatas = params[2].get("value") or []
    for calldata in calldatas:
        if not isinstance(calldata, str):
            continue
        if not calldata.startswith("0xa63f05ad"):
            continue
        payload = bytes.fromhex(calldata[10:])
        campaign = decode(["(bytes32,address,address,uint256,uint32,uint32,uint32,bytes)"], payload)[0]
        reward_token = normalize_addr(campaign[2])
        decimals = token_decimals_for_address(reward_token)
        amount_raw = int(campaign[3])
        return {
            "campaign_id_hex": "0x" + campaign[0].hex(),
            "creator": normalize_addr(campaign[1]),
            "reward_token": reward_token,
            "reward_token_decimals": decimals,
            "amount_raw": amount_raw,
            "amount_tokens": float(Decimal(amount_raw) / (Decimal(10) ** decimals)),
            "amount_tokens_6dp": float(Decimal(amount_raw) / Decimal(10**6)),
            "campaign_type": int(campaign[4]),
            "start_timestamp": int(campaign[5]),
            "duration_seconds": int(campaign[6]),
            "campaign_data_hex": "0x" + campaign[7].hex(),
        }
    return None


def extract_funding_from_tx(tx_payload: dict[str, Any], token_symbol: str) -> list[dict[str, Any]]:
    rows = []
    for transfer in tx_payload.get("token_transfers") or []:
        token = transfer.get("token") or {}
        if (token.get("symbol") or "").upper() != token_symbol.upper():
            continue
        total = transfer.get("total") or {}
        rows.append(
            {
                "tx_hash": transfer.get("transaction_hash"),
                "block_number": transfer.get("block_number"),
                "log_index": transfer.get("log_index"),
                "from": normalize_addr((transfer.get("from") or {}).get("hash")),
                "to": normalize_addr((transfer.get("to") or {}).get("hash")),
                "token_symbol": token.get("symbol"),
                "token_address": token.get("address_hash"),
                "raw_value": str(total.get("value")),
                "decimals": int(total.get("decimals") or 0),
                "amount": float(raw_to_amount(total.get("value"), total.get("decimals"))),
                "type": transfer.get("type"),
            }
        )
    rows.sort(key=lambda r: int(r["log_index"]))
    return rows


def parse_claimed_logs(path: Path, decimals: int = 6) -> list[dict[str, Any]]:
    payload = load_json(path)
    logs = payload.get("logs") or []
    rows = []
    for log in logs:
        amount_raw = int(log["data"], 16)
        rows.append(
            {
                "block_number": int(log["blockNumber"], 16),
                "tx_hash": log["transactionHash"],
                "log_index": int(log["logIndex"], 16),
                "user": "0x" + log["topics"][1][-40:],
                "amount_raw": amount_raw,
                "amount_tokens": float(Decimal(amount_raw) / (Decimal(10) ** decimals)),
            }
        )
    rows.sort(key=lambda r: (r["block_number"], r["log_index"]))
    return rows


def parse_hex_int(value: str | int | None) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    if value.startswith("0x"):
        return int(value, 16)
    return int(value)


def token_decimals_for_address(token_address: str) -> int:
    normalized = normalize_addr(token_address)
    for meta in CLAIM_TOKEN_REGISTRY.values():
        if normalize_addr(meta["address"]) == normalized:
            return int(meta["decimals"])
    return 18


def token_symbol_for_address(token_address: str, default: str = "UNKNOWN") -> str:
    normalized = normalize_addr(token_address)
    for meta in CLAIM_TOKEN_REGISTRY.values():
        if normalize_addr(meta["address"]) == normalized:
            return str(meta["symbol"])
    return default


def load_receipt_snapshot(snapshot_dir: Path, tx_hash: str) -> dict[str, Any] | None:
    path = snapshot_dir / f"base_rpc_receipt_{tx_hash}.json"
    if not path.exists():
        return None
    return load_json(path)


def decode_new_campaign_events(receipt_payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not receipt_payload:
        return []
    rows: list[dict[str, Any]] = []
    for log in receipt_payload.get("logs") or []:
        topics = log.get("topics") or []
        if not topics:
            continue
        if normalize_addr(topics[0]) != normalize_addr(NEW_CAMPAIGN_TOPIC):
            continue
        data = log.get("data") or "0x"
        if not isinstance(data, str) or not data.startswith("0x") or len(data) <= 2:
            continue
        try:
            decoded = decode(
                ["(bytes32,address,address,uint256,uint32,uint32,uint32,bytes)"],
                bytes.fromhex(data[2:]),
            )[0]
        except Exception:  # noqa: BLE001
            continue
        reward_token = normalize_addr(decoded[2])
        decimals = token_decimals_for_address(reward_token)
        rows.append(
            {
                "campaign_id_hex": "0x" + decoded[0].hex(),
                "creator": normalize_addr(decoded[1]),
                "reward_token": reward_token,
                "amount_raw": int(decoded[3]),
                "amount_tokens": float(Decimal(decoded[3]) / (Decimal(10) ** decimals)),
                "reward_token_decimals": decimals,
                "campaign_type": int(decoded[4]),
                "start_timestamp": int(decoded[5]),
                "duration_seconds": int(decoded[6]),
                "campaign_data_hex": "0x" + decoded[7].hex(),
                "log_address": normalize_addr(log.get("address")),
                "log_index": parse_hex_int(log.get("logIndex")),
                "block_number": parse_hex_int(log.get("blockNumber")),
                "tx_hash": log.get("transactionHash"),
            }
        )
    rows.sort(key=lambda r: r["log_index"])
    return rows


def pick_matching_campaign_event(
    events: list[dict[str, Any]],
    reward_token_hint: str | None,
) -> dict[str, Any] | None:
    if not events:
        return None
    if reward_token_hint:
        hint = normalize_addr(reward_token_hint)
        for event in events:
            if normalize_addr(event["reward_token"]) == hint:
                return event
    return events[0]


def resolve_campaign_reconstruction(
    snapshot_dir: Path,
    tx_hash: str,
    tx_payload: dict[str, Any],
) -> dict[str, Any]:
    calldata_campaign = decode_create_campaign(tx_payload)
    receipt_payload = load_receipt_snapshot(snapshot_dir, tx_hash)
    events = decode_new_campaign_events(receipt_payload)
    reward_token_hint = calldata_campaign["reward_token"] if calldata_campaign else None
    selected_event = pick_matching_campaign_event(events, reward_token_hint)

    selected_source = "unavailable"
    selected_campaign = None
    notes: list[str] = []

    if selected_event is not None:
        selected_source = "new_campaign_event"
        selected_campaign = {
            "campaign_id_hex": selected_event["campaign_id_hex"],
            "creator": selected_event["creator"],
            "reward_token": selected_event["reward_token"],
            "reward_token_decimals": selected_event["reward_token_decimals"],
            "amount_raw": selected_event["amount_raw"],
            "amount_tokens": selected_event["amount_tokens"],
            "amount_tokens_6dp": float(Decimal(selected_event["amount_raw"]) / Decimal(10**6)),
            "campaign_type": selected_event["campaign_type"],
            "start_timestamp": selected_event["start_timestamp"],
            "duration_seconds": selected_event["duration_seconds"],
            "campaign_data_hex": selected_event["campaign_data_hex"],
        }
    elif calldata_campaign is not None:
        selected_source = "calldata_createCampaign"
        selected_campaign = calldata_campaign

    if calldata_campaign and selected_event:
        if int(calldata_campaign["amount_raw"]) != int(selected_event["amount_raw"]):
            notes.append("calldata_amount_differs_from_new_campaign_event")
        if normalize_addr(calldata_campaign["reward_token"]) != normalize_addr(selected_event["reward_token"]):
            notes.append("calldata_reward_token_differs_from_new_campaign_event")
        if str(calldata_campaign["campaign_id_hex"]).lower() != str(selected_event["campaign_id_hex"]).lower():
            notes.append("calldata_campaign_id_differs_from_new_campaign_event")
        if normalize_addr(calldata_campaign["creator"]) != normalize_addr(selected_event["creator"]):
            notes.append("calldata_creator_differs_from_new_campaign_event")

    receipt_file = snapshot_dir / f"base_rpc_receipt_{tx_hash}.json"
    receipt_status = parse_hex_int(receipt_payload.get("status")) if receipt_payload else None

    return {
        "receipt_file": receipt_file.name if receipt_file.exists() else None,
        "receipt_status": receipt_status,
        "calldata_create_campaign": calldata_campaign,
        "new_campaign_events": events,
        "selected_source": selected_source,
        "selected_campaign": selected_campaign,
        "reconstruction_notes": notes,
    }


def load_claimed_logs_by_token(snapshot_dir: Path) -> dict[str, list[dict[str, Any]]]:
    by_token: dict[str, list[dict[str, Any]]] = {}
    seen: set[tuple[str, int, str]] = set()
    for path in sorted(snapshot_dir.glob("base_rpc_distributor_claimed_*.json")):
        match = re.match(r"base_rpc_distributor_claimed_([a-z0-9]+)_", path.name)
        if not match:
            continue
        token_key = match.group(1)
        token_meta = CLAIM_TOKEN_REGISTRY.get(token_key)
        if token_meta is None:
            continue
        token_address = normalize_addr(token_meta["address"])
        decimals = int(token_meta["decimals"])
        payload = load_json(path)
        logs = payload.get("logs") or []
        for log in logs:
            tx_hash = log["transactionHash"]
            log_index = int(log["logIndex"], 16)
            dedup_key = (tx_hash, log_index, token_address)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            amount_raw = int(log["data"], 16)
            row = {
                "source_file": path.name,
                "token_key": token_key,
                "token_symbol": token_meta["symbol"],
                "token_address": token_address,
                "block_number": int(log["blockNumber"], 16),
                "tx_hash": tx_hash,
                "log_index": log_index,
                "user": "0x" + log["topics"][1][-40:],
                "amount_raw": amount_raw,
                "amount_tokens": float(Decimal(amount_raw) / (Decimal(10) ** decimals)),
            }
            by_token.setdefault(token_address, []).append(row)
    for token_address in by_token:
        by_token[token_address].sort(key=lambda r: (r["block_number"], r["log_index"]))
    return by_token


def extract_token_transfers_by_address(tx_payload: dict[str, Any], token_address: str) -> list[dict[str, Any]]:
    target = normalize_addr(token_address)
    rows = []
    for transfer in tx_payload.get("token_transfers") or []:
        token = transfer.get("token") or {}
        addr = normalize_addr(token.get("address_hash"))
        if addr != target:
            continue
        total = transfer.get("total") or {}
        rows.append(
            {
                "tx_hash": transfer.get("transaction_hash"),
                "block_number": transfer.get("block_number"),
                "log_index": transfer.get("log_index"),
                "from": normalize_addr((transfer.get("from") or {}).get("hash")),
                "to": normalize_addr((transfer.get("to") or {}).get("hash")),
                "token_symbol": token.get("symbol"),
                "token_address": token.get("address_hash"),
                "raw_value": str(total.get("value")),
                "decimals": int(total.get("decimals") or 0),
                "amount": float(raw_to_amount(total.get("value"), total.get("decimals"))),
                "type": transfer.get("type"),
            }
        )
    rows.sort(key=lambda r: int(r["log_index"]))
    return rows


def find_prior_token_funding(
    base_treasury_payload: dict[str, Any],
    token_address: str,
    before_block: int,
) -> list[dict[str, Any]]:
    target = normalize_addr(token_address)
    rows = []
    for item in get_items(base_treasury_payload):
        token = item.get("token") or {}
        if normalize_addr(token.get("address_hash")) != target:
            continue
        if normalize_addr((item.get("from") or {}).get("hash")) != TREASURY:
            continue
        if normalize_addr((item.get("to") or {}).get("hash")) != DISTRIBUTOR:
            continue
        block = int(item.get("block_number"))
        if block >= before_block:
            continue
        total = item.get("total") or {}
        rows.append(
            {
                "block_number": block,
                "timestamp": item.get("timestamp"),
                "tx_hash": item.get("transaction_hash"),
                "amount": float(raw_to_amount(total.get("value"), total.get("decimals"))),
                "raw_value": str(total.get("value")),
            }
        )
    rows.sort(key=lambda r: (r["block_number"], r["tx_hash"]))
    return rows


def campaign_label_to_slug(label: str) -> str:
    return label.lower().replace(".", "_")


def summarize_reasons(reasons: list[str]) -> str:
    return ";".join(reasons)


def attribution_confidence_class(
    campaign_source: str | None,
    claim_events: int,
    prior_same_token_funding_count: int,
    residual_ratio: Decimal,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if claim_events == 0:
        reasons.append("no_reward_token_claims_observed")
        return "UNPROVEN", reasons

    if campaign_source != "new_campaign_event":
        reasons.append("campaign_not_reconstructed_from_receipt_event")
    if prior_same_token_funding_count > 0:
        reasons.append("prior_same_token_funding_exists")
    if residual_ratio > Decimal("0.05"):
        reasons.append("residual_ratio_above_0_05")

    if reasons:
        return "PARTIAL", reasons

    # Claimed events omit campaign id, so "EXACT" is reserved for future exact mappings.
    return "BOUNDED", ["token_scoped_claimed_events_without_campaign_id"]


def build_campaign_attribution_artifacts(
    snapshot_dir: Path,
    output_dir: Path,
    forum_by_label: dict[str, dict[str, Any]],
    campaign_inputs: list[dict[str, Any]],
    base_treasury_payload: dict[str, Any],
) -> None:
    claimed_by_token = load_claimed_logs_by_token(snapshot_dir)
    campaigns_for_window = []
    canonical_cycle_rows = []
    for campaign in campaign_inputs:
        campaigns_for_window.append(
            {
                "label": campaign["label"],
                "execute_block": int(campaign["execute_block"]),
                "reward_token": normalize_addr(campaign["reward_token"]),
                "claim_window_end_block": campaign.get("claim_window_end_block"),
            }
        )

    summaries = []
    for campaign in campaign_inputs:
        label = campaign["label"]
        slug = campaign_label_to_slug(label)
        execute_block = int(campaign["execute_block"])
        reward_token = normalize_addr(campaign["reward_token"])
        reward_symbol = campaign["reward_symbol"]
        campaign_id_hex = campaign.get("campaign_id_hex")
        campaign_source = campaign.get("campaign_source")
        campaign_reconstruction_notes = campaign.get("campaign_reconstruction_notes") or []
        claim_window_end_block = campaign.get("claim_window_end_block")

        next_same_token_block = None
        for candidate in sorted(campaigns_for_window, key=lambda c: c["execute_block"]):
            if candidate["reward_token"] == reward_token and candidate["execute_block"] > execute_block:
                next_same_token_block = candidate["execute_block"]
                break
        if claim_window_end_block is None and next_same_token_block is not None:
            claim_window_end_block = next_same_token_block - 1

        token_claims = claimed_by_token.get(reward_token, [])
        claim_rows = []
        for row in token_claims:
            if row["block_number"] < execute_block:
                continue
            if claim_window_end_block is not None and row["block_number"] > claim_window_end_block:
                continue
            claim_rows.append(row)

        write_csv(
            output_dir / f"payout_attribution_{slug}_claim_events.csv",
            claim_rows,
            [
                "source_file",
                "token_key",
                "token_symbol",
                "token_address",
                "block_number",
                "tx_hash",
                "log_index",
                "user",
                "amount_raw",
                "amount_tokens",
            ],
        )

        funding_rows = extract_token_transfers_by_address(campaign["tx_payload"], reward_token)
        funding_to_distributor = sum(
            parse_decimal(row["amount"]) for row in funding_rows if row["from"] == TREASURY and row["to"] == DISTRIBUTOR
        )
        funding_to_fee = sum(
            parse_decimal(row["amount"])
            for row in funding_rows
            if row["from"] == TREASURY and row["to"] == MERKL_FEE_RECIPIENT
        )

        claim_total = sum(parse_decimal(row["amount_tokens"]) for row in claim_rows)
        attributed_claimed = min(claim_total, funding_to_distributor)
        unattributed_residual = max(Decimal(0), funding_to_distributor - attributed_claimed)
        overflow_claims = max(Decimal(0), claim_total - funding_to_distributor)
        unique_claimants = len({row["user"] for row in claim_rows})
        residual_ratio = (unattributed_residual / funding_to_distributor) if funding_to_distributor > 0 else Decimal(1)

        prior_funding_rows = find_prior_token_funding(base_treasury_payload, reward_token, execute_block)
        prior_funding_total = sum(parse_decimal(row["amount"]) for row in prior_funding_rows)

        reasons = []
        status = "PROVEN"
        if not claim_rows:
            status = "PARTIAL"
            reasons.append("no_reward_token_claims_observed")
        if prior_funding_rows:
            status = "PARTIAL"
            reasons.append("prior_same_token_funding_exists")
        if unattributed_residual > Decimal("0.000001"):
            status = "PARTIAL"
            reasons.append("campaign_funding_not_fully_claimed_in_window")
        confidence_class, confidence_reasons = attribution_confidence_class(
            campaign_source=campaign_source,
            claim_events=len(claim_rows),
            prior_same_token_funding_count=len(prior_funding_rows),
            residual_ratio=residual_ratio,
        )

        related_activity = []
        for related_key in ["usdc", "abasusdc"]:
            meta = CLAIM_TOKEN_REGISTRY[related_key]
            rel_addr = normalize_addr(meta["address"])
            if rel_addr == reward_token:
                continue
            rel_claim_rows = [r for r in claimed_by_token.get(rel_addr, []) if r["block_number"] >= execute_block]
            related_activity.append(
                {
                    "token_symbol": meta["symbol"],
                    "claim_events": len(rel_claim_rows),
                    "claimed_total": float(sum(parse_decimal(r["amount_tokens"]) for r in rel_claim_rows)),
                }
            )

        summary = {
            "label": label,
            "forum_claim": forum_by_label.get(label),
            "governor_execute_tx": campaign["tx_hash"],
            "governor_execute_block": execute_block,
            "governor_execute_timestamp": campaign["tx_timestamp"],
            "campaign_id_hex": campaign_id_hex,
            "campaign_source": campaign_source,
            "campaign_reconstruction_notes": campaign_reconstruction_notes,
            "reward_token": reward_token,
            "reward_token_symbol": reward_symbol,
            "campaign_amount_tokens": float(campaign["campaign_amount_tokens"]),
            "funding_to_distributor_tokens": float(funding_to_distributor),
            "funding_to_fee_recipient_tokens": float(funding_to_fee),
            "claim_window_start_block": execute_block,
            "claim_window_end_block": claim_window_end_block,
            "claim_events_considered": len(claim_rows),
            "unique_claimants_considered": unique_claimants,
            "claimed_total_considered": float(claim_total),
            "attributed_claimed_total": float(attributed_claimed),
            "unattributed_residual": float(unattributed_residual),
            "residual_ratio": float(residual_ratio),
            "claims_over_campaign_cap": float(overflow_claims),
            "prior_same_token_funding_count": len(prior_funding_rows),
            "prior_same_token_funding_total": float(prior_funding_total),
            "staker_revenue_deposited_tokens": float(funding_to_distributor),
            "staker_revenue_claimed_tokens_considered": float(claim_total),
            "staker_revenue_claimed_tokens_attributed": float(attributed_claimed),
            "staker_revenue_unclaimed_tokens_residual": float(unattributed_residual),
            "canonical_metric_policy": (
                "deposited=funding_to_distributor; claimed_considered=all reward-token Claimed events "
                "in execution window; claimed_attributed=min(claimed_considered,deposited); "
                "unclaimed_residual=deposited-claimed_attributed floor 0"
            ),
            "attribution_confidence_class": confidence_class,
            "attribution_confidence_reasons": confidence_reasons,
            "status": status,
            "status_reasons": reasons,
            "attribution_model": "token_scoped_flow_cap_v1",
            "related_post_execute_claim_activity": related_activity,
            "attribution_note": (
                "Attribution is deterministic but token-scoped. Claimed events omit campaign ID, "
                "so campaign attribution uses reward-token claim windows and funding-cap constraints. "
                "Campaign IDs are reconstructed from NewCampaign receipt logs when available."
            ),
        }
        canonical_cycle_rows.append(
            {
                "label": label,
                "campaign_id_hex": campaign_id_hex,
                "campaign_source": campaign_source,
                "reward_token_symbol": reward_symbol,
                "reward_token": reward_token,
                "governor_execute_block": execute_block,
                "claim_window_start_block": execute_block,
                "claim_window_end_block": claim_window_end_block if claim_window_end_block is not None else "",
                "staker_revenue_deposited_tokens": float(funding_to_distributor),
                "staker_revenue_claimed_tokens_considered": float(claim_total),
                "staker_revenue_claimed_tokens_attributed": float(attributed_claimed),
                "staker_revenue_unclaimed_tokens_residual": float(unattributed_residual),
                "funding_to_fee_recipient_tokens": float(funding_to_fee),
                "residual_ratio": float(residual_ratio),
                "claim_events_considered": len(claim_rows),
                "unique_claimants_considered": unique_claimants,
                "prior_same_token_funding_count": len(prior_funding_rows),
                "attribution_confidence_class": confidence_class,
                "attribution_confidence_reasons": summarize_reasons(confidence_reasons),
                "status": status,
                "status_reasons": summarize_reasons(reasons),
            }
        )
        summaries.append(summary)

    summaries.sort(key=lambda r: r["label"])
    summary_payload = {
        "generated_from": snapshot_dir.as_posix(),
        "model": "token_scoped_flow_cap_v1",
        "campaigns": summaries,
    }
    save_json(output_dir / "payout_attribution_summary.json", summary_payload)

    write_csv(
        output_dir / "payout_attribution_cycle_table.csv",
        canonical_cycle_rows,
        [
            "label",
            "campaign_id_hex",
            "campaign_source",
            "reward_token_symbol",
            "reward_token",
            "governor_execute_block",
            "claim_window_start_block",
            "claim_window_end_block",
            "staker_revenue_deposited_tokens",
            "staker_revenue_claimed_tokens_considered",
            "staker_revenue_claimed_tokens_attributed",
            "staker_revenue_unclaimed_tokens_residual",
            "funding_to_fee_recipient_tokens",
            "residual_ratio",
            "claim_events_considered",
            "unique_claimants_considered",
            "prior_same_token_funding_count",
            "attribution_confidence_class",
            "attribution_confidence_reasons",
            "status",
            "status_reasons",
        ],
    )

    aggregate_by_token: dict[str, dict[str, Decimal]] = {}
    for summary in summaries:
        token_symbol = summary["reward_token_symbol"]
        token_totals = aggregate_by_token.setdefault(
            token_symbol,
            {
                "staker_revenue_deposited_tokens": Decimal(0),
                "staker_revenue_claimed_tokens_considered": Decimal(0),
                "staker_revenue_claimed_tokens_attributed": Decimal(0),
                "staker_revenue_unclaimed_tokens_residual": Decimal(0),
            },
        )
        token_totals["staker_revenue_deposited_tokens"] += parse_decimal(summary["staker_revenue_deposited_tokens"])
        token_totals["staker_revenue_claimed_tokens_considered"] += parse_decimal(
            summary["staker_revenue_claimed_tokens_considered"]
        )
        token_totals["staker_revenue_claimed_tokens_attributed"] += parse_decimal(
            summary["staker_revenue_claimed_tokens_attributed"]
        )
        token_totals["staker_revenue_unclaimed_tokens_residual"] += parse_decimal(
            summary["staker_revenue_unclaimed_tokens_residual"]
        )

    aggregate_token_rows = []
    for token_symbol, totals in sorted(aggregate_by_token.items()):
        aggregate_token_rows.append(
            {
                "reward_token_symbol": token_symbol,
                "staker_revenue_deposited_tokens": float(totals["staker_revenue_deposited_tokens"]),
                "staker_revenue_claimed_tokens_considered": float(totals["staker_revenue_claimed_tokens_considered"]),
                "staker_revenue_claimed_tokens_attributed": float(totals["staker_revenue_claimed_tokens_attributed"]),
                "staker_revenue_unclaimed_tokens_residual": float(totals["staker_revenue_unclaimed_tokens_residual"]),
            }
        )

    total_deposited = sum(parse_decimal(row["staker_revenue_deposited_tokens"]) for row in summaries)
    total_claimed_attributed = sum(parse_decimal(row["staker_revenue_claimed_tokens_attributed"]) for row in summaries)
    total_unclaimed = sum(parse_decimal(row["staker_revenue_unclaimed_tokens_residual"]) for row in summaries)
    save_json(
        output_dir / "staker_revenue_canonical_summary.json",
        {
            "generated_from": snapshot_dir.as_posix(),
            "metric_policy": {
                "staker_revenue_deposited_tokens": "funding_to_distributor transfer amount",
                "staker_revenue_claimed_tokens_considered": "all reward-token Claimed events in execution window",
                "staker_revenue_claimed_tokens_attributed": "min(claimed_considered, deposited)",
                "staker_revenue_unclaimed_tokens_residual": "max(0, deposited - claimed_attributed)",
            },
            "cycles": summaries,
            "aggregate": {
                "staker_revenue_deposited_tokens_total": float(total_deposited),
                "staker_revenue_claimed_tokens_attributed_total": float(total_claimed_attributed),
                "staker_revenue_unclaimed_tokens_residual_total": float(total_unclaimed),
                "reward_token_totals": aggregate_token_rows,
            },
        },
    )

    gate_threshold = Decimal("0.05")
    gate_rows = []
    for summary in summaries:
        funding = parse_decimal(summary["funding_to_distributor_tokens"])
        residual = parse_decimal(summary["unattributed_residual"])
        residual_ratio = (residual / funding) if funding > 0 else Decimal(1)
        confidence_class = summary["attribution_confidence_class"]
        pass_gate = confidence_class in {"EXACT", "BOUNDED"} and residual_ratio <= gate_threshold
        gate_rows.append(
            {
                "label": summary["label"],
                "status": summary["status"],
                "attribution_confidence_class": confidence_class,
                "residual_ratio": float(residual_ratio),
                "threshold": float(gate_threshold),
                "pass": pass_gate,
            }
        )

    save_json(
        output_dir / "payout_attribution_gate.json",
        {
            "generated_from": snapshot_dir.as_posix(),
            "rule": "campaign confidence must be EXACT or BOUNDED and residual_ratio <= 0.05",
            "all_campaigns_pass": all(row["pass"] for row in gate_rows),
            "campaigns": gate_rows,
        },
    )


def build_payout_chain_artifacts(
    snapshot_dir: Path,
    output_dir: Path,
    forum_claims: list[dict[str, Any]],
    base_treasury_payload: dict[str, Any],
) -> None:
    forum_by_label = {row["label"]: row for row in forum_claims}
    campaign_inputs: list[dict[str, Any]] = []

    sip313_tx = snapshot_dir / f"tx_{SIP313_TX}.json"
    if sip313_tx.exists():
        tx_payload = load_json(sip313_tx)
        campaign_resolution = resolve_campaign_reconstruction(snapshot_dir, SIP313_TX, tx_payload)
        campaign = campaign_resolution["selected_campaign"]
        funding_rows = extract_funding_from_tx(tx_payload, "USDC")

        claim_rows = []
        claim_file = optional_existing(snapshot_dir, ["base_rpc_distributor_claimed_usdc_40757499_41932732.json"])
        if claim_file is not None:
            claim_rows = parse_claimed_logs(claim_file, decimals=6)
            write_csv(
                output_dir / "payout_chain_sip3_13_claimed_usdc_events.csv",
                claim_rows,
                ["block_number", "tx_hash", "log_index", "user", "amount_raw", "amount_tokens"],
            )

        unique_users = len({row["user"] for row in claim_rows}) if claim_rows else 0
        claim_total_dec = sum(parse_decimal(row["amount_tokens"]) for row in claim_rows) if claim_rows else Decimal(0)
        claimed_total = float(claim_total_dec)
        funding_to_distributor_usdc = sum(
            parse_decimal(r["amount"]) for r in funding_rows if normalize_addr(r["to"]) == DISTRIBUTOR
        )
        funding_to_fee_usdc = sum(
            parse_decimal(r["amount"]) for r in funding_rows if normalize_addr(r["to"]) == MERKL_FEE_RECIPIENT
        )
        claimed_attributed_usdc = min(claim_total_dec, funding_to_distributor_usdc)
        unclaimed_residual_usdc = max(Decimal(0), funding_to_distributor_usdc - claimed_attributed_usdc)

        summary = {
            "label": "SIP3.13",
            "forum_claim": forum_by_label.get("SIP3.13"),
            "governor_execute_tx": SIP313_TX,
            "governor_execute_timestamp": tx_payload.get("timestamp"),
            "campaign_reconstruction": campaign_resolution,
            "create_campaign": campaign,
            "funding_transfers_usdc": funding_rows,
            "funding_to_distributor_usdc": float(funding_to_distributor_usdc),
            "funding_to_merkl_fee_recipient_usdc": float(funding_to_fee_usdc),
            "claimed_window_file": claim_file.name if claim_file else None,
            "claimed_window_scope": {
                "token": "USDC",
                "from_block": 40757499,
                "to_block": 41932732,
            },
            "claimed_events_count_in_window": len(claim_rows),
            "claimed_unique_users_in_window": unique_users,
            "claimed_total_usdc_in_window": claimed_total,
            "canonical_staker_revenue_metrics": {
                "staker_revenue_deposited_tokens": float(funding_to_distributor_usdc),
                "staker_revenue_claimed_tokens_considered": float(claim_total_dec),
                "staker_revenue_claimed_tokens_attributed": float(claimed_attributed_usdc),
                "staker_revenue_unclaimed_tokens_residual": float(unclaimed_residual_usdc),
                "metric_policy": (
                    "deposited=funding_to_distributor; claimed_considered=all USDC Claimed events in window; "
                    "claimed_attributed=min(claimed_considered,deposited); "
                    "unclaimed_residual=deposited-claimed_attributed floor 0"
                ),
            },
            "attribution_note": (
                "Claimed(user, token, amount) does not include campaign ID. "
                "Window totals represent all distributor USDC claims after execution, not guaranteed to be SIP3.13-only."
            ),
        }
        save_json(output_dir / "payout_chain_sip3_13_summary.json", summary)
        if campaign is not None:
            reward_token = normalize_addr(campaign["reward_token"])
            campaign_inputs.append(
                {
                    "label": "SIP3.13",
                    "tx_hash": SIP313_TX,
                    "tx_timestamp": tx_payload.get("timestamp"),
                    "execute_block": int(tx_payload.get("block_number")),
                    "campaign_id_hex": campaign.get("campaign_id_hex"),
                    "campaign_source": campaign_resolution["selected_source"],
                    "campaign_reconstruction_notes": campaign_resolution["reconstruction_notes"],
                    "reward_token": reward_token,
                    "reward_symbol": token_symbol_for_address(reward_token, default="USDC"),
                    "campaign_amount_tokens": parse_decimal(campaign.get("amount_tokens", campaign["amount_tokens_6dp"])),
                    "claim_window_end_block": 41932732,
                    "tx_payload": tx_payload,
                }
            )

    sip3131_tx = snapshot_dir / f"tx_{SIP3131_TX}.json"
    if sip3131_tx.exists():
        tx_payload = load_json(sip3131_tx)
        campaign_resolution = resolve_campaign_reconstruction(snapshot_dir, SIP3131_TX, tx_payload)
        campaign = campaign_resolution["selected_campaign"]

        usdc_funding = extract_funding_from_tx(tx_payload, "USDC")
        lvusdc_funding = extract_funding_from_tx(tx_payload, "LVUSDC")

        usdc_claim_post = []
        lvusdc_claim_post = []
        abasusdc_claim_post = []

        usdc_claim_file = optional_existing(snapshot_dir, ["base_rpc_distributor_claimed_usdc_41932733_latest.json"])
        lvusdc_claim_file = optional_existing(snapshot_dir, ["base_rpc_distributor_claimed_lvusdc_41932733_latest.json"])
        abasusdc_claim_file = optional_existing(snapshot_dir, ["base_rpc_distributor_claimed_abasusdc_41932733_latest.json"])

        if usdc_claim_file:
            usdc_claim_post = parse_claimed_logs(usdc_claim_file, decimals=6)
        if lvusdc_claim_file:
            lvusdc_claim_post = parse_claimed_logs(lvusdc_claim_file, decimals=6)
        if abasusdc_claim_file:
            abasusdc_claim_post = parse_claimed_logs(abasusdc_claim_file, decimals=6)

        lvusdc_funding_to_distributor = sum(
            parse_decimal(r["amount"]) for r in lvusdc_funding if normalize_addr(r["to"]) == DISTRIBUTOR
        )
        lvusdc_funding_to_fee = sum(
            parse_decimal(r["amount"]) for r in lvusdc_funding if normalize_addr(r["to"]) == MERKL_FEE_RECIPIENT
        )
        lvusdc_claim_total_dec = sum(parse_decimal(r["amount_tokens"]) for r in lvusdc_claim_post)
        lvusdc_claimed_attributed = min(lvusdc_claim_total_dec, lvusdc_funding_to_distributor)
        lvusdc_unclaimed_residual = max(Decimal(0), lvusdc_funding_to_distributor - lvusdc_claimed_attributed)

        summary = {
            "label": "SIP3.13.1",
            "forum_claim": forum_by_label.get("SIP3.13.1"),
            "governor_execute_tx": SIP3131_TX,
            "governor_execute_timestamp": tx_payload.get("timestamp"),
            "campaign_reconstruction": campaign_resolution,
            "create_campaign": campaign,
            "usdc_funding_transfers": usdc_funding,
            "lvusdc_funding_transfers": lvusdc_funding,
            "post_execution_claims": {
                "usdc_claim_file": usdc_claim_file.name if usdc_claim_file else None,
                "usdc_claim_events": len(usdc_claim_post),
                "usdc_claim_total": float(sum(parse_decimal(r["amount_tokens"]) for r in usdc_claim_post)),
                "lvusdc_claim_file": lvusdc_claim_file.name if lvusdc_claim_file else None,
                "lvusdc_claim_events": len(lvusdc_claim_post),
                "lvusdc_claim_total": float(sum(parse_decimal(r["amount_tokens"]) for r in lvusdc_claim_post)),
                "abasusdc_claim_file": abasusdc_claim_file.name if abasusdc_claim_file else None,
                "abasusdc_claim_events": len(abasusdc_claim_post),
                "abasusdc_claim_total": float(sum(parse_decimal(r["amount_tokens"]) for r in abasusdc_claim_post)),
            },
            "canonical_staker_revenue_metrics": {
                "staker_revenue_deposited_tokens": float(lvusdc_funding_to_distributor),
                "staker_revenue_claimed_tokens_considered": float(lvusdc_claim_total_dec),
                "staker_revenue_claimed_tokens_attributed": float(lvusdc_claimed_attributed),
                "staker_revenue_unclaimed_tokens_residual": float(lvusdc_unclaimed_residual),
                "funding_to_fee_recipient_tokens": float(lvusdc_funding_to_fee),
                "metric_policy": (
                    "deposited=funding_to_distributor; claimed_considered=all LVUSDC Claimed events post execution; "
                    "claimed_attributed=min(claimed_considered,deposited); "
                    "unclaimed_residual=deposited-claimed_attributed floor 0"
                ),
            },
            "attribution_note": (
                "Post-execution claim totals are token-scoped and time-scoped only. "
                "They show settlement activity status, not one-to-one campaign attribution."
            ),
        }
        save_json(output_dir / "payout_chain_sip3_13_1_summary.json", summary)
        if campaign is not None:
            reward_token = normalize_addr(campaign["reward_token"])
            campaign_inputs.append(
                {
                    "label": "SIP3.13.1",
                    "tx_hash": SIP3131_TX,
                    "tx_timestamp": tx_payload.get("timestamp"),
                    "execute_block": int(tx_payload.get("block_number")),
                    "campaign_id_hex": campaign.get("campaign_id_hex"),
                    "campaign_source": campaign_resolution["selected_source"],
                    "campaign_reconstruction_notes": campaign_resolution["reconstruction_notes"],
                    "reward_token": reward_token,
                    "reward_symbol": token_symbol_for_address(reward_token, default="LVUSDC"),
                    "campaign_amount_tokens": parse_decimal(campaign.get("amount_tokens", campaign["amount_tokens_6dp"])),
                    "tx_payload": tx_payload,
                }
            )

    if campaign_inputs:
        build_campaign_attribution_artifacts(
            snapshot_dir=snapshot_dir,
            output_dir=output_dir,
            forum_by_label=forum_by_label,
            campaign_inputs=campaign_inputs,
            base_treasury_payload=base_treasury_payload,
        )


def build_source_of_funds_artifacts(
    snapshot_dir: Path,
    output_dir: Path,
    base_inflows: list[dict[str, Any]],
    base_outflows: list[dict[str, Any]],
    eth_inflows: list[dict[str, Any]],
    eth_outflows: list[dict[str, Any]],
) -> None:
    canonical_path = output_dir / "staker_revenue_canonical_summary.json"
    canonical = load_json(canonical_path) if canonical_path.exists() else {}
    cycles = canonical.get("cycles") or []

    payout_by_token: dict[str, Decimal] = {}
    payout_by_month_token: dict[tuple[str, str], Decimal] = {}
    for cycle in cycles:
        token_symbol = str(cycle.get("reward_token_symbol") or "").upper()
        deposited = parse_decimal(cycle.get("staker_revenue_deposited_tokens"))
        if not token_symbol:
            continue
        payout_by_token[token_symbol] = payout_by_token.get(token_symbol, Decimal(0)) + deposited
        month_utc = parse_month_utc(cycle.get("governor_execute_timestamp"))
        if month_utc:
            key = (month_utc, token_symbol)
            payout_by_month_token[key] = payout_by_month_token.get(key, Decimal(0)) + deposited

    base_inflow_totals = summarize_token_totals_decimal(base_inflows)
    base_outflow_totals = summarize_token_totals_decimal(base_outflows)
    eth_inflow_totals = summarize_token_totals_decimal(eth_inflows)
    eth_outflow_totals = summarize_token_totals_decimal(eth_outflows)

    payout_tokens = sorted(payout_by_token.keys())
    comparable_tokens = sorted(token for token in payout_tokens if token in FEE_TOKEN_SYMBOLS)
    non_comparable_tokens = sorted(token for token in payout_tokens if token not in FEE_TOKEN_SYMBOLS)

    coverage_by_token = []
    insufficient_coverage_tokens: list[str] = []
    for token in comparable_tokens:
        inflow = base_inflow_totals.get(token, Decimal(0))
        payout = payout_by_token.get(token, Decimal(0))
        coverage_ratio = (inflow / payout) if payout > 0 else None
        if payout > 0 and inflow < payout:
            insufficient_coverage_tokens.append(token)
        coverage_by_token.append(
            {
                "token_symbol": token,
                "fee_aligned_inflow_to_treasury_base": float(inflow),
                "staker_payout_outflow_from_treasury_base": float(payout),
                "coverage_ratio": float(coverage_ratio) if coverage_ratio is not None else None,
                "coverage_meets_or_exceeds_payout": bool(inflow >= payout) if payout > 0 else None,
            }
        )

    comparable_inflow_total = sum(base_inflow_totals.get(token, Decimal(0)) for token in comparable_tokens)
    comparable_payout_total = sum(payout_by_token.get(token, Decimal(0)) for token in comparable_tokens)
    comparable_coverage_ratio = (
        comparable_inflow_total / comparable_payout_total if comparable_payout_total > 0 else None
    )

    status_basis: list[str] = []
    if not cycles:
        source_of_funds_status = "UNKNOWN"
        status_basis.append("no_staker_revenue_cycles_found_in_canonical_summary")
    elif comparable_payout_total <= 0:
        source_of_funds_status = "UNKNOWN"
        status_basis.append("no_payout_outflows_in_fee_token_set_for_comparison")
    elif insufficient_coverage_tokens:
        source_of_funds_status = "UNKNOWN"
        status_basis.append(
            "fee_aligned_inflow_below_payout_for_tokens:" + ",".join(sorted(insufficient_coverage_tokens))
        )
    elif non_comparable_tokens:
        source_of_funds_status = "BOUNDED"
        status_basis.append("non_fee_token_payouts_present:" + ",".join(non_comparable_tokens))
    else:
        source_of_funds_status = "BOUNDED"
        status_basis.append("coverage_sufficient_on_fee_tokens_using_fee-aligned_token_filter_proxy")

    monthly_fee_inflow_base: dict[tuple[str, str], Decimal] = {}
    for row in base_inflows:
        month_utc = parse_month_utc(row.get("timestamp"))
        if not month_utc:
            continue
        key = (month_utc, row["token_symbol"])
        monthly_fee_inflow_base[key] = monthly_fee_inflow_base.get(key, Decimal(0)) + parse_decimal(row["amount"])

    monthly_keys = sorted(set(monthly_fee_inflow_base.keys()) | set(payout_by_month_token.keys()))
    monthly_comparison_rows = []
    for month_utc, token_symbol in monthly_keys:
        inflow = monthly_fee_inflow_base.get((month_utc, token_symbol), Decimal(0))
        payout = payout_by_month_token.get((month_utc, token_symbol), Decimal(0))
        coverage_ratio = (inflow / payout) if payout > 0 else None
        monthly_comparison_rows.append(
            {
                "month_utc": month_utc,
                "token_symbol": token_symbol,
                "fee_aligned_inflow_to_treasury_base": float(inflow),
                "staker_payout_outflow_from_treasury_base": float(payout),
                "net_fee_inflow_minus_staker_payout": float(inflow - payout),
                "coverage_ratio": float(coverage_ratio) if coverage_ratio is not None else None,
            }
        )

    write_csv(
        output_dir / "source_of_funds_monthly_comparison.csv",
        monthly_comparison_rows,
        [
            "month_utc",
            "token_symbol",
            "fee_aligned_inflow_to_treasury_base",
            "staker_payout_outflow_from_treasury_base",
            "net_fee_inflow_minus_staker_payout",
            "coverage_ratio",
        ],
    )

    payload = {
        "generated_from": snapshot_dir.as_posix(),
        "analysis_scope": {
            "treasury_address": TREASURY,
            "fee_aligned_token_set": sorted(FEE_TOKEN_SYMBOLS),
            "fee_aligned_inflow_definition": "token transfer where to == TREASURY and token_symbol in fee_aligned_token_set",
            "staker_payout_outflow_definition": (
                "staker_revenue_deposited_tokens per cycle from staker_revenue_canonical_summary "
                "(funding_to_distributor transfer amount)"
            ),
            "comparison_basis": "base-chain treasury fee-aligned inflows vs base-chain staker payout outflows",
        },
        "treasury_fee_token_flows": {
            "base": {
                "inflow_count": len(base_inflows),
                "inflow_totals_by_token": {k: float(v) for k, v in sorted(base_inflow_totals.items())},
                "outflow_count": len(base_outflows),
                "outflow_totals_by_token": {k: float(v) for k, v in sorted(base_outflow_totals.items())},
                "net_totals_by_token": {
                    token: float(base_inflow_totals.get(token, Decimal(0)) - base_outflow_totals.get(token, Decimal(0)))
                    for token in sorted(set(base_inflow_totals) | set(base_outflow_totals))
                },
            },
            "ethereum": {
                "inflow_count": len(eth_inflows),
                "inflow_totals_by_token": {k: float(v) for k, v in sorted(eth_inflow_totals.items())},
                "outflow_count": len(eth_outflows),
                "outflow_totals_by_token": {k: float(v) for k, v in sorted(eth_outflow_totals.items())},
                "net_totals_by_token": {
                    token: float(eth_inflow_totals.get(token, Decimal(0)) - eth_outflow_totals.get(token, Decimal(0)))
                    for token in sorted(set(eth_inflow_totals) | set(eth_outflow_totals))
                },
            },
        },
        "staker_payout_outflows_from_treasury": {
            "cycle_count": len(cycles),
            "totals_by_token": {k: float(v) for k, v in sorted(payout_by_token.items())},
        },
        "source_of_funds_comparison": {
            "status": source_of_funds_status,
            "status_basis": status_basis,
            "comparable_tokens": comparable_tokens,
            "non_comparable_payout_tokens": non_comparable_tokens,
            "comparable_fee_aligned_inflow_total": float(comparable_inflow_total),
            "comparable_staker_payout_outflow_total": float(comparable_payout_total),
            "comparable_coverage_ratio": float(comparable_coverage_ratio) if comparable_coverage_ratio is not None else None,
            "coverage_by_token": coverage_by_token,
            "monthly_comparison_file": "source_of_funds_monthly_comparison.csv",
            "note": (
                "BOUNDED/UNKNOWN classification reflects token-level treasury flow evidence. "
                "It does not prove campaign-exact funding lineage for every payout token."
            ),
        },
    }
    save_json(output_dir / "source_of_funds_summary.json", payload)


def build_discrepancy_tickets(
    snapshot_dir: Path,
    output_dir: Path,
    kpi_summary: dict[str, Any],
    forum_claims: list[dict[str, Any]],
) -> None:
    forum_by_label = {row["label"]: row for row in forum_claims}
    tickets: list[dict[str, Any]] = []

    lazy_window_avg_tvl = parse_decimal(kpi_summary.get("lazy_tvl_window_avg_usd"))
    if lazy_window_avg_tvl <= 0:
        lazy_window_avg_tvl = parse_decimal(kpi_summary.get("lazy_latest_tvl_usd"))
    fees_annualized = parse_decimal(kpi_summary.get("fees_derived_90d_annualized"))
    observed_fee_rate = (fees_annualized / lazy_window_avg_tvl) if lazy_window_avg_tvl > 0 else Decimal(0)
    claimed_fee_rate = Decimal("0.0066")
    fee_delta = observed_fee_rate - claimed_fee_rate
    fee_delta_abs = abs(fee_delta)
    fee_status = "OPEN" if fee_delta_abs >= Decimal("0.0010") else "RESOLVED"
    fee_severity = "HIGH" if fee_delta_abs >= Decimal("0.0025") else ("MEDIUM" if fee_delta_abs >= Decimal("0.0010") else "LOW")
    fee_window_days = int(kpi_summary.get("fees_window_days") or 0)
    fee_window_start = kpi_summary.get("fees_window_start_date")
    fee_window_end = kpi_summary.get("fees_window_end_date")
    tvl_window_points = int(kpi_summary.get("lazy_tvl_window_points") or 0)
    formula_note = (
        "Formula: observed = fees_derived_90d_annualized / lazy_tvl_window_avg_usd, "
        "where fees_derived_90d_annualized = fees_derived_90d * (365 / days_in_window). "
        f"Window: {fee_window_start} to {fee_window_end} ({fee_window_days} fee days, {tvl_window_points} TVL points)."
    )
    tickets.append(
        {
            "ticket_id": "FEE-RATE-001",
            "category": "fee_reconciliation",
            "severity": fee_severity,
            "status": fee_status,
            "label": "aggregate",
            "title": "Realized annualized fee rate deviates from claimed 0.66%",
            "expected": float(claimed_fee_rate),
            "observed": float(observed_fee_rate),
            "delta_abs": float(fee_delta_abs),
            "delta_pct_of_expected": float((fee_delta_abs / claimed_fee_rate) * Decimal(100)) if claimed_fee_rate > 0 else None,
            "evidence_files": "kpi_summary.json;defillama_fees_dailyFees_lazy_summer.json;defillama_protocol_lazy_summer.json",
            "note": formula_note,
        }
    )

    sip313_summary_path = output_dir / "payout_chain_sip3_13_summary.json"
    sip3131_summary_path = output_dir / "payout_chain_sip3_13_1_summary.json"
    attribution_summary_path = output_dir / "payout_attribution_summary.json"

    if sip313_summary_path.exists() and "SIP3.13" in forum_by_label:
        sip313_summary = load_json(sip313_summary_path)
        forum_transfer = parse_decimal(forum_by_label["SIP3.13"]["treasury_transfer_usdc"])
        onchain_transfer = parse_decimal(sip313_summary["funding_to_distributor_usdc"]) + parse_decimal(
            sip313_summary["funding_to_merkl_fee_recipient_usdc"]
        )
        delta = onchain_transfer - forum_transfer
        delta_abs = abs(delta)
        tickets.append(
            {
                "ticket_id": "PAYOUT-ROUTING-001",
                "category": "payout_routing",
                "severity": "LOW" if delta_abs <= Decimal("0.000001") else "MEDIUM",
                "status": "RESOLVED" if delta_abs <= Decimal("0.000001") else "OPEN",
                "label": "SIP3.13",
                "title": "Forum treasury transfer vs on-chain routed amount",
                "expected": float(forum_transfer),
                "observed": float(onchain_transfer),
                "delta_abs": float(delta_abs),
                "delta_pct_of_expected": float((delta_abs / forum_transfer) * Decimal(100)) if forum_transfer > 0 else None,
                "evidence_files": "forum_payout_claims.csv;payout_chain_sip3_13_summary.json",
                "note": "On-chain observed = funding_to_distributor + funding_to_merkl_fee_recipient.",
            }
        )

    if sip3131_summary_path.exists() and "SIP3.13.1" in forum_by_label:
        sip3131_summary = load_json(sip3131_summary_path)
        forum_transfer = parse_decimal(forum_by_label["SIP3.13.1"]["treasury_transfer_usdc"])
        usdc_to_lvusdc = sum(
            parse_decimal(row["amount"])
            for row in sip3131_summary.get("usdc_funding_transfers") or []
            if normalize_addr(row.get("from")) == TREASURY and normalize_addr(row.get("to")) == LVUSDC_TOKEN
        )
        delta = usdc_to_lvusdc - forum_transfer
        delta_abs = abs(delta)
        tickets.append(
            {
                "ticket_id": "PAYOUT-ROUTING-002",
                "category": "payout_routing",
                "severity": "MEDIUM" if delta_abs > Decimal("1") else "LOW",
                "status": "OPEN" if delta_abs > Decimal("0.000001") else "RESOLVED",
                "label": "SIP3.13.1",
                "title": "Forum treasury transfer vs on-chain USDC routed into LVUSDC path",
                "expected": float(forum_transfer),
                "observed": float(usdc_to_lvusdc),
                "delta_abs": float(delta_abs),
                "delta_pct_of_expected": float((delta_abs / forum_transfer) * Decimal(100)) if forum_transfer > 0 else None,
                "evidence_files": "forum_payout_claims.csv;payout_chain_sip3_13_1_summary.json",
                "note": "Observed value uses treasury->LVUSDC USDC transfer in execute transaction.",
            }
        )

    if attribution_summary_path.exists():
        attribution = load_json(attribution_summary_path)
        for campaign in attribution.get("campaigns") or []:
            label = campaign.get("label")
            prior_count = int(campaign.get("prior_same_token_funding_count") or 0)
            claim_events = int(campaign.get("claim_events_considered") or 0)
            deposited = parse_decimal(campaign.get("staker_revenue_deposited_tokens"))
            residual = parse_decimal(campaign.get("staker_revenue_unclaimed_tokens_residual"))

            if prior_count > 0:
                tickets.append(
                    {
                        "ticket_id": f"PAYOUT-ATTRIB-OVERLAP-{label}",
                        "category": "payout_routing",
                        "severity": "MEDIUM",
                        "status": "OPEN",
                        "label": label,
                        "title": "Same-token prior funding overlap limits campaign attribution confidence",
                        "expected": 0.0,
                        "observed": float(prior_count),
                        "delta_abs": float(prior_count),
                        "delta_pct_of_expected": None,
                        "evidence_files": "payout_attribution_summary.json;base_treasury_fee_token_outflows.csv",
                        "note": "Prior same-token funding creates attribution overlap in Claimed-event windows.",
                    }
                )

            if deposited > 0 and claim_events == 0:
                tickets.append(
                    {
                        "ticket_id": f"PAYOUT-ATTRIB-CLAIMS-{label}",
                        "category": "payout_routing",
                        "severity": "HIGH",
                        "status": "OPEN",
                        "label": label,
                        "title": "Funded campaign has no observed reward-token claims",
                        "expected": float(deposited),
                        "observed": 0.0,
                        "delta_abs": float(deposited),
                        "delta_pct_of_expected": 100.0,
                        "evidence_files": "payout_attribution_summary.json;base_rpc_distributor_claimed_*",
                        "note": f"Residual unclaimed amount currently {float(residual)} in reward-token units.",
                    }
                )

    severity_counts: dict[str, int] = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    status_counts: dict[str, int] = {"OPEN": 0, "RESOLVED": 0}
    for ticket in tickets:
        severity_counts[ticket["severity"]] = severity_counts.get(ticket["severity"], 0) + 1
        status_counts[ticket["status"]] = status_counts.get(ticket["status"], 0) + 1

    save_json(
        output_dir / "discrepancy_tickets.json",
        {
            "generated_from": snapshot_dir.as_posix(),
            "summary": {
                "ticket_count": len(tickets),
                "severity_counts": severity_counts,
                "status_counts": status_counts,
            },
            "tickets": tickets,
        },
    )

    write_csv(
        output_dir / "discrepancy_tickets.csv",
        tickets,
        [
            "ticket_id",
            "category",
            "severity",
            "status",
            "label",
            "title",
            "expected",
            "observed",
            "delta_abs",
            "delta_pct_of_expected",
            "evidence_files",
            "note",
        ],
    )


def load_lvusdc_nav_snapshot(snapshot_dir: Path) -> tuple[Path | None, dict[str, Any], dict[int, Decimal]]:
    candidates = [
        snapshot_dir / "base_rpc_lvusdc_convertToAssets_latest.json",
        snapshot_dir / "base_rpc_lvusdc_convertToAssets_41932733_latest.json",
    ]
    for path in sorted(snapshot_dir.glob("base_rpc_lvusdc_convertToAssets_*_latest.json")):
        candidates.append(path)

    chosen_path: Path | None = None
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.exists():
            chosen_path = candidate
            break

    if chosen_path is None:
        return None, {}, {}

    payload = load_json(chosen_path)
    nav_by_block: dict[int, Decimal] = {}
    for row in payload.get("snapshots") or []:
        block_number = row.get("block_number")
        if block_number is None:
            continue
        value = row.get("assets_per_lvusdc")
        if value is None:
            value = row.get("usdc_per_lvusdc")
        if value is None:
            continue
        nav_by_block[int(block_number)] = parse_decimal(value)

    return chosen_path, payload, nav_by_block


def resolve_nav_for_block(nav_by_block: dict[int, Decimal], target_block: int) -> dict[str, Any]:
    if not nav_by_block:
        return {"nav": None, "source_block": None, "lookup_mode": "unavailable"}

    if target_block in nav_by_block:
        return {"nav": nav_by_block[target_block], "source_block": target_block, "lookup_mode": "exact"}

    lower = [block for block in nav_by_block if block <= target_block]
    if lower:
        source_block = max(lower)
        return {"nav": nav_by_block[source_block], "source_block": source_block, "lookup_mode": "nearest_prior"}

    higher = [block for block in nav_by_block if block >= target_block]
    if higher:
        source_block = min(higher)
        return {"nav": nav_by_block[source_block], "source_block": source_block, "lookup_mode": "nearest_next"}

    return {"nav": None, "source_block": None, "lookup_mode": "unavailable"}


def build_emissions_vs_revenue_decomposition(snapshot_dir: Path, output_dir: Path) -> None:
    reward_added_path = output_dir / "grm_rewardAdded_events.csv"
    canonical_path = output_dir / "staker_revenue_canonical_summary.json"
    attribution_path = output_dir / "payout_attribution_summary.json"

    if not reward_added_path.exists() or not canonical_path.exists() or not attribution_path.exists():
        return

    reward_rows = read_csv_rows(reward_added_path)
    emissions_total_raw = sum(parse_decimal(row.get("reward_raw")) for row in reward_rows)

    sumr_decimals = 18
    sumr_supply_path = output_dir / "sumr_supply_snapshot.json"
    if sumr_supply_path.exists():
        sumr_supply = load_json(sumr_supply_path)
        sumr_decimals = int(sumr_supply.get("decimals") or 18)
    emissions_total_sumr = emissions_total_raw / (Decimal(10) ** sumr_decimals)

    reward_block_numbers = [int(row["block_number"]) for row in reward_rows] if reward_rows else []
    emissions_block_min = min(reward_block_numbers) if reward_block_numbers else None
    emissions_block_max = max(reward_block_numbers) if reward_block_numbers else None

    canonical = load_json(canonical_path)
    cycles = canonical.get("cycles") or []
    reward_token_totals = canonical.get("aggregate", {}).get("reward_token_totals", []) or []
    token_totals_map = {row["reward_token_symbol"]: row for row in reward_token_totals}

    usdc_totals = token_totals_map.get("USDC", {})
    lvusdc_totals = token_totals_map.get("LVUSDC", {})

    revenue_usdc_deposited = parse_decimal(usdc_totals.get("staker_revenue_deposited_tokens"))
    revenue_usdc_claimed_attributed = parse_decimal(usdc_totals.get("staker_revenue_claimed_tokens_attributed"))
    revenue_usdc_unclaimed = parse_decimal(usdc_totals.get("staker_revenue_unclaimed_tokens_residual"))

    revenue_lvusdc_deposited = parse_decimal(lvusdc_totals.get("staker_revenue_deposited_tokens"))
    revenue_lvusdc_claimed_attributed = parse_decimal(lvusdc_totals.get("staker_revenue_claimed_tokens_attributed"))
    revenue_lvusdc_unclaimed = parse_decimal(lvusdc_totals.get("staker_revenue_unclaimed_tokens_residual"))

    lvusdc_nav_path, lvusdc_nav_payload, lvusdc_nav_by_block = load_lvusdc_nav_snapshot(snapshot_dir)
    lvusdc_cycles = [cycle for cycle in cycles if str(cycle.get("reward_token_symbol") or "").upper() == "LVUSDC"]
    observation_block = None
    if lvusdc_nav_payload.get("observation_block") is not None:
        observation_block = int(lvusdc_nav_payload.get("observation_block"))
    elif lvusdc_nav_by_block:
        observation_block = max(lvusdc_nav_by_block.keys())

    deposited_any = False
    deposited_available = True
    deposited_value_usdc = Decimal(0)
    deposited_details: list[dict[str, Any]] = []
    deposited_source_blocks: set[int] = set()

    claimed_any = False
    claimed_available = True
    claimed_value_usdc = Decimal(0)
    claimed_details: list[dict[str, Any]] = []
    claimed_source_blocks: set[int] = set()

    unclaimed_any = False
    unclaimed_available = True
    unclaimed_value_usdc = Decimal(0)
    unclaimed_details: list[dict[str, Any]] = []
    unclaimed_source_blocks: set[int] = set()

    for cycle in lvusdc_cycles:
        label = str(cycle.get("label") or "")
        execute_block = int(cycle.get("governor_execute_block") or cycle.get("claim_window_start_block") or 0)
        deposited_tokens = parse_decimal(cycle.get("staker_revenue_deposited_tokens"))
        claimed_attributed_tokens = parse_decimal(cycle.get("staker_revenue_claimed_tokens_attributed"))
        unclaimed_tokens = parse_decimal(cycle.get("staker_revenue_unclaimed_tokens_residual"))

        if deposited_tokens > 0:
            deposited_any = True
            nav_ref = resolve_nav_for_block(lvusdc_nav_by_block, execute_block)
            nav_value = nav_ref["nav"]
            cycle_value = None
            if nav_value is None:
                deposited_available = False
            else:
                cycle_value = deposited_tokens * nav_value
                deposited_value_usdc += cycle_value
                if nav_ref["source_block"] is not None:
                    deposited_source_blocks.add(int(nav_ref["source_block"]))
            deposited_details.append(
                {
                    "label": label,
                    "lvusdc_tokens": float(deposited_tokens),
                    "valuation_block": execute_block,
                    "nav_source_block": nav_ref["source_block"],
                    "nav_lookup_mode": nav_ref["lookup_mode"],
                    "usdc_per_lvusdc": float(nav_value) if nav_value is not None else None,
                    "usdc_equivalent": float(cycle_value) if cycle_value is not None else None,
                }
            )

        if claimed_attributed_tokens > 0:
            claimed_any = True
            slug = campaign_label_to_slug(label)
            claim_file = output_dir / f"payout_attribution_{slug}_claim_events.csv"
            claim_rows = read_csv_rows(claim_file) if claim_file.exists() else []
            claim_rows.sort(key=lambda row: (int(row.get("block_number") or 0), int(row.get("log_index") or 0)))
            remaining = claimed_attributed_tokens
            valued_tokens = Decimal(0)
            cycle_value = Decimal(0)
            nav_blocks_used: set[int] = set()
            missing_nav_blocks: list[int] = []
            lookup_modes: set[str] = set()
            for row in claim_rows:
                if remaining <= 0:
                    break
                amount_tokens = parse_decimal(row.get("amount_tokens"))
                if amount_tokens <= 0:
                    continue
                allocated = amount_tokens if amount_tokens <= remaining else remaining
                claim_block = int(row.get("block_number") or 0)
                nav_ref = resolve_nav_for_block(lvusdc_nav_by_block, claim_block)
                lookup_modes.add(str(nav_ref["lookup_mode"]))
                nav_value = nav_ref["nav"]
                if nav_value is None:
                    claimed_available = False
                    missing_nav_blocks.append(claim_block)
                else:
                    claim_value = allocated * nav_value
                    cycle_value += claim_value
                    valued_tokens += allocated
                    if nav_ref["source_block"] is not None:
                        nav_blocks_used.add(int(nav_ref["source_block"]))
                        claimed_source_blocks.add(int(nav_ref["source_block"]))
                remaining -= allocated

            if remaining > Decimal("0.0000001"):
                claimed_available = False

            claimed_value_usdc += cycle_value
            claimed_details.append(
                {
                    "label": label,
                    "valuation_method": "claim-event block convertToAssets with sequential attribution cap allocation",
                    "attributed_claim_tokens_target": float(claimed_attributed_tokens),
                    "attributed_claim_tokens_valued": float(valued_tokens),
                    "attributed_claim_tokens_unvalued": float(claimed_attributed_tokens - valued_tokens),
                    "claim_events_file": claim_file.name if claim_file.exists() else None,
                    "claim_events_count": len(claim_rows),
                    "nav_source_blocks": sorted(nav_blocks_used),
                    "nav_lookup_modes": sorted(lookup_modes),
                    "missing_nav_blocks": sorted(set(missing_nav_blocks)),
                    "usdc_equivalent": float(cycle_value),
                }
            )

        if unclaimed_tokens > 0:
            unclaimed_any = True
            valuation_block = observation_block if observation_block is not None else execute_block
            nav_ref = resolve_nav_for_block(lvusdc_nav_by_block, valuation_block)
            nav_value = nav_ref["nav"]
            cycle_value = None
            if nav_value is None:
                unclaimed_available = False
            else:
                cycle_value = unclaimed_tokens * nav_value
                unclaimed_value_usdc += cycle_value
                if nav_ref["source_block"] is not None:
                    unclaimed_source_blocks.add(int(nav_ref["source_block"]))
            unclaimed_details.append(
                {
                    "label": label,
                    "lvusdc_tokens": float(unclaimed_tokens),
                    "valuation_block": valuation_block,
                    "nav_source_block": nav_ref["source_block"],
                    "nav_lookup_mode": nav_ref["lookup_mode"],
                    "usdc_per_lvusdc": float(nav_value) if nav_value is not None else None,
                    "usdc_equivalent": float(cycle_value) if cycle_value is not None else None,
                }
            )

    lvusdc_segment_values: dict[str, float | None] = {
        "deposited": 0.0,
        "claimed_attributed": 0.0,
        "unclaimed_residual": 0.0,
    }
    if deposited_any:
        lvusdc_segment_values["deposited"] = float(deposited_value_usdc) if deposited_available else None
    if claimed_any:
        lvusdc_segment_values["claimed_attributed"] = float(claimed_value_usdc) if claimed_available else None
    if unclaimed_any:
        lvusdc_segment_values["unclaimed_residual"] = float(unclaimed_value_usdc) if unclaimed_available else None

    revenue_usdc_equivalent: dict[str, Any] = {
        "deposited": float(revenue_usdc_deposited),
        "claimed_attributed": float(revenue_usdc_claimed_attributed),
        "unclaimed_residual": float(revenue_usdc_unclaimed),
    }
    for segment, usdc_native in [
        ("deposited", revenue_usdc_deposited),
        ("claimed_attributed", revenue_usdc_claimed_attributed),
        ("unclaimed_residual", revenue_usdc_unclaimed),
    ]:
        lv_component = lvusdc_segment_values[segment]
        if lv_component is None:
            revenue_usdc_equivalent[segment] = None
        else:
            revenue_usdc_equivalent[segment] = float(usdc_native + Decimal(str(lv_component)))

    attribution = load_json(attribution_path)
    claim_window_starts = [int(c["claim_window_start_block"]) for c in attribution.get("campaigns") or [] if c.get("claim_window_start_block") is not None]
    claim_window_ends = [int(c["claim_window_end_block"]) for c in attribution.get("campaigns") or [] if c.get("claim_window_end_block") is not None]
    analysis_start_block = min(claim_window_starts) if claim_window_starts else None
    analysis_end_block = max(claim_window_ends) if claim_window_ends else (max(claim_window_starts) if claim_window_starts else None)

    emissions_events_in_analysis_window = 0
    if analysis_start_block is not None and analysis_end_block is not None:
        emissions_events_in_analysis_window = sum(
            1 for b in reward_block_numbers if analysis_start_block <= b <= analysis_end_block
        )

    break_even_sumr_price = None
    revenue_deposited_usdc_equiv = revenue_usdc_equivalent.get("deposited")
    if revenue_deposited_usdc_equiv is not None and emissions_total_sumr > 0:
        break_even_sumr_price = float(Decimal(str(revenue_deposited_usdc_equiv)) / emissions_total_sumr)

    payload = {
        "generated_from": snapshot_dir.as_posix(),
        "inputs": {
            "reward_added_events_file": reward_added_path.name,
            "canonical_revenue_file": canonical_path.name,
            "attribution_summary_file": attribution_path.name,
            "lvusdc_nav_snapshot_file": lvusdc_nav_path.name if lvusdc_nav_path is not None else None,
        },
        "emissions_component": {
            "event_count": len(reward_rows),
            "reward_token": "SUMR",
            "total_raw": str(int(emissions_total_raw)),
            "decimals": sumr_decimals,
            "total_sumr_tokens": float(emissions_total_sumr),
            "block_min": emissions_block_min,
            "block_max": emissions_block_max,
        },
        "revenue_component_token_native": {
            "USDC": {
                "deposited": float(revenue_usdc_deposited),
                "claimed_attributed": float(revenue_usdc_claimed_attributed),
                "unclaimed_residual": float(revenue_usdc_unclaimed),
            },
            "LVUSDC": {
                "deposited": float(revenue_lvusdc_deposited),
                "claimed_attributed": float(revenue_lvusdc_claimed_attributed),
                "unclaimed_residual": float(revenue_lvusdc_unclaimed),
            },
        },
        "lvusdc_nav_convertToAssets": {
            "snapshot_available": bool(lvusdc_nav_by_block),
            "source_file": lvusdc_nav_path.name if lvusdc_nav_path is not None else None,
            "method": "convertToAssets(1 LVUSDC) via historical eth_call",
            "shares_input_raw": lvusdc_nav_payload.get("shares_input_raw"),
            "asset_address": lvusdc_nav_payload.get("asset_address"),
            "lvusdc_decimals": lvusdc_nav_payload.get("lvusdc_decimals"),
            "asset_decimals": lvusdc_nav_payload.get("asset_decimals"),
            "funding_execute_block": lvusdc_nav_payload.get("funding_execute_block"),
            "observation_block": observation_block,
            "snapshot_count": len(lvusdc_nav_by_block),
            "block_min": min(lvusdc_nav_by_block.keys()) if lvusdc_nav_by_block else None,
            "block_max": max(lvusdc_nav_by_block.keys()) if lvusdc_nav_by_block else None,
            "summary": lvusdc_nav_payload.get("summary"),
        },
        "lvusdc_usdc_equivalent_valuation": {
            "method_version": "lvusdc_convertToAssets_block_level_v1",
            "segment_methods": {
                "deposited": "sum(cycle deposited LVUSDC * convertToAssets at governor_execute_block)",
                "claimed_attributed": "sum(attributed claim LVUSDC * convertToAssets at each claim event block)",
                "unclaimed_residual": "sum(cycle unclaimed LVUSDC residual * convertToAssets at observation block)",
            },
            "segments": {
                "deposited": {
                    "lvusdc_tokens_total": float(revenue_lvusdc_deposited),
                    "usdc_equivalent_total": lvusdc_segment_values["deposited"],
                    "nav_source_blocks": sorted(deposited_source_blocks),
                    "details": deposited_details,
                },
                "claimed_attributed": {
                    "lvusdc_tokens_total": float(revenue_lvusdc_claimed_attributed),
                    "usdc_equivalent_total": lvusdc_segment_values["claimed_attributed"],
                    "nav_source_blocks": sorted(claimed_source_blocks),
                    "details": claimed_details,
                },
                "unclaimed_residual": {
                    "lvusdc_tokens_total": float(revenue_lvusdc_unclaimed),
                    "usdc_equivalent_total": lvusdc_segment_values["unclaimed_residual"],
                    "nav_source_blocks": sorted(unclaimed_source_blocks),
                    "details": unclaimed_details,
                },
            },
        },
        "revenue_component_usdc_equivalent": revenue_usdc_equivalent,
        "window_comparability": {
            "campaign_analysis_start_block": analysis_start_block,
            "campaign_analysis_end_block": analysis_end_block,
            "emissions_events_in_campaign_window": emissions_events_in_analysis_window,
            "note": (
                "Emissions-vs-revenue comparability depends on overlapping windows. "
                "Current emissions events may sit outside payout campaign windows."
            ),
        },
        "usd_decomposition_formula": {
            "emissions_usd_formula": "emissions_sumr_tokens * sumr_price_usd",
            "revenue_usd_equivalent_basis": "USDC direct + LVUSDC valued by convertToAssets at segment-specific historical blocks",
            "break_even_sumr_price_for_emissions_equal_revenue_deposited": break_even_sumr_price,
        },
        "limitations": [
            "SUMR USD valuation is formula-based unless an external price snapshot is pinned.",
            "LVUSDC valuation is bounded by available NAV snapshots and attribution model assumptions.",
        ],
    }
    save_json(output_dir / "emissions_vs_revenue_decomposition.json", payload)

    table_rows = [
        {"metric": "emissions_total_sumr_tokens", "value": float(emissions_total_sumr), "unit": "SUMR", "notes": "From GRM RewardAdded events"},
        {
            "metric": "revenue_deposited_usdc_equivalent",
            "value": revenue_usdc_equivalent["deposited"],
            "unit": "USD-equivalent",
            "notes": "USDC direct + LVUSDC valued via convertToAssets at segment blocks",
        },
        {
            "metric": "revenue_claimed_attributed_usdc_equivalent",
            "value": revenue_usdc_equivalent["claimed_attributed"],
            "unit": "USD-equivalent",
            "notes": "Attributed claimed component only",
        },
        {
            "metric": "revenue_unclaimed_residual_usdc_equivalent",
            "value": revenue_usdc_equivalent["unclaimed_residual"],
            "unit": "USD-equivalent",
            "notes": "Unclaimed residual component",
        },
        {
            "metric": "break_even_sumr_price_for_emissions_equal_revenue_deposited",
            "value": break_even_sumr_price,
            "unit": "USD/SUMR",
            "notes": "Formula-based threshold; no external price feed required",
        },
    ]
    write_csv(
        output_dir / "emissions_vs_revenue_decomposition_table.csv",
        table_rows,
        ["metric", "value", "unit", "notes"],
    )


def write_readme(output_dir: Path, snapshot_dir: Path) -> None:
    text = f"""# Evidence Tables ({snapshot_dir.name})

Generated deterministically from JSON snapshots in `{snapshot_dir.as_posix()}`.

- `kpi_summary.json`: DeFiLlama-derived TVL/fees snapshot metrics.
- `defillama_context_summary.json`: scope separation and chain coverage context.
- `grm_rewardAdded_events.csv`: RewardAdded logs for GovernanceRewardsManager V2 (topic-filtered).
- `base_treasury_fee_token_inflows.csv`: Base treasury inflows for USDC/EURC/USDT/WETH.
- `base_treasury_fee_token_outflows.csv`: Base treasury outflows for USDC/EURC/USDT/WETH.
- `eth_treasury_fee_token_inflows.csv`: Ethereum treasury inflows for USDC/EURC/USDT/WETH.
- `eth_treasury_fee_token_outflows.csv`: Ethereum treasury outflows for USDC/EURC/USDT/WETH.
- `treasury_fee_token_net_flow_monthly.csv`: monthly inflow/outflow/net by chain and token.
- `treasury_flow_summary.json`: inflow/outflow totals by chain and token.
- `forum_payout_claims.csv`: SIP3.13 and SIP3.13.1 payout/revenue claims parsed from forum JSON.
- `*_method_counts.csv`: TipJar tx method counts per chain from Blockscout snapshots.
- `payout_chain_sip3_13_summary.json`: decoded proposal execution, receipt-based campaign reconstruction, claimant settlements, and canonical deposited/claimed/unclaimed revenue metrics for SIP3.13.
- `payout_chain_sip3_13_1_summary.json`: decoded proposal execution, receipt-based campaign reconstruction, post-execution claim status, and canonical deposited/claimed/unclaimed revenue metrics for SIP3.13.1.
- `payout_attribution_summary.json`: campaign attribution metrics including canonical deposited/claimed/unclaimed values and attribution confidence class.
- `payout_attribution_cycle_table.csv`: cycle-level attribution table with confidence class and residual per campaign.
- `staker_revenue_canonical_summary.json`: canonical deposited/claimed/unclaimed staker revenue aggregates by cycle and token.
- `source_of_funds_monthly_comparison.csv`: monthly fee-aligned inflow vs staker payout outflow comparison (base treasury).
- `source_of_funds_summary.json`: source-of-funds status (`PROVEN`/`BOUNDED`/`UNKNOWN`) with explicit basis and token-level coverage.
- `payout_attribution_gate.json`: scenario-readiness gate based on confidence class and residual threshold.
- `payout_attribution_*_claim_events.csv`: claimant-flow events considered by the attribution model.
- `discrepancy_tickets.json` / `discrepancy_tickets.csv`: machine-readable reconciliation discrepancies (fee + payout routing).
- `emissions_vs_revenue_decomposition.json` / `emissions_vs_revenue_decomposition_table.csv`: emissions-vs-revenue decomposition with on-chain formula basis and comparability notes.
"""
    (output_dir / "README.md").write_text(text, encoding="utf-8")


def run(snapshot_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    kpi_summary = build_kpi_summary(snapshot_dir)
    save_json(output_dir / "kpi_summary.json", kpi_summary)

    context_summary = build_defillama_context(snapshot_dir)
    save_json(output_dir / "defillama_context_summary.json", context_summary)

    base_tipjar_path = pick_existing(
        snapshot_dir,
        ["base_blockscout_tipjar_txs_all.json", "base_blockscout_tipjar_base_txs.json"],
    )
    arb_tipjar_path = pick_existing(
        snapshot_dir,
        ["arb_blockscout_tipjar_txs_all.json", "arb_blockscout_tipjar_arb_txs.json"],
    )
    eth_tipjar_path = pick_existing(
        snapshot_dir,
        ["eth_blockscout_tipjar_txs_all.json", "eth_blockscout_tipjar_eth_txs.json"],
    )

    tipjar_rows = []
    for chain, path in [
        ("base_tipjar", base_tipjar_path),
        ("arbitrum_tipjar", arb_tipjar_path),
        ("ethereum_tipjar", eth_tipjar_path),
    ]:
        chain_rows = parse_tipjar_methods(get_items(load_json(path)), chain)
        tipjar_rows.extend(chain_rows)
        write_csv(output_dir / f"{chain.replace('_tipjar', '')}_tipjar_method_counts.csv", chain_rows, ["chain", "method", "count"])
    save_json(output_dir / "tipjar_method_counts_combined.json", tipjar_rows)

    base_treasury = load_json(snapshot_dir / "base_blockscout_treasury_token_transfers_all.json")
    eth_treasury = load_json(snapshot_dir / "eth_blockscout_treasury_token_transfers_all.json")
    foundation = load_json(snapshot_dir / "base_blockscout_foundation_tipstream_token_transfers_all.json")

    base_inflows = extract_inflow_rows(base_treasury, TREASURY, FEE_TOKEN_SYMBOLS, include_name=True)
    base_outflows = extract_outflow_rows(base_treasury, TREASURY, FEE_TOKEN_SYMBOLS, include_name=True)
    eth_inflows = extract_inflow_rows(eth_treasury, TREASURY, FEE_TOKEN_SYMBOLS, include_name=True)
    eth_outflows = extract_outflow_rows(eth_treasury, TREASURY, FEE_TOKEN_SYMBOLS, include_name=True)
    foundation_outflows = extract_outflow_rows(foundation, FOUNDATION_TIPSTREAM, FEE_TOKEN_SYMBOLS, include_name=False)

    write_csv(
        output_dir / "base_treasury_fee_token_inflows.csv",
        base_inflows,
        ["block_number", "timestamp", "tx_hash", "token_symbol", "token_name", "raw_value", "amount", "from_address"],
    )
    write_csv(
        output_dir / "base_treasury_fee_token_outflows.csv",
        base_outflows,
        ["block_number", "timestamp", "tx_hash", "token_symbol", "token_name", "raw_value", "amount", "to_address"],
    )
    write_csv(
        output_dir / "eth_treasury_fee_token_inflows.csv",
        eth_inflows,
        ["block_number", "timestamp", "tx_hash", "token_symbol", "token_name", "raw_value", "amount", "from_address"],
    )
    write_csv(
        output_dir / "eth_treasury_fee_token_outflows.csv",
        eth_outflows,
        ["block_number", "timestamp", "tx_hash", "token_symbol", "token_name", "raw_value", "amount", "to_address"],
    )
    write_csv(
        output_dir / "base_foundation_tipstream_fee_token_outflows.csv",
        foundation_outflows,
        ["block_number", "timestamp", "tx_hash", "token_symbol", "raw_value", "amount", "to_address"],
    )
    monthly_net_rows = build_monthly_net_flow_rows("base", base_inflows, base_outflows)
    monthly_net_rows.extend(build_monthly_net_flow_rows("ethereum", eth_inflows, eth_outflows))
    write_csv(
        output_dir / "treasury_fee_token_net_flow_monthly.csv",
        monthly_net_rows,
        [
            "chain",
            "month_utc",
            "token_symbol",
            "inflow_count",
            "inflow_amount",
            "outflow_count",
            "outflow_amount",
            "net_amount",
        ],
    )
    save_json(
        output_dir / "treasury_outflow_summary.json",
        {
            "base_outflow_count": len(base_outflows),
            "base_totals": summarize_token_totals(base_outflows),
            "eth_outflow_count": len(eth_outflows),
            "eth_totals": summarize_token_totals(eth_outflows),
        },
    )
    save_json(
        output_dir / "treasury_flow_summary.json",
        {
            "base_inflow_count": len(base_inflows),
            "base_inflow_totals": summarize_token_totals(base_inflows),
            "base_outflow_count": len(base_outflows),
            "base_outflow_totals": summarize_token_totals(base_outflows),
            "eth_inflow_count": len(eth_inflows),
            "eth_inflow_totals": summarize_token_totals(eth_inflows),
            "eth_outflow_count": len(eth_outflows),
            "eth_outflow_totals": summarize_token_totals(eth_outflows),
            "monthly_net_flow_file": "treasury_fee_token_net_flow_monthly.csv",
        },
    )

    forum_claims, forum_ratios = build_forum_tables(snapshot_dir)
    write_csv(
        output_dir / "forum_payout_claims.csv",
        forum_claims,
        ["label", "topic_id", "title", "url", "protocol_revenue_usd", "staker_payout_usdc", "treasury_transfer_usdc"],
    )
    write_csv(
        output_dir / "forum_payout_ratios.csv",
        forum_ratios,
        ["label", "protocol_revenue_usd", "staker_payout_usdc", "staker_share_pct", "merkl_fee_pct_of_payout"],
    )

    reward_rows = build_reward_added_rows(snapshot_dir)
    write_csv(
        output_dir / "grm_rewardAdded_events.csv",
        reward_rows,
        ["tx_hash", "block_number", "event", "reward_token", "reward_raw"],
    )

    contract_checks = build_contract_source_checks(snapshot_dir)
    save_json(output_dir / "contract_source_checks.json", contract_checks)

    sumr_supply = build_sumr_supply(snapshot_dir)
    if sumr_supply is not None:
        save_json(output_dir / "sumr_supply_snapshot.json", sumr_supply)

    sample_rows = build_sample_tx_transfer_rows(snapshot_dir)
    if sample_rows:
        write_csv(
            output_dir / "base_sample_tx_transfer_decodes.csv",
            sample_rows,
            ["tx_hash", "block_number", "log_index", "token", "token_address", "from", "to", "raw_value", "amount"],
        )

    build_payout_chain_artifacts(snapshot_dir, output_dir, forum_claims, base_treasury)
    build_source_of_funds_artifacts(
        snapshot_dir=snapshot_dir,
        output_dir=output_dir,
        base_inflows=base_inflows,
        base_outflows=base_outflows,
        eth_inflows=eth_inflows,
        eth_outflows=eth_outflows,
    )
    build_discrepancy_tickets(snapshot_dir, output_dir, kpi_summary, forum_claims)
    build_emissions_vs_revenue_decomposition(snapshot_dir, output_dir)
    write_readme(output_dir, snapshot_dir)


def main() -> None:
    default_snapshot = DATA_DIR / "snapshots" / "external_review" / "2026-02-09-independent"
    parser = argparse.ArgumentParser(description="Build deterministic evidence artifacts from frozen snapshots.")
    parser.add_argument("--snapshot-dir", type=Path, default=default_snapshot)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    snapshot_dir: Path = args.snapshot_dir
    if not snapshot_dir.exists():
        raise FileNotFoundError(f"Snapshot dir not found: {snapshot_dir}")

    output_dir = args.output_dir or (RESULTS_DIR / "proofs" / f"evidence_{snapshot_dir.name}")
    run(snapshot_dir, output_dir)
    print(f"Wrote evidence artifacts to {output_dir}")


if __name__ == "__main__":
    main()
