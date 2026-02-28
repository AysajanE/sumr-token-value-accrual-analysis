"""
Append a monitoring snapshot after a refresh/evidence/workflow run.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import DATA_DIR, RESULTS_DIR


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv_rows(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def first_not_none(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def parse_cycle_table(path: Path) -> dict[str, dict[str, str]]:
    rows = read_csv_rows(path)
    return {row["label"]: row for row in rows}


def run(snapshot_dir: Path, evidence_dir: Path, tables_dir: Path) -> None:
    manifest = load_json(snapshot_dir / "manifest_claim_refresh_latest.json")
    last_run = manifest["runs"][-1]

    sip3131 = load_json(evidence_dir / "payout_chain_sip3_13_1_summary.json")
    post_claims = sip3131["post_execution_claims"]

    cycle_map = parse_cycle_table(evidence_dir / "payout_attribution_cycle_table.csv")
    sip313_cycle = cycle_map.get("SIP3.13", {})
    sip3131_cycle = cycle_map.get("SIP3.13.1", {})

    gate = load_json(evidence_dir / "payout_attribution_gate.json")
    v2 = load_json(tables_dir / "v2_workflow_summary.json")
    bounded = load_json(tables_dir / "v2_bounded_decision_bands.json") if (tables_dir / "v2_bounded_decision_bands.json").exists() else {}
    baseline = load_json(tables_dir / "baseline_manifest_latest.json") if (tables_dir / "baseline_manifest_latest.json").exists() else {}
    scenario_assumptions = load_json(tables_dir / "scenario_assumptions_latest.json") if (tables_dir / "scenario_assumptions_latest.json").exists() else {}
    tickets = load_json(evidence_dir / "discrepancy_tickets.json")
    bounded_baseline = bounded.get("bounds_baseline") or {}
    bounded_confidence = bounded.get("confidence") or {}
    baseline_scope = baseline.get("scope") or {}
    baseline_fingerprints = baseline.get("fingerprints") or {}
    scenario_values = (scenario_assumptions.get("assumptions") or {})
    scenario_token = scenario_values.get("token_price_usd") or {}
    scenario_supply = scenario_values.get("circulating_supply_tokens") or {}

    open_high = len([t for t in tickets.get("tickets", []) if t.get("status") == "OPEN" and t.get("severity") == "HIGH"])

    row: dict[str, Any] = {
        "observed_utc": datetime.now(timezone.utc).isoformat(),
        "refresh_run_utc": last_run.get("run_utc"),
        "refresh_from_block": last_run.get("from_block"),
        "refresh_to_block": last_run.get("to_block"),
        "refresh_files_written": len(last_run.get("files", [])),
        "sip313_confidence_class": sip313_cycle.get("attribution_confidence_class", ""),
        "sip313_claim_events": sip313_cycle.get("claim_events_considered", ""),
        "sip313_unclaimed_residual": sip313_cycle.get("staker_revenue_unclaimed_tokens_residual", ""),
        "sip3131_confidence_class": sip3131_cycle.get("attribution_confidence_class", ""),
        "sip3131_claim_events": sip3131_cycle.get("claim_events_considered", ""),
        "sip3131_unclaimed_residual": sip3131_cycle.get("staker_revenue_unclaimed_tokens_residual", ""),
        "post_usdc_claim_events": post_claims.get("usdc_claim_events"),
        "post_usdc_claim_total": post_claims.get("usdc_claim_total"),
        "post_lvusdc_claim_events": post_claims.get("lvusdc_claim_events"),
        "post_lvusdc_claim_total": post_claims.get("lvusdc_claim_total"),
        "post_abasusdc_claim_events": post_claims.get("abasusdc_claim_events"),
        "post_abasusdc_claim_total": post_claims.get("abasusdc_claim_total"),
        "all_campaigns_pass": gate.get("all_campaigns_pass"),
        "gate_rule": gate.get("rule"),
        "v2_gate_kpi_status": v2.get("gate_kpis_status"),
        "v2_scenario_status": v2.get("scenario_status"),
        "v2_bounded_band_status": first_not_none(v2.get("bounded_band_status"), bounded.get("status")),
        "v2_bounded_band_confidence_class": first_not_none(
            v2.get("bounded_band_confidence_class"),
            bounded_confidence.get("aggregate_confidence_class"),
        ),
        "v2_bounded_band_lower_usdc_equivalent": first_not_none(
            v2.get("bounded_band_baseline_lower_usdc_equivalent"),
            bounded_baseline.get("lower_bound_claimed_attributed_usdc_equivalent"),
        ),
        "v2_bounded_band_upper_usdc_equivalent": first_not_none(
            v2.get("bounded_band_baseline_upper_usdc_equivalent"),
            bounded_baseline.get("upper_bound_deposited_usdc_equivalent"),
        ),
        "baseline_manifest_generated_utc": baseline.get("generated_utc"),
        "baseline_manifest_file_count": baseline_scope.get("file_count"),
        "baseline_manifest_tree_sha256": baseline_fingerprints.get("tree_sha256"),
        "scenario_assumptions_generated_utc": scenario_assumptions.get("generated_utc"),
        "scenario_assumptions_status": scenario_assumptions.get("status"),
        "scenario_token_price_pinned": scenario_token.get("pinned"),
        "scenario_token_price_usd": scenario_token.get("value"),
        "scenario_token_price_source": first_not_none(scenario_token.get("source_label"), scenario_token.get("source_kind")),
        "scenario_circ_supply_tokens": scenario_supply.get("value"),
        "ticket_count": tickets.get("summary", {}).get("ticket_count"),
        "open_ticket_count": tickets.get("summary", {}).get("status_counts", {}).get("OPEN"),
        "resolved_ticket_count": tickets.get("summary", {}).get("status_counts", {}).get("RESOLVED"),
        "open_high_ticket_count": open_high,
    }

    fieldnames = list(row.keys())
    monitoring_csv = tables_dir / "monitoring_cycles.csv"
    history = read_csv_rows(monitoring_csv)
    history.append(row)
    write_csv_rows(monitoring_csv, history, fieldnames)

    latest_payload = {
        "generated_utc": row["observed_utc"],
        "snapshot_dir": snapshot_dir.as_posix(),
        "evidence_dir": evidence_dir.as_posix(),
        "tables_dir": tables_dir.as_posix(),
        "latest": row,
        "history_count": len(history),
    }
    write_json(tables_dir / "monitoring_latest.json", latest_payload)

    markdown = [
        "# Monitoring Snapshot",
        "",
        f"- Observed UTC: {row['observed_utc']}",
        f"- Refresh blocks: {row['refresh_from_block']} -> {row['refresh_to_block']}",
        f"- SIP3.13.1 LVUSDC claim events: {row['post_lvusdc_claim_events']}",
        f"- Gate passed: {row['all_campaigns_pass']}",
        f"- v2 gate KPI status: {row['v2_gate_kpi_status']}",
        f"- v2 scenario status: {row['v2_scenario_status']}",
        f"- v2 bounded band status: {row['v2_bounded_band_status']}",
        f"- v2 bounded band confidence: {row['v2_bounded_band_confidence_class']}",
        f"- v2 bounded lower/upper (USDC-eq): {row['v2_bounded_band_lower_usdc_equivalent']} / {row['v2_bounded_band_upper_usdc_equivalent']}",
        f"- Baseline manifest UTC: {row['baseline_manifest_generated_utc']}",
        f"- Baseline manifest files hashed: {row['baseline_manifest_file_count']}",
        f"- Scenario assumptions status: {row['scenario_assumptions_status']}",
        f"- Scenario token price pin: {row['scenario_token_price_usd']} ({row['scenario_token_price_source']})",
        f"- Open high-severity tickets: {row['open_high_ticket_count']}",
    ]
    (tables_dir / "monitoring_latest.md").write_text("\n".join(markdown) + "\n", encoding="utf-8")

    print(f"Appended monitoring snapshot to {monitoring_csv}")


def main() -> None:
    default_snapshot_dir = DATA_DIR / "snapshots" / "external_review" / "2026-02-09-independent"
    default_evidence_dir = RESULTS_DIR / "proofs" / "evidence_2026-02-09-independent"
    default_tables_dir = RESULTS_DIR / "tables"

    parser = argparse.ArgumentParser(description="Append a monitoring snapshot row from latest evidence outputs.")
    parser.add_argument("--snapshot-dir", type=Path, default=default_snapshot_dir)
    parser.add_argument("--evidence-dir", type=Path, default=default_evidence_dir)
    parser.add_argument("--tables-dir", type=Path, default=default_tables_dir)
    args = parser.parse_args()

    run(args.snapshot_dir, args.evidence_dir, args.tables_dir)


if __name__ == "__main__":
    main()
