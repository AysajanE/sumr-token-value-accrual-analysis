# SUMR Token Value Accrual Comprehensive Report (Evidence-First)

- Report generated UTC: `2026-03-04T21:18:12.774645+00:00`
- Monitoring snapshot UTC: `2026-03-04T21:04:29.548860+00:00`
- Monitoring source: `/Users/aeziz-local/Side Projects/$sumr-token-value-accrual-analysis/results/tables/monitoring_latest.json`
- Evidence directory: `results/proofs/evidence_2026-03-04-independent-rerun4`
- Tables directory: `results/tables`

## 1) Decision Snapshot

- Current investor-facing classification: **RESTRICTED**
- Technical classification code: `RESTRICTED`
- Interpretation: Current evidence does not satisfy strict validation and risk posture remains constrained.
- Strict gate status: `False` (rule: `campaign confidence must be EXACT or BOUNDED and residual_ratio <= 0.05`)
- v2 strict scenario status: `BLOCKED_NO_GATE_PASSED_CYCLES`
- v2 bounded band status: `READY_SUPPLEMENTAL_BOUNDED`
- Open high-severity tickets: `1`
- Protocol data-fidelity risk: `Claimed(user, token, amount)` logs omit `campaign_id`, so campaign attribution is bounded by token/window heuristics.

### Pillar Status

| Pillar | Current status | Evidence anchor |
| --- | --- | --- |
| Fee generation and fee-rate reconciliation | RESOLVED (LOW) | Observed annualized fee rate 0.65% |
| Treasury->staker payout routing | PROVEN_ON_CHAIN | SIP3.13 + SIP3.13.1 execute tx and funding transfer receipts |
| Campaign claim realization quality | PARTIAL | SIP3.13.1 residual ratio 76.54% |
| Campaign attribution data fidelity | RISK_PRESENT | Distributor claim events omit campaign IDs; attribution remains bounded rather than campaign-exact. |
| Source of funds | BOUNDED | USDC comparable coverage ratio 5.883x |
| Scenario assumption pinning | READY_PINNED | price=$0.005000 (manual_pin_baseline_assumption) |
| Strict gate for validated scenarios | BLOCKED | BLOCKED_NO_GATE_PASSED_CYCLES |

## 2) Data Provenance and Reproducibility

- Monitoring observed UTC: `2026-03-04T21:04:29.548860+00:00`
- Refresh block range: `41932733 -> 42933895`
- Baseline manifest UTC: `2026-03-04T21:04:20.001437+00:00`
- Baseline tree SHA256: `7aeb2b56d7bceb3e1b4177cc04f20f9cd8171b5bc537d7c64ab14ee1086c0fbd`
- Scenario assumptions status: `READY_PINNED`
- Circulating supply pin (tokens): `977,149,629.405695`
- Token price pin (USD): `$0.005000`
- Token price source: `manual_pin_baseline_assumption`

## 3) Protocol Baseline (Current Window)

| Metric | Value |
| --- | --- |
| Lazy Summer latest TVL | $47,907,854.00 |
| Lazy Summer peak TVL | $196,694,657.00 |
| Summer.fi latest TVL | $73,609,793.00 |
| 30d fees (derived) | $29,799.00 |
| 90d fees (derived) | $119,094.00 |
| 90d annualized fees | $482,992.33 |
| Window-matched average TVL | $74,606,528.86 |
| Observed annualized fee rate | 0.65% |
| Circulating supply (pinned) | 977,149,629.405695 |
| Token price (pinned) | $0.005000 |
| Implied market cap at pin | $4,885,748.15 |
| Implied FDV at pin | $5,000,000.00 |

### 3.1 Scope-Reconciliation Check (TVL Narratives)

| Context | Value | Interpretation |
| --- | --- | --- |
| Lazy Summer latest TVL | $47,907,854.00 | Primary token-backing protocol scope for this analysis. |
| Summer.fi TVL near 2024-11-01 | $190,117,326.00 | Potential source of 190M headline values; broader Summer.fi scope should not be mixed with Lazy Summer without explicit qualifier. |
| Lazy Summer peak TVL date | 2025-10-07 | Peak timing differs from older 2024 headline narratives; use date-scoped claims only. |

## 4) On-Chain Value Accrual Verification

### 4.1 Campaign-Level Routing and Realization

| Campaign | Reward token | Deposited to distributor | Claimed attributed | Residual unclaimed | Residual ratio | Confidence |
| --- | --- | --- | --- | --- | --- | --- |
| SIP3.13 | USDC | 5,833.985241 | 0.000000 | 5,833.985241 | 100.00% | UNPROVEN |
| SIP3.13.1 | LVUSDC | 8,301.739885 | 1,947.513023 | 6,354.226862 | 76.54% | PARTIAL |

### 4.1.a Campaign Attribution Data-Fidelity Risk

