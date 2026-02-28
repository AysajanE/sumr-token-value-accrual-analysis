# Validation Plan v2 — SUMR Value Accrual (Investor-Grade, Evidence-First)

Last updated: 2026-02-09 (UTC)

## 1) Objective and Decision Context

This plan is designed for one practical outcome:
- determine whether SUMR has **real, recurring, on-chain value accrual** to stakers,
- and whether that accrual is strong enough and reliable enough to inform position sizing decisions.

Primary decision questions:
1. Are protocol fees/tips real, persistent, and measurable on-chain?
2. Does a stable share of those fees route to staker revenue (not just treasury/emissions)?
3. Are stakers actually receiving claimable/claimed USDC-equivalent value?
4. Is the revenue component meaningful relative to SUMR valuation and dilution?

## 2) Scope Strategy (Core-First)

Use a two-lane scope to prevent drift:

- `Lane A (must-pass before modeling)`: core SUMR accrual claims (A-E).
- `Lane B (appendix credibility)`: broader market/context claims (F-J).

No scenario modeling or investor conclusion is final until Lane A gates pass.

## 3) Current Status Snapshot (Known Reality Entering v2)

As of existing evidence artifacts:
- proposal execution + treasury/distributor funding are strongly evidenced on-chain,
- campaign IDs can be reconstructed from `NewCampaign` receipt logs,
- but distributor `Claimed(user, token, amount)` events do not contain campaign ID,
- therefore some attribution remains token-window bounded rather than campaign-exact,
- scenario-readiness gate is currently `false`.

v2 is designed to close this gap explicitly and avoid over-claiming certainty.

## 4) Non-Negotiable Evidence Rules

1. On-chain decoded logs/state are ground truth; docs/API are hypotheses.
2. Every reported value must be reproducible from stored snapshots and code.
3. Store raw integers plus decimals; avoid float-only persistence.
4. Separate accounting states:
   - deposited revenue,
   - claimed revenue,
   - unclaimed distributor balance.
5. Never combine “deposited OR claimed” into one headline metric.
6. Any unresolved discrepancy must be ticketed, not averaged away.

## 5) Canonical Metric Framework (v2)

These are the only approved core metrics for report-level conclusions:

### 5.1 Fee and Revenue Metrics

- `protocol_fees_accrued_usd(period)`
- `staker_revenue_deposited_usd(period)`
- `staker_revenue_claimed_usd(period)`
- `staker_revenue_unclaimed_usd(as_of_block)`
- `treasury_revenue_usd(period)`

### 5.2 Routing and Share Metrics

- `staker_share_realized = staker_revenue_deposited_usd / protocol_fees_accrued_usd`
- `treasury_share_realized = treasury_revenue_usd / protocol_fees_accrued_usd`
- `distribution_lag_days` (deposit event to median claim event)

### 5.3 Staking and Dilution Metrics

- `staked_sumr_daily`
- `lock_weighted_stake_daily`
- `emission_rewards_sumr(period)` and `emission_rewards_usd(period)`
- `revenue_share_of_total_rewards = revenue_usd / (revenue_usd + emissions_usd)`

### 5.4 Yield/Valuation Interface Metrics

- `revenue_apr_on_staked_value`
- `ttm_staker_revenue_yield_on_mcap`
- `ttm_staker_revenue_yield_on_fdv`

## 6) Attribution Confidence Model (Required)

All payout-cycle conclusions must carry an attribution class:

- `EXACT`: claim event or deterministic mapping directly ties claim to campaign.
- `BOUNDED`: campaign attribution is bounded by token/window/funding cap and residual tracked.
- `PARTIAL`: only directional linkage; overlap prevents strong attribution.
- `UNPROVEN`: no reliable chain-based path to attribution.

For each cycle report:
- campaign ID (if reconstructed),
- funding to distributor,
- funding to fee recipient,
- claimed total considered,
- residual unattributed,
- confidence class,
- reasons for downgrade.

## 7) Workstreams and Gates

### 7.1 Workstream A — Contract and ABI Truth Set

Outputs:
- `data/contracts/registry.csv` fully reconciled,
- ABI bundle with hash pins,
- proxy implementation timeline for upgradeable contracts.

Gate A (pass/fail):
- all contracts needed for A-E are identified and decodable across the full analysis window.

