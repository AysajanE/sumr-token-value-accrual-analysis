"""
Generate investor-facing visualizations and executive summary from latest artifacts.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Iterable

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from src.config import PROJECT_ROOT, RESULTS_DIR


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = load_json(path)
    return payload if isinstance(payload, dict) else None


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_csv(path: Path, headers: list[str], rows: list[list[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)


def parse_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    return Decimal(str(value))


def fmt_num(value: Any, decimals: int = 2) -> str:
    amount = parse_decimal(value)
    if amount is None:
        return "n/a"
    quant = Decimal(1).scaleb(-decimals)
    rounded = amount.quantize(quant, rounding=ROUND_HALF_UP)
    return f"{rounded:,.{decimals}f}"


def fmt_usd(value: Any, decimals: int = 2) -> str:
    amount = parse_decimal(value)
    if amount is None:
        return "n/a"
    return f"${fmt_num(amount, decimals)}"


def fmt_pct(value: Any, decimals: int = 2) -> str:
    amount = parse_decimal(value)
    if amount is None:
        return "n/a"
    percent = amount * Decimal(100)
    quant = Decimal(1).scaleb(-decimals)
    rounded = percent.quantize(quant, rounding=ROUND_HALF_UP)
    return f"{rounded:.{decimals}f}%"


def fmt_ratio(value: Any, decimals: int = 3) -> str:
    amount = parse_decimal(value)
    if amount is None:
        return "n/a"
    quant = Decimal(1).scaleb(-decimals)
    rounded = amount.quantize(quant, rounding=ROUND_HALF_UP)
    return f"{rounded:.{decimals}f}x"


def fmt_address_short(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text.lower() == "none":
        return "n/a"
    if text.startswith("0x") and len(text) == 42:
        return f"{text[:6]}...{text[-4:]}"
    return text


def fmt_address_note(name: Any, evidence: Any) -> str:
    name_text = str(name or "").strip()
    if name_text:
        if name_text.lower() == "protocolaccessmanager":
            return "Access manager"
        return name_text
    evidence_text = str(evidence or "").strip()
    if not evidence_text:
        return "n/a"
    lowered = evidence_text.lower()
    if "protocolaccessmanager" in lowered or "access manager" in lowered:
        return "Access manager"
    if "creator" in lowered:
        return "Creator mapping"
    if "manifest" in lowered:
        return "Manifest evidence"
    if "constructor" in lowered:
        return "Constructor decode"
    if len(evidence_text) > 32:
        return evidence_text[:29] + "..."
    return evidence_text


def markdown_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return lines


def quantile(values: Iterable[Decimal], q: float) -> Decimal | None:
    ordered = sorted(values)
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    q_clamped = min(max(q, 0.0), 1.0)
    index = (len(ordered) - 1) * q_clamped
    lo = math.floor(index)
    hi = math.ceil(index)
    if lo == hi:
        return ordered[lo]
    fraction = Decimal(str(index - lo))
    return ordered[lo] + (ordered[hi] - ordered[lo]) * fraction


def select_scenario(
    scenarios: list[dict[str, Any]],
    tvl_multiplier: float,
    fee_rate: float,
    staker_share: float,
    staking_ratio: float,
) -> dict[str, Any] | None:
    for scenario in scenarios:
        if (
            math.isclose(float(scenario.get("tvl_multiplier")), tvl_multiplier, rel_tol=0.0, abs_tol=1e-9)
            and math.isclose(float(scenario.get("fee_rate")), fee_rate, rel_tol=0.0, abs_tol=1e-9)
            and math.isclose(float(scenario.get("staker_share")), staker_share, rel_tol=0.0, abs_tol=1e-9)
            and math.isclose(float(scenario.get("staking_ratio")), staking_ratio, rel_tol=0.0, abs_tol=1e-9)
        ):
            return scenario
    return None


def scenario_with_realization(scenario: dict[str, Any], realized_ratio: Decimal) -> dict[str, Decimal | None]:
    staker_revenue = parse_decimal(scenario.get("staker_revenue_usd")) or Decimal(0)
    yield_mcap = parse_decimal(scenario.get("revenue_yield_on_mcap"))
    yield_staked = parse_decimal(scenario.get("revenue_yield_on_staked"))
    return {
        "annual_upper": staker_revenue,
        "annual_lower": staker_revenue * realized_ratio,
        "yield_mcap_upper": yield_mcap,
        "yield_mcap_lower": (yield_mcap * realized_ratio) if yield_mcap is not None else None,
        "yield_staked_upper": yield_staked,
        "yield_staked_lower": (yield_staked * realized_ratio) if yield_staked is not None else None,
    }


def derive_investability_class(
    gate_passed: bool,
    bounded_status: str | None,
    open_high_ticket_count: int | None,
    source_of_funds_status: str | None,
) -> tuple[str, str]:
    high_tickets = int(open_high_ticket_count or 0)
    sof_status = source_of_funds_status or "UNKNOWN"
    if gate_passed and high_tickets == 0 and sof_status in {"PROVEN", "BOUNDED"}:
        return "STRICT_VALIDATED", "Strict gate and risk requirements met."
    if bounded_status == "READY_SUPPLEMENTAL_BOUNDED" and high_tickets == 0:
        return "CONDITIONAL_BOUNDED", "Evidence is investable with bounded-uncertainty framing; strict gate remains blocked."
    return "RESTRICTED", "Evidence remains constrained for conviction-grade sizing."


def investor_regime_label(classification_code: str) -> str:
    if classification_code == "STRICT_VALIDATED":
        return "STRICT"
    if classification_code == "CONDITIONAL_BOUNDED":
        return "CONDITIONAL"
    return "RESTRICTED"


def build_tvl_fees_chart(
    defillama_protocol_path: Path,
    defillama_fees_path: Path,
    output_path: Path,
) -> None:
    protocol = load_json(defillama_protocol_path)
    fees = load_json(defillama_fees_path)

    tvl = pd.DataFrame(protocol.get("tvl", []))
    tvl["date"] = pd.to_datetime(tvl["date"], unit="s", utc=True)
    tvl["totalLiquidityUSD"] = pd.to_numeric(tvl["totalLiquidityUSD"], errors="coerce")
    tvl = tvl.sort_values("date")

    fees_df = pd.DataFrame(fees.get("totalDataChart", []), columns=["date", "dailyFeesUSD"])
    fees_df["date"] = pd.to_datetime(fees_df["date"], unit="s", utc=True)
    fees_df["dailyFeesUSD"] = pd.to_numeric(fees_df["dailyFeesUSD"], errors="coerce")
    fees_df = fees_df.sort_values("date")
    fees_df["fees_30dma"] = fees_df["dailyFeesUSD"].rolling(30, min_periods=7).mean()

    sns.set_theme(style="whitegrid")
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True, constrained_layout=True)

    axes[0].plot(tvl["date"], tvl["totalLiquidityUSD"], color="#0b5cab", linewidth=2.0)
    axes[0].set_title("Lazy Summer TVL Trend", fontsize=13, weight="bold")
    axes[0].set_ylabel("TVL (USD)")
    axes[0].ticklabel_format(axis="y", style="plain")

    peak_idx = tvl["totalLiquidityUSD"].idxmax()
    latest_row = tvl.iloc[-1]
    axes[0].scatter(tvl.loc[peak_idx, "date"], tvl.loc[peak_idx, "totalLiquidityUSD"], color="#cc3d3d", s=30, zorder=3)
    axes[0].scatter(latest_row["date"], latest_row["totalLiquidityUSD"], color="#1f7a1f", s=30, zorder=3)
    axes[0].annotate(
        f"Peak: {tvl.loc[peak_idx, 'date'].strftime('%Y-%m-%d')}\n{fmt_usd(tvl.loc[peak_idx, 'totalLiquidityUSD'])}",
        xy=(tvl.loc[peak_idx, "date"], tvl.loc[peak_idx, "totalLiquidityUSD"]),
        xytext=(10, -35),
        textcoords="offset points",
        fontsize=9,
        bbox={"boxstyle": "round,pad=0.3", "facecolor": "white", "alpha": 0.8, "edgecolor": "#888"},
    )
    axes[0].annotate(
        f"Latest: {latest_row['date'].strftime('%Y-%m-%d')}\n{fmt_usd(latest_row['totalLiquidityUSD'])}",
        xy=(latest_row["date"], latest_row["totalLiquidityUSD"]),
        xytext=(-120, 12),
        textcoords="offset points",
        fontsize=9,
        bbox={"boxstyle": "round,pad=0.3", "facecolor": "white", "alpha": 0.8, "edgecolor": "#888"},
    )

    axes[1].bar(fees_df["date"], fees_df["dailyFeesUSD"], color="#6aaed6", width=1.0, alpha=0.6, label="Daily fees")
    axes[1].plot(fees_df["date"], fees_df["fees_30dma"], color="#123f75", linewidth=2.0, label="30d moving average")
    axes[1].set_title("Daily Fees (USD)", fontsize=13, weight="bold")
    axes[1].set_ylabel("Fees (USD/day)")
    axes[1].legend(loc="upper left")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=220)
    plt.close(fig)


def build_campaign_realization_chart(
    payout_summary_path: Path,
    output_path: Path,
) -> None:
    payload = load_json(payout_summary_path)
    campaigns = payload.get("campaigns", [])
    if not campaigns:
        return

    labels = [str(c.get("label")) for c in campaigns]
    claimed = [float(c.get("staker_revenue_claimed_tokens_attributed") or 0) for c in campaigns]
    residual = [float(c.get("staker_revenue_unclaimed_tokens_residual") or 0) for c in campaigns]
    confidence = [str(c.get("attribution_confidence_class", "n/a")) for c in campaigns]

    sns.set_theme(style="whitegrid")
    fig, ax = plt.subplots(figsize=(10, 6), constrained_layout=True)

    x = range(len(labels))
    ax.bar(x, claimed, color="#3a7ca5", label="Claimed attributed")
    ax.bar(x, residual, bottom=claimed, color="#d1495b", label="Unclaimed residual")
    ax.set_xticks(list(x), labels)
    ax.set_ylabel("Reward tokens")
    ax.set_title("Campaign Realization: Deposited vs Claimed vs Residual", fontsize=13, weight="bold")
    ax.legend(loc="upper right")

    for idx, (c_val, r_val, conf) in enumerate(zip(claimed, residual, confidence)):
        total = c_val + r_val
        ax.text(idx, total * 1.01 if total > 0 else 0.01, f"{fmt_pct((c_val / total) if total > 0 else 0)} realized\n{conf}", ha="center", va="bottom", fontsize=9)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=220)
    plt.close(fig)


def build_source_of_funds_chart(
    source_of_funds_monthly_path: Path,
    output_path: Path,
) -> None:
    rows = read_csv_rows(source_of_funds_monthly_path)
    df = pd.DataFrame(rows)
    if df.empty:
        return

    numeric_cols = [
        "fee_aligned_inflow_to_treasury_base",
        "staker_payout_outflow_from_treasury_base",
        "net_fee_inflow_minus_staker_payout",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    df["month_utc"] = pd.to_datetime(df["month_utc"], format="%Y-%m", utc=True, errors="coerce")

    grouped = (
        df.groupby("month_utc", as_index=False)[numeric_cols]
        .sum()
        .sort_values("month_utc")
    )

    sns.set_theme(style="whitegrid")
    fig, ax = plt.subplots(figsize=(11, 6), constrained_layout=True)
    x = range(len(grouped))
    width = 0.36

    ax.bar([i - width / 2 for i in x], grouped["fee_aligned_inflow_to_treasury_base"], width=width, label="Fee-aligned inflow", color="#2a9d8f")
    ax.bar([i + width / 2 for i in x], grouped["staker_payout_outflow_from_treasury_base"], width=width, label="Staker payout outflow", color="#e76f51")
    ax.plot(x, grouped["net_fee_inflow_minus_staker_payout"], color="#264653", marker="o", linewidth=2, label="Net inflow - payout")

    labels = [d.strftime("%Y-%m") for d in grouped["month_utc"]]
    ax.set_xticks(list(x), labels, rotation=45, ha="right")
    ax.set_ylabel("Token amount (native units)")
    ax.set_title("Treasury Source-of-Funds Monthly Comparison (Base)", fontsize=13, weight="bold")
    ax.legend(loc="upper left")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=220)
    plt.close(fig)


def build_scenario_heatmap_chart(
    scenario_matrix_path: Path,
    bounded_bands_path: Path,
    output_path: Path,
) -> None:
    scenario_payload = load_json(scenario_matrix_path)
    bounded = load_json(bounded_bands_path)
    scenarios = scenario_payload.get("scenarios", [])
    realized_ratio = float(parse_decimal((bounded.get("bounds_baseline") or {}).get("realized_ratio_lower_to_upper")) or Decimal(0))

    df = pd.DataFrame(scenarios)
    if df.empty:
        return

    for col in ["fee_rate", "staker_share", "staking_ratio", "tvl_multiplier", "revenue_yield_on_staked"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    base_df = df[
        df["fee_rate"].sub(0.0066).abs().lt(1e-9)
        & df["staker_share"].sub(0.20).abs().lt(1e-9)
    ].copy()
    if base_df.empty:
        return

    upper = base_df.pivot(index="staking_ratio", columns="tvl_multiplier", values="revenue_yield_on_staked").sort_index().sort_index(axis=1)
    lower = upper * realized_ratio

    upper_pct = upper * 100
    lower_pct = lower * 100

    sns.set_theme(style="whitegrid")
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5), constrained_layout=True)

    sns.heatmap(
        upper_pct,
        annot=True,
        fmt=".2f",
        cmap="YlGnBu",
        cbar_kws={"label": "Yield on staked value (%)"},
        ax=axes[0],
    )
    axes[0].set_title("Upper-Bound Yield Heatmap", fontsize=12, weight="bold")
    axes[0].set_xlabel("TVL multiplier")
    axes[0].set_ylabel("Staking ratio")

    sns.heatmap(
        lower_pct,
        annot=True,
        fmt=".2f",
        cmap="YlOrRd",
        cbar_kws={"label": "Yield on staked value (%)"},
        ax=axes[1],
    )
    axes[1].set_title("Lower-Bound Yield Heatmap", fontsize=12, weight="bold")
    axes[1].set_xlabel("TVL multiplier")
    axes[1].set_ylabel("Staking ratio")

    fig.suptitle("Yield Sensitivity: TVL Growth vs Staking Participation\n(Assumes 0.66% fee rate and 20% staker share)", fontsize=13, weight="bold")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=220)
    plt.close(fig)


def build_scenario_distribution_chart(
    scenario_matrix_path: Path,
    bounded_bands_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    scenario_payload = load_json(scenario_matrix_path)
    bounded = load_json(bounded_bands_path)
    scenarios = scenario_payload.get("scenarios", [])
    realized_ratio = parse_decimal((bounded.get("bounds_baseline") or {}).get("realized_ratio_lower_to_upper")) or Decimal(0)

    upper_yields: list[float] = []
    lower_yields: list[float] = []
    annual_upper: list[Decimal] = []
    annual_lower: list[Decimal] = []

    for s in scenarios:
        staker_share = parse_decimal(s.get("staker_share")) or Decimal(0)
        if staker_share <= 0:
            continue
        y_up = parse_decimal(s.get("revenue_yield_on_mcap"))
        rev_up = parse_decimal(s.get("staker_revenue_usd")) or Decimal(0)
        rev_lo = rev_up * realized_ratio
        annual_upper.append(rev_up)
        annual_lower.append(rev_lo)
        if y_up is not None:
            upper_yields.append(float(y_up))
            lower_yields.append(float(y_up * realized_ratio))

    sns.set_theme(style="whitegrid")
    fig, ax = plt.subplots(figsize=(10, 6), constrained_layout=True)
    if upper_yields:
        sns.histplot(upper_yields, bins=30, color="#5e60ce", alpha=0.45, label="Upper (full realization)", ax=ax, stat="density")
    if lower_yields:
        sns.histplot(lower_yields, bins=30, color="#ff9f1c", alpha=0.45, label="Lower (bounded realization)", ax=ax, stat="density")
    ax.set_title("Scenario Yield Distribution (Yield on Market Cap)", fontsize=13, weight="bold")
    ax.set_xlabel("Yield on market cap (decimal)")
    ax.set_ylabel("Density")
    ax.legend()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=220)
    plt.close(fig)

    quantiles = {
        "annual_staker_revenue_usd": {
            "lower_p10": float(quantile(annual_lower, 0.10)) if annual_lower else None,
            "lower_p50": float(quantile(annual_lower, 0.50)) if annual_lower else None,
            "lower_p90": float(quantile(annual_lower, 0.90)) if annual_lower else None,
            "upper_p10": float(quantile(annual_upper, 0.10)) if annual_upper else None,
            "upper_p50": float(quantile(annual_upper, 0.50)) if annual_upper else None,
            "upper_p90": float(quantile(annual_upper, 0.90)) if annual_upper else None,
        },
        "yield_on_mcap": {
            "lower_p10": float(quantile((Decimal(str(v)) for v in lower_yields), 0.10)) if lower_yields else None,
            "lower_p50": float(quantile((Decimal(str(v)) for v in lower_yields), 0.50)) if lower_yields else None,
            "lower_p90": float(quantile((Decimal(str(v)) for v in lower_yields), 0.90)) if lower_yields else None,
            "upper_p10": float(quantile((Decimal(str(v)) for v in upper_yields), 0.10)) if upper_yields else None,
            "upper_p50": float(quantile((Decimal(str(v)) for v in upper_yields), 0.50)) if upper_yields else None,
            "upper_p90": float(quantile((Decimal(str(v)) for v in upper_yields), 0.90)) if upper_yields else None,
        },
    }
    return quantiles


def build_reference_scenarios_chart(
    scenario_matrix_path: Path,
    bounded_bands_path: Path,
    output_path: Path,
) -> list[dict[str, Any]]:
    scenario_payload = load_json(scenario_matrix_path)
    bounded = load_json(bounded_bands_path)
    realized_ratio = parse_decimal((bounded.get("bounds_baseline") or {}).get("realized_ratio_lower_to_upper")) or Decimal(0)
    scenarios = scenario_payload.get("scenarios", [])

    specs = [
        ("Downside", 0.5, 0.0010, 0.10, 0.30),
        ("Base", 1.0, 0.0066, 0.20, 0.30),
        ("Upside", 2.0, 0.0100, 0.30, 0.30),
    ]

    rows: list[dict[str, Any]] = []
    for name, tvl_mult, fee_rate, staker_share, staking_ratio in specs:
        scenario = select_scenario(
            scenarios=scenarios,
            tvl_multiplier=tvl_mult,
            fee_rate=fee_rate,
            staker_share=staker_share,
            staking_ratio=staking_ratio,
        )
        if scenario is None:
            continue
        realized = scenario_with_realization(scenario, realized_ratio)
        rows.append(
            {
                "scenario_case": name,
                "tvl_multiplier": tvl_mult,
                "fee_rate": fee_rate,
                "staker_share": staker_share,
                "staking_ratio": staking_ratio,
                "annual_staker_usd_lower": float(realized["annual_lower"]) if realized["annual_lower"] is not None else None,
                "annual_staker_usd_upper": float(realized["annual_upper"]) if realized["annual_upper"] is not None else None,
                "yield_on_mcap_lower": float(realized["yield_mcap_lower"]) if realized["yield_mcap_lower"] is not None else None,
                "yield_on_mcap_upper": float(realized["yield_mcap_upper"]) if realized["yield_mcap_upper"] is not None else None,
                "yield_on_staked_lower": float(realized["yield_staked_lower"]) if realized["yield_staked_lower"] is not None else None,
                "yield_on_staked_upper": float(realized["yield_staked_upper"]) if realized["yield_staked_upper"] is not None else None,
            }
        )

    sns.set_theme(style="whitegrid")
    fig, ax = plt.subplots(figsize=(10, 6), constrained_layout=True)
    x = range(len(rows))
    lower = [r["annual_staker_usd_lower"] or 0 for r in rows]
    upper = [r["annual_staker_usd_upper"] or 0 for r in rows]
    labels = [r["scenario_case"] for r in rows]
    ax.bar([i - 0.18 for i in x], lower, width=0.36, color="#f4a261", label="Lower bound annual staker revenue")
    ax.bar([i + 0.18 for i in x], upper, width=0.36, color="#2a9d8f", label="Upper bound annual staker revenue")
    ax.set_xticks(list(x), labels)
    ax.set_ylabel("USD / year")
    ax.set_title("Reference Scenario Comparison (Investor Cases)", fontsize=13, weight="bold")
    ax.legend(loc="upper left")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=220)
    plt.close(fig)
    return rows


def build_probability_weighted_paths_chart(
    pnl_paths_csv_path: Path,
    pnl_payload: dict[str, Any] | None,
    pnl_price_refresh_payload: dict[str, Any] | None,
    output_path: Path,
) -> None:
    if not pnl_paths_csv_path.exists():
        return
    df = pd.read_csv(pnl_paths_csv_path)
    if df.empty:
        return

    for col in ["year", "total_value_usd"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["year", "total_value_usd", "scenario_case", "bound"])
    if df.empty:
        return

    base_initial = parse_decimal(((pnl_payload or {}).get("assumptions") or {}).get("initial_position_value_usd"))
    ref_initial = parse_decimal(((pnl_price_refresh_payload or {}).get("reference_price_scenario") or {}).get("initial_position_value_usd"))
    scale_factor = Decimal(1)
    if base_initial not in (None, Decimal(0)) and ref_initial not in (None, Decimal(0)):
        scale_factor = ref_initial / base_initial

    scaled_df = df.copy()
    scaled_df["total_value_usd"] = scaled_df["total_value_usd"] * float(scale_factor)

    refresh_expected = ((pnl_price_refresh_payload or {}).get("reference_price_scenario") or {}).get("expected") or []
    if refresh_expected:
        expected_df = pd.DataFrame(refresh_expected)
    else:
        expected_rows = (pnl_payload or {}).get("expected") or []
        expected_df = pd.DataFrame(expected_rows)
        if not expected_df.empty and "expected_total_value_usd" in expected_df.columns:
            expected_df["expected_total_value_usd"] = (
                pd.to_numeric(expected_df["expected_total_value_usd"], errors="coerce") * float(scale_factor)
            )

    sns.set_theme(style="whitegrid")
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5), constrained_layout=True)

    for idx, bound in enumerate(["Lower", "Upper"]):
        ax = axes[idx]
        sub = scaled_df[scaled_df["bound"] == bound]
        for case in ["Downside", "Base", "Upside"]:
            case_rows = sub[sub["scenario_case"] == case].sort_values("year")
            if case_rows.empty:
                continue
            ax.plot(case_rows["year"], case_rows["total_value_usd"], marker="o", label=case)

        if not expected_df.empty:
            expected_sub = expected_df[expected_df["bound"] == bound].copy()
            if not expected_sub.empty:
                expected_sub["year"] = pd.to_numeric(expected_sub["year"], errors="coerce")
                expected_sub["expected_total_value_usd"] = pd.to_numeric(
                    expected_sub["expected_total_value_usd"], errors="coerce"
                )
                expected_sub = expected_sub.sort_values("year")
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

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=220)
    plt.close(fig)


def build_staking_sensitivity_rows(
    scenario_matrix_path: Path,
    bounded_bands_path: Path,
) -> list[dict[str, Any]]:
    scenario_payload = load_json(scenario_matrix_path)
    bounded = load_json(bounded_bands_path)
    realized_ratio = parse_decimal((bounded.get("bounds_baseline") or {}).get("realized_ratio_lower_to_upper")) or Decimal(0)
    scenarios = scenario_payload.get("scenarios", [])

    rows: list[dict[str, Any]] = []
    for staking_ratio in [0.10, 0.30, 0.60]:
        scenario = select_scenario(
            scenarios=scenarios,
            tvl_multiplier=1.0,
            fee_rate=0.0066,
            staker_share=0.20,
            staking_ratio=staking_ratio,
        )
        if scenario is None:
            continue
        realized = scenario_with_realization(scenario, realized_ratio)
        rows.append(
            {
                "staking_ratio": staking_ratio,
                "annual_staker_usd_lower": float(realized["annual_lower"]) if realized["annual_lower"] is not None else None,
                "annual_staker_usd_upper": float(realized["annual_upper"]) if realized["annual_upper"] is not None else None,
                "yield_on_staked_lower": float(realized["yield_staked_lower"]) if realized["yield_staked_lower"] is not None else None,
                "yield_on_staked_upper": float(realized["yield_staked_upper"]) if realized["yield_staked_upper"] is not None else None,
                "yield_on_mcap_lower": float(realized["yield_mcap_lower"]) if realized["yield_mcap_lower"] is not None else None,
                "yield_on_mcap_upper": float(realized["yield_mcap_upper"]) if realized["yield_mcap_upper"] is not None else None,
            }
        )
    return rows


def build_markdown_summary(
    output_path: Path,
    tables_dir: Path,
    monitoring: dict[str, Any],
    kpi: dict[str, Any],
    tickets: dict[str, Any],
    source_of_funds: dict[str, Any],
    bounded_bands: dict[str, Any],
    scenario_assumptions: dict[str, Any],
    emissions: dict[str, Any],
    defillama_context: dict[str, Any],
    scenario_quantiles: dict[str, Any],
    reference_rows: list[dict[str, Any]],
    staking_sensitivity_rows: list[dict[str, Any]],
    benchmark_payload: dict[str, Any] | None,
    macro_payload: dict[str, Any] | None,
    treasury_payload: dict[str, Any] | None,
    staking_payload: dict[str, Any] | None,
    pnl_payload: dict[str, Any] | None,
    extended_snapshot_dir: str | None,
    chart_paths_relative: dict[str, str],
) -> None:
    latest = monitoring.get("latest", {})
    source_comp = source_of_funds.get("source_of_funds_comparison") or {}
    bounded_baseline = bounded_bands.get("bounds_baseline") or {}
    scenario_values = scenario_assumptions.get("assumptions") or {}
    token_price_pin = scenario_values.get("token_price_usd") or {}
    circ_supply_pin = scenario_values.get("circulating_supply_tokens") or {}

    investability_code, note = derive_investability_class(
        gate_passed=bool(latest.get("all_campaigns_pass")),
        bounded_status=latest.get("v2_bounded_band_status"),
        open_high_ticket_count=latest.get("open_high_ticket_count"),
        source_of_funds_status=source_comp.get("status"),
    )
    investability = investor_regime_label(investability_code)

    break_even_price = parse_decimal(
        ((emissions.get("usd_decomposition_formula") or {}).get("break_even_sumr_price_for_emissions_equal_revenue_deposited"))
    )
    token_price = parse_decimal(token_price_pin.get("value"))
    price_to_break_even = None
    if token_price is not None and break_even_price not in (None, Decimal(0)):
        price_to_break_even = token_price / break_even_price

    summer_nov_2024_tvl = defillama_context.get("summer_nearest_2024_11_01_tvl_usd")
    summer_nov_2024_date = defillama_context.get("summer_nearest_2024_11_01_date")
    key_rows = [
        ["Classification", investability],
        ["Latest TVL (Lazy Summer)", fmt_usd(kpi.get("lazy_latest_tvl_usd"))],
        ["Summer.fi TVL near 2024-11-01", f"{fmt_usd(summer_nov_2024_tvl)} ({summer_nov_2024_date or 'n/a'})"],
        ["30d Fees (derived)", fmt_usd(kpi.get("fees_derived_30d"))],
        ["90d Annualized Fees", fmt_usd(kpi.get("fees_derived_90d_annualized"))],
        ["Observed Fee Rate", fmt_pct(kpi.get("implied_fee_rate_vs_window_avg_tvl"))],
        ["Bounded Realization Ratio", fmt_pct(bounded_baseline.get("realized_ratio_lower_to_upper"))],
        ["Bounded Lower (USDC-eq)", fmt_usd(bounded_baseline.get("lower_bound_claimed_attributed_usdc_equivalent"))],
        ["Bounded Upper (USDC-eq)", fmt_usd(bounded_baseline.get("upper_bound_deposited_usdc_equivalent"))],
        ["Source-of-Funds Status", str(source_comp.get("status", "n/a"))],
        ["Comparable Coverage Ratio", fmt_ratio(source_comp.get("comparable_coverage_ratio"))],
        ["SUMR price break-even (emissions vs deposited revenue)", fmt_usd(break_even_price, 6)],
        ["Pinned price / break-even", fmt_ratio(price_to_break_even, 3)],
        ["Strict Gate Passed", str(latest.get("all_campaigns_pass"))],
        ["Open High-Severity Tickets", str(latest.get("open_high_ticket_count"))],
        ["Pinned Token Price", f"{fmt_usd(token_price_pin.get('value'), 6)} ({token_price_pin.get('source_label') or token_price_pin.get('source_kind')})"],
        ["Pinned Circulating Supply", fmt_num(circ_supply_pin.get("value"), 6)],
    ]

    quant_rows = [
        [
            "Annual Staker Revenue (USD)",
            fmt_usd((scenario_quantiles.get("annual_staker_revenue_usd") or {}).get("lower_p10")),
            fmt_usd((scenario_quantiles.get("annual_staker_revenue_usd") or {}).get("lower_p50")),
            fmt_usd((scenario_quantiles.get("annual_staker_revenue_usd") or {}).get("lower_p90")),
            fmt_usd((scenario_quantiles.get("annual_staker_revenue_usd") or {}).get("upper_p10")),
            fmt_usd((scenario_quantiles.get("annual_staker_revenue_usd") or {}).get("upper_p50")),
            fmt_usd((scenario_quantiles.get("annual_staker_revenue_usd") or {}).get("upper_p90")),
        ],
        [
            "Yield on Market Cap",
            fmt_pct((scenario_quantiles.get("yield_on_mcap") or {}).get("lower_p10")),
            fmt_pct((scenario_quantiles.get("yield_on_mcap") or {}).get("lower_p50")),
            fmt_pct((scenario_quantiles.get("yield_on_mcap") or {}).get("lower_p90")),
            fmt_pct((scenario_quantiles.get("yield_on_mcap") or {}).get("upper_p10")),
            fmt_pct((scenario_quantiles.get("yield_on_mcap") or {}).get("upper_p50")),
            fmt_pct((scenario_quantiles.get("yield_on_mcap") or {}).get("upper_p90")),
        ],
    ]

    reference_cashflow_rows: list[list[str]] = []
    reference_yield_rows: list[list[str]] = []
    for row in reference_rows:
        reference_cashflow_rows.append(
            [
                str(row.get("scenario_case")),
                f"{row.get('tvl_multiplier'):.1f}x / {row.get('fee_rate'):.2%} / {row.get('staker_share'):.0%}",
                fmt_usd(row.get("annual_staker_usd_lower")),
                fmt_usd(row.get("annual_staker_usd_upper")),
            ]
        )
        reference_yield_rows.append(
            [
                str(row.get("scenario_case")),
                f"staking {row.get('staking_ratio'):.0%}",
                fmt_pct(row.get("yield_on_mcap_lower")),
                fmt_pct(row.get("yield_on_mcap_upper")),
                fmt_pct(row.get("yield_on_staked_lower")),
                fmt_pct(row.get("yield_on_staked_upper")),
            ]
        )

    ticket_open = [t for t in tickets.get("tickets", []) if t.get("status") == "OPEN"]
    open_ticket_text = ", ".join(f"{t.get('ticket_id')} ({t.get('severity')})" for t in ticket_open) if ticket_open else "none"

    benchmark_rows_raw = (benchmark_payload or {}).get("peers") or []
    benchmark_rows = []
    for row in benchmark_rows_raw[:10]:
        benchmark_rows.append(
            [
                str(row.get("name", "n/a")),
                fmt_usd(row.get("latest_tvl_usd")),
                fmt_usd(row.get("fees_30d_usd")),
                fmt_pct(row.get("annualized_fee_rate_on_tvl")),
                fmt_pct(row.get("annualized_holders_yield_on_tvl")),
            ]
        )

    macro_lending = ((macro_payload or {}).get("lending_market") or {})
    macro_global = ((macro_payload or {}).get("global_market") or {})
    macro_lazy = ((macro_payload or {}).get("lazy_summer_positioning") or {})
    macro_rows = [
        ["Global DeFi", str(macro_global.get("protocol_count", "n/a")), fmt_usd(macro_global.get("tvl_total_usd")), fmt_usd(macro_global.get("fees_30d_usd")), "n/a"],
        ["Lending category", str(macro_lending.get("protocol_count", "n/a")), fmt_usd(macro_lending.get("tvl_total_usd")), fmt_usd(macro_lending.get("fees_30d_usd")), "n/a"],
        [
            "Lazy Summer",
            str(macro_lazy.get("rank_by_tvl_within_yield_aggregators", "n/a")),
            fmt_usd(macro_lazy.get("latest_tvl_usd")),
            fmt_usd(macro_lazy.get("fees_30d_usd")),
            fmt_pct(macro_lazy.get("fee_share_of_global"), 4),
        ],
    ]

    treasury_rows_raw = (treasury_payload or {}).get("rows") or []
    treasury_rows = []
    for row in treasury_rows_raw:
        if row.get("opex_case") != "BASE":
            continue
        treasury_rows.append(
            [
                f"{row.get('scenario_case')} ({row.get('bound')})",
                fmt_usd(row.get("retained_before_opex_usd")),
                fmt_usd(row.get("annual_opex_usd")),
                fmt_usd(row.get("annual_net_treasury_cashflow_usd")),
                "Self-funding" if row.get("annual_net_treasury_cashflow_usd", 0) >= 0 else fmt_num(row.get("runway_years_stable_reserve"), 2),
            ]
        )

    staking_summary = (staking_payload or {}).get("position_summary") or {}
    staking_lockup_rows_raw = (staking_payload or {}).get("lockup_distribution") or []
    staking_lockup_rows = []
    for row in staking_lockup_rows_raw:
        staking_lockup_rows.append(
            [
                str(row.get("lockup_bucket", "n/a")),
                str(int(row.get("position_count", 0))),
                fmt_num(row.get("total_amount_sumr"), 2),
                fmt_num(row.get("total_weighted_sumr"), 2),
            ]
        )

    pnl_probs = ((pnl_payload or {}).get("assumptions") or {}).get("probabilities") or {}
    pnl_expected_raw = (pnl_payload or {}).get("expected") or []
    pnl_expected_rows = []
    for row in pnl_expected_raw:
        pnl_expected_rows.append(
            [
                f"{row.get('bound')} Y{row.get('year')}",
                fmt_usd(row.get("expected_total_value_usd")),
                fmt_usd(row.get("expected_pnl_usd")),
                fmt_pct(row.get("expected_annualized_return")),
            ]
        )

    lazy_peak_tvl = parse_decimal(kpi.get("lazy_peak_tvl_usd"))
    lazy_latest_tvl = parse_decimal(kpi.get("lazy_latest_tvl_usd"))
    lazy_drawdown_from_peak = None
    if lazy_peak_tvl not in (None, Decimal(0)) and lazy_latest_tvl is not None:
        lazy_drawdown_from_peak = Decimal(1) - (lazy_latest_tvl / lazy_peak_tvl)

    ticket_summary = tickets.get("summary") or {}
    severity_counts = ticket_summary.get("severity_counts") or {}
    status_counts = ticket_summary.get("status_counts") or {}
    closed_ticket_count = int(status_counts.get("RESOLVED", 0))

    benchmark_generated_utc = (benchmark_payload or {}).get("generated_utc")
    macro_generated_utc = (macro_payload or {}).get("generated_utc")
    treasury_assumptions = (treasury_payload or {}).get("assumptions") or {}
    treasury_reserve = (treasury_payload or {}).get("reserve_snapshot") or {}
    pnl_assumptions = (pnl_payload or {}).get("assumptions") or {}
    pnl_prob_method = pnl_assumptions.get("probability_method") or {}
    extended_snapshot_label = "n/a"
    if extended_snapshot_dir:
        extended_snapshot_label = Path(extended_snapshot_dir).name

    total_staked_sumr = parse_decimal(staking_summary.get("total_staked_sumr"))
    top_stakers = (staking_payload or {}).get("top_stakers") or []
    top1_share = None
    top10_share = None
    if total_staked_sumr not in (None, Decimal(0)) and top_stakers:
        top1_amount = parse_decimal(top_stakers[0].get("total_amount_sumr")) if top_stakers[0] else None
        if top1_amount is not None:
            top1_share = top1_amount / total_staked_sumr
        top10_amount = Decimal(0)
        for staker in top_stakers[:10]:
            amount = parse_decimal(staker.get("total_amount_sumr"))
            if amount is not None:
                top10_amount += amount
        top10_share = top10_amount / total_staked_sumr

    def read_optional_csv(path: Path) -> list[dict[str, str]]:
        if not path.exists():
            return []
        return read_csv_rows(path)

    tokenomics_payload = load_optional_json(tables_dir / "investor_tokenomics_snapshot_latest.json") or {}
    staking_assumptions_payload = load_optional_json(tables_dir / "investor_staking_assumptions_latest.json") or {}
    upside_payload = load_optional_json(tables_dir / "investor_upside_plausibility_indicators_latest.json") or {}
    pnl_price_refresh_payload = load_optional_json(tables_dir / "investor_probability_weighted_pnl_price_refresh_latest.json") or {}

    reconcile_rows_raw = read_optional_csv(tables_dir / "investor_verified_vs_external_reconciliation_latest.csv")
    unlock_rows_raw = read_optional_csv(tables_dir / "investor_unlock_schedule_next_24m_latest.csv")
    address_rows_raw = read_optional_csv(tables_dir / "investor_onchain_address_map_latest.csv")
    security_rows_raw = read_optional_csv(tables_dir / "investor_security_posture_latest.csv")
    liquidity_rows_raw = read_optional_csv(tables_dir / "investor_liquidity_market_structure_latest.csv")

    tokenomics_onchain = tokenomics_payload.get("onchain") or {}
    tokenomics_model = tokenomics_payload.get("tokenomics_model") or {}
    onchain_sumr = tokenomics_onchain.get("sumr") or {}
    onchain_balances = tokenomics_onchain.get("sumr_balances_tokens") or {}

    max_supply_tokens = Decimal("1000000000")
    total_supply_tokens = parse_decimal(onchain_sumr.get("total_supply_tokens"))
    remaining_mintable_tokens = (
        max_supply_tokens - total_supply_tokens
        if total_supply_tokens is not None
        else None
    )
    circulating_at_tte = parse_decimal(tokenomics_model.get("circulating_supply_at_tte_tokens"))
    non_circulating_modeled = (
        max_supply_tokens - circulating_at_tte
        if circulating_at_tte is not None
        else None
    )

    ref_price_scenario = (pnl_price_refresh_payload.get("reference_price_scenario") or {})
    ref_entry_price = parse_decimal(ref_price_scenario.get("entry_price_usd"))
    ref_initial_position = parse_decimal(ref_price_scenario.get("initial_position_value_usd"))

    tvl_reconcile_row = next((r for r in reconcile_rows_raw if "TVL" in (r.get("metric") or "")), None)
    fees_reconcile_row = next((r for r in reconcile_rows_raw if "Fees 30d" in (r.get("metric") or "")), None)

    unlock_12 = unlock_rows_raw[:12]
    unlock_24 = unlock_rows_raw[:24]
    unlock_12_total = sum(parse_decimal(r.get("monthly_emitted_tokens")) or Decimal(0) for r in unlock_12)
    unlock_24_total = sum(parse_decimal(r.get("monthly_emitted_tokens")) or Decimal(0) for r in unlock_24)

    destination_cols = [
        ("category_1_community_tokens", "Community"),
        ("category_2_stakeholders_tokens", "Stakeholders"),
        ("category_3a_core_tb_mb_tokens", "Core TB/MB"),
        ("category_3b_core_tb_tokens", "Core TB"),
        ("category_3c_core_unallocated_tokens", "Core unallocated"),
        ("category_4_foundation_tokens", "Foundation"),
    ]
    destination_rows: list[list[str]] = []
    for col, label in destination_cols:
        sum_12 = sum(parse_decimal(r.get(col)) or Decimal(0) for r in unlock_12)
        sum_24 = sum(parse_decimal(r.get(col)) or Decimal(0) for r in unlock_24)
        destination_rows.append([label, fmt_num(sum_12, 0), fmt_num(sum_24, 0)])

    base_reference_row = next((r for r in reference_rows if str(r.get("scenario_case")) == "Base"), None)
    base_cashflow_lower = parse_decimal((base_reference_row or {}).get("annual_staker_usd_lower"))
    base_cashflow_upper = parse_decimal((base_reference_row or {}).get("annual_staker_usd_upper"))
    break_even_emission_lower = (
        base_cashflow_lower / break_even_price
        if base_cashflow_lower is not None and break_even_price not in (None, Decimal(0))
        else None
    )
    break_even_emission_upper = (
        base_cashflow_upper / break_even_price
        if base_cashflow_upper is not None and break_even_price not in (None, Decimal(0))
        else None
    )

    unlock_12_usd = (unlock_12_total * ref_entry_price) if ref_entry_price is not None else None
    unlock_24_usd = (unlock_24_total * ref_entry_price) if ref_entry_price is not None else None
    unlock_12_vs_lower = (
        unlock_12_usd / base_cashflow_lower
        if unlock_12_usd is not None and base_cashflow_lower not in (None, Decimal(0))
        else None
    )
    unlock_12_vs_upper = (
        unlock_12_usd / base_cashflow_upper
        if unlock_12_usd is not None and base_cashflow_upper not in (None, Decimal(0))
        else None
    )
    unlock_24_vs_lower = (
        unlock_24_usd / base_cashflow_lower
        if unlock_24_usd is not None and base_cashflow_lower not in (None, Decimal(0))
        else None
    )
    unlock_24_vs_upper = (
        unlock_24_usd / base_cashflow_upper
        if unlock_24_usd is not None and base_cashflow_upper not in (None, Decimal(0))
        else None
    )

    staking_snapshot = (staking_assumptions_payload.get("staking_snapshot") or {})
    investor_assumption = (staking_assumptions_payload.get("investor_position_assumption") or {})
    multiplier_sensitivity = (staking_assumptions_payload.get("multiplier_sensitivity") or {})

    liquidity_row = liquidity_rows_raw[0] if liquidity_rows_raw else {}
    security_row = security_rows_raw[0] if security_rows_raw else {}

    address_by_role = {str(row.get("role")): row for row in address_rows_raw}
    address_focus = [
        ("fee_collector_tipjar_base", "Fee collector (TipJar)", "Base"),
        ("distributor_proxy", "Distributor proxy", "Base"),
        ("distributor_implementation", "Distributor implementation", "Base"),
        ("treasury_wallet", "Treasury wallet", "Base"),
        ("foundation_tipstream_safe", "Tipstream safe custody", "Base"),
        ("distribution_creator_deployer", "Distribution creator/deployer", "Base"),
        ("protocol_access_manager", "Access manager module", "Base"),
    ]
    address_rows: list[list[str]] = []
    for role_key, role_label, chain_label in address_focus:
        row = address_by_role.get(role_key) or {}
        verified_value = str(row.get("is_verified") or "").strip().lower()
        confidence = "High" if verified_value == "true" else ("Low" if verified_value == "false" else "n/a")
        address_rows.append(
            [
                role_label,
                chain_label,
                f"`{fmt_address_short(row.get('address'))}`",
                confidence,
                fmt_address_note(row.get("name"), row.get("evidence")),
            ]
        )

    scenario_expected = ref_price_scenario.get("expected") or []
    lower_expected = [r for r in scenario_expected if r.get("bound") == "Lower"]
    upper_expected = [r for r in scenario_expected if r.get("bound") == "Upper"]

    upside_metrics = (upside_payload.get("metrics") or {})
    verified_fee_productivity = parse_decimal(kpi.get("implied_fee_rate_vs_window_avg_tvl"))
    live_fees_30d = parse_decimal(upside_metrics.get("fees_30d_usd"))
    live_latest_tvl = parse_decimal(upside_metrics.get("latest_tvl_usd"))
    live_fee_productivity = (
        (live_fees_30d * Decimal(365) / Decimal(30)) / live_latest_tvl
        if live_fees_30d is not None and live_latest_tvl not in (None, Decimal(0))
        else None
    )
    upside_table = [
        [
            "TVL drawdown from peak",
            f"{fmt_num(upside_metrics.get('drawdown_from_peak_pct'), 2)}%",
            "Weak for upside",
        ],
        [
            "TVL change, last 30d",
            f"{fmt_num(upside_metrics.get('tvl_change_30d_pct'), 2)}%",
            "Weak for upside",
        ],
        [
            "TVL change, last 90d",
            f"{fmt_num(upside_metrics.get('tvl_change_90d_pct'), 2)}%",
            "Weak for upside",
        ],
        [
            "Fees change, latest 30d vs prior 30d",
            f"{fmt_num(upside_metrics.get('fees_change_30d_pct'), 2)}%",
            "Weak for upside",
        ],
        [
            "Fee productivity (30d annualized fees / latest TVL)",
            fmt_pct(live_fee_productivity, 3),
            "Live run-rate lens; directly comparable to current TVL scale",
        ],
        [
            "Assumed holders-revenue yield on TVL",
            fmt_pct(
                (live_fee_productivity * parse_decimal(upside_metrics.get("holder_fee_split_assumption")))
                if live_fee_productivity is not None
                else None,
                3,
            ),
            "Still modest without re-acceleration",
        ],
    ]

    staking_table_rows: list[list[str]] = []
    for row in staking_sensitivity_rows:
        staking_table_rows.append(
            [
                f"{(row.get('staking_ratio') or 0) * 100:.2f}%",
                fmt_pct(row.get("yield_on_staked_lower")),
                fmt_pct(row.get("yield_on_staked_upper")),
            ]
        )

    reconciliation_table_rows = []
    if tvl_reconcile_row:
        reconciliation_table_rows.append(
            [
                "Lazy Summer TVL (USD)",
                fmt_num(tvl_reconcile_row.get("verified_value"), 2),
                fmt_num(tvl_reconcile_row.get("external_value"), 2),
                fmt_pct(tvl_reconcile_row.get("delta_pct_of_verified")),
                str(tvl_reconcile_row.get("valuation_source_of_truth") or "n/a"),
            ]
        )
    if fees_reconcile_row:
        reconciliation_table_rows.append(
            [
                "Lazy Summer Fees 30d (USD)",
                fmt_num(fees_reconcile_row.get("verified_value"), 2),
                fmt_num(fees_reconcile_row.get("external_value"), 2),
                fmt_pct(fees_reconcile_row.get("delta_pct_of_verified")),
                str(fees_reconcile_row.get("valuation_source_of_truth") or "n/a"),
            ]
        )

    unlock_schedule_rows = []
    for row in unlock_12:
        unlock_schedule_rows.append(
            [
                str(row.get("period") or "n/a"),
                str(row.get("date") or "n/a"),
                fmt_num(row.get("monthly_emitted_tokens"), 0),
                f"{fmt_num(row.get('cumulative_emitted_pct'), 2)}%",
            ]
        )

    price_to_break_even = (
        (ref_entry_price / break_even_price)
        if ref_entry_price is not None and break_even_price not in (None, Decimal(0))
        else None
    )
    discount_to_break_even = (
        Decimal(1) - price_to_break_even
        if price_to_break_even is not None
        else None
    )
    bounded_realization_ratio = parse_decimal(bounded_baseline.get("realized_ratio_lower_to_upper"))
    fee_productivity_floor = Decimal("0.005")
    fee_floor_status = "above" if verified_fee_productivity is not None and verified_fee_productivity >= fee_productivity_floor else "below"
    cashflow_low_k = (base_cashflow_lower / Decimal("1000")) if base_cashflow_lower is not None else None
    cashflow_high_k = (base_cashflow_upper / Decimal("1000")) if base_cashflow_upper is not None else None
    dilution_ratios = [unlock_12_vs_lower, unlock_12_vs_upper, unlock_24_vs_lower, unlock_24_vs_upper]
    dilution_ratios_double_digit = all(r is not None and r >= Decimal("10") for r in dilution_ratios)
    investability_lower = str(investability).lower()

    lines = [
        "---",
        "title: SUMR Investor Executive Summary",
        "---",
        "",
        "# Executive Summary",
        "",
        f"Classification remains **{investability}**: value accrual is real on-chain, but full institutional attribution confidence is still bounded.",
        "",
        "Why the mechanism can work:",
        "",
        f"1. The mechanism works only if fee productivity remains near or above a 0.50% annualized-on-TVL floor (verified lens currently {fmt_pct(verified_fee_productivity, 3)}, {fee_floor_status} that floor) and governance routes a stable, auditable share of fees to stakers.",
        f"2. Bounded realization ratio ({fmt_pct(bounded_realization_ratio)}): conservative share of claimed distributions directly evidenced on-chain via source-of-funds mapping. This is an evidence-coverage statistic, not a missing-funds claim; underwriting target remains >=80% for >=60 consecutive days.",
        f"3. At {fmt_usd(ref_entry_price, 6)}, SUMR trades at {fmt_ratio(price_to_break_even, 3)} of modeled reward-emission break-even ({fmt_usd(break_even_price, 6)}), about {fmt_pct(discount_to_break_even)} below the level where expected annual staker cash distributions would equal modeled annual reward emissions in USD terms; this is a sustainability signal, not a full valuation model.",
        "",
        "Kill switches (explicit invalidation triggers):",
        "",
        "1. Fee productivity falls below 0.30% annualized for 90 consecutive days.",
        "2. Governance controls are not hardened (no published privileged role-member map and no effective routing/upgrade timelocks).",
        "3. Evidence coverage remains below 80% for 60 consecutive days with unresolved discrepancy tickets.",
        "4. Newly liquid supply accelerates without offsetting mitigation (lock extensions, emission reductions, or buyback/sink policy).",
        "",
        "Key blockers to institutional underwriting (current):",
        "",
        "1. Attribution quality is below high-confidence threshold (>=80% for >=60 consecutive days) and open discrepancy tickets remain.",
        "2. Dilution and newly liquid supply overhang remain large versus modeled staker cash distributions.",
        "3. Governance/control transparency is incomplete for privileged roles and routing constraints.",
        "",
        "> **What you're underwriting (compact):** Fee persistence plus governance routing to holders, at a discount to modeled reward-emission break-even, with known risks: thin liquidity, holder concentration, unlock overhang, and control risk.",
        "",
        "# Current Snapshot",
        "",
    ]
    lines.extend(
        markdown_table(
            ["Item", "Value"],
            [
                ["Reference price", fmt_usd(ref_entry_price, 6)],
                ["Model entry position (1,000,000 SUMR)", fmt_usd(ref_initial_position)],
                ["Circulating supply (on-chain totalSupply snapshot)", f"{fmt_num(total_supply_tokens, 2)} SUMR"],
                ["Market cap at reference price", fmt_usd((total_supply_tokens * ref_entry_price) if total_supply_tokens is not None and ref_entry_price is not None else None)],
                ["Break-even price", fmt_usd(break_even_price, 6)],
                ["Price to break-even", fmt_ratio((ref_entry_price / break_even_price) if ref_entry_price is not None and break_even_price not in (None, Decimal(0)) else None, 3)],
                ["Lazy Summer TVL (verified baseline)", fmt_usd((tvl_reconcile_row or {}).get("verified_value"))],
                ["TVL drawdown from peak", fmt_pct(lazy_drawdown_from_peak)],
                ["Fees, last 30 days (verified baseline)", fmt_usd((fees_reconcile_row or {}).get("verified_value"))],
                ["Fee productivity (90d annualized fees / 90d avg TVL, verified lens)", fmt_pct(verified_fee_productivity, 3)],
                ["Fee productivity (30d annualized fees / latest TVL, live lens)", fmt_pct(live_fee_productivity, 3)],
                ["Fee trend vs prior 30 days (live external)", f"{fmt_num(upside_metrics.get('fees_change_30d_pct'), 2)}%"],
            ],
        )
    )
    lines.extend(
        [
            "",
            f"![TVL and Fees Trend]({chart_paths_relative['tvl_fees']})",
            "",
            "# Verified vs External Data Reconciliation",
            "",
            "This table reconciles frozen verification baselines versus live external snapshots to avoid source mixing.",
            "Fee productivity lenses: verified uses 90d annualized fees / 90d average TVL; live uses 30d annualized fees / latest TVL.",
            "",
        ]
    )
    lines.extend(
        markdown_table(
            ["Metric", "Verified baseline", "External snapshot", "Delta vs verified", "Valuation source-of-truth"],
            reconciliation_table_rows if reconciliation_table_rows else [["n/a", "n/a", "n/a", "n/a", "n/a"]],
        )
    )
    lines.extend(
        [
            "",
            "# Value Accrual and Evidence Quality",
            "",
            "Observed economic split remains 70% depositors / 20% stakers / 10% treasury. Mechanism existence is supported by routing and payout evidence, but campaign attribution remains bounded.",
            "",
            f"![Campaign Realization Quality]({chart_paths_relative['campaign_realization']})",
            "",
            f"![Source-of-Funds Monthly Comparison]({chart_paths_relative['source_of_funds']})",
            "",
            "# Supply and dilution: (i) vesting/unlocks, (ii) reward emissions, and (iii) implied sell-pressure (scenario-based)",
            "",
            "Dilution remains central because investor return is net of newly liquid supply pressure and reward-emission policy.",
            "",
            "## Supply and Dilution Waterfall (vesting/unlocks context)",
            "",
        ]
    )
    lines.extend(
        markdown_table(
            ["Bucket", "Tokens", "Notes"],
            [
                ["Max supply hard cap", fmt_num(max_supply_tokens, 2), "Contract-level cap"],
                ["Current on-chain total supply", fmt_num(total_supply_tokens, 2), "Minted supply snapshot"],
                ["Remaining mintable to cap", fmt_num(remaining_mintable_tokens, 2), "Max supply minus on-chain supply"],
                ["Modeled circulating at TTE", fmt_num(circulating_at_tte, 2), "Tokenomics sheet model input"],
                ["Modeled non-circulating/unvested", fmt_num(non_circulating_modeled, 2), "1B minus modeled circulating"],
                ["On-chain treasury wallet balance", fmt_num(onchain_balances.get("treasury"), 2), "Address map treasury wallet"],
                ["On-chain distributor balance", fmt_num(onchain_balances.get("distributor"), 2), "Address map distributor pipeline"],
            ],
        )
    )
    lines.extend(
        [
            "",
            "## Monthly Newly Liquid Supply Schedule (next 12 months)",
            "",
        ]
    )
    lines.extend(
        markdown_table(
            ["Period", "Date", "Monthly newly liquid SUMR", "Cumulative newly liquid % of max supply"],
            unlock_schedule_rows if unlock_schedule_rows else [["n/a", "n/a", "n/a", "n/a"]],
        )
    )
    lines.extend(
        [
            "",
            "Destination split from modeled newly-liquid supply schedule:",
            "",
        ]
    )
    lines.extend(
        markdown_table(
            ["Destination category", "Next 12 months SUMR", "Next 24 months SUMR"],
            destination_rows if destination_rows else [["n/a", "n/a", "n/a"]],
        )
    )
    lines.extend(
        [
            "",
            f"Estimated annual cash distributions to stakers (USD): {fmt_usd(base_cashflow_lower)} ({fmt_num(cashflow_low_k, 1)}k, low) to {fmt_usd(base_cashflow_upper)} ({fmt_num(cashflow_high_k, 1)}k, high).",
            "(Note: protocol-side outflow, staker-side inflow.)",
            "",
            "## Net Dilution Pressure vs Expected Staker Cash Distribution",
            "",
        ]
    )
    lines.extend(
        markdown_table(
            [
                "Horizon",
                "Modeled newly liquid SUMR (unlocks + scheduled emissions)",
                "Implied USD value",
                f"Ratio vs lower cashflow ({fmt_usd(base_cashflow_lower)})",
                f"Ratio vs upper cashflow ({fmt_usd(base_cashflow_upper)})",
            ],
            [
                [
                    "Next 12 months",
                    fmt_num(unlock_12_total, 0),
                    fmt_usd(unlock_12_usd),
                    fmt_ratio(unlock_12_vs_lower, 2),
                    fmt_ratio(unlock_12_vs_upper, 2),
                ],
                [
                    "Next 24 months",
                    fmt_num(unlock_24_total, 0),
                    fmt_usd(unlock_24_usd),
                    fmt_ratio(unlock_24_vs_lower, 2),
                    fmt_ratio(unlock_24_vs_upper, 2),
                ],
            ],
        )
    )
    lines.extend(
        [
            "",
            "The ratio NewlyLiquidSupply_USD (unlocks + scheduled emissions) / Cash_to_Stakers tests whether supply expansion is plausibly offset by distributable cashflow.",
            (
                "Current modeled ratios remain in double digits across both 12- and 24-month horizons, implying cashflow is presently too small to absorb dilution without TVL/fee growth or explicit supply-control measures."
                if dilution_ratios_double_digit
                else "Current modeled ratios do not remain uniformly in double digits, but still indicate dilution pressure requires active monitoring versus cashflow."
            ),
            "",
            "## Break-Even Definition and Inputs",
            "",
            "Break-even is defined as:",
            "",
            "$$",
            r"P_{\text{break-even}} = \frac{C_{\text{stakers}}}{E_{\text{SUMR}}}",
            "$$",
            "",
            f"- C_stakers (annual cash distributions to stakers): lower {fmt_usd(base_cashflow_lower)}, upper {fmt_usd(base_cashflow_upper)} (staker inflow sign convention).",
            f"- E_SUMR (annual reward emissions to stakers used in incentive distribution): lower bound {fmt_num(break_even_emission_lower, 0)} SUMR/year, upper bound {fmt_num(break_even_emission_upper, 0)} SUMR/year.",
            "- E_SUMR is not total vesting unlocks. Newly liquid supply from vesting/unlocks is modeled separately in the dilution schedule above.",
            "- Break-even is a sustainability threshold under stated assumptions, not an intrinsic valuation model.",
            "- Emission routing is governance-sensitive and not immutable.",
            "- Attribution remains bounded; treat break-even as a bounded range, not a single hard floor.",
            "",
            "# Staking Economics",
            "",
            "Rewards are distributed pro rata to weighted stake, not raw stake.",
            "",
        ]
    )
    lines.extend(
        markdown_table(
            ["Assumption item", "Value"],
            [
                ["Investor tokens", f"{fmt_num(investor_assumption.get('investor_tokens'), 0)} SUMR"],
                ["Reward allocation basis", str(investor_assumption.get("reward_allocation_basis") or "n/a")],
                ["Base assumed investor multiplier", f"{fmt_num(investor_assumption.get('base_assumed_investor_multiplier'), 4)}x"],
                ["Base assumed weighted investor stake", f"{fmt_num(investor_assumption.get('base_assumed_weighted_stake_tokens'), 2)} weighted SUMR"],
                ["Total network weighted stake (snapshot)", f"{fmt_num(staking_snapshot.get('total_weighted_sumr'), 2)} weighted SUMR"],
                ["Investor weighted share (base)", fmt_pct(investor_assumption.get("base_assumed_weighted_share_of_network"))],
                ["Raw staking participation (network)", fmt_pct(staking_snapshot.get("observed_raw_staking_ratio_vs_circulating"))],
                ["No lock weighted share", fmt_pct(multiplier_sensitivity.get("no_lock_weighted_share_of_network"))],
                ["Long lock weighted share", fmt_pct(multiplier_sensitivity.get("long_lock_weighted_share_of_network"))],
            ],
        )
    )
    lines.extend(
        [
            "",
            "Base-case APR sensitivity:",
            "",
        ]
    )
    lines.extend(
        markdown_table(
            ["Staking participation", "APR (lower bound)", "APR (upper bound)"],
            staking_table_rows if staking_table_rows else [["n/a", "n/a", "n/a"]],
        )
    )
    lines.extend(
        [
            "",
            f"![Staking Lockup Distribution]({chart_paths_relative['staking_lockup']})",
            "",
            "# Liquidity and Market Structure",
            "",
        ]
    )
    lines.extend(
        markdown_table(
            ["Item", "Value"],
            [
                ["Aggregate observed DEX reserve liquidity", fmt_usd(liquidity_row.get("aggregate_reserve_usd"))],
                ["Aggregate observed DEX volume, 30 days", fmt_usd(liquidity_row.get("aggregate_volume_30d_usd"))],
                ["Top holder share of supply", fmt_pct(liquidity_row.get("top1_pct_total_supply"))],
                ["Top 10 holders share of supply", fmt_pct(liquidity_row.get("top10_pct_total_supply"))],
                ["Top 10 stakers share of staked supply", fmt_pct(liquidity_row.get("top10_stakers_pct_of_staked"))],
                ["Staked SUMR unlocking in 90 days", fmt_pct(liquidity_row.get("unlocking_90d_pct_of_staked"))],
                ["Staked SUMR unlocking in 365 days", fmt_pct(liquidity_row.get("unlocking_365d_pct_of_staked"))],
            ],
        )
    )
    lines.extend(
        [
            "",
            f"![External Peer Benchmarks]({chart_paths_relative['peer_benchmarks']})",
            "",
            "Peer benchmarks are directional and snapshot-based (DeFiLlama/TokenTerminal-style aggregation), used for order-of-magnitude context rather than strict accounting comparability.",
            "",
            "# On-Chain Address Map (Investor-Facing)",
            "",
        ]
    )
    lines.extend(markdown_table(["Entity role", "Chain", "Address (short)", "Confidence", "Notes"], address_rows))
    lines.extend(
        [
            "",
            "Full raw addresses and provenance fields are in results/tables/investor_onchain_address_map_latest.csv.",
            "Coverage note: this map is in-scope on-chain infrastructure mapping and is not yet a complete consolidated off-chain custody map.",
            "",
            "# Governance, Security, and Control Risk",
            "",
        ]
    )
    lines.extend(
        markdown_table(
            ["Security control signal", "Current reading"],
            [
                ["Named audit provider keyword hits", str(security_row.get("auditor_keyword_hits") or "n/a")],
                ["Audit links discovered", str(security_row.get("audit_links_count") or "n/a")],
                ["Bug bounty mention present", str(security_row.get("bug_bounty_mentions") or "n/a")],
                ["Immunefi links detected", str(security_row.get("immunefi_links_count") or "n/a")],
                ["Incident history", str(security_row.get("incident_postmortem_title") or "n/a")],
                ["Incident postmortem published", str(security_row.get("incident_postmortem_published") or "n/a")],
                ["Proxy contracts in mapped surface", str(security_row.get("proxy_contract_count") or "n/a")],
                ["Admin authority module", f"`{security_row.get('admin_authority_module') or 'n/a'}`"],
            ],
        )
    )
    lines.extend(
        [
            "",
            "# Scenario Outlook at Lower Entry Price",
            "",
            f"All scenario outputs in this section assume 1,000,000 SUMR at entry {fmt_usd(ref_entry_price, 6)} (initial cost {fmt_usd(ref_initial_position)}).",
            "Figures should be interpreted relative to this entry cost.",
            "",
            f"Model probability weights: Downside {fmt_pct(pnl_probs.get('Downside'))}, Base {fmt_pct(pnl_probs.get('Base'))}, Upside {fmt_pct(pnl_probs.get('Upside'))}.",
            "",
            "Lower-bound probability-weighted outcomes:",
            "",
        ]
    )
    lines.extend(
        markdown_table(
            ["Horizon", "Expected value", "Expected PnL", "Annualized"],
            [
                [
                    f"{row.get('year')} {'year' if int(row.get('year') or 0) == 1 else 'years'}",
                    fmt_usd(row.get("expected_total_value_usd")),
                    fmt_usd(row.get("expected_pnl_usd")),
                    fmt_pct(row.get("expected_annualized_return")),
                ]
                for row in lower_expected
            ]
            if lower_expected
            else [["n/a", "n/a", "n/a", "n/a"]],
        )
    )
    lines.extend(
        [
            "",
            "Upper-bound probability-weighted outcomes:",
            "",
        ]
    )
    lines.extend(
        markdown_table(
            ["Horizon", "Expected value", "Expected PnL", "Annualized"],
            [
                [
                    f"{row.get('year')} {'year' if int(row.get('year') or 0) == 1 else 'years'}",
                    fmt_usd(row.get("expected_total_value_usd")),
                    fmt_usd(row.get("expected_pnl_usd")),
                    fmt_pct(row.get("expected_annualized_return")),
                ]
                for row in upper_expected
            ]
            if upper_expected
            else [["n/a", "n/a", "n/a", "n/a"]],
        )
    )
    lines.extend(
        [
            "",
            f"![Probability-Weighted Outcome Paths]({chart_paths_relative['probability_pnl']})",
            "",
            f"![Scenario Yield Heatmap]({chart_paths_relative['scenario_heatmap']})",
            "",
            "## Upside Plausibility Evidence Block",
            "",
        ]
    )
    lines.extend(markdown_table(["Indicator", "Current reading", "Directional interpretation"], upside_table))
    lines.extend(
        [
            "",
            "Conclusion: upside convexity exists in the model, but current live leading indicators do not yet justify de-risking the downside case.",
            "",
            "# Treasury Stress Context",
            "",
            "Treasury context should be treated as scenario-sensitive support, not a primary valuation pillar.",
            "Runway interpretation is explicitly provisional: treasury mapping is not yet fully comprehensive across all potential custody surfaces.",
            "",
            f"![Treasury Runway Stress Case]({chart_paths_relative['treasury_runway']})",
            "",
            "# Practical Underwriting Framework",
            "",
            "## Underwriting upgrades required to move from conditional to investable",
            "",
            "1. Evidence coverage: bounded realization ratio >=80% for >=60 consecutive days, with discrepancy tickets closed or explicitly documented.",
            "2. Unit economics persistence: fee productivity >=0.50% annualized for >=90 days, measured as 90d annualized fees divided by 90d average TVL.",
            "3. Governance constraints: published privileged role-member list, effective upgrade/routing timelocks, and on-chain auditable revenue-routing policy.",
            "4. Liquidity/treasury resilience: stable reserve and market depth sufficient to support downside runway, or a disclosed and credible backstop.",
            "",
            "## Kill-Switch Signals",
            "",
            "1. Fee productivity falls below 0.30% annualized for 90 consecutive days.",
            "2. Governance controls are not hardened (no published privileged role-member map and no effective routing/upgrade timelocks).",
            "3. Evidence coverage remains below 80% for 60 consecutive days with unresolved discrepancy tickets.",
            "4. Newly liquid supply accelerates without offsetting mitigation (lock extensions, emission reductions, or buyback/sink policy).",
            "",
            "# Final Classification",
            "",
            f"At {fmt_usd(ref_entry_price, 6)}, SUMR offers asymmetric optionality: if governance reliably routes fees to stakers and TVL stabilizes or grows, modeled break-even economics and scenario returns become plausible.",
            f"However, the token remains a **{investability_lower} candidate** because (i) evidence coverage is not yet institutional-grade, (ii) liquidity and holder concentration remain high-risk, and (iii) unlock/dilution dynamics can dominate price action independent of fundamentals.",
            "",
            "This document is research and underwriting support material, not investment advice.",
        ]
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(
    output_markdown_path: Path,
    monitoring_path: Path,
    evidence_dir: Path | None,
    tables_dir: Path | None,
    charts_dir: Path,
) -> None:
    monitoring = load_json(monitoring_path)

    if evidence_dir is None:
        monitoring_evidence_dir = monitoring.get("evidence_dir")
        if not monitoring_evidence_dir:
            raise ValueError("Could not resolve evidence directory from args or monitoring payload.")
        resolved_evidence_dir = Path(monitoring_evidence_dir)
    else:
        resolved_evidence_dir = evidence_dir

    if tables_dir is None:
        monitoring_tables_dir = monitoring.get("tables_dir")
        if not monitoring_tables_dir:
            raise ValueError("Could not resolve tables directory from args or monitoring payload.")
        resolved_tables_dir = Path(monitoring_tables_dir)
    else:
        resolved_tables_dir = tables_dir

    snapshot_dir = Path(monitoring.get("snapshot_dir") or "data/snapshots/external_review/2026-02-09-independent")

    kpi = load_json(resolved_evidence_dir / "kpi_summary.json")
    tickets = load_json(resolved_evidence_dir / "discrepancy_tickets.json")
    source_of_funds = load_json(resolved_evidence_dir / "source_of_funds_summary.json")
    emissions = load_json(resolved_evidence_dir / "emissions_vs_revenue_decomposition.json")
    bounded_bands = load_json(resolved_tables_dir / "v2_bounded_decision_bands.json")
    scenario_assumptions = load_json(resolved_tables_dir / "scenario_assumptions_latest.json")
    defillama_context = load_json(resolved_evidence_dir / "defillama_context_summary.json")
    benchmark_payload = load_optional_json(resolved_tables_dir / "investor_external_benchmark_peers.json")
    macro_payload = load_optional_json(resolved_tables_dir / "investor_macro_context.json")
    treasury_payload = load_optional_json(resolved_tables_dir / "investor_treasury_runway_model.json")
    staking_payload = load_optional_json(resolved_tables_dir / "investor_staking_distribution.json")
    pnl_payload = load_optional_json(resolved_tables_dir / "investor_probability_weighted_pnl.json")
    pnl_price_refresh_payload = load_optional_json(resolved_tables_dir / "investor_probability_weighted_pnl_price_refresh_latest.json")
    extended_summary_payload = load_optional_json(resolved_tables_dir / "investor_extended_summary.json")
    extended_snapshot_dir = None
    if extended_summary_payload is not None:
        extended_snapshot_dir = str(extended_summary_payload.get("snapshot_dir") or "")

    tvl_fees_chart = charts_dir / "investor_tvl_fees_trend.png"
    campaign_chart = charts_dir / "investor_campaign_realization.png"
    source_chart = charts_dir / "investor_source_of_funds_monthly.png"
    scenario_heatmap_chart = charts_dir / "investor_scenario_yield_heatmap.png"
    scenario_dist_chart = charts_dir / "investor_scenario_yield_distribution.png"
    reference_chart = charts_dir / "investor_reference_scenarios.png"

    build_tvl_fees_chart(
        defillama_protocol_path=snapshot_dir / "defillama_protocol_lazy_summer.json",
        defillama_fees_path=snapshot_dir / "defillama_fees_dailyFees_lazy_summer.json",
        output_path=tvl_fees_chart,
    )
    build_campaign_realization_chart(
        payout_summary_path=resolved_evidence_dir / "payout_attribution_summary.json",
        output_path=campaign_chart,
    )
    build_source_of_funds_chart(
        source_of_funds_monthly_path=resolved_evidence_dir / "source_of_funds_monthly_comparison.csv",
        output_path=source_chart,
    )
    build_scenario_heatmap_chart(
        scenario_matrix_path=resolved_tables_dir / "scenario_matrix_latest.json",
        bounded_bands_path=resolved_tables_dir / "v2_bounded_decision_bands.json",
        output_path=scenario_heatmap_chart,
    )
    quantiles = build_scenario_distribution_chart(
        scenario_matrix_path=resolved_tables_dir / "scenario_matrix_latest.json",
        bounded_bands_path=resolved_tables_dir / "v2_bounded_decision_bands.json",
        output_path=scenario_dist_chart,
    )
    reference_rows = build_reference_scenarios_chart(
        scenario_matrix_path=resolved_tables_dir / "scenario_matrix_latest.json",
        bounded_bands_path=resolved_tables_dir / "v2_bounded_decision_bands.json",
        output_path=reference_chart,
    )
    staking_sensitivity_rows = build_staking_sensitivity_rows(
        scenario_matrix_path=resolved_tables_dir / "scenario_matrix_latest.json",
        bounded_bands_path=resolved_tables_dir / "v2_bounded_decision_bands.json",
    )
    build_probability_weighted_paths_chart(
        pnl_paths_csv_path=resolved_tables_dir / "investor_probability_weighted_pnl_paths.csv",
        pnl_payload=pnl_payload,
        pnl_price_refresh_payload=pnl_price_refresh_payload,
        output_path=charts_dir / "investor_probability_weighted_pnl_paths.png",
    )

    charts_relative = {
        "tvl_fees": "../results/charts/investor_tvl_fees_trend.png",
        "campaign_realization": "../results/charts/investor_campaign_realization.png",
        "source_of_funds": "../results/charts/investor_source_of_funds_monthly.png",
        "peer_benchmarks": "../results/charts/investor_external_peer_benchmarks.png",
        "macro_lending": "../results/charts/investor_macro_lending_fee_league.png",
        "treasury_runway": "../results/charts/investor_treasury_runway_base_opex.png",
        "staking_lockup": "../results/charts/investor_staking_lockup_distribution.png",
        "probability_pnl": "../results/charts/investor_probability_weighted_pnl_paths.png",
        "scenario_heatmap": "../results/charts/investor_scenario_yield_heatmap.png",
        "scenario_distribution": "../results/charts/investor_scenario_yield_distribution.png",
        "reference_scenarios": "../results/charts/investor_reference_scenarios.png",
    }

    build_markdown_summary(
        output_path=output_markdown_path,
        tables_dir=resolved_tables_dir,
        monitoring=monitoring,
        kpi=kpi,
        tickets=tickets,
        source_of_funds=source_of_funds,
        bounded_bands=bounded_bands,
        scenario_assumptions=scenario_assumptions,
        emissions=emissions,
        defillama_context=defillama_context,
        scenario_quantiles=quantiles,
        reference_rows=reference_rows,
        staking_sensitivity_rows=staking_sensitivity_rows,
        benchmark_payload=benchmark_payload,
        macro_payload=macro_payload,
        treasury_payload=treasury_payload,
        staking_payload=staking_payload,
        pnl_payload=pnl_payload,
        extended_snapshot_dir=extended_snapshot_dir,
        chart_paths_relative=charts_relative,
    )

    tables_dir_out = resolved_tables_dir
    write_json(
        tables_dir_out / "investor_scenario_quantiles.json",
        {
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "schema": "investor_scenario_quantiles_v1",
            "quantiles": quantiles,
        },
    )
    class_code = derive_investability_class(
        gate_passed=bool(monitoring.get("latest", {}).get("all_campaigns_pass")),
        bounded_status=monitoring.get("latest", {}).get("v2_bounded_band_status"),
        open_high_ticket_count=monitoring.get("latest", {}).get("open_high_ticket_count"),
        source_of_funds_status=(source_of_funds.get("source_of_funds_comparison") or {}).get("status"),
    )[0]
    write_json(
        tables_dir_out / "investor_key_metrics.json",
        {
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "schema": "investor_key_metrics_v1",
            "classification": class_code,
            "classification_display": investor_regime_label(class_code),
            "kpi_summary": {
                "lazy_latest_tvl_usd": kpi.get("lazy_latest_tvl_usd"),
                "fees_derived_30d": kpi.get("fees_derived_30d"),
                "fees_derived_90d_annualized": kpi.get("fees_derived_90d_annualized"),
                "implied_fee_rate_vs_window_avg_tvl": kpi.get("implied_fee_rate_vs_window_avg_tvl"),
            },
            "gate_status": {
                "all_campaigns_pass": monitoring.get("latest", {}).get("all_campaigns_pass"),
                "v2_scenario_status": monitoring.get("latest", {}).get("v2_scenario_status"),
                "v2_bounded_band_status": monitoring.get("latest", {}).get("v2_bounded_band_status"),
            },
            "break_even_summary": {
                "sumr_price_break_even_usd": (emissions.get("usd_decomposition_formula") or {}).get(
                    "break_even_sumr_price_for_emissions_equal_revenue_deposited"
                ),
                "pinned_price_usd": (scenario_assumptions.get("assumptions") or {}).get("token_price_usd", {}).get("value"),
            },
            "tvl_scope_context": {
                "lazy_latest_tvl_usd": kpi.get("lazy_latest_tvl_usd"),
                "summer_nearest_2024_11_01_tvl_usd": defillama_context.get("summer_nearest_2024_11_01_tvl_usd"),
                "summer_nearest_2024_11_01_date": defillama_context.get("summer_nearest_2024_11_01_date"),
            },
        },
    )
    write_csv(
        tables_dir_out / "investor_reference_scenarios.csv",
        headers=[
            "scenario_case",
            "tvl_multiplier",
            "fee_rate",
            "staker_share",
            "staking_ratio",
            "annual_staker_usd_lower",
            "annual_staker_usd_upper",
            "yield_on_mcap_lower",
            "yield_on_mcap_upper",
            "yield_on_staked_lower",
            "yield_on_staked_upper",
        ],
        rows=[
            [
                row.get("scenario_case"),
                row.get("tvl_multiplier"),
                row.get("fee_rate"),
                row.get("staker_share"),
                row.get("staking_ratio"),
                row.get("annual_staker_usd_lower"),
                row.get("annual_staker_usd_upper"),
                row.get("yield_on_mcap_lower"),
                row.get("yield_on_mcap_upper"),
                row.get("yield_on_staked_lower"),
                row.get("yield_on_staked_upper"),
            ]
            for row in reference_rows
        ],
    )
    write_csv(
        tables_dir_out / "investor_staking_sensitivity.csv",
        headers=[
            "staking_ratio",
            "annual_staker_usd_lower",
            "annual_staker_usd_upper",
            "yield_on_staked_lower",
            "yield_on_staked_upper",
            "yield_on_mcap_lower",
            "yield_on_mcap_upper",
        ],
        rows=[
            [
                row.get("staking_ratio"),
                row.get("annual_staker_usd_lower"),
                row.get("annual_staker_usd_upper"),
                row.get("yield_on_staked_lower"),
                row.get("yield_on_staked_upper"),
                row.get("yield_on_mcap_lower"),
                row.get("yield_on_mcap_upper"),
            ]
            for row in staking_sensitivity_rows
        ],
    )

    print(f"Wrote investor executive summary to {output_markdown_path}")
    print("Charts written:")
    for chart in [tvl_fees_chart, campaign_chart, source_chart, scenario_heatmap_chart, scenario_dist_chart, reference_chart]:
        print(f"- {chart}")


def main() -> None:
    default_output_path = PROJECT_ROOT / "paper" / "investor_executive_summary.md"
    default_monitoring_path = RESULTS_DIR / "tables" / "monitoring_latest.json"
    default_charts_dir = RESULTS_DIR / "charts"

    parser = argparse.ArgumentParser(description="Generate investor-facing summary with charts and scenario tables.")
    parser.add_argument("--output-path", type=Path, default=default_output_path)
    parser.add_argument("--monitoring-path", type=Path, default=default_monitoring_path)
    parser.add_argument("--evidence-dir", type=Path, default=None)
    parser.add_argument("--tables-dir", type=Path, default=None)
    parser.add_argument("--charts-dir", type=Path, default=default_charts_dir)
    args = parser.parse_args()

    run(
        output_markdown_path=args.output_path,
        monitoring_path=args.monitoring_path,
        evidence_dir=args.evidence_dir,
        tables_dir=args.tables_dir,
        charts_dir=args.charts_dir,
    )


if __name__ == "__main__":
    main()
