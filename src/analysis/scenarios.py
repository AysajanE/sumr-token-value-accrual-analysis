"""
Scenario modeling with explicit pinned-assumption provenance.

This module avoids silent hardcoded supply/price defaults by resolving assumptions
from pinned artifacts and writing an assumption register alongside scenario outputs.
"""

from __future__ import annotations

import argparse
import itertools
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import DATA_DIR, MAX_SUPPLY, RESULTS_DIR


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def parse_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal(0)
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    return Decimal(str(value))


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else (Path.cwd() / path).resolve()


def float_or_none(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def build_scenario_matrix(
    current_tvl: float,
    tvl_multipliers: list[float] | None = None,
    fee_rates: list[float] | None = None,
    staker_shares: list[float] | None = None,
    staking_ratios: list[float] | None = None,
    circ_supply: float | None = None,
    token_price: float | None = None,
) -> pd.DataFrame:
    """
    Generate scenario matrix with projected staker revenue and yields.

    `circ_supply` must be explicitly pinned (no hidden defaults).
    `token_price` may be absent; in that case yield fields are emitted as null.
    """
    if circ_supply is None or circ_supply <= 0:
        raise ValueError("circulating supply must be provided from a pinned source and be > 0")

    if tvl_multipliers is None:
        tvl_multipliers = [0.5, 1.0, 2.0, 5.0]
    if fee_rates is None:
        fee_rates = [0.0010, 0.0030, 0.0066, 0.0100]
    if staker_shares is None:
        staker_shares = [0.0, 0.10, 0.20, 0.30]
    if staking_ratios is None:
        staking_ratios = [0.10, 0.30, 0.60]

    rows: list[dict[str, Any]] = []
    for tvl_mult, fee_rate, staker_share, stake_ratio in itertools.product(
        tvl_multipliers, fee_rates, staker_shares, staking_ratios
    ):
        tvl = current_tvl * tvl_mult
        annual_fees = tvl * fee_rate
        staker_revenue = annual_fees * staker_share
        staked_sumr = circ_supply * stake_ratio

        staked_value = staked_sumr * token_price if token_price is not None else None
        mcap = circ_supply * token_price if token_price is not None else None
        fdv = MAX_SUPPLY * token_price if token_price is not None else None

        rows.append(
            {
                "tvl_usd": tvl,
                "tvl_multiplier": tvl_mult,
                "fee_rate": fee_rate,
                "staker_share": staker_share,
                "staking_ratio": stake_ratio,
                "circulating_supply_tokens": circ_supply,
                "token_price_usd": token_price,
                "annual_fees_usd": annual_fees,
                "staker_revenue_usd": staker_revenue,
                "mcap_usd": mcap,
                "fdv_usd": fdv,
                "staked_value_usd": staked_value,
                "revenue_yield_on_mcap": (staker_revenue / mcap) if mcap and mcap > 0 else None,
                "revenue_yield_on_fdv": (staker_revenue / fdv) if fdv and fdv > 0 else None,
                "revenue_yield_on_staked": (staker_revenue / staked_value) if staked_value and staked_value > 0 else None,
            }
        )

    return pd.DataFrame(rows)


def load_kpi_tvl_pin(kpi_path: Path) -> dict[str, Any]:
    payload = load_json(kpi_path)
    current_tvl = payload.get("lazy_latest_tvl_usd")
    if current_tvl is None:
        raise ValueError(f"Missing `lazy_latest_tvl_usd` in KPI artifact: {kpi_path}")
    return {
        "value": parse_decimal(current_tvl),
        "source_file": kpi_path.as_posix(),
        "as_of_utc": payload.get("as_of_utc"),
        "field": "lazy_latest_tvl_usd",
        "pinned": True,
    }


def load_supply_pin(supply_snapshot_path: Path) -> dict[str, Any]:
    payload = load_json(supply_snapshot_path)
    sumr = payload.get("sumr") or {}
    total_supply_raw = sumr.get("totalSupply_raw")
    decimals = int(sumr.get("decimals") or 18)
    if total_supply_raw is None:
        raise ValueError(f"Missing `sumr.totalSupply_raw` in supply snapshot: {supply_snapshot_path}")

    total_supply_tokens = parse_decimal(total_supply_raw) / (Decimal(10) ** decimals)
    return {
        "value": total_supply_tokens,
        "source_file": supply_snapshot_path.as_posix(),
        "as_of_block": payload.get("latest_block"),
        "field": "sumr.totalSupply_raw / 10^decimals",
        "pinned": True,
        "raw": str(total_supply_raw),
        "decimals": decimals,
    }


def load_assumption_pin_payload(assumptions_pin_path: Path) -> tuple[Path | None, dict[str, Any]]:
    if not assumptions_pin_path.exists():
        return None, {}
    return assumptions_pin_path, load_json(assumptions_pin_path)


def resolve_circulating_supply_pin(
    onchain_supply_pin: dict[str, Any],
    assumptions_pin_path: Path | None,
    assumptions_pin_payload: dict[str, Any],
) -> dict[str, Any]:
    override_value = assumptions_pin_payload.get("circ_supply_tokens")
    if override_value is None:
        return {
            "value": onchain_supply_pin["value"],
            "source_file": onchain_supply_pin.get("source_file"),
            "source_kind": "onchain_total_supply_snapshot",
            "pinned": True,
            "notes": "Derived from SUMR totalSupply snapshot.",
        }

    return {
        "value": parse_decimal(override_value),
        "source_file": assumptions_pin_path.as_posix() if assumptions_pin_path is not None else None,
        "source_kind": "manual_pin_file_override",
        "pinned": True,
        "notes": assumptions_pin_payload.get("circ_supply_notes"),
    }


def resolve_token_price_pin(
    assumptions_pin_path: Path | None,
    assumptions_pin_payload: dict[str, Any],
    token_price_usd_cli: float | None,
    token_price_source_cli: str | None,
    token_price_as_of_utc_cli: str | None,
) -> dict[str, Any]:
    if token_price_usd_cli is not None:
        return {
            "value": parse_decimal(token_price_usd_cli),
            "source_file": None,
            "source_kind": "cli_pin",
            "source_label": token_price_source_cli or "manual_cli",
            "as_of_utc": token_price_as_of_utc_cli,
            "pinned": True,
        }

    file_value = assumptions_pin_payload.get("token_price_usd")
    if file_value is None:
        return {
            "value": None,
            "source_file": assumptions_pin_path.as_posix() if assumptions_pin_path is not None else None,
            "source_kind": "missing",
            "source_label": None,
            "as_of_utc": None,
            "pinned": False,
        }

    return {
        "value": parse_decimal(file_value),
        "source_file": assumptions_pin_path.as_posix() if assumptions_pin_path is not None else None,
        "source_kind": "pin_file",
        "source_label": assumptions_pin_payload.get("token_price_source"),
        "as_of_utc": assumptions_pin_payload.get("token_price_as_of_utc"),
        "pinned": True,
    }


def scenario_status(token_price_pin: dict[str, Any]) -> tuple[str, str]:
    if token_price_pin.get("pinned"):
        return "READY_PINNED", "Supply and token price assumptions are pinned with explicit provenance."
    return (
        "PARTIAL_UNPINNED_TOKEN_PRICE",
        "Token price pin is missing. Yield-on-mcap/fdv/staked fields are null to avoid false precision.",
    )


def run(
    kpi_path: Path,
    supply_snapshot_path: Path,
    assumptions_pin_path: Path,
    output_dir: Path,
    token_price_usd_cli: float | None,
    token_price_source_cli: str | None,
    token_price_as_of_utc_cli: str | None,
) -> None:
    kpi_tvl_pin = load_kpi_tvl_pin(kpi_path)
    onchain_supply_pin = load_supply_pin(supply_snapshot_path)
    assumptions_file_path, assumptions_payload = load_assumption_pin_payload(assumptions_pin_path)

    circulating_supply_pin = resolve_circulating_supply_pin(
        onchain_supply_pin=onchain_supply_pin,
        assumptions_pin_path=assumptions_file_path,
        assumptions_pin_payload=assumptions_payload,
    )
    token_price_pin = resolve_token_price_pin(
        assumptions_pin_path=assumptions_file_path,
        assumptions_pin_payload=assumptions_payload,
        token_price_usd_cli=token_price_usd_cli,
        token_price_source_cli=token_price_source_cli,
        token_price_as_of_utc_cli=token_price_as_of_utc_cli,
    )

    current_tvl = kpi_tvl_pin["value"]
    circ_supply = circulating_supply_pin["value"]
    token_price = token_price_pin["value"]

    df = build_scenario_matrix(
        current_tvl=float(current_tvl),
        circ_supply=float(circ_supply),
        token_price=float_or_none(token_price),
    )
    records = df.where(pd.notnull(df), None).to_dict(orient="records")

    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    status, reason = scenario_status(token_price_pin)

    assumptions_register = {
        "generated_utc": now.isoformat(),
        "schema": "scenario_assumptions_register_v1",
        "status": status,
        "reason": reason,
        "inputs": {
            "kpi_path": kpi_path.as_posix(),
            "supply_snapshot_path": supply_snapshot_path.as_posix(),
            "assumptions_pin_path": assumptions_file_path.as_posix() if assumptions_file_path is not None else None,
        },
        "assumptions": {
            "current_tvl_usd": {
                "value": float(current_tvl),
                "pinned": bool(kpi_tvl_pin.get("pinned")),
                "source_file": kpi_tvl_pin.get("source_file"),
                "source_field": kpi_tvl_pin.get("field"),
                "as_of_utc": kpi_tvl_pin.get("as_of_utc"),
            },
            "circulating_supply_tokens": {
                "value": float(circ_supply),
                "pinned": bool(circulating_supply_pin.get("pinned")),
                "source_kind": circulating_supply_pin.get("source_kind"),
                "source_file": circulating_supply_pin.get("source_file"),
                "notes": circulating_supply_pin.get("notes"),
            },
            "token_price_usd": {
                "value": float_or_none(token_price),
                "pinned": bool(token_price_pin.get("pinned")),
                "source_kind": token_price_pin.get("source_kind"),
                "source_label": token_price_pin.get("source_label"),
                "source_file": token_price_pin.get("source_file"),
                "as_of_utc": token_price_pin.get("as_of_utc"),
            },
        },
    }

    scenario_payload = {
        "generated_utc": now.isoformat(),
        "schema": "scenario_matrix_v2_pinned_assumptions",
        "status": status,
        "reason": reason,
        "assumptions_file": "scenario_assumptions_latest.json",
        "dimensions": {
            "tvl_multipliers": [0.5, 1.0, 2.0, 5.0],
            "fee_rates": [0.0010, 0.0030, 0.0066, 0.0100],
            "staker_shares": [0.0, 0.10, 0.20, 0.30],
            "staking_ratios": [0.10, 0.30, 0.60],
        },
        "scenario_count": len(records),
        "scenarios": records,
    }

    assumptions_dated = output_dir / f"scenario_assumptions_{stamp}.json"
    assumptions_latest = output_dir / "scenario_assumptions_latest.json"
    scenario_dated_json = output_dir / f"scenario_matrix_{stamp}.json"
    scenario_latest_json = output_dir / "scenario_matrix_latest.json"
    scenario_dated_csv = output_dir / f"scenario_matrix_{stamp}.csv"
    scenario_latest_csv = output_dir / "scenario_matrix_latest.csv"
    scenario_latest_md = output_dir / "scenario_matrix_latest.md"

    save_json(assumptions_dated, assumptions_register)
    save_json(assumptions_latest, assumptions_register)
    save_json(scenario_dated_json, scenario_payload)
    save_json(scenario_latest_json, scenario_payload)

    output_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(scenario_dated_csv, index=False)
    df.to_csv(scenario_latest_csv, index=False)

    md = [
        "# Scenario Matrix (Pinned Assumptions)",
        "",
        f"- Generated UTC: {now.isoformat()}",
        f"- Status: {status}",
        f"- Reason: {reason}",
        f"- Current TVL (USD): {float(current_tvl):,.2f}",
        f"- Circulating supply (tokens): {float(circ_supply):,.6f}",
        f"- Token price (USD): {float_or_none(token_price)}",
        f"- Scenario rows: {len(records)}",
    ]
    scenario_latest_md.write_text("\n".join(md) + "\n", encoding="utf-8")

    print("Scenario artifacts refreshed with assumption provenance")
    print(f"Status: {status}")
    print(f"Rows written: {len(records)}")
    print(f"Assumptions file: {assumptions_latest}")
    print(f"Scenario CSV: {scenario_latest_csv}")


def main() -> None:
    default_snapshot_dir = DATA_DIR / "snapshots" / "external_review" / "2026-02-09-independent"
    default_kpi_path = RESULTS_DIR / "proofs" / "evidence_2026-02-09-independent" / "kpi_summary.json"
    default_supply_snapshot_path = default_snapshot_dir / "base_rpc_supply_and_receipts.json"
    default_assumptions_pin_path = default_snapshot_dir / "scenario_assumptions_pin.json"
    default_output_dir = RESULTS_DIR / "tables"

    parser = argparse.ArgumentParser(description="Build scenario matrix with pinned assumption provenance.")
    parser.add_argument("--kpi-path", type=Path, default=default_kpi_path)
    parser.add_argument("--supply-snapshot-path", type=Path, default=default_supply_snapshot_path)
    parser.add_argument("--assumptions-pin-path", type=Path, default=default_assumptions_pin_path)
    parser.add_argument("--output-dir", type=Path, default=default_output_dir)
    parser.add_argument("--token-price-usd", type=float, default=None)
    parser.add_argument("--token-price-source", type=str, default=None)
    parser.add_argument("--token-price-as-of-utc", type=str, default=None)
    args = parser.parse_args()

    run(
        kpi_path=resolve_path(args.kpi_path),
        supply_snapshot_path=resolve_path(args.supply_snapshot_path),
        assumptions_pin_path=resolve_path(args.assumptions_pin_path),
        output_dir=resolve_path(args.output_dir),
        token_price_usd_cli=args.token_price_usd,
        token_price_source_cli=args.token_price_source,
        token_price_as_of_utc_cli=args.token_price_as_of_utc,
    )


if __name__ == "__main__":
    main()
