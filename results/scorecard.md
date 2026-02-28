# Validation Scorecard -- Remediated (Evidence-Strict)

Claim-by-claim verdicts under strict verification rules.

Last updated: 2026-02-09 (UTC)

Primary snapshot sources:
- `data/snapshots/external_review/2026-02-09/manifest.json`
- `data/snapshots/external_review/2026-02-09/manifest_paginated_core.json`

Primary derived evidence tables:
- `results/proofs/evidence_2026-02-09/README.md`

## Core Claims (A-E)

| # | Claim | Verdict | Confidence | Evidence Class | Evidence / Notes |
|---|-------|---------|------------|----------------|------------------|
| A | ~0.66% annual fee on vault deposits | **PARTIAL** | MEDIUM | API_DERIVED | Fee engine is active on-chain, but latest API-derived realized run-rate is closer to ~0.9% (`kpi_summary.json`: 90d annualized fees / latest TVL). Specific 0.66% value is not currently reproduced via vault-level on-chain computation in this repo. |
| B | 20% of tips go to SUMR stakers | **PARTIAL** | MEDIUM | GOVERNANCE_FORUM + ONCHAIN_EXECUTED | SIP3.13 and SIP3.13.1 forum proposals state 20% and arithmetic checks to 20.0% (`forum_payout_ratios.csv`). Full end-to-end claim settlement trace per cycle is not fully assembled in artifacts. |
| C | Paid as USDC (denominated LV tokens) | **PARTIAL** | MEDIUM | GOVERNANCE_FORUM + ONCHAIN_EXECUTED | Forum proposals specify LVUSDC/USDC-denominated payouts (`forum_payout_claims.csv`). Supporting treasury/foundation funding-path transfers observed (`eth_treasury_fee_token_outflows.csv`, `base_foundation_tipstream_fee_token_outflows.csv`), but full claimant-level settlement proof is still incomplete. |
| D | Staking: locks 0-3y, 20% penalty, dual rewards framing | **PASS** | HIGH | ONCHAIN_EXECUTED + GOVERNANCE_FORUM | Contract source checks confirm lock/penalty constants and architecture (`contract_source_checks.json`). Dual-rewards framing is supported at governance-claim level (forum) plus emissions on-chain. |
| E | Max supply 1B, mint-controlled cap | **PASS** | HIGH | ONCHAIN_EXECUTED | `cap()` = 1B in raw/on-chain state; current supply snapshot recorded (`sumr_supply_snapshot.json`). |

---

## Infrastructure Claims (F-J)

| # | Claim | Verdict | Confidence | Evidence Class | Evidence / Notes |
|---|-------|---------|------------|----------------|------------------|
| F | Fee collection mechanism works (TipJar) | **PASS** | HIGH | ONCHAIN_EXECUTED | Multiple `shakeAll` executions observed across Base/Arb/Eth (`*_tipjar_method_counts.csv`), with decoded transfer evidence in sampled Base txs (`base_sample_tx_transfer_decodes.csv`). |
| G | Fee split matches docs (30/20/20/30) | **PASS** | HIGH | ONCHAIN_EXECUTED | Sampled Base transactions show exact split amounts (`base_sample_tx_transfer_decodes.csv`). |
| H | Treasury accumulates fee revenue | **PASS** | HIGH | ONCHAIN_EXECUTED | Treasury appears as fee recipient in sampled TipJar distributions and has subsequent fee-token movement history (`base_sample_tx_transfer_decodes.csv`, `base_treasury_fee_token_outflows.csv`, `eth_treasury_fee_token_outflows.csv`). |
| I | Governance-controlled revenue sharing exists | **PARTIAL** | HIGH | GOVERNANCE_FORUM + ONCHAIN_EXECUTED | Monthly governance proposals exist and funding-path txs are observed, but distribution remains manual and not fully evidenced end-to-end within one deterministic proof chain in current artifacts. |
| J | Stakers receive protocol revenue | **PARTIAL** | MEDIUM | GOVERNANCE_FORUM + ONCHAIN_EXECUTED | Proposal-level evidence and partial funding-path chain are present; claimant-level completion proof remains a gap in this artifact set. |

---

## Context Claims (K-O)

| # | Claim | Verdict | Confidence | Evidence Class | Evidence / Notes |
|---|-------|---------|------------|----------------|------------------|
| K | DeFi lending TVL ~$58B (ATH framing) | **PARTIAL** | MEDIUM | API_DERIVED + external market sources | Current aggregate values are source- and definition-dependent; ATH framing remains time/definition sensitive. |
| L | Lazy Summer peaked $190M in Nov 2024 | **FAIL** | HIGH | API_DERIVED | Lazy Summer starts in Feb 2025 and peaks in Oct 2025; ~190M on Nov 2024 maps to Summer.fi dataset, not Lazy Summer (`defillama_context_summary.json`). |
| M | Lending grew 15B to 120B+ | **PARTIAL** | MEDIUM | external market sources | Directional growth is plausible, but exact metric definitions (TVL vs other lending metrics) are not standardized in the claim. |
| N | Euler 940% YoY | **PARTIAL** | MEDIUM | external market sources | Growth magnitude appears plausible in specific windows; “YoY” wording is often imprecise versus YTD windows. |
| O | Coinbase $1B+ Morpho; EF 2,400 ETH | **PARTIAL** | HIGH | external market sources | Underlying facts are externally reported, but they are not direct Lazy Summer protocol validation evidence. |

---

## KPI Snapshot (As of 2026-02-09 UTC)

Source: `results/proofs/evidence_2026-02-09/kpi_summary.json`

| Metric | Value |
|--------|-------|
| Lazy Summer latest TVL | 58,578,780 |
| Lazy Summer peak TVL/date | 196,694,657 (2025-10-07) |
| Summer.fi latest TVL | 87,410,562 |
| Fees 24h | 842 |
| Fees 7d | 7,723 |
| Fees 30d (API) | 41,973 |
| Fees all-time (API) | 680,366 |
| Fees 90d annualized (derived) | 535,665.8889 |

Additional on-chain movement summary:
- Base treasury fee-token outflows in current dataset: 16 events (`base_treasury_fee_token_outflows.csv`)
- Ethereum treasury fee-token outflows in current dataset: 5 events (`eth_treasury_fee_token_outflows.csv`)

---

## Score Summary (Remediated)

| Category | PASS | FAIL | PARTIAL |
|----------|:----:|:----:|:-------:|
| Core (A-E) | 2 | 0 | 3 |
| Infrastructure (F-J) | 3 | 0 | 2 |
| Context (K-O) | 0 | 1 | 4 |
| **Total** | **5** | **1** | **9** |

---

## Key Corrections Applied

1. Removed over-claims that were not fully chain-proven end-to-end.
2. Downgraded payout-related claims from PASS to PARTIAL pending full settlement trace proof.
3. Corrected prior incorrect statement that treasury had only one fee-token outflow.
4. Corrected prior incorrect statement that GRM V2 had no RewardAdded history.
5. Enforced explicit source-class distinction: on-chain vs governance/forum vs API-derived.
