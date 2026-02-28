# SUMR Token Value Accrual Comprehensive Report (Evidence-First)

- Report generated UTC: `2026-02-26T20:07:55.800197+00:00`
- Monitoring snapshot UTC: `2026-02-25T21:03:28.819095+00:00`
- Monitoring source: `results/tables/monitoring_latest.json`
- Evidence directory: `results/proofs/evidence_2026-02-09-independent`
- Tables directory: `results/tables`

## 1) Decision Snapshot

- Current investor-facing classification: **CONDITIONAL**
- Technical classification code: `CONDITIONAL_BOUNDED`
- Interpretation: Routing and funding evidence are present, but strict gate validation is still blocked.
- Strict gate status: `False` (rule: `campaign confidence must be EXACT or BOUNDED and residual_ratio <= 0.05`)
- v2 strict scenario status: `BLOCKED_NO_GATE_PASSED_CYCLES`
- v2 bounded band status: `READY_SUPPLEMENTAL_BOUNDED`
- Open high-severity tickets: `0`
- Protocol data-fidelity risk: `Claimed(user, token, amount)` logs omit `campaign_id`, so campaign attribution is bounded by token/window heuristics.

### Pillar Status

| Pillar | Current status | Evidence anchor |
| --- | --- | --- |
| Fee generation and fee-rate reconciliation | RESOLVED (LOW) | Observed annualized fee rate 0.62% |
| Treasury->staker payout routing | PROVEN_ON_CHAIN | SIP3.13 + SIP3.13.1 execute tx and funding transfer receipts |
| Campaign claim realization quality | PARTIAL | SIP3.13.1 residual ratio 76.66% |
| Campaign attribution data fidelity | RISK_PRESENT | Distributor claim events omit campaign IDs; attribution remains bounded rather than campaign-exact. |
| Source of funds | BOUNDED | USDC comparable coverage ratio 5.703x |
| Scenario assumption pinning | READY_PINNED | price=$0.005000 (manual_pin_baseline_assumption) |
| Strict gate for validated scenarios | BLOCKED | BLOCKED_NO_GATE_PASSED_CYCLES |

## 2) Data Provenance and Reproducibility

- Monitoring observed UTC: `2026-02-25T21:03:28.819095+00:00`
- Refresh block range: `41932733 -> 42628137`
- Baseline manifest UTC: `2026-02-25T21:03:02.142321+00:00`
- Baseline tree SHA256: `83b02e7a3b8c3f6954c76010a5769c4f2e4cd8d8edbca25297e669e1dc14d7c7`
- Scenario assumptions status: `READY_PINNED`
- Circulating supply pin (tokens): `977,149,629.397309`
- Token price pin (USD): `$0.005000`
- Token price source: `manual_pin_baseline_assumption`

## 3) Protocol Baseline (Current Window)

| Metric | Value |
| --- | --- |
| Lazy Summer latest TVL | $58,578,780.00 |
| Lazy Summer peak TVL | $196,694,657.00 |
| Summer.fi latest TVL | $87,410,562.00 |
| 30d fees (derived) | $41,418.00 |
| 90d fees (derived) | $132,082.00 |
| 90d annualized fees | $535,665.89 |
| Window-matched average TVL | $86,389,173.69 |
| Observed annualized fee rate | 0.62% |
| Circulating supply (pinned) | 977,149,629.397309 |
| Token price (pinned) | $0.005000 |
| Implied market cap at pin | $4,885,748.15 |
| Implied FDV at pin | $5,000,000.00 |

### 3.1 Scope-Reconciliation Check (TVL Narratives)

| Context | Value | Interpretation |
| --- | --- | --- |
| Lazy Summer latest TVL | $58,578,780.00 | Primary token-backing protocol scope for this analysis. |
| Summer.fi TVL near 2024-11-01 | $190,117,326.00 | Potential source of 190M headline values; broader Summer.fi scope should not be mixed with Lazy Summer without explicit qualifier. |
| Lazy Summer peak TVL date | 2025-10-07 | Peak timing differs from older 2024 headline narratives; use date-scoped claims only. |

## 4) On-Chain Value Accrual Verification

### 4.1 Campaign-Level Routing and Realization

| Campaign | Reward token | Deposited to distributor | Claimed attributed | Residual unclaimed | Residual ratio | Confidence |
| --- | --- | --- | --- | --- | --- | --- |
| SIP3.13 | USDC | 5,833.985241 | 5,833.985241 | 0.000000 | 0.00% | PARTIAL |
| SIP3.13.1 | LVUSDC | 8,301.739885 | 1,937.690789 | 6,364.049096 | 76.66% | PARTIAL |

### 4.1.a Campaign Attribution Data-Fidelity Risk

- Contract event schema issue: `Claimed(user, token, amount)` does not emit campaign ID.
- Impact: campaign-level realization cannot be reconstructed as a single deterministic join key.
- Practical effect: confidence remains `PARTIAL` unless residuals compress or event schema is upgraded.
- Risk ownership: protocol contract/event design, not downstream analytics implementation.

### 4.2 Canonical Revenue Accounting (Aggregate)

- Deposited total (token-native): `14,135.725126`
- Claimed attributed total (token-native): `7,771.676030`
- Unclaimed residual total (token-native): `6,364.049096`
- Canonical policy: `min(claimed_considered, deposited)`

### 4.3 Source-of-Funds Evidence