- Contract event schema issue: `Claimed(user, token, amount)` does not emit campaign ID.
- Impact: campaign-level realization cannot be reconstructed as a single deterministic join key.
- Practical effect: confidence remains `PARTIAL` unless residuals compress or event schema is upgraded.
- Risk ownership: protocol contract/event design, not downstream analytics implementation.

### 4.2 Canonical Revenue Accounting (Aggregate)

- Deposited total (token-native): `14,135.725126`
- Claimed attributed total (token-native): `1,947.513023`
- Unclaimed residual total (token-native): `12,188.212103`
- Canonical policy: `min(claimed_considered, deposited)`

### 4.3 Source-of-Funds Evidence

- Source-of-funds status: `BOUNDED`
- Status basis: `non_fee_token_payouts_present:LVUSDC`
- Comparable token set: `USDC`
- Non-comparable payout tokens: `LVUSDC`
- Comparable fee-aligned inflow total: `34,324.196522`
- Comparable staker payout outflow total: `5,833.985241`
- Comparable coverage ratio: `5.883x`

Recent monthly comparison (latest 6 rows):

| Month | Token | Fee-aligned inflow | Staker payout outflow | Net inflow - payout | Coverage |
| --- | --- | --- | --- | --- | --- |
| 2026-01 | WETH | 0.365521 | 0.000000 | 0.365521 | n/a |
| 2026-02 | LVUSDC | 0.000000 | 8,301.739885 | -8,301.739885 | 0.000x |
| 2026-02 | USDC | 10,427.000000 | 0.000000 | 10,427.000000 | n/a |
| 2026-03 | EURC | 179.875547 | 0.000000 | 179.875547 | n/a |
| 2026-03 | USDC | 1,052.969575 | 0.000000 | 1,052.969575 | n/a |
| 2026-03 | WETH | 0.082541 | 0.000000 | 0.082541 | n/a |

### 4.4 Emissions vs Revenue Decomposition

- Emissions events observed: `4`
- Total SUMR emissions (tokens): `3,396,151.000000`
- Revenue deposited (USDC-equivalent): `$14,619.86`
- Revenue claimed attributed (USDC-equivalent): `$2,062.01`
- Revenue unclaimed residual (USDC-equivalent): `$12,571.21`
- Break-even SUMR price for emissions = deposited revenue: `$0.004305`
- Pinned token price / break-even: `1.161x`
- Inflationary pressure factor at pinned price: `1.161x` (values >1 imply emissions value exceeds deposited revenue value).
- LVUSDC valuation method: `lvusdc_convertToAssets_block_level_v1`

## 5) Gate and Discrepancy Status

- Gate rule: `campaign confidence must be EXACT or BOUNDED and residual_ratio <= 0.05`
- All campaigns pass strict gate: `False`
- v2 gate KPI status: `BLOCKED_NO_GATE_PASSED_CYCLES`
- v2 strict scenario status: `BLOCKED_NO_GATE_PASSED_CYCLES`
- Supplemental bounded status: `READY_SUPPLEMENTAL_BOUNDED`

Campaign gate checks:

| Campaign | Confidence class | Residual ratio | Pass |
| --- | --- | --- | --- |
| SIP3.13 | UNPROVEN | 100.00% | False |
| SIP3.13.1 | PARTIAL | 76.54% | False |

Discrepancy ticket inventory:

| Ticket | Severity | Status | Title | Delta vs expected |
| --- | --- | --- | --- | --- |
| FEE-RATE-001 | LOW | RESOLVED | Realized annualized fee rate deviates from claimed 0.66% | 1.911% |
| PAYOUT-ROUTING-001 | LOW | RESOLVED | Forum treasury transfer vs on-chain routed amount | 0.000% |
| PAYOUT-ROUTING-002 | MEDIUM | OPEN | Forum treasury transfer vs on-chain USDC routed into LVUSDC path | 0.047% |
| PAYOUT-ATTRIB-OVERLAP-SIP3.13 | MEDIUM | OPEN | Same-token prior funding overlap limits campaign attribution confidence | n/a |
| PAYOUT-ATTRIB-CLAIMS-SIP3.13 | HIGH | OPEN | Funded campaign has no observed reward-token claims | 100.000% |

## 6) Scenario Analysis (Pinned Assumptions)

- Scenario matrix status: `READY_PINNED`
- Scenario count: `192`
- Positive staker-share scenarios: `144`
- Realization ratio applied for lower-bound outputs: `14.10%`

### 6.1 Distribution Summary Across Positive Staker-Share Scenarios

