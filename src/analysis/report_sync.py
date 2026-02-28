"""
Refresh investor-report fact blocks from latest monitoring/evidence artifacts.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from src.config import PROJECT_ROOT, RESULTS_DIR

AUTO_FACTS_START = "<!-- BEGIN AUTO_FACTS -->"
AUTO_FACTS_END = "<!-- END AUTO_FACTS -->"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def format_amount(value: Any, decimals: int = 6) -> str:
    if value is None:
        return "n/a"
    amount = Decimal(str(value))
    return f"{amount:,.{decimals}f}"


def format_percent(value: Any, decimals: int = 4) -> str:
    if value is None:
        return "n/a"
    amount = Decimal(str(value)) * Decimal(100)
    return f"{amount:.{decimals}f}%"


def find_ticket(tickets_payload: dict[str, Any], ticket_id: str) -> dict[str, Any]:
    for ticket in tickets_payload.get("tickets", []):
        if ticket.get("ticket_id") == ticket_id:
            return ticket
    return {}


def count_open_high_tickets(tickets_payload: dict[str, Any]) -> int:
    return len(
        [
            ticket
            for ticket in tickets_payload.get("tickets", [])
            if ticket.get("status") == "OPEN" and ticket.get("severity") == "HIGH"
        ]
    )


def first_not_none(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def build_auto_facts(
    monitoring: dict[str, Any],
    kpi: dict[str, Any],
    tickets: dict[str, Any],
    bounded_bands: dict[str, Any],
    scenario_assumptions: dict[str, Any],
    monitoring_path: Path,
) -> str:
    latest = monitoring.get("latest", {})
    fee_ticket = find_ticket(tickets, "FEE-RATE-001")
    open_high_count = count_open_high_tickets(tickets)
    baseline_band = bounded_bands.get("bounds_baseline") or {}
    confidence_band = bounded_bands.get("confidence") or {}
    scenario_values = scenario_assumptions.get("assumptions") or {}
    scenario_token = scenario_values.get("token_price_usd") or {}
    scenario_supply = scenario_values.get("circulating_supply_tokens") or {}

    lines = [
        "## Current Facts (Auto-Generated)",
        "",
        "### Sources",
        f"- Synced UTC: {datetime.now(timezone.utc).isoformat()}",
        f"- Monitoring source: `{monitoring_path.as_posix()}`",
        f"- Evidence as-of: `{kpi.get('as_of_utc')}`",
        "",
        "### Fee-Rate Reconciliation (FEE-RATE-001)",
        f"- Fee window: `{kpi.get('fees_window_start_date')}` -> `{kpi.get('fees_window_end_date')}` (`{kpi.get('fees_window_days')}` days)",
        f"- Fees (window sum): `{format_amount(kpi.get('fees_derived_90d'))}` USD",
        f"- Annualized fees: `{format_amount(kpi.get('fees_derived_90d_annualized'))}` USD",
        f"- Avg TVL (matched fee window): `{format_amount(kpi.get('lazy_tvl_window_avg_usd'))}` USD (`{kpi.get('lazy_tvl_window_points')}` points)",
        "- Formula: `observed_rate = fees_derived_90d_annualized / lazy_tvl_window_avg_usd`",
        f"- Observed realized annualized fee rate: `{format_percent(fee_ticket.get('observed'))}`",
        f"- Ticket status: `{fee_ticket.get('status', 'UNKNOWN')}` (`{fee_ticket.get('severity', 'UNKNOWN')}`)",
        f"- Ticket note: {fee_ticket.get('note', 'n/a')}",
        "",
        "### Monitoring Snapshot",
        f"- Observed UTC: `{latest.get('observed_utc')}`",
        f"- Refresh block range: `{latest.get('refresh_from_block')}` -> `{latest.get('refresh_to_block')}`",
        f"- SIP3.13 confidence: `{latest.get('sip313_confidence_class')}`",
        f"- SIP3.13.1 confidence: `{latest.get('sip3131_confidence_class')}`",
        f"- LVUSDC claim events (post-exec): `{latest.get('post_lvusdc_claim_events')}`",
        f"- LVUSDC claim total (post-exec): `{format_amount(latest.get('post_lvusdc_claim_total'))}`",
        f"- Gate passed: `{latest.get('all_campaigns_pass')}`",
        f"- v2 gate KPI status: `{latest.get('v2_gate_kpi_status')}`",
        f"- v2 scenario status: `{latest.get('v2_scenario_status')}`",
        "",
        "### Bounded Decision Bands (Supplemental, Non-Gate-Validated)",
        f"- Bounded band status: `{latest.get('v2_bounded_band_status')}`",
        "- Policy: bounded bands are supplemental; strict gate outputs remain the validated scenario path.",
        f"- Aggregate confidence class: `{first_not_none(latest.get('v2_bounded_band_confidence_class'), confidence_band.get('aggregate_confidence_class'))}`",
        f"- Lower bound (claimed attributed, USDC-eq): `{format_amount(first_not_none(latest.get('v2_bounded_band_lower_usdc_equivalent'), baseline_band.get('lower_bound_claimed_attributed_usdc_equivalent')))}`",
        f"- Upper bound (deposited, USDC-eq): `{format_amount(first_not_none(latest.get('v2_bounded_band_upper_usdc_equivalent'), baseline_band.get('upper_bound_deposited_usdc_equivalent')))}`",
        f"- Realized ratio (lower/upper): `{format_percent(baseline_band.get('realized_ratio_lower_to_upper'))}`",
        "",
        "### Scenario Assumption Pins",
        f"- Scenario assumptions status: `{first_not_none(latest.get('scenario_assumptions_status'), scenario_assumptions.get('status'))}`",
        f"- Circulating supply pin (tokens): `{format_amount(first_not_none(latest.get('scenario_circ_supply_tokens'), scenario_supply.get('value')))}`",
        f"- Token price pin (USD): `{format_amount(first_not_none(latest.get('scenario_token_price_usd'), scenario_token.get('value')))}`",
        f"- Token price source: `{first_not_none(latest.get('scenario_token_price_source'), scenario_token.get('source_label'), scenario_token.get('source_kind'))}`",
        f"- Open high-severity tickets: `{open_high_count}`",
    ]
    return "\n".join(lines) + "\n"


def replace_marked_section(text: str, replacement: str) -> str:
    if AUTO_FACTS_START not in text or AUTO_FACTS_END not in text:
        raise ValueError(
            "Missing report markers. Expected both "
            f"`{AUTO_FACTS_START}` and `{AUTO_FACTS_END}` in report file."
        )

    before, rest = text.split(AUTO_FACTS_START, 1)
    _, after = rest.split(AUTO_FACTS_END, 1)
    return f"{before}{AUTO_FACTS_START}\n\n{replacement}\n{AUTO_FACTS_END}{after}"


def run(report_path: Path, monitoring_path: Path, evidence_dir: Path | None) -> None:
    monitoring = load_json(monitoring_path)
    tables_dir = Path(monitoring.get("tables_dir") or monitoring_path.parent)

    resolved_evidence_dir = evidence_dir
    if resolved_evidence_dir is None:
        monitoring_evidence_dir = monitoring.get("evidence_dir")
        if not monitoring_evidence_dir:
            raise ValueError("Could not resolve evidence directory from args or monitoring payload.")
        resolved_evidence_dir = Path(monitoring_evidence_dir)

    kpi = load_json(resolved_evidence_dir / "kpi_summary.json")
    tickets = load_json(resolved_evidence_dir / "discrepancy_tickets.json")
    sip3131 = load_json(resolved_evidence_dir / "payout_chain_sip3_13_1_summary.json")
    bounded_path = tables_dir / "v2_bounded_decision_bands.json"
    bounded_bands = load_json(bounded_path) if bounded_path.exists() else {}
    scenario_assumptions_path = tables_dir / "scenario_assumptions_latest.json"
    scenario_assumptions = load_json(scenario_assumptions_path) if scenario_assumptions_path.exists() else {}

    monitoring_lvusdc_events = monitoring.get("latest", {}).get("post_lvusdc_claim_events")
    evidence_lvusdc_events = (sip3131.get("post_execution_claims") or {}).get("lvusdc_claim_events")
    if monitoring_lvusdc_events is not None and evidence_lvusdc_events is not None:
        if int(monitoring_lvusdc_events) != int(evidence_lvusdc_events):
            raise ValueError(
                "LVUSDC claim event mismatch between monitoring and evidence artifacts: "
                f"{monitoring_lvusdc_events} (monitoring) vs {evidence_lvusdc_events} (evidence). "
                "Run `make monitor_cycle` before `make report`."
            )

    auto_facts = build_auto_facts(monitoring, kpi, tickets, bounded_bands, scenario_assumptions, monitoring_path)
    original = report_path.read_text(encoding="utf-8")
    updated = replace_marked_section(original, auto_facts)
    report_path.write_text(updated, encoding="utf-8")

    print(f"Updated report facts in {report_path}")


def main() -> None:
    default_report_path = PROJECT_ROOT / "paper" / "report.md"
    default_monitoring_path = RESULTS_DIR / "tables" / "monitoring_latest.json"

    parser = argparse.ArgumentParser(description="Sync report fact block from latest monitoring/evidence artifacts.")
    parser.add_argument("--report-path", type=Path, default=default_report_path)
    parser.add_argument("--monitoring-path", type=Path, default=default_monitoring_path)
    parser.add_argument("--evidence-dir", type=Path, default=None)
    args = parser.parse_args()

    run(report_path=args.report_path, monitoring_path=args.monitoring_path, evidence_dir=args.evidence_dir)


if __name__ == "__main__":
    main()