- Source-of-funds status: `BOUNDED`
- Status basis: `non_fee_token_payouts_present:LVUSDC`
- Comparable token set: `USDC`
- Non-comparable payout tokens: `LVUSDC`
- Comparable fee-aligned inflow total: `33,271.226947`
- Comparable staker payout outflow total: `5,833.985241`
- Comparable coverage ratio: `5.703x`

Recent monthly comparison (latest 6 rows):

| Month | Token | Fee-aligned inflow | Staker payout outflow | Net inflow - payout | Coverage |
| --- | --- | --- | --- | --- | --- |
| 2025-12 | WETH | 0.000000 | 0.000000 | 0.000000 | n/a |
| 2026-01 | EURC | 641.965818 | 0.000000 | 641.965818 | n/a |
| 2026-01 | USDC | 3,320.673117 | 5,833.985241 | -2,513.312124 | 0.569x |
| 2026-01 | WETH | 0.365521 | 0.000000 | 0.365521 | n/a |
| 2026-02 | LVUSDC | 0.000000 | 8,301.739885 | -8,301.739885 | 0.000x |
| 2026-02 | USDC | 10,427.000000 | 0.000000 | 10,427.000000 | n/a |

### 4.4 Emissions vs Revenue Decomposition

- Emissions events observed: `4`
- Total SUMR emissions (tokens): `3,396,151.000000`
- Revenue deposited (USDC-equivalent): `$14,619.86`
- Revenue claimed attributed (USDC-equivalent): `$7,885.58`
- Revenue unclaimed residual (USDC-equivalent): `$6,743.75`
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
| SIP3.13 | PARTIAL | 0.00% | False |
| SIP3.13.1 | PARTIAL | 76.66% | False |

Discrepancy ticket inventory:

| Ticket | Severity | Status | Title | Delta vs expected |
| --- | --- | --- | --- | --- |
| FEE-RATE-001 | LOW | RESOLVED | Realized annualized fee rate deviates from claimed 0.66% | 6.051% |
| PAYOUT-ROUTING-001 | LOW | RESOLVED | Forum treasury transfer vs on-chain routed amount | 0.000% |
| PAYOUT-ROUTING-002 | MEDIUM | OPEN | Forum treasury transfer vs on-chain USDC routed into LVUSDC path | 0.047% |
| PAYOUT-ATTRIB-OVERLAP-SIP3.13 | MEDIUM | OPEN | Same-token prior funding overlap limits campaign attribution confidence | n/a |

## 6) Scenario Analysis (Pinned Assumptions)

- Scenario matrix status: `READY_PINNED`
- Scenario count: `192`
- Positive staker-share scenarios: `144`
- Realization ratio applied for lower-bound outputs: `53.94%`

### 6.1 Distribution Summary Across Positive Staker-Share Scenarios

| Metric | P10 | P50 | P90 | Min | Max |
| --- | --- | --- | --- | --- | --- |
| Annual staker revenue (lower, USD) | $5,213.33 | $31,595.91 | $180,096.68 | $1,579.80 | $473,938.64 |
| Annual staker revenue (upper, USD) | $9,665.50 | $58,578.78 | $333,899.05 | $2,928.94 | $878,681.70 |
| Yield on mcap (lower) | 0.11% | 0.65% | 3.69% | 0.03% | 9.70% |
| Yield on mcap (upper) | 0.20% | 1.20% | 6.83% | 0.06% | 17.98% |
| Yield on FDV (lower) | 0.10% | 0.63% | 3.60% | 0.03% | 9.48% |
| Yield on FDV (upper) | 0.19% | 1.17% | 6.68% | 0.06% | 17.57% |
| Yield on staked value (lower) | 0.32% | 2.59% | 18.70% | 0.05% | 97.00% |
| Yield on staked value (upper) | 0.60% | 4.80% | 34.67% | 0.10% | 179.85% |

### 6.2 Reference Scenarios (Lower/Upper Realization Bands)

| Case | Parameters (TVL / fee / staker share / staking ratio) | Annual staker USD (lower) | Annual staker USD (upper) | Yield on mcap (lower) | Yield on mcap (upper) | Yield on staked (lower) | Yield on staked (upper) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Downside | 0.5x / 0.10% / 10% / 30% | $1,579.80 | $2,928.94 | 0.03% | 0.06% | 0.11% | 0.20% |
| Base | 1.0x / 0.66% / 20% / 30% | $41,706.60 | $77,323.99 | 0.85% | 1.58% | 2.85% | 5.28% |
| Upside | 2.0x / 1.00% / 30% / 30% | $189,575.46 | $351,472.68 | 3.88% | 7.19% | 12.93% | 23.98% |

### 6.3 Baseline Sensitivity by Staking Ratio

Fixed assumptions: TVL=1.0x current, fee rate=0.66%, staker share=20%.

| Staking ratio | Annual staker USD (lower) | Annual staker USD (upper) | Yield on staked (lower) | Yield on staked (upper) | Yield on mcap (lower) | Yield on mcap (upper) |
| --- | --- | --- | --- | --- | --- | --- |
| 10% | $41,706.60 | $77,323.99 | 8.54% | 15.83% | 0.85% | 1.58% |
| 30% | $41,706.60 | $77,323.99 | 2.85% | 5.28% | 0.85% | 1.58% |
| 60% | $41,706.60 | $77,323.99 | 1.42% | 2.64% | 0.85% | 1.58% |

## 7) Evidence-Based Decision Framework

Current regime and implications:
- Regime: `CONDITIONAL_BOUNDED`
- Strict gate: `False`
- Source-of-funds: `BOUNDED`
- Open high-severity tickets: `0`

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