| Metric | P10 | P50 | P90 | Min | Max |
| --- | --- | --- | --- | --- | --- |
| Annual staker revenue (lower, USD) | $1,114.90 | $6,757.00 | $38,514.88 | $337.85 | $101,354.95 |
| Annual staker revenue (upper, USD) | $7,904.80 | $47,907.85 | $273,074.77 | $2,395.39 | $718,617.81 |
| Yield on mcap (lower) | 0.02% | 0.14% | 0.79% | 0.01% | 2.07% |
| Yield on mcap (upper) | 0.16% | 0.98% | 5.59% | 0.05% | 14.71% |
| Yield on FDV (lower) | 0.02% | 0.14% | 0.77% | 0.01% | 2.03% |
| Yield on FDV (upper) | 0.16% | 0.96% | 5.46% | 0.05% | 14.37% |
| Yield on staked value (lower) | 0.07% | 0.55% | 4.00% | 0.01% | 20.75% |
| Yield on staked value (upper) | 0.49% | 3.92% | 28.36% | 0.08% | 147.08% |

### 6.2 Reference Scenarios (Lower/Upper Realization Bands)

| Case | Parameters (TVL / fee / staker share / staking ratio) | Annual staker USD (lower) | Annual staker USD (upper) | Yield on mcap (lower) | Yield on mcap (upper) | Yield on staked (lower) | Yield on staked (upper) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Downside | 0.5x / 0.10% / 10% / 30% | $337.85 | $2,395.39 | 0.01% | 0.05% | 0.02% | 0.16% |
| Base | 1.0x / 0.66% / 20% / 30% | $8,919.24 | $63,238.37 | 0.18% | 1.29% | 0.61% | 4.31% |
| Upside | 2.0x / 1.00% / 30% / 30% | $40,541.98 | $287,447.12 | 0.83% | 5.88% | 2.77% | 19.61% |

### 6.3 Baseline Sensitivity by Staking Ratio

Fixed assumptions: TVL=1.0x current, fee rate=0.66%, staker share=20%.

| Staking ratio | Annual staker USD (lower) | Annual staker USD (upper) | Yield on staked (lower) | Yield on staked (upper) | Yield on mcap (lower) | Yield on mcap (upper) |
| --- | --- | --- | --- | --- | --- | --- |
| 10% | $8,919.24 | $63,238.37 | 1.83% | 12.94% | 0.18% | 1.29% |
| 30% | $8,919.24 | $63,238.37 | 0.61% | 4.31% | 0.18% | 1.29% |
| 60% | $8,919.24 | $63,238.37 | 0.30% | 2.16% | 0.18% | 1.29% |

## 7) Evidence-Based Decision Framework

Current regime and implications:
- Regime: `RESTRICTED`
- Strict gate: `False`
- Source-of-funds: `BOUNDED`
- Open high-severity tickets: `1`

Upgrade triggers to strict-validated regime:
1. At least one monitoring cycle where `payout_attribution_gate.json` reports `all_campaigns_pass = true`.
2. SIP3.13.1 residual ratio declines to <= 5% under current gate rule.
3. Source-of-funds status reaches `PROVEN` or remains `BOUNDED` while eliminating non-comparable payout tokens.
4. Distributor contract/event upgrade emits campaign IDs in claim events, removing attribution ambiguity.
5. No open HIGH-severity discrepancy tickets.

Downside control triggers:
1. Fee-rate reconciliation re-opens with MEDIUM/HIGH severity.
2. Source-of-funds status degrades from `BOUNDED` to `UNKNOWN`.
3. Realization ratio trend declines across consecutive monitoring cycles.

## 8) Monitoring Runbook

Refresh and regenerate full decision package:
```bash
make monitor_cycle
make analyze
make report
```

Primary outputs to track each cycle:
- `results/tables/monitoring_latest.json`
- `results/proofs/evidence_2026-02-09-independent/discrepancy_tickets.json`
- `results/proofs/evidence_2026-02-09-independent/source_of_funds_summary.json`
- `results/proofs/evidence_2026-02-09-independent/emissions_vs_revenue_decomposition.json`
- `results/tables/v2_workflow_summary.json`
- `results/tables/v2_bounded_decision_bands.json`
- `results/tables/scenario_assumptions_latest.json`
- `results/tables/scenario_matrix_latest.json`

## 9) Artifact References

- `paper/report.md`
- `results/tables/monitoring_latest.json`
- `results/proofs/evidence_2026-02-09-independent/kpi_summary.json`
- `results/proofs/evidence_2026-02-09-independent/payout_attribution_summary.json`
- `results/proofs/evidence_2026-02-09-independent/staker_revenue_canonical_summary.json`
- `results/proofs/evidence_2026-02-09-independent/source_of_funds_summary.json`
- `results/proofs/evidence_2026-02-09-independent/emissions_vs_revenue_decomposition.json`
- `results/proofs/evidence_2026-02-09-independent/discrepancy_tickets.json`
- `results/tables/v2_workflow_summary.json`
- `results/tables/v2_bounded_decision_bands.json`
- `results/tables/scenario_assumptions_latest.json`
- `results/tables/scenario_matrix_latest.json`

## 10) Caveats

- This is an evidence synthesis report, not financial advice.
- Strict gate remains the validated-scenario standard; bounded bands are supplemental.
- Scenario outputs are assumption-sensitive even with pinning and should be refreshed with each new cycle.