### 7.2 Workstream B — Fee Engine Verification

Outputs:
- daily fee accrual series by vault and aggregate,
- fee recipient routing map and transfer/mint evidence,
- reconciliation vs DeFiLlama with discrepancy tickets.

Gate B:
- fee accrual method is reproducible and reconciles within tolerance or fully explained.

### 7.3 Workstream C — Staker Revenue Flow Verification

Outputs:
- cycle-level funding/deposit/claim accounting,
- attribution confidence table per cycle,
- campaign proof pack with tx-level references.

Gate C:
- each reported staker revenue dollar has tx/log proof and valuation source,
- no mixed metric (deposited+claimed) in headline reporting.

### 7.4 Workstream D — Staking Mechanics and Emissions

Outputs:
- lock distribution and early-withdraw penalty validation,
- emissions vs revenue decomposition,
- governance mutability log (parameter changes over time).

Gate D:
- emissions/revenue split is quantified and reproducible.

### 7.5 Workstream E — Scenario Modeling (Only After A-D)

Outputs:
- scenario tables and sensitivity charts,
- assumptions register with range-based uncertainty.

Gate E:
- scenarios only use metrics that passed gates A-D.

## 8) Quality Controls (Operational)

1. Dedup key: `(tx_hash, log_index, chain_id)`.
2. Reorg-safe ingestion with confirmation buffer.
3. ABI versioning by implementation block range.
4. Daily deterministic artifact builds (`make` targets only).
5. Machine-readable readiness gate in output artifacts.

## 9) Known Hurdles and Mitigations

### 9.1 Hurdle: Claim events without campaign ID
- Risk: false precision in cycle attribution.
- Mitigation:
  - use confidence classes (`EXACT/BOUNDED/PARTIAL/UNPROVEN`),
  - reconstruct campaign IDs from receipt logs where possible,
  - track residual unattributed value explicitly.

### 9.2 Hurdle: Reward token NAV valuation at historical blocks
- Risk: mispricing LV-denominated rewards.
- Mitigation:
  - primary method = on-chain `convertToAssets`/share-price at event block,
  - store price source and block number for every valuation.

### 9.3 Hurdle: Multi-chain and timing mismatches
- Risk: false discrepancy vs APIs.
- Mitigation:
  - explicit scope labels (Lazy Summer vs Summer.fi, Base-only vs multi-chain),
  - timestamp alignment rules and discrepancy tickets.

### 9.4 Hurdle: Governance parameter mutability
- Risk: forward projections overstate stability.
- Mitigation:
  - maintain parameter-change log,
  - include governance haircuts in scenarios.

## 10) Deliverables for Stakeholder/Investor Sharing

Required package:
1. Executive verdict table: claim-by-claim with confidence and evidence class.
2. Core metrics dashboard (A-E only) with source traceability.
3. Proof pack (10+ tx proofs) with decoded fields and valuation method.
4. Residual uncertainty register (open gaps and why they matter).
5. Scenario appendix (only post-gate).

## 11) Report Framing Standard (to avoid overclaims)

Each major conclusion must include:
- `what is proven`,
- `what is bounded but not exact`,
- `what remains unknown`,
- `decision implication`.

No statement should imply campaign-exact payout attribution unless class is `EXACT`.

## 12) Execution Plan (Next 2 Cycles)

### Cycle 1 (Immediate)
1. Freeze current baseline artifacts and manifests.
2. Finalize canonical metric schema in code and docs.
3. Generate cycle-level attribution table with confidence classes.
4. Close top discrepancy tickets for fee and payout routing.

### Cycle 2
1. Complete staking emissions vs revenue decomposition.
2. Build report-grade KPI tables and visuals from gated metrics only.
3. Draft investor-facing narrative with explicit uncertainty register.
4. Run scenario analysis only on gate-passed variables.

## 13) Exit Criteria (Plan Complete)

This plan is complete only when all are true:
1. Lane A (A-E) has evidence-backed verdicts with confidence classes.
2. Staker revenue metrics are separated into deposited/claimed/unclaimed.
3. Attribution residuals are explicit and decision-relevant.
4. Scenario outputs are traceable to gate-passed historical metrics.
5. Final report is shareable without material caveat omissions.
