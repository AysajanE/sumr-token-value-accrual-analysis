"""
v2 execution workflow artifacts:
1) Discrepancy ticket closure workflow
2) Gate-passed KPI tables/charts
3) Gate-validated scenario outputs
4) Supplemental bounded decision-band outputs (non-gate replacement)
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt

from src.config import RESULTS_DIR

getcontext().prec = 50


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_decimal(value: str | int | float | None) -> Decimal:
    if value is None:
        return Decimal(0)
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    return Decimal(value)


CONFIDENCE_RANK = {
    "EXACT": 0,
    "BOUNDED": 1,
    "PARTIAL": 2,
    "UNPROVEN": 3,
}


def aggregate_confidence_class(campaign_rows: list[dict[str, Any]]) -> str:
    if not campaign_rows:
        return "UNKNOWN"

    classes = [str(row.get("attribution_confidence_class") or "UNKNOWN").upper() for row in campaign_rows]
    classes_sorted = sorted(classes, key=lambda cls: CONFIDENCE_RANK.get(cls, 99), reverse=True)
    return classes_sorted[0] if classes_sorted else "UNKNOWN"


def decimal_ratio(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator <= 0:
        return Decimal(0)
    return numerator / denominator


def ensure_transition_plan(ticket: dict[str, Any]) -> dict[str, Any]:
    ticket_id = ticket["ticket_id"]
    status = ticket["status"]
    severity = ticket["severity"]
    category = ticket["category"]

    if status == "RESOLVED":
        return {
            "next_status": "RESOLVED",
            "recommended_terminal_status": "RESOLVED",
            "open_to_investigating_action": "Validate resolved evidence artifacts remain reproducible after refresh.",
            "investigating_to_resolved_criteria": "Delta remains within threshold and evidence artifacts are current.",
            "investigating_to_accepted_risk_criteria": "",
            "owner": "analysis-qc",
            "priority_rank": 99,
        }

    open_to_investigating_action = "Reproduce discrepancy from latest artifacts and confirm root cause."
    investigating_to_resolved_criteria = "Root cause addressed and ticket delta meets threshold with updated evidence."
    investigating_to_accepted_risk_criteria = "Root cause is structural/non-actionable; document impact and keep monitoring."
    recommended_terminal_status = "RESOLVED"
    owner = "analysis-qc"

    if ticket_id.startswith("FEE-RATE-"):
        owner = "analysis-fees"
        investigating_to_resolved_criteria = (
            "Reconciled definition/scope and fee-rate delta is within tolerance or documented formula correction is accepted."
        )
    elif ticket_id.startswith("PAYOUT-ROUTING-"):
        owner = "analysis-payouts"
        investigating_to_resolved_criteria = (
            "Forum claim and on-chain routing either fully match or residual is explained with source-backed adjustment."
        )
    elif ticket_id.startswith("PAYOUT-ATTRIB-OVERLAP-"):
        owner = "analysis-attribution"
        recommended_terminal_status = "ACCEPTED_RISK"
        investigating_to_resolved_criteria = (
            "Only if exact campaign-level claim mapping becomes available from new data or protocol changes."
        )
        investigating_to_accepted_risk_criteria = (
            "Attribution overlap remains structural; impact disclosed and confidence class remains PARTIAL."
        )
    elif ticket_id.startswith("PAYOUT-ATTRIB-CLAIMS-"):
        owner = "analysis-attribution"
        investigating_to_resolved_criteria = (
            "Observed reward-token claims become non-zero and residual declines with refreshed claim snapshots."
        )
    elif category == "fee_reconciliation":
        owner = "analysis-fees"
    elif category == "payout_routing":
        owner = "analysis-payouts"

    severity_rank = {"HIGH": 1, "MEDIUM": 2, "LOW": 3}.get(severity, 9)
    return {
        "next_status": "INVESTIGATING",
        "recommended_terminal_status": recommended_terminal_status,
        "open_to_investigating_action": open_to_investigating_action,
        "investigating_to_resolved_criteria": investigating_to_resolved_criteria,
        "investigating_to_accepted_risk_criteria": investigating_to_accepted_risk_criteria,
        "owner": owner,
        "priority_rank": severity_rank,
    }


def build_ticket_closure_workflow(evidence_dir: Path) -> dict[str, Any]:
    tickets_path = evidence_dir / "discrepancy_tickets.json"
    payload = load_json(tickets_path)
    tickets = payload.get("tickets", [])
    rows: list[dict[str, Any]] = []

    for ticket in tickets:
        transition = ensure_transition_plan(ticket)
        rows.append(
            {
                "ticket_id": ticket["ticket_id"],
                "category": ticket["category"],
                "severity": ticket["severity"],
                "current_status": ticket["status"],
                "next_status": transition["next_status"],
                "recommended_terminal_status": transition["recommended_terminal_status"],
                "owner": transition["owner"],
                "priority_rank": transition["priority_rank"],
                "label": ticket.get("label"),
                "title": ticket.get("title"),
                "expected": ticket.get("expected"),
                "observed": ticket.get("observed"),
                "delta_abs": ticket.get("delta_abs"),
                "delta_pct_of_expected": ticket.get("delta_pct_of_expected"),
                "evidence_files": ticket.get("evidence_files"),
                "open_to_investigating_action": transition["open_to_investigating_action"],
                "investigating_to_resolved_criteria": transition["investigating_to_resolved_criteria"],
                "investigating_to_accepted_risk_criteria": transition["investigating_to_accepted_risk_criteria"],
            }
        )

    rows.sort(key=lambda r: (r["priority_rank"], r["ticket_id"]))

    write_csv(
        evidence_dir / "ticket_closure_workflow.csv",
        rows,
        [
            "ticket_id",
            "category",
            "severity",
            "current_status",
            "next_status",
            "recommended_terminal_status",
            "owner",
            "priority_rank",
            "label",
            "title",
            "expected",
            "observed",
            "delta_abs",
            "delta_pct_of_expected",
            "evidence_files",
            "open_to_investigating_action",
            "investigating_to_resolved_criteria",
            "investigating_to_accepted_risk_criteria",
        ],
    )

    summary = {
        "ticket_count": len(rows),
        "open_tickets": sum(1 for r in rows if r["current_status"] == "OPEN"),
        "resolved_tickets": sum(1 for r in rows if r["current_status"] == "RESOLVED"),
        "target_terminal_status_counts": {
            "RESOLVED": sum(1 for r in rows if r["recommended_terminal_status"] == "RESOLVED"),
            "ACCEPTED_RISK": sum(1 for r in rows if r["recommended_terminal_status"] == "ACCEPTED_RISK"),
        },
    }

    workflow_payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source_file": tickets_path.name,
        "status_model": ["OPEN", "INVESTIGATING", "RESOLVED", "ACCEPTED_RISK"],
        "summary": summary,
        "tickets": rows,
    }
    save_json(evidence_dir / "ticket_closure_workflow.json", workflow_payload)
    return workflow_payload


def chart_gate_passed_revenue(campaign_rows: list[dict[str, Any]], chart_path: Path) -> None:
    chart_path.parent.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(8, 5))
    if not campaign_rows:
        plt.text(0.5, 0.5, "No gate-passed cycles", ha="center", va="center", fontsize=12)
        plt.axis("off")
        plt.title("Gate-Passed Cycle Revenue Components")
        plt.tight_layout()
        plt.savefig(chart_path, dpi=160)
        plt.close()
        return

    labels = [row["label"] for row in campaign_rows]
    claimed = [float(row["staker_revenue_claimed_tokens_attributed"]) for row in campaign_rows]
    residual = [float(row["staker_revenue_unclaimed_tokens_residual"]) for row in campaign_rows]
    x = range(len(labels))

    plt.bar(x, claimed, label="claimed_attributed")
    plt.bar(x, residual, bottom=claimed, label="unclaimed_residual")
    plt.xticks(list(x), labels)
    plt.ylabel("Reward Token Units")
    plt.title("Gate-Passed Cycle Revenue Components")
    plt.legend()
    plt.tight_layout()
    plt.savefig(chart_path, dpi=160)
    plt.close()


def chart_gate_passed_efficiency(campaign_rows: list[dict[str, Any]], chart_path: Path) -> None:
    chart_path.parent.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(8, 5))
    if not campaign_rows:
        plt.text(0.5, 0.5, "No gate-passed cycles", ha="center", va="center", fontsize=12)
        plt.axis("off")
        plt.title("Gate-Passed Claim Efficiency")
        plt.tight_layout()
        plt.savefig(chart_path, dpi=160)
        plt.close()
        return

    labels = [row["label"] for row in campaign_rows]
    efficiency = []
    for row in campaign_rows:
        dep = parse_decimal(row["staker_revenue_deposited_tokens"])
        clm = parse_decimal(row["staker_revenue_claimed_tokens_attributed"])
        efficiency.append(float((clm / dep) if dep > 0 else Decimal(0)))
    x = range(len(labels))

    plt.bar(x, efficiency)
    plt.ylim(0, 1.05)
    plt.xticks(list(x), labels)
    plt.ylabel("Claim Efficiency (claimed_attributed / deposited)")
    plt.title("Gate-Passed Claim Efficiency")
    plt.tight_layout()
    plt.savefig(chart_path, dpi=160)
    plt.close()


def build_gate_passed_kpis(evidence_dir: Path, tables_dir: Path, charts_dir: Path) -> dict[str, Any]:
    gate = load_json(evidence_dir / "payout_attribution_gate.json")
    summary = load_json(evidence_dir / "payout_attribution_summary.json")
    campaigns = summary.get("campaigns", [])
    gate_rows = gate.get("campaigns", [])

    passed_labels = {row["label"] for row in gate_rows if row.get("pass")}
    passed_campaigns = [c for c in campaigns if c.get("label") in passed_labels]

    deposited = sum(parse_decimal(c.get("staker_revenue_deposited_tokens")) for c in passed_campaigns)
    claimed = sum(parse_decimal(c.get("staker_revenue_claimed_tokens_attributed")) for c in passed_campaigns)
    unclaimed = sum(parse_decimal(c.get("staker_revenue_unclaimed_tokens_residual")) for c in passed_campaigns)

    weighted_residual_ratio = (unclaimed / deposited) if deposited > 0 else Decimal(0)
    claim_efficiency = (claimed / deposited) if deposited > 0 else Decimal(0)

    kpi_payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source_files": [
            (evidence_dir / "payout_attribution_gate.json").name,
            (evidence_dir / "payout_attribution_summary.json").name,
        ],
        "status": "BLOCKED_NO_GATE_PASSED_CYCLES" if not passed_campaigns else "READY",
        "campaigns_total": len(campaigns),
        "campaigns_passed": len(passed_campaigns),
        "gate_pass_rate": float(Decimal(len(passed_campaigns)) / Decimal(len(campaigns))) if campaigns else 0.0,
        "staker_revenue_deposited_tokens_total": float(deposited),
        "staker_revenue_claimed_tokens_attributed_total": float(claimed),
        "staker_revenue_unclaimed_tokens_residual_total": float(unclaimed),
        "claim_efficiency": float(claim_efficiency),
        "weighted_residual_ratio": float(weighted_residual_ratio),
    }

    tables_dir.mkdir(parents=True, exist_ok=True)
    save_json(tables_dir / "v2_gate_passed_kpis.json", kpi_payload)
    write_csv(
        tables_dir / "v2_gate_passed_cycles.csv",
        passed_campaigns,
        [
            "label",
            "campaign_id_hex",
            "campaign_source",
            "reward_token_symbol",
            "staker_revenue_deposited_tokens",
            "staker_revenue_claimed_tokens_considered",
            "staker_revenue_claimed_tokens_attributed",
            "staker_revenue_unclaimed_tokens_residual",
            "residual_ratio",
            "attribution_confidence_class",
            "attribution_confidence_reasons",
        ],
    )

    md = [
        "# v2 Gate-Passed KPI Summary",
        "",
        f"- Generated UTC: {kpi_payload['generated_utc']}",
        f"- Status: {kpi_payload['status']}",
        f"- Campaigns passed: {kpi_payload['campaigns_passed']} / {kpi_payload['campaigns_total']}",
        f"- Pass rate: {kpi_payload['gate_pass_rate']:.4f}",
        f"- Deposited total: {kpi_payload['staker_revenue_deposited_tokens_total']:.6f}",
        f"- Claimed attributed total: {kpi_payload['staker_revenue_claimed_tokens_attributed_total']:.6f}",
        f"- Unclaimed residual total: {kpi_payload['staker_revenue_unclaimed_tokens_residual_total']:.6f}",
        f"- Claim efficiency: {kpi_payload['claim_efficiency']:.4f}",
        f"- Weighted residual ratio: {kpi_payload['weighted_residual_ratio']:.4f}",
    ]
    (tables_dir / "v2_gate_passed_kpis.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    chart_gate_passed_revenue(passed_campaigns, charts_dir / "v2_gate_passed_revenue_components.png")
    chart_gate_passed_efficiency(passed_campaigns, charts_dir / "v2_gate_passed_claim_efficiency.png")
    return {"kpis": kpi_payload, "passed_campaigns": passed_campaigns}


def build_gate_validated_scenarios(
    passed_campaigns: list[dict[str, Any]],
    tables_dir: Path,
    charts_dir: Path,
) -> dict[str, Any]:
    tables_dir.mkdir(parents=True, exist_ok=True)
    charts_dir.mkdir(parents=True, exist_ok=True)

    if not passed_campaigns:
        payload = {
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "status": "BLOCKED_NO_GATE_PASSED_CYCLES",
            "reason": "No campaigns satisfy gate rule (EXACT/BOUNDED confidence + residual threshold).",
            "scenarios": [],
        }
        save_json(tables_dir / "v2_gate_validated_scenarios.json", payload)
        write_csv(
            tables_dir / "v2_gate_validated_scenarios.csv",
            [
                {
                    "scenario_id": "blocked",
                    "status": payload["status"],
                    "reason": payload["reason"],
                    "projected_deposited": 0.0,
                    "projected_claimed": 0.0,
                    "projected_unclaimed": 0.0,
                }
            ],
            ["scenario_id", "status", "reason", "projected_deposited", "projected_claimed", "projected_unclaimed"],
        )
        (tables_dir / "v2_gate_validated_scenarios.md").write_text(
            "# v2 Gate-Validated Scenarios\n\n- Status: BLOCKED_NO_GATE_PASSED_CYCLES\n"
            "- Reason: No campaigns satisfy gate rule (EXACT/BOUNDED confidence + residual threshold).\n",
            encoding="utf-8",
        )
        return payload

    deposited_values = [parse_decimal(row["staker_revenue_deposited_tokens"]) for row in passed_campaigns]
    claimed_values = [parse_decimal(row["staker_revenue_claimed_tokens_attributed"]) for row in passed_campaigns]

    baseline_deposited = sum(deposited_values) / Decimal(len(deposited_values))
    total_dep = sum(deposited_values)
    total_clm = sum(claimed_values)
    baseline_efficiency = (total_clm / total_dep) if total_dep > 0 else Decimal(0)

    payout_scale_multipliers = [Decimal("0.5"), Decimal("1.0"), Decimal("2.0"), Decimal("5.0")]
    efficiency_multipliers = [Decimal("0.8"), Decimal("1.0"), Decimal("1.2")]

    rows = []
    for p_mult in payout_scale_multipliers:
        for e_mult in efficiency_multipliers:
            projected_dep = baseline_deposited * p_mult
            projected_eff = min(Decimal(1), baseline_efficiency * e_mult)
            projected_clm = projected_dep * projected_eff
            projected_unclaimed = projected_dep - projected_clm
            rows.append(
                {
                    "scenario_id": f"p{p_mult}_e{e_mult}",
                    "status": "RUN",
                    "payout_scale_multiplier": float(p_mult),
                    "efficiency_multiplier": float(e_mult),
                    "projected_deposited": float(projected_dep),
                    "projected_claimed": float(projected_clm),
                    "projected_unclaimed": float(projected_unclaimed),
                    "projected_claim_efficiency": float(projected_eff),
                }
            )

    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "status": "RUN",
        "baseline": {
            "baseline_deposited_per_cycle": float(baseline_deposited),
            "baseline_claim_efficiency": float(baseline_efficiency),
            "source": "gate-passed campaigns only",
        },
        "scenarios": rows,
    }
    save_json(tables_dir / "v2_gate_validated_scenarios.json", payload)
    write_csv(
        tables_dir / "v2_gate_validated_scenarios.csv",
        rows,
        [
            "scenario_id",
            "status",
            "payout_scale_multiplier",
            "efficiency_multiplier",
            "projected_deposited",
            "projected_claimed",
            "projected_unclaimed",
            "projected_claim_efficiency",
        ],
    )
    (tables_dir / "v2_gate_validated_scenarios.md").write_text(
        "# v2 Gate-Validated Scenarios\n\n"
        f"- Baseline deposited per cycle: {float(baseline_deposited):.6f}\n"
        f"- Baseline claim efficiency: {float(baseline_efficiency):.6f}\n"
        "- Source: gate-passed campaigns only\n",
        encoding="utf-8",
    )

    plt.figure(figsize=(8, 5))
    x = [row["scenario_id"] for row in rows]
    y = [row["projected_claimed"] for row in rows]
    plt.bar(x, y)
    plt.xticks(rotation=45, ha="right")
    plt.ylabel("Projected Claimed (token units)")
    plt.title("v2 Gate-Validated Scenario Output")
    plt.tight_layout()
    plt.savefig(charts_dir / "v2_gate_validated_scenarios.png", dpi=160)
    plt.close()
    return payload


def chart_bounded_decision_bands(rows: list[dict[str, Any]], chart_path: Path) -> None:
    chart_path.parent.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(8, 5))
    if not rows:
        plt.text(0.5, 0.5, "No bounded-band rows", ha="center", va="center", fontsize=12)
        plt.axis("off")
        plt.title("v2 Supplemental Bounded Decision Bands")
        plt.tight_layout()
        plt.savefig(chart_path, dpi=160)
        plt.close()
        return

    labels = [row["scenario_id"] for row in rows]
    lower = [float(row["lower_bound_claimed_attributed_usdc_equivalent"]) for row in rows]
    upper = [float(row["upper_bound_deposited_usdc_equivalent"]) for row in rows]
    x = range(len(labels))

    plt.bar(x, upper, color="#dbeafe", label="upper_bound_deposited")
    plt.bar(x, lower, color="#1d4ed8", label="lower_bound_claimed")
    plt.xticks(list(x), labels, rotation=30, ha="right")
    plt.ylabel("USDC-equivalent")
    plt.title("v2 Supplemental Bounded Decision Bands")
    plt.legend()
    plt.tight_layout()
    plt.savefig(chart_path, dpi=160)
    plt.close()


def build_bounded_decision_bands(
    evidence_dir: Path,
    tables_dir: Path,
    charts_dir: Path,
    gate_kpis_status: str,
    gate_scenario_status: str,
) -> dict[str, Any]:
    tables_dir.mkdir(parents=True, exist_ok=True)
    charts_dir.mkdir(parents=True, exist_ok=True)

    summary_path = evidence_dir / "payout_attribution_summary.json"
    decomposition_path = evidence_dir / "emissions_vs_revenue_decomposition.json"
    gate_path = evidence_dir / "payout_attribution_gate.json"

    payout_summary = load_json(summary_path)
    decomposition = load_json(decomposition_path)
    gate = load_json(gate_path)

    campaigns = payout_summary.get("campaigns", [])
    revenue_equiv = decomposition.get("revenue_component_usdc_equivalent") or {}

    has_usdc_equiv = all(
        revenue_equiv.get(key) is not None for key in ("deposited", "claimed_attributed", "unclaimed_residual")
    )

    lower = parse_decimal(revenue_equiv.get("claimed_attributed")) if has_usdc_equiv else Decimal(0)
    upper = parse_decimal(revenue_equiv.get("deposited")) if has_usdc_equiv else Decimal(0)
    residual = parse_decimal(revenue_equiv.get("unclaimed_residual")) if has_usdc_equiv else Decimal(0)
    width = upper - lower
    realized_ratio = decimal_ratio(lower, upper)

    class_counts: dict[str, int] = {}
    campaign_details: list[dict[str, Any]] = []
    for row in campaigns:
        confidence_class = str(row.get("attribution_confidence_class") or "UNKNOWN").upper()
        class_counts[confidence_class] = class_counts.get(confidence_class, 0) + 1
        campaign_details.append(
            {
                "label": row.get("label"),
                "confidence_class": confidence_class,
                "residual_ratio": row.get("residual_ratio"),
                "confidence_reasons": row.get("attribution_confidence_reasons") or [],
            }
        )

    aggregate_class = aggregate_confidence_class(campaigns)
    multipliers = [Decimal("0.5"), Decimal("1.0"), Decimal("2.0"), Decimal("5.0")]

    if has_usdc_equiv:
        status = "READY_SUPPLEMENTAL_BOUNDED"
        reason = (
            "Bounded bands generated from claimed_attributed (lower) and deposited (upper) "
            "USDC-equivalent values."
        )
        rows = []
        for multiplier in multipliers:
            projected_lower = lower * multiplier
            projected_upper = upper * multiplier
            projected_width = width * multiplier
            projected_residual = residual * multiplier
            rows.append(
                {
                    "scenario_id": f"band_x{multiplier}",
                    "status": "RUN",
                    "payout_scale_multiplier": float(multiplier),
                    "lower_bound_claimed_attributed_usdc_equivalent": float(projected_lower),
                    "upper_bound_deposited_usdc_equivalent": float(projected_upper),
                    "range_width_usdc_equivalent": float(projected_width),
                    "unclaimed_residual_usdc_equivalent": float(projected_residual),
                    "realized_ratio_lower_to_upper": float(realized_ratio),
                    "aggregate_confidence_class": aggregate_class,
                }
            )
    else:
        status = "UNAVAILABLE_MISSING_USDC_EQ_REVENUE"
        reason = "Missing required fields in emissions_vs_revenue_decomposition.revenue_component_usdc_equivalent."
        rows = [
            {
                "scenario_id": "unavailable",
                "status": status,
                "payout_scale_multiplier": 0.0,
                "lower_bound_claimed_attributed_usdc_equivalent": None,
                "upper_bound_deposited_usdc_equivalent": None,
                "range_width_usdc_equivalent": None,
                "unclaimed_residual_usdc_equivalent": None,
                "realized_ratio_lower_to_upper": None,
                "aggregate_confidence_class": aggregate_class,
            }
        ]

    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "reason": reason,
        "source_files": [
            summary_path.name,
            decomposition_path.name,
            gate_path.name,
        ],
        "strict_gate_context": {
            "gate_rule": gate.get("rule"),
            "all_campaigns_pass": gate.get("all_campaigns_pass"),
            "v2_gate_kpis_status": gate_kpis_status,
            "v2_gate_scenario_status": gate_scenario_status,
            "policy_note": (
                "Bounded decision bands are supplemental outputs and do not replace strict gate-validated scenarios."
            ),
        },
        "bounds_baseline": {
            "lower_bound_claimed_attributed_usdc_equivalent": float(lower) if has_usdc_equiv else None,
            "upper_bound_deposited_usdc_equivalent": float(upper) if has_usdc_equiv else None,
            "range_width_usdc_equivalent": float(width) if has_usdc_equiv else None,
            "unclaimed_residual_usdc_equivalent": float(residual) if has_usdc_equiv else None,
            "realized_ratio_lower_to_upper": float(realized_ratio) if has_usdc_equiv else None,
        },
        "confidence": {
            "aggregate_confidence_class": aggregate_class,
            "class_counts": class_counts,
            "campaigns": campaign_details,
        },
        "scenario_bands": rows,
    }
    save_json(tables_dir / "v2_bounded_decision_bands.json", payload)
    write_csv(
        tables_dir / "v2_bounded_decision_bands.csv",
        rows,
        [
            "scenario_id",
            "status",
            "payout_scale_multiplier",
            "lower_bound_claimed_attributed_usdc_equivalent",
            "upper_bound_deposited_usdc_equivalent",
            "range_width_usdc_equivalent",
            "unclaimed_residual_usdc_equivalent",
            "realized_ratio_lower_to_upper",
            "aggregate_confidence_class",
        ],
    )

    baseline = payload["bounds_baseline"]
    md = [
        "# v2 Supplemental Bounded Decision Bands",
        "",
        f"- Status: {status}",
        f"- Reason: {reason}",
        "- Policy: Supplemental output; strict gate outputs remain unchanged.",
        f"- Aggregate confidence class: {aggregate_class}",
        f"- Lower bound (claimed attributed, USDC-eq): {baseline['lower_bound_claimed_attributed_usdc_equivalent']}",
        f"- Upper bound (deposited, USDC-eq): {baseline['upper_bound_deposited_usdc_equivalent']}",
        f"- Range width (USDC-eq): {baseline['range_width_usdc_equivalent']}",
        f"- Realized ratio (lower/upper): {baseline['realized_ratio_lower_to_upper']}",
    ]
    (tables_dir / "v2_bounded_decision_bands.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    chart_rows = rows if status == "READY_SUPPLEMENTAL_BOUNDED" else []
    chart_bounded_decision_bands(chart_rows, charts_dir / "v2_bounded_decision_bands.png")
    return payload


def run(evidence_dir: Path, tables_dir: Path, charts_dir: Path) -> None:
    closure = build_ticket_closure_workflow(evidence_dir)
    gate_kpis = build_gate_passed_kpis(evidence_dir, tables_dir, charts_dir)
    scenarios = build_gate_validated_scenarios(gate_kpis["passed_campaigns"], tables_dir, charts_dir)
    bounded = build_bounded_decision_bands(
        evidence_dir=evidence_dir,
        tables_dir=tables_dir,
        charts_dir=charts_dir,
        gate_kpis_status=gate_kpis["kpis"]["status"],
        gate_scenario_status=scenarios["status"],
    )

    summary = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "evidence_dir": evidence_dir.as_posix(),
        "tables_dir": tables_dir.as_posix(),
        "charts_dir": charts_dir.as_posix(),
        "ticket_workflow": closure["summary"],
        "gate_kpis_status": gate_kpis["kpis"]["status"],
        "scenario_status": scenarios["status"],
        "bounded_band_status": bounded["status"],
        "bounded_band_confidence_class": bounded["confidence"]["aggregate_confidence_class"],
        "bounded_band_baseline_lower_usdc_equivalent": bounded["bounds_baseline"][
            "lower_bound_claimed_attributed_usdc_equivalent"
        ],
        "bounded_band_baseline_upper_usdc_equivalent": bounded["bounds_baseline"][
            "upper_bound_deposited_usdc_equivalent"
        ],
    }
    save_json(tables_dir / "v2_workflow_summary.json", summary)
    print(f"Wrote v2 workflow outputs to {tables_dir} and {charts_dir}")


def main() -> None:
    default_evidence = RESULTS_DIR / "proofs" / "evidence_2026-02-09-independent"
    default_tables = RESULTS_DIR / "tables"
    default_charts = RESULTS_DIR / "charts"

    parser = argparse.ArgumentParser(description="Build v2 closure workflow, gate-passed KPIs, and gate-validated scenarios.")
    parser.add_argument("--evidence-dir", type=Path, default=default_evidence)
    parser.add_argument("--tables-dir", type=Path, default=default_tables)
    parser.add_argument("--charts-dir", type=Path, default=default_charts)
    args = parser.parse_args()

    if not args.evidence_dir.exists():
        raise FileNotFoundError(f"Evidence directory not found: {args.evidence_dir}")

    run(args.evidence_dir, args.tables_dir, args.charts_dir)


if __name__ == "__main__":
    main()
