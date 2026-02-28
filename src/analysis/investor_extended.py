"""
Extended investor-facing artifact builder.

This module fills previously removed scope with reproducible artifacts:
1) External peer benchmarks + macro market context snapshots.
2) Treasury operating-cost / runway model with explicit assumptions.
3) Probability-weighted scenario returns and position PnL paths.
4) On-chain staking-position distribution metrics.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd
import requests
import seaborn as sns
from web3 import Web3

from src.config import BASE_RPC_URL, DATA_DIR, PROJECT_ROOT, RESULTS_DIR


PEER_PROTOCOLS = [
    {"slug": "lazy-summer-protocol", "name": "Lazy Summer (SUMR)"},
    {"slug": "aave", "name": "Aave"},
    {"slug": "gmx", "name": "GMX"},
    {"slug": "makerdao", "name": "MakerDAO"},
    {"slug": "morpho", "name": "Morpho"},
    {"slug": "euler", "name": "Euler"},
    {"slug": "compound-finance", "name": "Compound"},
    {"slug": "maple", "name": "Maple"},
    {"slug": "yearn-finance", "name": "Yearn"},
    {"slug": "pendle", "name": "Pendle"},
]

DATA_TYPES = [
    "dailyFees",
    "dailyRevenue",
    "dailyHoldersRevenue",
    "dailyProtocolRevenue",
]

TREASURY = "0x447bf9d1485abdc4c1778025dfdfbe8b894c3796"
DISTRIBUTOR = "0x3ef3d8ba38ebe18db133cec108f4d14ce00dd9ae"
MERKL_FEE_RECIPIENT = "0xeac6a75e19beb1283352d24c0311de865a867dab"
SUMMER_STAKING = "0xca2e14c7c03c9961c296c89e2d2279f5f7db15b4"
SUMMER_STAKING_DEPLOY_BLOCK = 38595477
SUMR_TOKEN = "0x194f360d130f2393a5e9f3117a6a1b78abea1624"
REFERENCE_PRICE_USD = 0.003319

TOKEN_ADDRESSES_BASE = {
    "USDC": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
    "EURC": "0x60a3e35cc302bfa44cb288bc5a4f316fdb1adb42",
    "USDT": "0xfde4c96c8593536e31f229ea8f37b2ad57a5f6f1",
    "WETH": "0x4200000000000000000000000000000000000006",
}

STABLE_SYMBOLS = {"USDC", "EURC", "USDT"}

ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function",
    },
]


@dataclass
class CaseScenario:
    case: str
    tvl_multiplier: float
    annual_staker_revenue_lower_usd: float
    annual_staker_revenue_upper_usd: float
    yield_on_staked_lower: float
    yield_on_staked_upper: float


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_csv(path: Path, headers: list[str], rows: list[list[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)


def parse_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, str) and not value.strip():
        return 0.0
    return float(value)


def pct_change(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return (current / previous - 1.0) * 100.0


def write_versioned_json(prefix: str, payload: dict[str, Any], tables_dir: Path, stamp: str) -> None:
    save_json(tables_dir / f"{prefix}_{stamp}.json", payload)
    save_json(tables_dir / f"{prefix}_latest.json", payload)


def write_versioned_csv(prefix: str, headers: list[str], rows: list[list[Any]], tables_dir: Path, stamp: str) -> None:
    write_csv(tables_dir / f"{prefix}_{stamp}.csv", headers=headers, rows=rows)
    write_csv(tables_dir / f"{prefix}_latest.csv", headers=headers, rows=rows)


def request_json(url: str, params: dict[str, Any] | None = None, retries: int = 5, timeout: int = 60) -> Any:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(min(20, attempt * 2))
    raise RuntimeError(f"Request failed for {url}: {last_error}") from last_error


def latest_tvl_usd(protocol_payload: dict[str, Any]) -> float:
    tvl = protocol_payload.get("tvl") or []
    if not tvl:
        return 0.0
    return parse_float((tvl[-1] or {}).get("totalLiquidityUSD"))


def fetch_external_snapshots(snapshot_dir: Path) -> dict[str, Any]:
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    manifest_entries: list[dict[str, Any]] = []

    def capture(url: str, file_name: str, params: dict[str, Any] | None = None) -> None:
        payload = request_json(url, params=params)
        out = snapshot_dir / file_name
        save_json(out, payload)
        entry = {
            "file": out.name,
            "source_url": url,
        }
        if params:
            entry["params"] = params
        manifest_entries.append(entry)

    for peer in PEER_PROTOCOLS:
        slug = peer["slug"]
        capture(
            url=f"https://api.llama.fi/protocol/{slug}",
            file_name=f"peer_{slug}_protocol.json",
        )
        for data_type in DATA_TYPES:
            capture(
                url=f"https://api.llama.fi/summary/fees/{slug}",
                params={"dataType": data_type},
                file_name=f"peer_{slug}_{data_type}.json",
            )

    capture(
        url="https://api.llama.fi/overview/fees",
        params={"excludeTotalDataChart": "true", "excludeTotalDataChartBreakdown": "true", "dataType": "dailyFees"},
        file_name="overview_fees_dailyFees.json",
    )
    capture(
        url="https://api.llama.fi/overview/fees",
        params={"excludeTotalDataChart": "true", "excludeTotalDataChartBreakdown": "true", "dataType": "dailyRevenue"},
        file_name="overview_fees_dailyRevenue.json",
    )
    capture(
        url="https://api.llama.fi/overview/fees",
        params={"excludeTotalDataChart": "true", "excludeTotalDataChartBreakdown": "true", "dataType": "dailyHoldersRevenue"},
        file_name="overview_fees_dailyHoldersRevenue.json",
    )
    capture(
        url="https://api.llama.fi/overview/fees",
        params={"excludeTotalDataChart": "true", "excludeTotalDataChartBreakdown": "true", "dataType": "dailyProtocolRevenue"},
        file_name="overview_fees_dailyProtocolRevenue.json",
    )
    capture(
        url="https://api.llama.fi/protocols",
        file_name="protocols_all.json",
    )
    capture(
        url="https://coins.llama.fi/prices/current/base:0x4200000000000000000000000000000000000006",
        file_name="price_base_weth.json",
    )

    manifest = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot_dir": snapshot_dir.as_posix(),
        "sources": manifest_entries,
    }
    save_json(snapshot_dir / "manifest.json", manifest)
    return manifest


def build_peer_benchmarks(snapshot_dir: Path, tables_dir: Path, charts_dir: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for peer in PEER_PROTOCOLS:
        slug = peer["slug"]
        protocol = load_json(snapshot_dir / f"peer_{slug}_protocol.json")
        fees = load_json(snapshot_dir / f"peer_{slug}_dailyFees.json")
        revenue = load_json(snapshot_dir / f"peer_{slug}_dailyRevenue.json")
        holders = load_json(snapshot_dir / f"peer_{slug}_dailyHoldersRevenue.json")
        protocol_revenue = load_json(snapshot_dir / f"peer_{slug}_dailyProtocolRevenue.json")

        latest_tvl = latest_tvl_usd(protocol)
        fees_30d = parse_float(fees.get("total30d"))
        revenue_30d = parse_float(revenue.get("total30d"))
        holders_30d = parse_float(holders.get("total30d"))
        protocol_rev_30d = parse_float(protocol_revenue.get("total30d"))
        annualization = 365.0 / 30.0

        fee_rate = (fees_30d * annualization / latest_tvl) if latest_tvl > 0 else 0.0
        holders_yield_tvl = (holders_30d * annualization / latest_tvl) if latest_tvl > 0 else 0.0
        holders_share_fees = (holders_30d / fees_30d) if fees_30d > 0 else 0.0
        protocol_share_fees = (protocol_rev_30d / fees_30d) if fees_30d > 0 else 0.0

        rows.append(
            {
                "slug": slug,
                "name": peer["name"],
                "category": protocol.get("category") or fees.get("category"),
                "latest_tvl_usd": latest_tvl,
                "fees_30d_usd": fees_30d,
                "revenue_30d_usd": revenue_30d,
                "holders_revenue_30d_usd": holders_30d,
                "protocol_revenue_30d_usd": protocol_rev_30d,
                "annualized_fee_rate_on_tvl": fee_rate,
                "annualized_holders_yield_on_tvl": holders_yield_tvl,
                "holders_revenue_share_of_fees": holders_share_fees,
                "protocol_revenue_share_of_fees": protocol_share_fees,
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        payload = {"status": "NO_DATA", "rows": []}
        save_json(tables_dir / "investor_external_benchmark_peers.json", payload)
        return payload

    df["fees_30d_rank"] = df["fees_30d_usd"].rank(method="min", ascending=False).astype(int)
    df["fee_rate_rank"] = df["annualized_fee_rate_on_tvl"].rank(method="min", ascending=False).astype(int)

    df_sorted = df.sort_values("fees_30d_usd", ascending=False)
    headers = list(df_sorted.columns)
    rows_out = df_sorted.values.tolist()
    write_csv(tables_dir / "investor_external_benchmark_peers.csv", headers=headers, rows=rows_out)

    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "schema": "investor_external_benchmark_v1",
        "peer_count": int(len(df_sorted)),
        "peers": df_sorted.to_dict(orient="records"),
    }
    save_json(tables_dir / "investor_external_benchmark_peers.json", payload)

    # Chart: fees scale and holders-yield scale across peers.
    sns.set_theme(style="whitegrid")
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5), constrained_layout=True)

    fees_plot = df_sorted.copy()
    axes[0].barh(fees_plot["name"], fees_plot["fees_30d_usd"], color="#1f77b4")
    axes[0].set_title("30d Fees by Protocol (USD)", fontsize=12, weight="bold")
    axes[0].set_xlabel("USD (log scale)")
    axes[0].set_xscale("log")
    axes[0].invert_yaxis()

    yield_plot = df_sorted.copy()
    axes[1].barh(yield_plot["name"], yield_plot["annualized_holders_yield_on_tvl"] * 100.0, color="#2ca02c")
    axes[1].set_title("Annualized Holders Revenue / TVL", fontsize=12, weight="bold")
    axes[1].set_xlabel("Percent")
    axes[1].invert_yaxis()

    charts_dir.mkdir(parents=True, exist_ok=True)
    chart_path = charts_dir / "investor_external_peer_benchmarks.png"
    fig.savefig(chart_path, dpi=220)
    plt.close(fig)

    payload["chart"] = chart_path.as_posix()
    save_json(tables_dir / "investor_external_benchmark_peers.json", payload)
    return payload


def build_macro_context(snapshot_dir: Path, tables_dir: Path, charts_dir: Path) -> dict[str, Any]:
    protocols = load_json(snapshot_dir / "protocols_all.json")
    overview_fees = load_json(snapshot_dir / "overview_fees_dailyFees.json")
    overview_revenue = load_json(snapshot_dir / "overview_fees_dailyRevenue.json")
    overview_holders = load_json(snapshot_dir / "overview_fees_dailyHoldersRevenue.json")

    protocols_df = pd.DataFrame(protocols)
    if "category" not in protocols_df.columns:
        protocols_df["category"] = ""
    protocols_df["tvl"] = pd.to_numeric(protocols_df.get("tvl"), errors="coerce").fillna(0.0)

    lending_df = protocols_df[protocols_df["category"].fillna("").str.lower() == "lending"].copy()
    yield_agg_df = protocols_df[protocols_df["category"].fillna("").str.lower() == "yield aggregator"].copy()

    lazy_protocol_row = protocols_df[protocols_df["slug"] == "lazy-summer-protocol"]
    lazy_tvl = float(lazy_protocol_row.iloc[0]["tvl"]) if not lazy_protocol_row.empty else 0.0

    lazy_rank_tvl_yield_agg = None
    if not yield_agg_df.empty:
        yield_agg_df = yield_agg_df.sort_values("tvl", ascending=False).reset_index(drop=True)
        match = yield_agg_df[yield_agg_df["slug"] == "lazy-summer-protocol"]
        if not match.empty:
            lazy_rank_tvl_yield_agg = int(match.index[0] + 1)

    overview_fees_df = pd.DataFrame(overview_fees.get("protocols") or [])
    overview_fees_df["total30d"] = pd.to_numeric(overview_fees_df.get("total30d"), errors="coerce").fillna(0.0)

    overview_revenue_df = pd.DataFrame(overview_revenue.get("protocols") or [])
    overview_revenue_df["total30d"] = pd.to_numeric(overview_revenue_df.get("total30d"), errors="coerce").fillna(0.0)

    overview_holders_df = pd.DataFrame(overview_holders.get("protocols") or [])
    overview_holders_df["total30d"] = pd.to_numeric(overview_holders_df.get("total30d"), errors="coerce").fillna(0.0)

    lending_fee_30d = float(
        overview_fees_df[overview_fees_df["category"].fillna("").str.lower() == "lending"]["total30d"].sum()
    )
    global_fee_30d = float(parse_float(overview_fees.get("total30d")))

    lending_revenue_30d = float(
        overview_revenue_df[overview_revenue_df["category"].fillna("").str.lower() == "lending"]["total30d"].sum()
    )
    global_revenue_30d = float(parse_float(overview_revenue.get("total30d")))

    lending_holders_30d = float(
        overview_holders_df[overview_holders_df["category"].fillna("").str.lower() == "lending"]["total30d"].sum()
    )
    global_holders_30d = float(parse_float(overview_holders.get("total30d")))

    lazy_fee_30d = float(
        overview_fees_df.loc[overview_fees_df["slug"] == "lazy-summer-protocol", "total30d"].sum()
    )

    top_lending = (
        overview_fees_df[overview_fees_df["category"].fillna("").str.lower() == "lending"]
        .sort_values("total30d", ascending=False)
        .head(10)
        .copy()
    )

    top_headers = ["name", "slug", "total30d"]
    top_rows = [[row["name"], row["slug"], float(row["total30d"])] for _, row in top_lending.iterrows()]
    write_csv(tables_dir / "investor_macro_top_lending_30d_fees.csv", headers=top_headers, rows=top_rows)

    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "schema": "investor_macro_context_v1",
        "lending_market": {
            "protocol_count": int(len(lending_df)),
            "tvl_total_usd": float(lending_df["tvl"].sum()),
            "fees_30d_usd": lending_fee_30d,
            "revenue_30d_usd": lending_revenue_30d,
            "holders_revenue_30d_usd": lending_holders_30d,
        },
        "global_market": {
            "protocol_count": int(len(protocols_df)),
            "tvl_total_usd": float(protocols_df["tvl"].sum()),
            "fees_30d_usd": global_fee_30d,
            "revenue_30d_usd": global_revenue_30d,
            "holders_revenue_30d_usd": global_holders_30d,
        },
        "lazy_summer_positioning": {
            "latest_tvl_usd": lazy_tvl,
            "rank_by_tvl_within_yield_aggregators": lazy_rank_tvl_yield_agg,
            "yield_aggregator_count": int(len(yield_agg_df)),
            "fees_30d_usd": lazy_fee_30d,
            "fee_share_of_global": (lazy_fee_30d / global_fee_30d) if global_fee_30d > 0 else 0.0,
            "fee_share_of_lending": (lazy_fee_30d / lending_fee_30d) if lending_fee_30d > 0 else 0.0,
        },
        "top_lending_by_30d_fees": top_rows,
    }
    save_json(tables_dir / "investor_macro_context.json", payload)

    # Chart: top lending fee league table + Lazy Summer marker.
    plot_rows = top_lending[["name", "total30d"]].copy()
    plot_rows = pd.concat(
        [
            plot_rows,
            pd.DataFrame([{"name": "Lazy Summer (Reference)", "total30d": lazy_fee_30d}]),
        ],
        ignore_index=True,
    )

    sns.set_theme(style="whitegrid")
    fig, ax = plt.subplots(figsize=(10, 6), constrained_layout=True)
    ax.barh(plot_rows["name"], plot_rows["total30d"], color=["#4c78a8"] * (len(plot_rows) - 1) + ["#e45756"])
    ax.set_xscale("log")
    ax.invert_yaxis()
    ax.set_xlabel("30d Fees (USD, log scale)")
    ax.set_title("Macro Context: Lending 30d Fee League Table", fontsize=13, weight="bold")

    charts_dir.mkdir(parents=True, exist_ok=True)
    chart_path = charts_dir / "investor_macro_lending_fee_league.png"
    fig.savefig(chart_path, dpi=220)
    plt.close(fig)

    payload["chart"] = chart_path.as_posix()
    save_json(tables_dir / "investor_macro_context.json", payload)
    return payload


def select_case_scenarios(scenario_matrix: dict[str, Any], realized_ratio: float) -> list[CaseScenario]:
    scenarios = scenario_matrix.get("scenarios") or []

    def pick(tvl_mult: float, fee: float, share: float, staking: float) -> dict[str, Any] | None:
        for row in scenarios:
            if (
                math.isclose(parse_float(row.get("tvl_multiplier")), tvl_mult, abs_tol=1e-9)
                and math.isclose(parse_float(row.get("fee_rate")), fee, abs_tol=1e-9)
                and math.isclose(parse_float(row.get("staker_share")), share, abs_tol=1e-9)
                and math.isclose(parse_float(row.get("staking_ratio")), staking, abs_tol=1e-9)
            ):
                return row
        return None

    specs = [
        ("Downside", 0.5, 0.0010, 0.10, 0.30),
        ("Base", 1.0, 0.0066, 0.20, 0.30),
        ("Upside", 2.0, 0.0100, 0.30, 0.30),
    ]
    out: list[CaseScenario] = []
    for name, tvl_mult, fee, share, staking in specs:
        row = pick(tvl_mult, fee, share, staking)
        if row is None:
            continue
        upper = parse_float(row.get("staker_revenue_usd"))
        lower = upper * realized_ratio
        y_upper = parse_float(row.get("revenue_yield_on_staked"))
        y_lower = y_upper * realized_ratio
        out.append(
            CaseScenario(
                case=name,
                tvl_multiplier=tvl_mult,
                annual_staker_revenue_lower_usd=lower,
                annual_staker_revenue_upper_usd=upper,
                yield_on_staked_lower=y_lower,
                yield_on_staked_upper=y_upper,
            )
        )
    return out


def derive_case_probabilities(
    lazy_protocol_payload: dict[str, Any],
    gate_passed: bool,
) -> dict[str, float]:
    tvl_rows = lazy_protocol_payload.get("tvl") or []
    if not tvl_rows:
        return {"Downside": 0.30, "Base": 0.40, "Upside": 0.30}

    df = pd.DataFrame(tvl_rows)
    df["totalLiquidityUSD"] = pd.to_numeric(df["totalLiquidityUSD"], errors="coerce")
    df = df.dropna(subset=["totalLiquidityUSD"])
    if df.empty:
        return {"Downside": 0.30, "Base": 0.40, "Upside": 0.30}

    latest_tvl = float(df.iloc[-1]["totalLiquidityUSD"])
    trailing = df.tail(min(365, len(df)))
    ratios = trailing["totalLiquidityUSD"] / latest_tvl

    empirical = {
        "Downside": float((ratios <= 0.8).mean()),
        "Base": float(((ratios > 0.8) & (ratios < 1.5)).mean()),
        "Upside": float((ratios >= 1.5).mean()),
    }

    # Blend empirical occupancy with a neutral prior.
    alpha = 0.50
    blended = {
        key: alpha * empirical[key] + (1.0 - alpha) * (1.0 / 3.0)
        for key in ["Downside", "Base", "Upside"]
    }

    # Strict-gate failure implies conservative skew: shift upside mass to downside.
    if not gate_passed:
        shift = min(0.10, blended["Upside"])
        blended["Upside"] -= shift
        blended["Downside"] += shift

    total = sum(blended.values())
    if total <= 0:
        return {"Downside": 0.30, "Base": 0.40, "Upside": 0.30}

    return {k: v / total for k, v in blended.items()}


def build_probability_weighted_pnl(
    snapshot_dir: Path,
    monitoring: dict[str, Any],
    scenario_assumptions: dict[str, Any],
    scenario_matrix: dict[str, Any],
    bounded_bands: dict[str, Any],
    tables_dir: Path,
    charts_dir: Path,
) -> dict[str, Any]:
    realized_ratio = parse_float((bounded_bands.get("bounds_baseline") or {}).get("realized_ratio_lower_to_upper"))
    cases = select_case_scenarios(scenario_matrix=scenario_matrix, realized_ratio=realized_ratio)
    lazy_protocol = load_json(snapshot_dir / "peer_lazy-summer-protocol_protocol.json")
    gate_passed = bool((monitoring.get("latest") or {}).get("all_campaigns_pass"))
    probs = derive_case_probabilities(lazy_protocol, gate_passed=gate_passed)

    token_price = parse_float(((scenario_assumptions.get("assumptions") or {}).get("token_price_usd") or {}).get("value"))
    if token_price <= 0:
        token_price = 0.005

    tokens_held = 1_000_000.0
    horizon_years = 3
    price_elasticity = 0.80
    initial_value = tokens_held * token_price

    rows: list[dict[str, Any]] = []

    for case in cases:
        probability = probs.get(case.case, 0.0)
        terminal_price_multiplier = case.tvl_multiplier ** price_elasticity

        for bound_label, yield_rate in [
            ("Lower", case.yield_on_staked_lower),
            ("Upper", case.yield_on_staked_upper),
        ]:
            cumulative_cash = 0.0
            for year in range(1, horizon_years + 1):
                start_mult = 1.0 + (terminal_price_multiplier - 1.0) * ((year - 1) / horizon_years)
                end_mult = 1.0 + (terminal_price_multiplier - 1.0) * (year / horizon_years)
                avg_mult = (start_mult + end_mult) / 2.0

                avg_position_value = initial_value * avg_mult
                annual_cash_yield = avg_position_value * yield_rate
                cumulative_cash += annual_cash_yield
                terminal_token_value = initial_value * end_mult
                total_value = terminal_token_value + cumulative_cash
                pnl = total_value - initial_value

                rows.append(
                    {
                        "scenario_case": case.case,
                        "bound": bound_label,
                        "year": year,
                        "probability": probability,
                        "terminal_price_multiplier": terminal_price_multiplier,
                        "yield_on_staked": yield_rate,
                        "annual_cash_yield_usd": annual_cash_yield,
                        "cumulative_cash_yield_usd": cumulative_cash,
                        "terminal_token_value_usd": terminal_token_value,
                        "total_value_usd": total_value,
                        "pnl_usd": pnl,
                        "moic": total_value / initial_value if initial_value > 0 else 0.0,
                    }
                )

    df = pd.DataFrame(rows)
    if df.empty:
        payload = {"status": "NO_SCENARIO_ROWS", "rows": []}
        save_json(tables_dir / "investor_probability_weighted_pnl.json", payload)
        return payload

    expected_rows: list[dict[str, Any]] = []
    for bound in ["Lower", "Upper"]:
        for year in sorted(df["year"].unique()):
            sub = df[(df["bound"] == bound) & (df["year"] == year)].copy()
            expected_total = float((sub["total_value_usd"] * sub["probability"]).sum())
            expected_pnl = expected_total - initial_value
            expected_irr = (expected_total / initial_value) ** (1.0 / year) - 1.0 if initial_value > 0 else 0.0
            expected_rows.append(
                {
                    "bound": bound,
                    "year": int(year),
                    "expected_total_value_usd": expected_total,
                    "expected_pnl_usd": expected_pnl,
                    "expected_annualized_return": expected_irr,
                }
            )

    write_csv(
        tables_dir / "investor_probability_weighted_pnl_paths.csv",
        headers=list(df.columns),
        rows=df.values.tolist(),
    )
    write_csv(
        tables_dir / "investor_probability_weighted_pnl_expected.csv",
        headers=list(expected_rows[0].keys()),
        rows=[[row[k] for k in expected_rows[0].keys()] for row in expected_rows],
    )

    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "schema": "investor_probability_weighted_pnl_v1",
        "assumptions": {
            "tokens_held": tokens_held,
            "entry_price_usd": token_price,
            "initial_position_value_usd": initial_value,
            "horizon_years": horizon_years,
            "price_to_tvl_elasticity": price_elasticity,
            "probabilities": probs,
            "probability_method": {
                "tvl_regimes": {"Downside": "ratio<=0.8", "Base": "0.8<ratio<1.5", "Upside": "ratio>=1.5"},
                "lookback_days": min(365, len(lazy_protocol.get("tvl") or [])),
                "prior_blend_alpha": 0.5,
                "gate_failure_upside_to_downside_shift": 0.10 if not gate_passed else 0.0,
            },
            "price_multiplier_method": "terminal_price_multiplier = tvl_multiplier ** 0.80",
        },
        "rows": rows,
        "expected": expected_rows,
    }
    save_json(tables_dir / "investor_probability_weighted_pnl.json", payload)

    # Chart: scenario path fan + expected path.
    sns.set_theme(style="whitegrid")
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5), constrained_layout=True)

    for idx, bound in enumerate(["Lower", "Upper"]):
        ax = axes[idx]
        sub = df[df["bound"] == bound]
        for case in ["Downside", "Base", "Upside"]:
            case_rows = sub[sub["scenario_case"] == case].sort_values("year")
            if case_rows.empty:
                continue
            ax.plot(case_rows["year"], case_rows["total_value_usd"], marker="o", label=case)

        expected_sub = pd.DataFrame([row for row in expected_rows if row["bound"] == bound]).sort_values("year")
        ax.plot(
            expected_sub["year"],
            expected_sub["expected_total_value_usd"],
            marker="o",
            linewidth=2.5,
            color="black",
            label="Probability-weighted expected",
        )
        ax.set_title(f"{bound}-Bound Position Value Path", fontsize=12, weight="bold")
        ax.set_xlabel("Year")
        ax.set_ylabel("USD")
        ax.legend(loc="best")

    charts_dir.mkdir(parents=True, exist_ok=True)
    chart_path = charts_dir / "investor_probability_weighted_pnl_paths.png"
    fig.savefig(chart_path, dpi=220)
    plt.close(fig)

    payload["chart"] = chart_path.as_posix()
    save_json(tables_dir / "investor_probability_weighted_pnl.json", payload)
    return payload


def fetch_base_treasury_balances(rpc_url: str) -> dict[str, Any]:
    w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
    if not w3.is_connected():
        raise RuntimeError(f"Could not connect to Base RPC: {rpc_url}")

    treasury_checksum = Web3.to_checksum_address(TREASURY)
    balances: dict[str, Any] = {
        "rpc_url": rpc_url,
        "block_number": w3.eth.block_number,
        "tokens": {},
    }

    for symbol, address in TOKEN_ADDRESSES_BASE.items():
        contract = w3.eth.contract(address=Web3.to_checksum_address(address), abi=ERC20_ABI)
        try:
            decimals = int(contract.functions.decimals().call())
            raw = int(contract.functions.balanceOf(treasury_checksum).call())
            amount = raw / (10 ** decimals)
            balances["tokens"][symbol] = {
                "address": address,
                "raw": raw,
                "decimals": decimals,
                "amount": amount,
            }
        except Exception:  # noqa: BLE001
            balances["tokens"][symbol] = {
                "address": address,
                "raw": 0,
                "decimals": None,
                "amount": 0.0,
                "status": "unavailable_on_rpc",
            }

    return balances


def build_treasury_runway_model(
    snapshot_dir: Path,
    evidence_dir: Path,
    scenario_matrix: dict[str, Any],
    bounded_bands: dict[str, Any],
    tables_dir: Path,
    charts_dir: Path,
    rpc_url: str,
) -> dict[str, Any]:
    outflows = pd.read_csv(evidence_dir / "base_treasury_fee_token_outflows.csv")
    inflows = pd.read_csv(evidence_dir / "base_treasury_fee_token_inflows.csv")
    monthly = pd.read_csv(evidence_dir / "source_of_funds_monthly_comparison.csv")

    for col in ["amount"]:
        outflows[col] = pd.to_numeric(outflows[col], errors="coerce").fillna(0.0)
        inflows[col] = pd.to_numeric(inflows[col], errors="coerce").fillna(0.0)

    stable_inflows = inflows[inflows["token_symbol"].isin(STABLE_SYMBOLS)]
    stable_outflows = outflows[outflows["token_symbol"].isin(STABLE_SYMBOLS)]

    operating_outflows = stable_outflows[
        ~stable_outflows["to_address"].str.lower().isin({DISTRIBUTOR, MERKL_FEE_RECIPIENT})
    ]
    merkl_outflows = stable_outflows[stable_outflows["to_address"].str.lower() == MERKL_FEE_RECIPIENT]

    observed_months = int(monthly["month_utc"].nunique()) if not monthly.empty else 12
    observed_months = max(observed_months, 1)

    annual_opex_low = float(operating_outflows["amount"].sum()) * (12.0 / observed_months)
    annual_opex_base = float(operating_outflows["amount"].sum() + merkl_outflows["amount"].sum()) * (12.0 / observed_months)
    annual_opex_high = annual_opex_base * 2.0

    price_payload = load_json(snapshot_dir / "price_base_weth.json")
    weth_price = parse_float((price_payload.get("coins") or {}).get("base:0x4200000000000000000000000000000000000006", {}).get("price"))

    balances = fetch_base_treasury_balances(rpc_url=rpc_url)
    stable_reserve = sum(parse_float((balances["tokens"].get(sym) or {}).get("amount")) for sym in ["USDC", "EURC", "USDT"])
    weth_amount = parse_float((balances["tokens"].get("WETH") or {}).get("amount"))
    reserve_total = stable_reserve + weth_amount * weth_price

    realized_ratio = parse_float((bounded_bands.get("bounds_baseline") or {}).get("realized_ratio_lower_to_upper"))
    cases = select_case_scenarios(scenario_matrix=scenario_matrix, realized_ratio=realized_ratio)

    opex_cases = {
        "LOW": annual_opex_low,
        "BASE": annual_opex_base,
        "HIGH": annual_opex_high,
    }

    rows: list[dict[str, Any]] = []
    for case in cases:
        for bound, staker_revenue in [
            ("Lower", case.annual_staker_revenue_lower_usd),
            ("Upper", case.annual_staker_revenue_upper_usd),
        ]:
            treasury_inflow = staker_revenue * 1.5
            staker_outflow = staker_revenue
            retained_before_opex = treasury_inflow - staker_outflow

            for opex_label, annual_opex in opex_cases.items():
                annual_net = retained_before_opex - annual_opex
                runway_stable = math.inf if annual_net >= 0 else (stable_reserve / abs(annual_net) if annual_net != 0 else math.inf)
                runway_total = math.inf if annual_net >= 0 else (reserve_total / abs(annual_net) if annual_net != 0 else math.inf)

                rows.append(
                    {
                        "scenario_case": case.case,
                        "bound": bound,
                        "annual_staker_revenue_usd": staker_revenue,
                        "treasury_inflow_usd": treasury_inflow,
                        "staker_outflow_usd": staker_outflow,
                        "retained_before_opex_usd": retained_before_opex,
                        "opex_case": opex_label,
                        "annual_opex_usd": annual_opex,
                        "annual_net_treasury_cashflow_usd": annual_net,
                        "runway_years_stable_reserve": runway_stable,
                        "runway_years_total_reserve": runway_total,
                    }
                )

    df = pd.DataFrame(rows)

    write_csv(
        tables_dir / "investor_treasury_runway_model.csv",
        headers=list(df.columns),
        rows=df.values.tolist(),
    )

    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "schema": "investor_treasury_runway_model_v1",
        "assumptions": {
            "treasury_inflow_formula": "treasury_inflow = staker_revenue * 1.5 (30% treasury-controlled flow vs 20% staker payout)",
            "staker_outflow_formula": "staker_outflow = staker_revenue",
            "retained_before_opex_formula": "retained_before_opex = 0.5 * staker_revenue",
            "opex_low_definition": "stablecoin outflows to non-distributor/non-merkl addresses annualized from observed window",
            "opex_base_definition": "opex_low + merkl stablecoin outflows annualized",
            "opex_high_definition": "2x opex_base stress case",
            "observed_months": observed_months,
        },
        "reserve_snapshot": {
            "stable_reserve_usd": stable_reserve,
            "weth_amount": weth_amount,
            "weth_price_usd": weth_price,
            "total_reserve_usd": reserve_total,
            "rpc_block_number": balances.get("block_number"),
        },
        "rows": rows,
    }
    save_json(tables_dir / "investor_treasury_runway_model.json", payload)

    # Chart: base opex runway by scenario/bound.
    base_df = df[df["opex_case"] == "BASE"].copy()
    if not base_df.empty:
        sns.set_theme(style="whitegrid")
        fig, ax = plt.subplots(figsize=(10, 5.5), constrained_layout=True)

        labels = [f"{row['scenario_case']} ({row['bound']})" for _, row in base_df.iterrows()]
        values = [float(row["runway_years_stable_reserve"]) if math.isfinite(float(row["runway_years_stable_reserve"])) else 25.0 for _, row in base_df.iterrows()]
        colors = ["#2ca02c" if math.isfinite(float(row["runway_years_stable_reserve"])) and float(row["runway_years_stable_reserve"]) > 10 else "#d62728" for _, row in base_df.iterrows()]

        x = list(range(len(labels)))
        ax.bar(x, values, color=colors)
        ax.axhline(1.0, color="black", linestyle="--", linewidth=1)
        ax.set_ylabel("Runway (years, stable reserve basis)")
        ax.set_title("Treasury Runway Under Base Opex Assumption", fontsize=13, weight="bold")
        ax.set_xticks(x, labels, rotation=20, ha="right")

        chart_path = charts_dir / "investor_treasury_runway_base_opex.png"
        charts_dir.mkdir(parents=True, exist_ok=True)
        fig.savefig(chart_path, dpi=220)
        plt.close(fig)

        payload["chart"] = chart_path.as_posix()
        save_json(tables_dir / "investor_treasury_runway_model.json", payload)

    return payload


def fetch_blockscout_logs_all(address: str, topic: str) -> list[dict[str, Any]]:
    base_url = f"https://base.blockscout.com/api/v2/addresses/{address}/logs"
    params: dict[str, Any] = {"topic": topic}
    all_items: list[dict[str, Any]] = []

    while True:
        payload = request_json(base_url, params=params, retries=6, timeout=90)
        items = payload.get("items") or []
        all_items.extend(items)
        next_params = payload.get("next_page_params")
        if not next_params:
            break
        params = next_params

    return all_items


def call_with_retry(callable_fn, retries: int = 5, sleep_seconds: int = 2) -> Any:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return callable_fn()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(min(20, sleep_seconds * attempt))
    raise RuntimeError(f"RPC call failed after retries: {last_error}") from last_error


def assign_lockup_bucket(lockup_days: float) -> str:
    if lockup_days <= 0:
        return "0d"
    if lockup_days <= 14:
        return "1-14d"
    if lockup_days <= 90:
        return "15-90d"
    if lockup_days <= 180:
        return "91-180d"
    if lockup_days <= 365:
        return "181-365d"
    if lockup_days <= 730:
        return "366-730d"
    return "731-1095d"


def assign_remaining_bucket(remaining_days: float) -> str:
    if remaining_days <= 0:
        return "Unlocked"
    if remaining_days <= 30:
        return "1-30d"
    if remaining_days <= 90:
        return "31-90d"
    if remaining_days <= 180:
        return "91-180d"
    if remaining_days <= 365:
        return "181-365d"
    return ">365d"


def build_staking_distribution(
    snapshot_contract_path: Path,
    tables_dir: Path,
    charts_dir: Path,
    rpc_url: str,
) -> dict[str, Any]:
    contract_payload = load_json(snapshot_contract_path)
    abi = contract_payload.get("abi")
    if not isinstance(abi, list):
        raise ValueError(f"Expected list ABI in {snapshot_contract_path}")

    w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
    if not w3.is_connected():
        raise RuntimeError(f"Could not connect to Base RPC: {rpc_url}")

    staking_address = Web3.to_checksum_address(SUMMER_STAKING)
    contract = w3.eth.contract(address=staking_address, abi=abi)

    topic = Web3.keccak(text="StakedWithLockup(address,uint256,uint256,uint256,uint256)").hex()
    logs = fetch_blockscout_logs_all(address=SUMMER_STAKING, topic=topic)

    users = sorted(
        {
            Web3.to_checksum_address("0x" + str(item["topics"][1])[-40:])
            for item in logs
            if item.get("topics") and len(item.get("topics")) > 1
        }
    )

    latest_block = int(call_with_retry(lambda: w3.eth.block_number))
    latest_block_payload = call_with_retry(lambda: w3.eth.get_block(latest_block))
    latest_ts = int(latest_block_payload["timestamp"])

    positions: list[dict[str, Any]] = []
    for idx, user in enumerate(users, start=1):
        if idx % 100 == 0:
            print(f"staking-distribution: processed {idx}/{len(users)} staker addresses")

        count = int(call_with_retry(lambda: contract.functions.getUserStakesCount(user).call(block_identifier=latest_block)))
        for stake_index in range(count):
            amount_raw, weighted_raw, lockup_end, lockup_period = call_with_retry(
                lambda: contract.functions.getUserStake(user, stake_index).call(block_identifier=latest_block)
            )
            amount_raw = int(amount_raw)
            if amount_raw <= 0:
                continue
            weighted_raw = int(weighted_raw)
            lockup_end = int(lockup_end)
            lockup_period = int(lockup_period)

            amount = amount_raw / 1e18
            weighted = weighted_raw / 1e18
            lockup_days = lockup_period / 86400.0
            remaining_days = max(lockup_end - latest_ts, 0) / 86400.0

            positions.append(
                {
                    "user": user,
                    "stake_index": stake_index,
                    "amount_sumr": amount,
                    "weighted_amount_sumr": weighted,
                    "multiplier": (weighted / amount) if amount > 0 else 0.0,
                    "lockup_period_days": lockup_days,
                    "remaining_days": remaining_days,
                    "lockup_end_timestamp": lockup_end,
                    "lockup_bucket": assign_lockup_bucket(lockup_days),
                    "remaining_bucket": assign_remaining_bucket(remaining_days),
                }
            )

    df = pd.DataFrame(positions)
    if df.empty:
        payload = {
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "schema": "investor_staking_distribution_v1",
            "status": "NO_ACTIVE_POSITIONS",
            "log_count": len(logs),
            "staker_address_count": len(users),
        }
        save_json(tables_dir / "investor_staking_distribution.json", payload)
        return payload

    lockup = (
        df.groupby("lockup_bucket", as_index=False)
        .agg(position_count=("user", "count"), total_amount_sumr=("amount_sumr", "sum"), total_weighted_sumr=("weighted_amount_sumr", "sum"))
    )
    remaining = (
        df.groupby("remaining_bucket", as_index=False)
        .agg(position_count=("user", "count"), total_amount_sumr=("amount_sumr", "sum"), total_weighted_sumr=("weighted_amount_sumr", "sum"))
    )
    top_stakers = (
        df.groupby("user", as_index=False)
        .agg(active_positions=("stake_index", "count"), total_amount_sumr=("amount_sumr", "sum"), total_weighted_sumr=("weighted_amount_sumr", "sum"))
        .sort_values("total_amount_sumr", ascending=False)
        .head(20)
    )

    total_amount = float(df["amount_sumr"].sum())
    weighted_amount = float(df["weighted_amount_sumr"].sum())

    summary = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "schema": "investor_staking_distribution_v1",
        "snapshot_block": latest_block,
        "snapshot_timestamp_utc": datetime.fromtimestamp(latest_ts, tz=timezone.utc).isoformat(),
        "address_discovery": {
            "source": "blockscout_logs",
            "event": "StakedWithLockup",
            "event_topic": topic,
            "contract": SUMMER_STAKING,
            "discovered_log_count": len(logs),
            "discovered_unique_addresses": len(users),
            "first_scanned_block": SUMMER_STAKING_DEPLOY_BLOCK,
            "last_scanned_block": latest_block,
        },
        "position_summary": {
            "active_position_count": int(len(df)),
            "unique_active_stakers": int(df["user"].nunique()),
            "total_staked_sumr": total_amount,
            "total_weighted_sumr": weighted_amount,
            "weighted_multiplier": (weighted_amount / total_amount) if total_amount > 0 else 0.0,
            "avg_lockup_days_simple": float(df["lockup_period_days"].mean()),
            "avg_lockup_days_amount_weighted": float((df["lockup_period_days"] * df["amount_sumr"]).sum() / total_amount) if total_amount > 0 else 0.0,
            "avg_remaining_days_amount_weighted": float((df["remaining_days"] * df["amount_sumr"]).sum() / total_amount) if total_amount > 0 else 0.0,
            "median_position_size_sumr": float(df["amount_sumr"].median()),
            "p90_position_size_sumr": float(df["amount_sumr"].quantile(0.90)),
        },
        "lockup_distribution": lockup.to_dict(orient="records"),
        "remaining_distribution": remaining.to_dict(orient="records"),
        "top_stakers": top_stakers.to_dict(orient="records"),
    }

    write_csv(tables_dir / "investor_staking_positions_snapshot.csv", headers=list(df.columns), rows=df.values.tolist())
    write_csv(tables_dir / "investor_staking_lockup_distribution.csv", headers=list(lockup.columns), rows=lockup.values.tolist())
    write_csv(tables_dir / "investor_staking_remaining_distribution.csv", headers=list(remaining.columns), rows=remaining.values.tolist())
    write_csv(tables_dir / "investor_staking_top_stakers.csv", headers=list(top_stakers.columns), rows=top_stakers.values.tolist())
    save_json(tables_dir / "investor_staking_distribution.json", summary)

    # Chart: lockup distribution by total staked SUMR.
    bucket_order = ["0d", "1-14d", "15-90d", "91-180d", "181-365d", "366-730d", "731-1095d"]
    lockup_plot = lockup.set_index("lockup_bucket").reindex(bucket_order).fillna(0.0).reset_index()

    sns.set_theme(style="whitegrid")
    fig, ax = plt.subplots(figsize=(10, 5.5), constrained_layout=True)
    ax.bar(lockup_plot["lockup_bucket"], lockup_plot["total_amount_sumr"], color="#5e81ac")
    ax.set_title("Active Staked SUMR by Lockup Bucket", fontsize=13, weight="bold")
    ax.set_xlabel("Lockup bucket")
    ax.set_ylabel("SUMR")

    charts_dir.mkdir(parents=True, exist_ok=True)
    chart_path = charts_dir / "investor_staking_lockup_distribution.png"
    fig.savefig(chart_path, dpi=220)
    plt.close(fig)

    summary["chart"] = chart_path.as_posix()
    save_json(tables_dir / "investor_staking_distribution.json", summary)
    return summary


def fetch_live_sumr_price() -> dict[str, Any]:
    url = f"https://api.dexscreener.com/latest/dex/tokens/{SUMR_TOKEN}"
    payload = request_json(url)
    pairs = payload.get("pairs") or []
    base_pairs = [p for p in pairs if str(p.get("chainId")).lower() == "base"]
    if not base_pairs:
        return {"price_usd": 0.0, "source": {"url": url, "selected_pair": None, "selected_dex": None}}

    def liquidity_usd(pair: dict[str, Any]) -> float:
        return parse_float((pair.get("liquidity") or {}).get("usd"))

    selected = max(base_pairs, key=liquidity_usd)
    return {
        "price_usd": parse_float(selected.get("priceUsd")),
        "source": {
            "url": url,
            "selected_pair": selected.get("pairAddress"),
            "selected_dex": selected.get("dexId"),
        },
    }


def build_upside_plausibility_artifacts(snapshot_dir: Path, tables_dir: Path, stamp: str) -> dict[str, Any]:
    protocol = load_json(snapshot_dir / "peer_lazy-summer-protocol_protocol.json")
    fees = load_json(snapshot_dir / "peer_lazy-summer-protocol_dailyFees.json")

    tvl_rows = protocol.get("tvl") or []
    tvl_df = pd.DataFrame(tvl_rows)
    if tvl_df.empty:
        payload = {
            "as_of_utc": datetime.now(timezone.utc).isoformat(),
            "schema": "investor_upside_plausibility_indicators_v1",
            "metrics": {},
            "notes": ["No Lazy Summer TVL rows returned from snapshot source."],
        }
        write_versioned_json("investor_upside_plausibility_indicators", payload, tables_dir, stamp)
        write_versioned_csv(
            "investor_upside_plausibility_indicators",
            headers=["as_of_utc"],
            rows=[[payload["as_of_utc"]]],
            tables_dir=tables_dir,
            stamp=stamp,
        )
        return payload

    tvl_df["totalLiquidityUSD"] = pd.to_numeric(tvl_df["totalLiquidityUSD"], errors="coerce")
    tvl_df = tvl_df.dropna(subset=["totalLiquidityUSD"]).sort_values("date")
    latest_tvl = float(tvl_df.iloc[-1]["totalLiquidityUSD"])
    peak_tvl = float(tvl_df["totalLiquidityUSD"].max())
    tvl_30d_ago = float(tvl_df.iloc[-31]["totalLiquidityUSD"]) if len(tvl_df) >= 31 else latest_tvl
    tvl_90d_ago = float(tvl_df.iloc[-91]["totalLiquidityUSD"]) if len(tvl_df) >= 91 else tvl_30d_ago

    fee_chart = fees.get("totalDataChart") or []
    fee_values = [parse_float(row[1]) for row in fee_chart if isinstance(row, list) and len(row) >= 2]
    fees_30d = float(sum(fee_values[-30:])) if fee_values else parse_float(fees.get("total30d"))
    fees_prev_30d = float(sum(fee_values[-60:-30])) if len(fee_values) >= 60 else 0.0
    fees_change_30d_pct = pct_change(fees_30d, fees_prev_30d) if fees_prev_30d > 0 else 0.0

    annualized_fee_rate_decimal = ((fees_30d * 365.0 / 30.0) / latest_tvl) if latest_tvl > 0 else 0.0
    holder_fee_split_assumption = 0.20
    holders_revenue_30d_assumed = fees_30d * holder_fee_split_assumption
    annualized_holders_rate_decimal = annualized_fee_rate_decimal * holder_fee_split_assumption

    payload = {
        "as_of_utc": datetime.now(timezone.utc).isoformat(),
        "schema": "investor_upside_plausibility_indicators_v1",
        "source_urls": {
            "tvl": "https://api.llama.fi/protocol/lazy-summer-protocol",
            "fees": "https://api.llama.fi/summary/fees/lazy-summer-protocol",
        },
        "model_probability_snapshot": None,
        "metrics": {
            "latest_tvl_usd": latest_tvl,
            "peak_tvl_usd": peak_tvl,
            "drawdown_from_peak_pct": pct_change(latest_tvl, peak_tvl),
            "tvl_change_30d_pct": pct_change(latest_tvl, tvl_30d_ago),
            "tvl_change_90d_pct": pct_change(latest_tvl, tvl_90d_ago),
            "fees_30d_usd": fees_30d,
            "fees_prev_30d_usd": fees_prev_30d,
            "fees_change_30d_pct": fees_change_30d_pct,
            "annualized_fees_on_tvl_pct": annualized_fee_rate_decimal * 100.0,
            "holder_fee_split_assumption": holder_fee_split_assumption,
            "holders_revenue_30d_assumed_usd": holders_revenue_30d_assumed,
            "annualized_holders_revenue_on_tvl_pct_assumed": annualized_holders_rate_decimal * 100.0,
        },
        "notes": [
            "Generated from latest external snapshot bundle captured by investor_extended.",
            "Holders revenue uses 20% split assumption for directional plausibility framing.",
        ],
    }
    headers = [
        "as_of_utc",
        "latest_tvl_usd",
        "peak_tvl_usd",
        "drawdown_from_peak_pct",
        "tvl_change_30d_pct",
        "tvl_change_90d_pct",
        "fees_30d_usd",
        "fees_prev_30d_usd",
        "fees_change_30d_pct",
        "annualized_fees_on_tvl_pct",
        "holder_fee_split_assumption",
        "holders_revenue_30d_assumed_usd",
        "annualized_holders_revenue_on_tvl_pct_assumed",
    ]
    metrics = payload["metrics"]
    rows = [[payload["as_of_utc"]] + [metrics[h] for h in headers[1:]]]
    write_versioned_json("investor_upside_plausibility_indicators", payload, tables_dir, stamp)
    write_versioned_csv("investor_upside_plausibility_indicators", headers, rows, tables_dir, stamp)
    return payload


def build_verified_vs_external_reconciliation_artifacts(
    evidence_dir: Path,
    snapshot_manifest: dict[str, Any],
    snapshot_dir: Path,
    tables_dir: Path,
    stamp: str,
) -> dict[str, Any]:
    kpi = load_json(evidence_dir / "kpi_summary.json")
    protocol = load_json(snapshot_dir / "peer_lazy-summer-protocol_protocol.json")
    fees = load_json(snapshot_dir / "peer_lazy-summer-protocol_dailyFees.json")

    latest_tvl = latest_tvl_usd(protocol)
    live_fees_30d = parse_float(fees.get("total30d"))
    snapshot_time = snapshot_manifest.get("generated_utc") or datetime.now(timezone.utc).isoformat()

    verified_tvl = parse_float(kpi.get("lazy_latest_tvl_usd"))
    verified_fees_30d = parse_float(kpi.get("fees_derived_30d"))

    rows = [
        {
            "metric": "Lazy Summer TVL (USD)",
            "verified_value": verified_tvl,
            "external_value": latest_tvl,
            "delta_external_minus_verified": latest_tvl - verified_tvl,
            "delta_pct_of_verified": ((latest_tvl - verified_tvl) / verified_tvl) if verified_tvl else 0.0,
            "verified_definition_time": "Frozen evidence baseline (kpi_summary from external_review snapshot).",
            "external_definition_time": f"Live external benchmark snapshot (protocol TVL at {snapshot_time}).",
            "valuation_source_of_truth": "Use verified baseline for underwriting; external used for peer context only.",
        },
        {
            "metric": "Lazy Summer Fees 30d (USD)",
            "verified_value": verified_fees_30d,
            "external_value": live_fees_30d,
            "delta_external_minus_verified": live_fees_30d - verified_fees_30d,
            "delta_pct_of_verified": ((live_fees_30d - verified_fees_30d) / verified_fees_30d) if verified_fees_30d else 0.0,
            "verified_definition_time": "Frozen evidence baseline: derived rolling-30d from daily fee chart.",
            "external_definition_time": f"Live external benchmark snapshot: total30d endpoint at {snapshot_time}.",
            "valuation_source_of_truth": "Use verified baseline for valuation narratives; external used for comparables and market-share context.",
        },
    ]
    payload = {
        "as_of_utc": datetime.now(timezone.utc).isoformat(),
        "schema": "investor_verified_vs_external_reconciliation_v1",
        "rows": rows,
    }
    headers = [
        "metric",
        "verified_value",
        "external_value",
        "delta_external_minus_verified",
        "delta_pct_of_verified",
        "verified_definition_time",
        "external_definition_time",
        "valuation_source_of_truth",
    ]
    csv_rows = [[row[h] for h in headers] for row in rows]
    write_versioned_json("investor_verified_vs_external_reconciliation", payload, tables_dir, stamp)
    write_versioned_csv("investor_verified_vs_external_reconciliation", headers, csv_rows, tables_dir, stamp)
    return payload


def build_price_and_pnl_refresh_artifacts(
    evidence_dir: Path,
    scenario_matrix: dict[str, Any],
    bounded_bands: dict[str, Any],
    staking_payload: dict[str, Any],
    pnl_payload: dict[str, Any],
    tables_dir: Path,
    stamp: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    emissions = load_json(evidence_dir / "emissions_vs_revenue_decomposition.json")
    supply = load_json(evidence_dir / "sumr_supply_snapshot.json")

    break_even_price = parse_float(
        ((emissions.get("usd_decomposition_formula") or {}).get("break_even_sumr_price_for_emissions_equal_revenue_deposited"))
    )
    circulating_supply_tokens = parse_float(supply.get("totalSupply_tokens"))

    realized_ratio = parse_float((bounded_bands.get("bounds_baseline") or {}).get("realized_ratio_lower_to_upper"))
    cases = select_case_scenarios(scenario_matrix=scenario_matrix, realized_ratio=realized_ratio)
    base_case = next((c for c in cases if c.case == "Base"), None)
    annual_lower = base_case.annual_staker_revenue_lower_usd if base_case else 0.0
    annual_upper = base_case.annual_staker_revenue_upper_usd if base_case else 0.0

    observed_staking_ratio = parse_float(((staking_payload.get("position_summary") or {}).get("observed_raw_staking_ratio_vs_circulating")))
    if observed_staking_ratio <= 0:
        observed_staking_ratio = 0.20

    live_price_info = fetch_live_sumr_price()
    live_price = parse_float(live_price_info.get("price_usd"))
    if live_price <= 0:
        live_price = REFERENCE_PRICE_USD

    def compute_price_stats(price_usd: float) -> dict[str, Any]:
        market_cap = circulating_supply_tokens * price_usd
        apr_ratios = [observed_staking_ratio, 0.2, 0.3, 0.5]
        apr_map: dict[str, Any] = {}
        for ratio in apr_ratios:
            denom = market_cap * ratio
            apr_map[str(ratio)] = {
                "staking_ratio": ratio,
                "apr_lower": (annual_lower / denom) if denom > 0 else 0.0,
                "apr_upper": (annual_upper / denom) if denom > 0 else 0.0,
            }
        return {
            "price_usd": price_usd,
            "market_cap_usd": market_cap,
            "price_to_break_even_ratio": (price_usd / break_even_price) if break_even_price > 0 else 0.0,
            "pct_below_break_even": (1.0 - (price_usd / break_even_price)) if break_even_price > 0 else 0.0,
            "yield_on_market_cap_lower": (annual_lower / market_cap) if market_cap > 0 else 0.0,
            "yield_on_market_cap_upper": (annual_upper / market_cap) if market_cap > 0 else 0.0,
            "apr_by_staking_ratio": apr_map,
        }

    reference_stats = compute_price_stats(REFERENCE_PRICE_USD)
    live_stats = compute_price_stats(live_price)

    price_context_payload = {
        "as_of_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "schema": "investor_price_context_refresh_v1",
        "inputs": {
            "circulating_supply_tokens": circulating_supply_tokens,
            "break_even_price_usd": break_even_price,
            "annual_staker_cashflow_lower_usd": annual_lower,
            "annual_staker_cashflow_upper_usd": annual_upper,
            "observed_staking_ratio": observed_staking_ratio,
            "reference_price_usd": REFERENCE_PRICE_USD,
        },
        "reference_price_analysis": reference_stats,
        "live_price_analysis": live_stats,
        "live_price_source": live_price_info.get("source"),
        "notes": [
            "Reference price analysis is pinned to 0.003319 for executive-summary consistency.",
            "Live spot uses highest-liquidity Base DEX pair at runtime.",
        ],
    }
    write_versioned_json("investor_price_context_refresh", price_context_payload, tables_dir, stamp)
    write_versioned_csv(
        "investor_price_context_refresh",
        headers=[
            "as_of_utc",
            "reference_price_usd",
            "reference_market_cap_usd",
            "reference_price_to_break_even_ratio",
            "reference_yield_mcap_lower",
            "reference_yield_mcap_upper",
            "live_price_usd",
            "live_market_cap_usd",
            "live_price_to_break_even_ratio",
        ],
        rows=[
            [
                price_context_payload["as_of_utc"],
                reference_stats["price_usd"],
                reference_stats["market_cap_usd"],
                reference_stats["price_to_break_even_ratio"],
                reference_stats["yield_on_market_cap_lower"],
                reference_stats["yield_on_market_cap_upper"],
                live_stats["price_usd"],
                live_stats["market_cap_usd"],
                live_stats["price_to_break_even_ratio"],
            ]
        ],
        tables_dir=tables_dir,
        stamp=stamp,
    )

    assumptions = pnl_payload.get("assumptions") or {}
    base_expected = pnl_payload.get("expected") or []
    base_rows = pnl_payload.get("rows") or []
    base_entry_price = parse_float(assumptions.get("entry_price_usd"))
    base_initial = parse_float(assumptions.get("initial_position_value_usd"))
    tokens_held = parse_float(assumptions.get("tokens_held"))
    if base_entry_price <= 0:
        base_entry_price = REFERENCE_PRICE_USD
    if base_initial <= 0:
        base_initial = tokens_held * base_entry_price

    def scale_expected(expected_rows: list[dict[str, Any]], new_price: float) -> list[dict[str, Any]]:
        new_initial = tokens_held * new_price
        scale = (new_initial / base_initial) if base_initial > 0 else 1.0
        scaled_rows: list[dict[str, Any]] = []
        for row in expected_rows:
            year = int(row.get("year"))
            expected_total = parse_float(row.get("expected_total_value_usd")) * scale
            annualized = (expected_total / new_initial) ** (1.0 / year) - 1.0 if new_initial > 0 else 0.0
            scaled_rows.append(
                {
                    "bound": str(row.get("bound")),
                    "year": year,
                    "expected_total_value_usd": expected_total,
                    "expected_pnl_usd": expected_total - new_initial,
                    "expected_annualized_return": annualized,
                }
            )
        return scaled_rows

    def implied_terminal_price_path(new_price: float) -> list[dict[str, Any]]:
        if not base_rows or tokens_held <= 0:
            return []
        df = pd.DataFrame(base_rows)
        if df.empty:
            return []
        df = df[df["bound"] == "Lower"].copy()
        if df.empty:
            return []
        path: list[dict[str, Any]] = []
        for year in sorted(df["year"].unique()):
            sub = df[df["year"] == year]
            weighted_terminal_value = float((sub["terminal_token_value_usd"] * sub["probability"]).sum())
            base_terminal_price = weighted_terminal_value / tokens_held
            scaled_terminal_price = base_terminal_price * (new_price / base_entry_price)
            path.append({"year": int(year), "expected_terminal_token_price_usd": scaled_terminal_price})
        return path

    reference_expected = scale_expected(base_expected, REFERENCE_PRICE_USD)
    live_expected = scale_expected(base_expected, live_price)
    pnl_refresh_payload = {
        "as_of_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "schema": "investor_probability_weighted_pnl_price_refresh_v1",
        "base_model_source": (tables_dir / "investor_probability_weighted_pnl.json").as_posix(),
        "assumption_held_constant": {
            "probabilities": assumptions.get("probabilities"),
            "price_elasticity": assumptions.get("price_to_tvl_elasticity"),
            "tokens_held": tokens_held,
            "horizon_years": assumptions.get("horizon_years"),
            "entry_price_original_usd": base_entry_price,
            "initial_position_original_usd": base_initial,
        },
        "reference_price_scenario": {
            "entry_price_usd": REFERENCE_PRICE_USD,
            "initial_position_value_usd": tokens_held * REFERENCE_PRICE_USD,
            "expected": reference_expected,
            "implied_expected_token_price_path": implied_terminal_price_path(REFERENCE_PRICE_USD),
        },
        "live_price_scenario": {
            "entry_price_usd": live_price,
            "initial_position_value_usd": tokens_held * live_price,
            "expected": live_expected,
            "implied_expected_token_price_path": implied_terminal_price_path(live_price),
        },
    }
    write_versioned_json("investor_probability_weighted_pnl_price_refresh", pnl_refresh_payload, tables_dir, stamp)
    write_versioned_csv(
        "investor_probability_weighted_pnl_price_refresh",
        headers=["bound", "year", "expected_total_value_usd", "expected_pnl_usd", "expected_annualized_return"],
        rows=[
            [
                row["bound"],
                row["year"],
                row["expected_total_value_usd"],
                row["expected_pnl_usd"],
                row["expected_annualized_return"],
            ]
            for row in reference_expected
        ],
        tables_dir=tables_dir,
        stamp=stamp,
    )
    return price_context_payload, pnl_refresh_payload


def run(
    monitoring_path: Path,
    evidence_dir: Path | None,
    tables_dir: Path,
    charts_dir: Path,
    snapshot_root: Path,
    rpc_url: str,
) -> None:
    monitoring = load_json(monitoring_path)

    if evidence_dir is None:
        monitoring_evidence_dir = monitoring.get("evidence_dir")
        if not monitoring_evidence_dir:
            raise ValueError("Could not resolve evidence directory from args or monitoring payload.")
        resolved_evidence_dir = Path(monitoring_evidence_dir)
    else:
        resolved_evidence_dir = evidence_dir

    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    snapshot_dir = snapshot_root / stamp
    snapshot_manifest = fetch_external_snapshots(snapshot_dir=snapshot_dir)

    latest_manifest_path = snapshot_root / "latest_manifest.json"
    save_json(
        latest_manifest_path,
        {
            "generated_utc": now.isoformat(),
            "latest_snapshot_dir": snapshot_dir.as_posix(),
            "manifest": snapshot_manifest,
        },
    )

    scenario_matrix = load_json(tables_dir / "scenario_matrix_latest.json")
    scenario_assumptions = load_json(tables_dir / "scenario_assumptions_latest.json")
    bounded_bands = load_json(tables_dir / "v2_bounded_decision_bands.json")

    benchmark_payload = build_peer_benchmarks(snapshot_dir=snapshot_dir, tables_dir=tables_dir, charts_dir=charts_dir)
    macro_payload = build_macro_context(snapshot_dir=snapshot_dir, tables_dir=tables_dir, charts_dir=charts_dir)
    pnl_payload = build_probability_weighted_pnl(
        snapshot_dir=snapshot_dir,
        monitoring=monitoring,
        scenario_assumptions=scenario_assumptions,
        scenario_matrix=scenario_matrix,
        bounded_bands=bounded_bands,
        tables_dir=tables_dir,
        charts_dir=charts_dir,
    )
    treasury_payload = build_treasury_runway_model(
        snapshot_dir=snapshot_dir,
        evidence_dir=resolved_evidence_dir,
        scenario_matrix=scenario_matrix,
        bounded_bands=bounded_bands,
        tables_dir=tables_dir,
        charts_dir=charts_dir,
        rpc_url=rpc_url,
    )
    staking_payload = build_staking_distribution(
        snapshot_contract_path=DATA_DIR
        / "snapshots"
        / "external_review"
        / "2026-02-09-independent"
        / "base_blockscout_summerstaking_contract.json",
        tables_dir=tables_dir,
        charts_dir=charts_dir,
        rpc_url=rpc_url,
    )
    upside_payload = build_upside_plausibility_artifacts(snapshot_dir=snapshot_dir, tables_dir=tables_dir, stamp=stamp)
    reconciliation_payload = build_verified_vs_external_reconciliation_artifacts(
        evidence_dir=resolved_evidence_dir,
        snapshot_manifest=snapshot_manifest,
        snapshot_dir=snapshot_dir,
        tables_dir=tables_dir,
        stamp=stamp,
    )
    price_context_payload, pnl_price_refresh_payload = build_price_and_pnl_refresh_artifacts(
        evidence_dir=resolved_evidence_dir,
        scenario_matrix=scenario_matrix,
        bounded_bands=bounded_bands,
        staking_payload=staking_payload,
        pnl_payload=pnl_payload,
        tables_dir=tables_dir,
        stamp=stamp,
    )

    output = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "schema": "investor_extended_summary_v1",
        "snapshot_dir": snapshot_dir.as_posix(),
        "snapshot_manifest": (snapshot_dir / "manifest.json").as_posix(),
        "latest_snapshot_pointer": latest_manifest_path.as_posix(),
        "artifacts": {
            "benchmark": (tables_dir / "investor_external_benchmark_peers.json").as_posix(),
            "macro": (tables_dir / "investor_macro_context.json").as_posix(),
            "pnl": (tables_dir / "investor_probability_weighted_pnl.json").as_posix(),
            "pnl_price_refresh": (tables_dir / "investor_probability_weighted_pnl_price_refresh_latest.json").as_posix(),
            "price_context_refresh": (tables_dir / "investor_price_context_refresh_latest.json").as_posix(),
            "upside_plausibility": (tables_dir / "investor_upside_plausibility_indicators_latest.json").as_posix(),
            "verified_vs_external_reconciliation": (tables_dir / "investor_verified_vs_external_reconciliation_latest.json").as_posix(),
            "treasury": (tables_dir / "investor_treasury_runway_model.json").as_posix(),
            "staking": (tables_dir / "investor_staking_distribution.json").as_posix(),
        },
        "highlights": {
            "benchmark_peer_count": benchmark_payload.get("peer_count"),
            "lending_tvl_total_usd": ((macro_payload.get("lending_market") or {}).get("tvl_total_usd")),
            "lazy_fee_share_of_global": ((macro_payload.get("lazy_summer_positioning") or {}).get("fee_share_of_global")),
            "pnl_probabilities": ((pnl_payload.get("assumptions") or {}).get("probabilities")),
            "reference_price_usd": ((price_context_payload.get("reference_price_analysis") or {}).get("price_usd")),
            "live_price_usd": ((price_context_payload.get("live_price_analysis") or {}).get("price_usd")),
            "fees_change_30d_pct": ((upside_payload.get("metrics") or {}).get("fees_change_30d_pct")),
            "reconciliation_rows": len(reconciliation_payload.get("rows") or []),
            "treasury_stable_reserve_usd": ((treasury_payload.get("reserve_snapshot") or {}).get("stable_reserve_usd")),
            "staking_active_positions": ((staking_payload.get("position_summary") or {}).get("active_position_count")),
        },
    }
    save_json(tables_dir / "investor_extended_summary.json", output)

    print(f"Wrote extended investor artifacts to {tables_dir}")
    print(f"External snapshot directory: {snapshot_dir}")


def main() -> None:
    default_monitoring_path = RESULTS_DIR / "tables" / "monitoring_latest.json"
    default_tables_dir = RESULTS_DIR / "tables"
    default_charts_dir = RESULTS_DIR / "charts"
    default_snapshot_root = DATA_DIR / "snapshots" / "investor_external"

    parser = argparse.ArgumentParser(description="Build extended investor-facing artifacts and charts.")
    parser.add_argument("--monitoring-path", type=Path, default=default_monitoring_path)
    parser.add_argument("--evidence-dir", type=Path, default=None)
    parser.add_argument("--tables-dir", type=Path, default=default_tables_dir)
    parser.add_argument("--charts-dir", type=Path, default=default_charts_dir)
    parser.add_argument("--snapshot-root", type=Path, default=default_snapshot_root)
    parser.add_argument("--rpc-url", type=str, default=BASE_RPC_URL or "https://base.drpc.org")
    args = parser.parse_args()

    run(
        monitoring_path=args.monitoring_path,
        evidence_dir=args.evidence_dir,
        tables_dir=args.tables_dir,
        charts_dir=args.charts_dir,
        snapshot_root=args.snapshot_root,
        rpc_url=args.rpc_url,
    )


if __name__ == "__main__":
    main()
