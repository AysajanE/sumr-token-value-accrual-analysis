"""
Generate a comprehensive, decision-focused SUMR value-accrual report
from latest deterministic artifacts.
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

from src.config import MAX_SUPPLY, PROJECT_ROOT, RESULTS_DIR


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def parse_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    return Decimal(str(value))


def first_not_none(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def fmt_num(value: Any, decimals: int = 2) -> str:
    amount = parse_decimal(value)
    if amount is None:
        return "n/a"
    quant = Decimal(1).scaleb(-decimals)
    rounded = amount.quantize(quant, rounding=ROUND_HALF_UP)
    return f"{rounded:,.{decimals}f}"


def fmt_int(value: Any) -> str:
    amount = parse_decimal(value)
    if amount is None:
        return "n/a"
    return f"{int(amount):,}"


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


def find_ticket(tickets_payload: dict[str, Any], ticket_id: str) -> dict[str, Any]:
    for ticket in tickets_payload.get("tickets", []):
        if ticket.get("ticket_id") == ticket_id:
            return ticket
    return {}


def derive_investability_class(
    gate_passed: bool,
    bounded_status: str | None,
    open_high_ticket_count: int | None,
    source_of_funds_status: str | None,
) -> tuple[str, str]:
    high_tickets = int(open_high_ticket_count or 0)
    sof_status = source_of_funds_status or "UNKNOWN"

    if gate_passed and high_tickets == 0 and sof_status in {"PROVEN", "BOUNDED"}:
        return (
            "STRICT_VALIDATED",
            "Strict gate criteria passed and no open high-severity tickets in latest monitoring cycle.",
        )

    if bounded_status == "READY_SUPPLEMENTAL_BOUNDED" and high_tickets == 0:
        return (
            "CONDITIONAL_BOUNDED",
            "Routing and funding evidence are present, but strict gate validation is still blocked.",
        )

    return (
        "RESTRICTED",
        "Current evidence does not satisfy strict validation and risk posture remains constrained.",
    )


def investor_regime_label(classification_code: str) -> str:
    if classification_code == "STRICT_VALIDATED":
        return "STRICT"
    if classification_code == "CONDITIONAL_BOUNDED":
        return "CONDITIONAL"
    return "RESTRICTED"


def scenario_with_realization(
    scenario: dict[str, Any], realized_ratio: Decimal
) -> dict[str, Decimal | None]:
    staker_revenue = parse_decimal(scenario.get("staker_revenue_usd")) or Decimal(0)
    yield_mcap = parse_decimal(scenario.get("revenue_yield_on_mcap"))
    yield_fdv = parse_decimal(scenario.get("revenue_yield_on_fdv"))
    yield_staked = parse_decimal(scenario.get("revenue_yield_on_staked"))

    return {
        "annual_staker_usd_upper": staker_revenue,
        "annual_staker_usd_lower": staker_revenue * realized_ratio,
        "yield_on_mcap_upper": yield_mcap,
        "yield_on_mcap_lower": (yield_mcap * realized_ratio) if yield_mcap is not None else None,
        "yield_on_fdv_upper": yield_fdv,
        "yield_on_fdv_lower": (yield_fdv * realized_ratio) if yield_fdv is not None else None,
        "yield_on_staked_upper": yield_staked,
        "yield_on_staked_lower": (yield_staked * realized_ratio) if yield_staked is not None else None,
    }


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


def build_report(
    monitoring: dict[str, Any],
    kpi: dict[str, Any],
    defillama_context: dict[str, Any],
    tickets: dict[str, Any],
    payout_summary: dict[str, Any],
    canonical_summary: dict[str, Any],
    gate: dict[str, Any],
    source_of_funds: dict[str, Any],
    emissions: dict[str, Any],
    v2_summary: dict[str, Any],
    bounded_bands: dict[str, Any],
    scenario_assumptions: dict[str, Any],
    scenario_matrix: dict[str, Any],
    baseline_manifest: dict[str, Any],
    source_of_funds_monthly_rows: list[dict[str, str]],
    monitoring_path: Path,
    evidence_dir: Path,
    tables_dir: Path,
) -> str:
    latest = monitoring.get("latest", {})
    scenarios = scenario_matrix.get("scenarios", [])
    campaigns = payout_summary.get("campaigns", [])
    aggregate = canonical_summary.get("aggregate", {})

    bounded_baseline = bounded_bands.get("bounds_baseline") or {}
    realized_ratio = parse_decimal(bounded_baseline.get("realized_ratio_lower_to_upper")) or Decimal(0)
    fee_ticket = find_ticket(tickets, "FEE-RATE-001")
    source_comparison = source_of_funds.get("source_of_funds_comparison") or {}

    token_price_assumption = ((scenario_assumptions.get("assumptions") or {}).get("token_price_usd")) or {}
    circ_supply_assumption = ((scenario_assumptions.get("assumptions") or {}).get("circulating_supply_tokens")) or {}

    source_status = source_comparison.get("status")
    investability_class, investability_note = derive_investability_class(
        gate_passed=bool(gate.get("all_campaigns_pass")),
        bounded_status=first_not_none(v2_summary.get("bounded_band_status"), bounded_bands.get("status")),
        open_high_ticket_count=latest.get("open_high_ticket_count"),
        source_of_funds_status=source_status,
    )
    investor_regime = investor_regime_label(investability_class)

    annual_upper_values: list[Decimal] = []
    annual_lower_values: list[Decimal] = []
    mcap_yield_upper_values: list[Decimal] = []
    mcap_yield_lower_values: list[Decimal] = []
    fdv_yield_upper_values: list[Decimal] = []
    fdv_yield_lower_values: list[Decimal] = []
    staked_yield_upper_values: list[Decimal] = []
    staked_yield_lower_values: list[Decimal] = []
    positive_share_scenarios = 0

    for scenario in scenarios:
        staker_share = parse_decimal(scenario.get("staker_share")) or Decimal(0)
        if staker_share <= 0:
            continue
        positive_share_scenarios += 1

        realized = scenario_with_realization(scenario, realized_ratio)
        annual_upper = realized["annual_staker_usd_upper"]
        annual_lower = realized["annual_staker_usd_lower"]
        if annual_upper is not None:
            annual_upper_values.append(annual_upper)
        if annual_lower is not None:
            annual_lower_values.append(annual_lower)

        for value, target in [
            (realized["yield_on_mcap_upper"], mcap_yield_upper_values),
            (realized["yield_on_mcap_lower"], mcap_yield_lower_values),
            (realized["yield_on_fdv_upper"], fdv_yield_upper_values),
            (realized["yield_on_fdv_lower"], fdv_yield_lower_values),
            (realized["yield_on_staked_upper"], staked_yield_upper_values),
            (realized["yield_on_staked_lower"], staked_yield_lower_values),
        ]:
            if value is not None:
                target.append(value)

    reference_specs = [
        ("Downside", 0.5, 0.0010, 0.10, 0.30),
        ("Base", 1.0, 0.0066, 0.20, 0.30),
        ("Upside", 2.0, 0.0100, 0.30, 0.30),
    ]
    reference_rows: list[list[str]] = []
    for name, tvl_mult, fee_rate, staker_share, staking_ratio in reference_specs:
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
        reference_rows.append(
            [
                name,
                f"{tvl_mult:.1f}x / {fee_rate:.2%} / {staker_share:.0%} / {staking_ratio:.0%}",
                fmt_usd(realized["annual_staker_usd_lower"]),
                fmt_usd(realized["annual_staker_usd_upper"]),
                fmt_pct(realized["yield_on_mcap_lower"]),
                fmt_pct(realized["yield_on_mcap_upper"]),
                fmt_pct(realized["yield_on_staked_lower"]),
                fmt_pct(realized["yield_on_staked_upper"]),
            ]
        )

    staking_sensitivity_rows: list[list[str]] = []
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
        staking_sensitivity_rows.append(
            [
                f"{staking_ratio:.0%}",
                fmt_usd(realized["annual_staker_usd_lower"]),
                fmt_usd(realized["annual_staker_usd_upper"]),
                fmt_pct(realized["yield_on_staked_lower"]),
                fmt_pct(realized["yield_on_staked_upper"]),
                fmt_pct(realized["yield_on_mcap_lower"]),
                fmt_pct(realized["yield_on_mcap_upper"]),
            ]
        )

    campaign_rows: list[list[str]] = []
    for campaign in campaigns:
        campaign_rows.append(
            [
                str(campaign.get("label", "n/a")),
                str(campaign.get("reward_token_symbol", "n/a")),
                fmt_num(campaign.get("staker_revenue_deposited_tokens"), 6),
                fmt_num(campaign.get("staker_revenue_claimed_tokens_attributed"), 6),
                fmt_num(campaign.get("staker_revenue_unclaimed_tokens_residual"), 6),
                fmt_pct(campaign.get("residual_ratio"), 2),
                str(campaign.get("attribution_confidence_class", "n/a")),
            ]
        )

    ticket_rows: list[list[str]] = []
    for ticket in tickets.get("tickets", []):
        ticket_rows.append(
            [
                str(ticket.get("ticket_id", "n/a")),
                str(ticket.get("severity", "n/a")),
                str(ticket.get("status", "n/a")),
                str(ticket.get("title", "n/a")),
                fmt_pct(ticket.get("delta_pct_of_expected") / 100 if ticket.get("delta_pct_of_expected") is not None else None, 3),
            ]
        )

    gate_rows: list[list[str]] = []
    for campaign in gate.get("campaigns", []):
        gate_rows.append(
            [
                str(campaign.get("label", "n/a")),
                str(campaign.get("attribution_confidence_class", "n/a")),
                fmt_pct(campaign.get("residual_ratio"), 2),
                str(campaign.get("pass", False)),
            ]
        )

    monthly_rows_sorted = sorted(
        source_of_funds_monthly_rows,
        key=lambda row: (
            row.get("month_utc", ""),
            row.get("token_symbol", ""),
        ),
    )
    monthly_tail = monthly_rows_sorted[-6:]
    monthly_table_rows: list[list[str]] = []
    for row in monthly_tail:
        monthly_table_rows.append(
            [
                row.get("month_utc", "n/a"),
                row.get("token_symbol", "n/a"),
                fmt_num(row.get("fee_aligned_inflow_to_treasury_base"), 6),
                fmt_num(row.get("staker_payout_outflow_from_treasury_base"), 6),
                fmt_num(row.get("net_fee_inflow_minus_staker_payout"), 6),
                fmt_ratio(row.get("coverage_ratio"), 3) if row.get("coverage_ratio") else "n/a",
            ]
        )

    break_even_sumr_price = parse_decimal(
        ((emissions.get("usd_decomposition_formula") or {}).get("break_even_sumr_price_for_emissions_equal_revenue_deposited"))
    )
    token_price = parse_decimal(token_price_assumption.get("value"))
    price_to_break_even = None
    if token_price is not None and break_even_sumr_price not in (None, Decimal(0)):
        price_to_break_even = token_price / break_even_sumr_price

    summer_nov_2024_tvl = defillama_context.get("summer_nearest_2024_11_01_tvl_usd")
    summer_nov_2024_date = defillama_context.get("summer_nearest_2024_11_01_date")

    now = datetime.now(timezone.utc).isoformat()
    generated_from = monitoring.get("generated_utc") or now

    lines: list[str] = [
        "# SUMR Token Value Accrual Comprehensive Report (Evidence-First)",
        "",
        f"- Report generated UTC: `{now}`",
        f"- Monitoring snapshot UTC: `{generated_from}`",
        f"- Monitoring source: `{monitoring_path.as_posix()}`",
        f"- Evidence directory: `{evidence_dir.as_posix()}`",
        f"- Tables directory: `{tables_dir.as_posix()}`",
        "",
        "## 1) Decision Snapshot",
        "",
        f"- Current investor-facing classification: **{investor_regime}**",
        f"- Technical classification code: `{investability_class}`",
        f"- Interpretation: {investability_note}",
        f"- Strict gate status: `{gate.get('all_campaigns_pass')}` (rule: `{gate.get('rule')}`)",
        f"- v2 strict scenario status: `{v2_summary.get('scenario_status')}`",
        f"- v2 bounded band status: `{first_not_none(v2_summary.get('bounded_band_status'), bounded_bands.get('status'))}`",
        f"- Open high-severity tickets: `{latest.get('open_high_ticket_count')}`",
        "- Protocol data-fidelity risk: `Claimed(user, token, amount)` logs omit `campaign_id`, so campaign attribution is bounded by token/window heuristics.",
        "",
        "### Pillar Status",
        "",
    ]

    lines.extend(
        markdown_table(
            headers=["Pillar", "Current status", "Evidence anchor"],
            rows=[
                [
                    "Fee generation and fee-rate reconciliation",
                    f"{fee_ticket.get('status', 'UNKNOWN')} ({fee_ticket.get('severity', 'UNKNOWN')})",
                    f"Observed annualized fee rate {fmt_pct(fee_ticket.get('observed'))}",
                ],
                [
                    "Treasury->staker payout routing",
                    "PROVEN_ON_CHAIN",
                    "SIP3.13 + SIP3.13.1 execute tx and funding transfer receipts",
                ],
                [
                    "Campaign claim realization quality",
                    "PARTIAL",
                    f"SIP3.13.1 residual ratio {fmt_pct((campaigns[1] if len(campaigns) > 1 else {}).get('residual_ratio'))}",
                ],
                [
                    "Campaign attribution data fidelity",
                    "RISK_PRESENT",
                    "Distributor claim events omit campaign IDs; attribution remains bounded rather than campaign-exact.",
                ],
                [
                    "Source of funds",
                    str(source_status or "UNKNOWN"),
                    f"USDC comparable coverage ratio {fmt_ratio(source_comparison.get('comparable_coverage_ratio'))}",
                ],
                [
                    "Scenario assumption pinning",
                    str(scenario_assumptions.get("status", "UNKNOWN")),
                    f"price={fmt_usd(token_price_assumption.get('value'), 6)} ({token_price_assumption.get('source_label') or token_price_assumption.get('source_kind')})",
                ],
                [
                    "Strict gate for validated scenarios",
                    "BLOCKED" if not gate.get("all_campaigns_pass") else "PASSED",
                    str(v2_summary.get("scenario_status")),
                ],
            ],
        )
    )

    lines.extend(
        [
            "",
            "## 2) Data Provenance and Reproducibility",
            "",
            f"- Monitoring observed UTC: `{latest.get('observed_utc')}`",
            f"- Refresh block range: `{latest.get('refresh_from_block')} -> {latest.get('refresh_to_block')}`",
            f"- Baseline manifest UTC: `{first_not_none(latest.get('baseline_manifest_generated_utc'), baseline_manifest.get('generated_utc'))}`",
            f"- Baseline tree SHA256: `{first_not_none(latest.get('baseline_manifest_tree_sha256'), (baseline_manifest.get('fingerprints') or {}).get('tree_sha256'))}`",
            f"- Scenario assumptions status: `{scenario_assumptions.get('status')}`",
            f"- Circulating supply pin (tokens): `{fmt_num(circ_supply_assumption.get('value'), 6)}`",
            f"- Token price pin (USD): `{fmt_usd(token_price_assumption.get('value'), 6)}`",
            f"- Token price source: `{token_price_assumption.get('source_label') or token_price_assumption.get('source_kind')}`",
            "",
            "## 3) Protocol Baseline (Current Window)",
            "",
        ]
    )

    lines.extend(
        markdown_table(
            headers=["Metric", "Value"],
            rows=[
                ["Lazy Summer latest TVL", fmt_usd(kpi.get("lazy_latest_tvl_usd"))],
                ["Lazy Summer peak TVL", fmt_usd(kpi.get("lazy_peak_tvl_usd"))],
                ["Summer.fi latest TVL", fmt_usd(kpi.get("summer_latest_tvl_usd"))],
                ["30d fees (derived)", fmt_usd(kpi.get("fees_derived_30d"))],
                ["90d fees (derived)", fmt_usd(kpi.get("fees_derived_90d"))],
                ["90d annualized fees", fmt_usd(kpi.get("fees_derived_90d_annualized"))],
                ["Window-matched average TVL", fmt_usd(kpi.get("lazy_tvl_window_avg_usd"))],
                ["Observed annualized fee rate", fmt_pct(kpi.get("implied_fee_rate_vs_window_avg_tvl"))],
                ["Circulating supply (pinned)", fmt_num(circ_supply_assumption.get("value"), 6)],
                ["Token price (pinned)", fmt_usd(token_price_assumption.get("value"), 6)],
                ["Implied market cap at pin", fmt_usd((parse_decimal(circ_supply_assumption.get("value")) or Decimal(0)) * (token_price or Decimal(0)))],
                ["Implied FDV at pin", fmt_usd((parse_decimal(MAX_SUPPLY) or Decimal(0)) * (token_price or Decimal(0)))],
            ],
        )
    )

    lines.extend(
        [
            "",
            "### 3.1 Scope-Reconciliation Check (TVL Narratives)",
            "",
        ]
    )
    lines.extend(
        markdown_table(
            headers=["Context", "Value", "Interpretation"],
            rows=[
                [
                    "Lazy Summer latest TVL",
                    fmt_usd(kpi.get("lazy_latest_tvl_usd")),
                    "Primary token-backing protocol scope for this analysis.",
                ],
                [
                    f"Summer.fi TVL near {summer_nov_2024_date or '2024-11-01'}",
                    fmt_usd(summer_nov_2024_tvl),
                    "Potential source of 190M headline values; broader Summer.fi scope should not be mixed with Lazy Summer without explicit qualifier.",
                ],
                [
                    "Lazy Summer peak TVL date",
                    str(kpi.get("lazy_peak_date")),
                    "Peak timing differs from older 2024 headline narratives; use date-scoped claims only.",
                ],
            ],
        )
    )

    lines.extend(
        [
            "",
            "## 4) On-Chain Value Accrual Verification",
            "",
            "### 4.1 Campaign-Level Routing and Realization",
            "",
        ]
    )
    lines.extend(
        markdown_table(
            headers=[
                "Campaign",
                "Reward token",
                "Deposited to distributor",
                "Claimed attributed",
                "Residual unclaimed",
                "Residual ratio",
                "Confidence",
            ],
            rows=campaign_rows,
        )
    )

    lines.extend(
        [
            "",
            "### 4.1.a Campaign Attribution Data-Fidelity Risk",
            "",
            "- Contract event schema issue: `Claimed(user, token, amount)` does not emit campaign ID.",
            "- Impact: campaign-level realization cannot be reconstructed as a single deterministic join key.",
            "- Practical effect: confidence remains `PARTIAL` unless residuals compress or event schema is upgraded.",
            "- Risk ownership: protocol contract/event design, not downstream analytics implementation.",
        ]
    )

    lines.extend(
        [
            "",
            "### 4.2 Canonical Revenue Accounting (Aggregate)",
            "",
            f"- Deposited total (token-native): `{fmt_num(aggregate.get('staker_revenue_deposited_tokens_total'), 6)}`",
            f"- Claimed attributed total (token-native): `{fmt_num(aggregate.get('staker_revenue_claimed_tokens_attributed_total'), 6)}`",
            f"- Unclaimed residual total (token-native): `{fmt_num(aggregate.get('staker_revenue_unclaimed_tokens_residual_total'), 6)}`",
            f"- Canonical policy: `{(canonical_summary.get('metric_policy') or {}).get('staker_revenue_claimed_tokens_attributed')}`",
            "",
            "### 4.3 Source-of-Funds Evidence",
            "",
            f"- Source-of-funds status: `{source_status}`",
            f"- Status basis: `{'; '.join(source_comparison.get('status_basis', [])) if source_comparison.get('status_basis') else 'n/a'}`",
            f"- Comparable token set: `{', '.join(source_comparison.get('comparable_tokens', [])) or 'n/a'}`",
            f"- Non-comparable payout tokens: `{', '.join(source_comparison.get('non_comparable_payout_tokens', [])) or 'none'}`",
            f"- Comparable fee-aligned inflow total: `{fmt_num(source_comparison.get('comparable_fee_aligned_inflow_total'), 6)}`",
            f"- Comparable staker payout outflow total: `{fmt_num(source_comparison.get('comparable_staker_payout_outflow_total'), 6)}`",
            f"- Comparable coverage ratio: `{fmt_ratio(source_comparison.get('comparable_coverage_ratio'), 3)}`",
            "",
            "Recent monthly comparison (latest 6 rows):",
            "",
        ]
    )
    lines.extend(
        markdown_table(
            headers=[
                "Month",
                "Token",
                "Fee-aligned inflow",
                "Staker payout outflow",
                "Net inflow - payout",
                "Coverage",
            ],
            rows=monthly_table_rows if monthly_table_rows else [["n/a", "n/a", "n/a", "n/a", "n/a", "n/a"]],
        )
    )

    lines.extend(
        [
            "",
            "### 4.4 Emissions vs Revenue Decomposition",
            "",
            f"- Emissions events observed: `{(emissions.get('emissions_component') or {}).get('event_count')}`",
            f"- Total SUMR emissions (tokens): `{fmt_num((emissions.get('emissions_component') or {}).get('total_sumr_tokens'), 6)}`",
            f"- Revenue deposited (USDC-equivalent): `{fmt_usd((emissions.get('revenue_component_usdc_equivalent') or {}).get('deposited'))}`",
            f"- Revenue claimed attributed (USDC-equivalent): `{fmt_usd((emissions.get('revenue_component_usdc_equivalent') or {}).get('claimed_attributed'))}`",
            f"- Revenue unclaimed residual (USDC-equivalent): `{fmt_usd((emissions.get('revenue_component_usdc_equivalent') or {}).get('unclaimed_residual'))}`",
            f"- Break-even SUMR price for emissions = deposited revenue: `{fmt_usd(break_even_sumr_price, 6)}`",
            f"- Pinned token price / break-even: `{fmt_ratio(price_to_break_even, 3) if price_to_break_even is not None else 'n/a'}`",
            f"- Inflationary pressure factor at pinned price: `{fmt_ratio(price_to_break_even, 3) if price_to_break_even is not None else 'n/a'}` (values >1 imply emissions value exceeds deposited revenue value).",
            f"- LVUSDC valuation method: `{((emissions.get('lvusdc_usdc_equivalent_valuation') or {}).get('method_version'))}`",
            "",
            "## 5) Gate and Discrepancy Status",
            "",
            f"- Gate rule: `{gate.get('rule')}`",
            f"- All campaigns pass strict gate: `{gate.get('all_campaigns_pass')}`",
            f"- v2 gate KPI status: `{v2_summary.get('gate_kpis_status')}`",
            f"- v2 strict scenario status: `{v2_summary.get('scenario_status')}`",
            f"- Supplemental bounded status: `{first_not_none(v2_summary.get('bounded_band_status'), bounded_bands.get('status'))}`",
            "",
            "Campaign gate checks:",
            "",
        ]
    )
    lines.extend(
        markdown_table(
            headers=["Campaign", "Confidence class", "Residual ratio", "Pass"],
            rows=gate_rows if gate_rows else [["n/a", "n/a", "n/a", "n/a"]],
        )
    )

    lines.extend(
        [
            "",
            "Discrepancy ticket inventory:",
            "",
        ]
    )
    lines.extend(
        markdown_table(
            headers=["Ticket", "Severity", "Status", "Title", "Delta vs expected"],
            rows=ticket_rows if ticket_rows else [["n/a", "n/a", "n/a", "n/a", "n/a"]],
        )
    )

    lines.extend(
        [
            "",
            "## 6) Scenario Analysis (Pinned Assumptions)",
            "",
            f"- Scenario matrix status: `{scenario_matrix.get('status')}`",
            f"- Scenario count: `{fmt_int(scenario_matrix.get('scenario_count'))}`",
            f"- Positive staker-share scenarios: `{fmt_int(positive_share_scenarios)}`",
            f"- Realization ratio applied for lower-bound outputs: `{fmt_pct(realized_ratio)}`",
            "",
            "### 6.1 Distribution Summary Across Positive Staker-Share Scenarios",
            "",
        ]
    )

    lines.extend(
        markdown_table(
            headers=["Metric", "P10", "P50", "P90", "Min", "Max"],
            rows=[
                [
                    "Annual staker revenue (lower, USD)",
                    fmt_usd(quantile(annual_lower_values, 0.10)),
                    fmt_usd(quantile(annual_lower_values, 0.50)),
                    fmt_usd(quantile(annual_lower_values, 0.90)),
                    fmt_usd(min(annual_lower_values) if annual_lower_values else None),
                    fmt_usd(max(annual_lower_values) if annual_lower_values else None),
                ],
                [
                    "Annual staker revenue (upper, USD)",
                    fmt_usd(quantile(annual_upper_values, 0.10)),
                    fmt_usd(quantile(annual_upper_values, 0.50)),
                    fmt_usd(quantile(annual_upper_values, 0.90)),
                    fmt_usd(min(annual_upper_values) if annual_upper_values else None),
                    fmt_usd(max(annual_upper_values) if annual_upper_values else None),
                ],
                [
                    "Yield on mcap (lower)",
                    fmt_pct(quantile(mcap_yield_lower_values, 0.10)),
                    fmt_pct(quantile(mcap_yield_lower_values, 0.50)),
                    fmt_pct(quantile(mcap_yield_lower_values, 0.90)),
                    fmt_pct(min(mcap_yield_lower_values) if mcap_yield_lower_values else None),
                    fmt_pct(max(mcap_yield_lower_values) if mcap_yield_lower_values else None),
                ],
                [
                    "Yield on mcap (upper)",
                    fmt_pct(quantile(mcap_yield_upper_values, 0.10)),
                    fmt_pct(quantile(mcap_yield_upper_values, 0.50)),
                    fmt_pct(quantile(mcap_yield_upper_values, 0.90)),
                    fmt_pct(min(mcap_yield_upper_values) if mcap_yield_upper_values else None),
                    fmt_pct(max(mcap_yield_upper_values) if mcap_yield_upper_values else None),
                ],
                [
                    "Yield on FDV (lower)",
                    fmt_pct(quantile(fdv_yield_lower_values, 0.10)),
                    fmt_pct(quantile(fdv_yield_lower_values, 0.50)),
                    fmt_pct(quantile(fdv_yield_lower_values, 0.90)),
                    fmt_pct(min(fdv_yield_lower_values) if fdv_yield_lower_values else None),
                    fmt_pct(max(fdv_yield_lower_values) if fdv_yield_lower_values else None),
                ],
                [
                    "Yield on FDV (upper)",
                    fmt_pct(quantile(fdv_yield_upper_values, 0.10)),
                    fmt_pct(quantile(fdv_yield_upper_values, 0.50)),
                    fmt_pct(quantile(fdv_yield_upper_values, 0.90)),
                    fmt_pct(min(fdv_yield_upper_values) if fdv_yield_upper_values else None),
                    fmt_pct(max(fdv_yield_upper_values) if fdv_yield_upper_values else None),
                ],
                [
                    "Yield on staked value (lower)",
                    fmt_pct(quantile(staked_yield_lower_values, 0.10)),
                    fmt_pct(quantile(staked_yield_lower_values, 0.50)),
                    fmt_pct(quantile(staked_yield_lower_values, 0.90)),
                    fmt_pct(min(staked_yield_lower_values) if staked_yield_lower_values else None),
                    fmt_pct(max(staked_yield_lower_values) if staked_yield_lower_values else None),
                ],
                [
                    "Yield on staked value (upper)",
                    fmt_pct(quantile(staked_yield_upper_values, 0.10)),
                    fmt_pct(quantile(staked_yield_upper_values, 0.50)),
                    fmt_pct(quantile(staked_yield_upper_values, 0.90)),
                    fmt_pct(min(staked_yield_upper_values) if staked_yield_upper_values else None),
                    fmt_pct(max(staked_yield_upper_values) if staked_yield_upper_values else None),
                ],
            ],
        )
    )

    lines.extend(
        [
            "",
            "### 6.2 Reference Scenarios (Lower/Upper Realization Bands)",
            "",
        ]
    )
    lines.extend(
        markdown_table(
            headers=[
                "Case",
                "Parameters (TVL / fee / staker share / staking ratio)",
                "Annual staker USD (lower)",
                "Annual staker USD (upper)",
                "Yield on mcap (lower)",
                "Yield on mcap (upper)",
                "Yield on staked (lower)",
                "Yield on staked (upper)",
            ],
            rows=reference_rows if reference_rows else [["n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a"]],
        )
    )

    lines.extend(
        [
            "",
            "### 6.3 Baseline Sensitivity by Staking Ratio",
            "",
            "Fixed assumptions: TVL=1.0x current, fee rate=0.66%, staker share=20%.",
            "",
        ]
    )
    lines.extend(
        markdown_table(
            headers=[
                "Staking ratio",
                "Annual staker USD (lower)",
                "Annual staker USD (upper)",
                "Yield on staked (lower)",
                "Yield on staked (upper)",
                "Yield on mcap (lower)",
                "Yield on mcap (upper)",
            ],
            rows=staking_sensitivity_rows if staking_sensitivity_rows else [["n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a"]],
        )
    )

    lines.extend(
        [
            "",
            "## 7) Evidence-Based Decision Framework",
            "",
            "Current regime and implications:",
            f"- Regime: `{investability_class}`",
            f"- Strict gate: `{gate.get('all_campaigns_pass')}`",
            f"- Source-of-funds: `{source_status}`",
            f"- Open high-severity tickets: `{latest.get('open_high_ticket_count')}`",
            "",
            "Upgrade triggers to strict-validated regime:",
            "1. At least one monitoring cycle where `payout_attribution_gate.json` reports `all_campaigns_pass = true`.",
            "2. SIP3.13.1 residual ratio declines to <= 5% under current gate rule.",
            "3. Source-of-funds status reaches `PROVEN` or remains `BOUNDED` while eliminating non-comparable payout tokens.",
            "4. Distributor contract/event upgrade emits campaign IDs in claim events, removing attribution ambiguity.",
            "5. No open HIGH-severity discrepancy tickets.",
            "",
            "Downside control triggers:",
            "1. Fee-rate reconciliation re-opens with MEDIUM/HIGH severity.",
            "2. Source-of-funds status degrades from `BOUNDED` to `UNKNOWN`.",
            "3. Realization ratio trend declines across consecutive monitoring cycles.",
            "",
            "## 8) Monitoring Runbook",
            "",
            "Refresh and regenerate full decision package:",
            "```bash",
            "make monitor_cycle",
            "make analyze",
            "make report",
            "```",
            "",
            "Primary outputs to track each cycle:",
            "- `results/tables/monitoring_latest.json`",
            "- `results/proofs/evidence_2026-02-09-independent/discrepancy_tickets.json`",
            "- `results/proofs/evidence_2026-02-09-independent/source_of_funds_summary.json`",
            "- `results/proofs/evidence_2026-02-09-independent/emissions_vs_revenue_decomposition.json`",
            "- `results/tables/v2_workflow_summary.json`",
            "- `results/tables/v2_bounded_decision_bands.json`",
            "- `results/tables/scenario_assumptions_latest.json`",
            "- `results/tables/scenario_matrix_latest.json`",
            "",
            "## 9) Artifact References",
            "",
            "- `paper/report.md`",
            "- `results/tables/monitoring_latest.json`",
            "- `results/proofs/evidence_2026-02-09-independent/kpi_summary.json`",
            "- `results/proofs/evidence_2026-02-09-independent/payout_attribution_summary.json`",
            "- `results/proofs/evidence_2026-02-09-independent/staker_revenue_canonical_summary.json`",
            "- `results/proofs/evidence_2026-02-09-independent/source_of_funds_summary.json`",
            "- `results/proofs/evidence_2026-02-09-independent/emissions_vs_revenue_decomposition.json`",
            "- `results/proofs/evidence_2026-02-09-independent/discrepancy_tickets.json`",
            "- `results/tables/v2_workflow_summary.json`",
            "- `results/tables/v2_bounded_decision_bands.json`",
            "- `results/tables/scenario_assumptions_latest.json`",
            "- `results/tables/scenario_matrix_latest.json`",
            "",
            "## 10) Caveats",
            "",
            "- This is an evidence synthesis report, not financial advice.",
            "- Strict gate remains the validated-scenario standard; bounded bands are supplemental.",
            "- Scenario outputs are assumption-sensitive even with pinning and should be refreshed with each new cycle.",
            "",
        ]
    )

    return "\n".join(lines)


def run(
    output_path: Path,
    monitoring_path: Path,
    evidence_dir: Path | None,
    tables_dir: Path | None,
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

    kpi = load_json(resolved_evidence_dir / "kpi_summary.json")
    defillama_context = load_json(resolved_evidence_dir / "defillama_context_summary.json")
    tickets = load_json(resolved_evidence_dir / "discrepancy_tickets.json")
    payout_summary = load_json(resolved_evidence_dir / "payout_attribution_summary.json")
    canonical_summary = load_json(resolved_evidence_dir / "staker_revenue_canonical_summary.json")
    gate = load_json(resolved_evidence_dir / "payout_attribution_gate.json")
    source_of_funds = load_json(resolved_evidence_dir / "source_of_funds_summary.json")
    emissions = load_json(resolved_evidence_dir / "emissions_vs_revenue_decomposition.json")

    v2_summary = load_json(resolved_tables_dir / "v2_workflow_summary.json")
    bounded_bands = load_json(resolved_tables_dir / "v2_bounded_decision_bands.json")
    scenario_assumptions = load_json(resolved_tables_dir / "scenario_assumptions_latest.json")
    scenario_matrix = load_json(resolved_tables_dir / "scenario_matrix_latest.json")
    baseline_manifest_path = resolved_tables_dir / "baseline_manifest_latest.json"
    baseline_manifest = load_json(baseline_manifest_path) if baseline_manifest_path.exists() else {}
    source_of_funds_monthly_rows = load_csv_rows(resolved_evidence_dir / "source_of_funds_monthly_comparison.csv")

    report_text = build_report(
        monitoring=monitoring,
        kpi=kpi,
        defillama_context=defillama_context,
        tickets=tickets,
        payout_summary=payout_summary,
        canonical_summary=canonical_summary,
        gate=gate,
        source_of_funds=source_of_funds,
        emissions=emissions,
        v2_summary=v2_summary,
        bounded_bands=bounded_bands,
        scenario_assumptions=scenario_assumptions,
        scenario_matrix=scenario_matrix,
        baseline_manifest=baseline_manifest,
        source_of_funds_monthly_rows=source_of_funds_monthly_rows,
        monitoring_path=monitoring_path,
        evidence_dir=resolved_evidence_dir,
        tables_dir=resolved_tables_dir,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report_text, encoding="utf-8")
    print(f"Wrote comprehensive report to {output_path}")


def main() -> None:
    default_output_path = PROJECT_ROOT / "paper" / "comprehensive_value_accrual_report.md"
    default_monitoring_path = RESULTS_DIR / "tables" / "monitoring_latest.json"

    parser = argparse.ArgumentParser(description="Generate comprehensive SUMR value-accrual report from artifacts.")
    parser.add_argument("--output-path", type=Path, default=default_output_path)
    parser.add_argument("--monitoring-path", type=Path, default=default_monitoring_path)
    parser.add_argument("--evidence-dir", type=Path, default=None)
    parser.add_argument("--tables-dir", type=Path, default=None)
    args = parser.parse_args()

    run(
        output_path=args.output_path,
        monitoring_path=args.monitoring_path,
        evidence_dir=args.evidence_dir,
        tables_dir=args.tables_dir,
    )


if __name__ == "__main__":
    main()
