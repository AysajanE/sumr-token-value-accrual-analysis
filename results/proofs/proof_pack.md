# Evidence Pack -- Remediated, Source-Classed

This file separates what is directly proven on-chain from governance/forum claims and API-derived context.

Last updated: 2026-02-09 (UTC)

Primary evidence snapshot set:
- `data/snapshots/external_review/2026-02-09/manifest.json`
- `data/snapshots/external_review/2026-02-09/manifest_paginated_core.json`

Derived evidence tables:
- `results/proofs/evidence_2026-02-09/README.md`

## Evidence Classes

- `ONCHAIN_EXECUTED`: direct chain state/log/tx evidence.
- `GOVERNANCE_FORUM`: governance proposal text and forum statements.
- `API_DERIVED`: DeFiLlama/API state (timestamped snapshots).

---

## ONCHAIN_EXECUTED Proofs

### OC-01 TipJar split is executed on-chain (Base)

Evidence files:
- `results/proofs/evidence_2026-02-09/base_sample_tx_transfer_decodes.csv`

Verified transactions:
- `0xfb6877c5b85275982707f52d83a595092d1ddd98799cc65da05daf618be14f2d` (Base)
- `0xc16d8c1b1c2d5767b078f52fe9aad7f50018782b2b66e56f43f8f003a5e1eaa7` (Base)
- `0xbffa7e0b7852bb7521b5e664eab3358ebc64a1ec700c51563e0374fbb8652684` (Base, pre-SIP5.1)

What is proven:
- Current TipJar distributions execute exact 30/20/20/30 splits across USDC, EURC, and WETH in sampled txs.
- Pre-SIP5.1 tx shows the earlier 99.3% treasury pattern.

### OC-02 TipJar execution activity across chains

Evidence files:
- `results/proofs/evidence_2026-02-09/base_tipjar_method_counts.csv`
- `results/proofs/evidence_2026-02-09/arbitrum_tipjar_method_counts.csv`
- `results/proofs/evidence_2026-02-09/ethereum_tipjar_method_counts.csv`

Observed counts (from current explorer snapshots):
- Base TipJar: 12 `shakeAll` + 1 non-method tx
- Arbitrum TipJar: 10 `0xfffa445e` (shake selector) + 1 non-method tx
- Ethereum TipJar: 10 `shakeAll` + 1 non-method tx

What is proven:
- Cross-chain shake execution is active on Base/Arbitrum/Ethereum.

### OC-03 Treasury fee-token outflows are multiple, not singular

Evidence files:
- `results/proofs/evidence_2026-02-09/base_treasury_fee_token_outflows.csv`
- `results/proofs/evidence_2026-02-09/eth_treasury_fee_token_outflows.csv`
- `results/proofs/evidence_2026-02-09/treasury_outflow_summary.json`

Base outflows (USDC/EURC only in dataset):
- 16 events total
- USDC total: 21,327.865901
- EURC total: 4,010

Ethereum outflows (USDC/USDT/WETH):
- 5 events total
- USDC total: 92,699
- USDT total: 25,000
- WETH total: 8

Representative txs:
- Base treasury -> ops safe: `0x7a009081881a1834df80306b9acc15e6209b892fff443d810fe2692789fd206f`
- Base treasury -> distributor-related addresses: `0xc8b309fc0d63936a7a78d8bc02a1827aa416b4a3ad57501a87e8e640a6d55fa1`, `0x512757b0e0befc1a5e161840cf1f00348acbd459cad9b3535cc19a7eb0846184`, `0x04474b353ce96b331d71245e5423eb1e5da58dae561757f08f48ee709d3b3d6c`, `0x53953e2bf7b3b652f3a9e43c300e7391e187fe095460f681a525cc1669b58b58`, `0xec8f2bf10b21d8e69008b62f52c73335fa5da3033c03b14844af9e3a9ca71e81`, `0x5aa10ad32d3d6a3d15d614954dbbe960da2f4376301e28b39b063d485dc15941`, `0xccd1029fb6677c5b317120b4be3324c7080db88bf252e30abd56d24320ee4fad`
- Ethereum treasury -> foundation tipstream: `0x7fdc13df7c8815eb5cfaa675fc0deff3899741383336fdba0c3e0bfdca1c6c0c` (7,699 USDC)

What is proven:
- The statement "only one fee-token outflow" is false.
- Treasury fee-token outflows include both ops-safe and distributor/foundation-directed flows.

### OC-04 Treasury to staking transfer (SUMR emissions path)

Evidence files:
- `results/proofs/evidence_2026-02-09/base_sample_tx_transfer_decodes.csv`

Verified tx:
- `0x214ad55d65fd936af8082992101b0998891d1f25d80516e668f139a846f0e955`

What is proven:
- Treasury transferred 450,000 SUMR to SummerStakingV2 in this tx.
- This tx is SUMR-denominated emissions funding, not USDC/EURC/WETH transfer.

### OC-05 GovernanceRewardsManager V2 has RewardAdded history (SUMR token)

Evidence files:
- `data/snapshots/external_review/2026-02-09/base_blockscout_grm_rewardAdded_all.json`
- `results/proofs/evidence_2026-02-09/grm_rewardAdded_events.csv`

Observed RewardAdded tx hashes:
- `0x94e31b02404bc2dcc0776079dccfd1c3fcc0b9fcddc1e3f86d3a97f0d1e2585f`
- `0x94ff6dfe3cda7ac289d4b84455e6dbd1317a6dabb8e0a46c829b28034c04c163`
- `0x92d23885ffaf1a0cb3298ef0215d3fa83cac74b65a8cf3741bbd486c3f274eea`
- `0x96a3814ce6d9a7b3758863fbcc826f7b7346eda2da5850eb679d082c7eeab095`

What is proven:
- RewardAdded exists on GRM V2.
- All observed RewardAdded entries use SUMR token address `0x194f...1624`.
- "No RewardAdded ever" is incorrect.
- "No fee-token RewardAdded observed" remains supported by current topic-filtered evidence.

### OC-06 SUMR cap and supply snapshot

Evidence file:
- `results/proofs/evidence_2026-02-09/sumr_supply_snapshot.json`

Snapshot values:
- `decimals`: 18
- `cap_raw`: 1,000,000,000,000,000,000,000,000,000
- `cap_tokens`: 1,000,000,000
- `totalSupply_raw`: 977,149,629,397,309,000,000,000,000
- `totalSupply_tokens`: 977,149,629.397309

What is proven:
- 1B cap is on-chain enforced value in current contract state.

### OC-07 stSUMR transfer constraints and SummerStaking constants

Evidence files:
- `data/snapshots/external_review/2026-02-09/base_blockscout_stsumr_contract.json`
- `data/snapshots/external_review/2026-02-09/base_blockscout_summerstaking_contract.json`
- `results/proofs/evidence_2026-02-09/contract_source_checks.json`

What is proven:
- stSUMR source contains `_canTransfer` mint/burn-only rule and `xSumr_TransferNotAllowed` revert path.
- SummerStaking source contains constants for 3-year max lock, 2%-20% penalty bounds, 110-day fixed penalty period, coefficient 700.

---

## GOVERNANCE_FORUM Evidence (Not On-Chain Execution Proof)

### GF-01 SIP payout claims and arithmetic

Evidence files:
- `data/snapshots/external_review/2026-02-09/summer_forum_sip3_13.json`
- `data/snapshots/external_review/2026-02-09/summer_forum_sip3_13_1.json`
- `results/proofs/evidence_2026-02-09/forum_payout_claims.csv`
- `results/proofs/evidence_2026-02-09/forum_payout_ratios.csv`

Parsed claim values:
- SIP3.13: revenue 28,876.00; payout 5,775.20; treasury transfer 5,953.65368
- SIP3.13.1: revenue 43,504.49; payout 8,700.898; treasury transfer 8,961.92494

Computed from forum-stated values:
- staker share = 20.0% in both entries
- implied Merkl fee = ~3.09% (SIP3.13) and ~3.00% (SIP3.13.1)

What this supports:
- Governance proposal text claims 20% revenue share and LVUSDC/USDC-denominated payout framing.

What this does not by itself prove:
- It does not fully prove end-user claim settlement on-chain without execution + distributor claim traces.

### GF-02 Funding-path related transfers observed on-chain

Evidence files:
- `results/proofs/evidence_2026-02-09/eth_treasury_fee_token_outflows.csv`
- `results/proofs/evidence_2026-02-09/base_treasury_fee_token_outflows.csv`
- `results/proofs/evidence_2026-02-09/base_foundation_tipstream_fee_token_outflows.csv`

Observed transfers consistent with forum-described funding path:
- Ethereum treasury -> foundation tipstream: 7,699 USDC in tx `0x7fdc13df...`
- Base foundation tipstream -> base treasury: 10,427 USDC in tx `0x900f4d21...`

Interpretation status:
- Supports plausibility of cross-chain treasury funding workflow.
- Still partial for full payout lifecycle proof.

---

## API_DERIVED Evidence (Timestamped Snapshots)

### AP-01 TVL history and scope separation

Evidence files:
- `data/snapshots/external_review/2026-02-09/defillama_protocol_lazy_summer.json`
- `data/snapshots/external_review/2026-02-09/defillama_protocol_summer_fi.json`
- `results/proofs/evidence_2026-02-09/defillama_context_summary.json`

Snapshot results:
- Lazy Summer first point: 2025-02-11
- Lazy Summer peak: 196,694,657 on 2025-10-07
- Lazy Summer latest: 58,578,780 on 2026-02-09
- Summer.fi near 2024-11-01: 190,117,326

What this supports:
- Lazy Summer and Summer.fi are distinct DeFiLlama entities.
- "190M in Nov 2024" aligns with Summer.fi dataset, not Lazy Summer dataset.

### AP-02 Fees and run-rate snapshot

Evidence files:
- `data/snapshots/external_review/2026-02-09/defillama_fees_dailyFees_lazy_summer.json`
- `results/proofs/evidence_2026-02-09/kpi_summary.json`

Snapshot values:
- total24h: 842
- total7d: 7,723
- total30d: 41,973
- totalAllTime: 680,366
- derived 90d annualized (from daily chart): 535,665.8889

### AP-03 Chain coverage in current API metadata

Evidence file:
- `results/proofs/evidence_2026-02-09/defillama_context_summary.json`

Current `chainTvls` keys:
- Base, Ethereum, Arbitrum, Sonic, Hyperliquid L1

What this supports:
- API-side scope includes five chains.

---

## Claim Support Status (Remediated)

- `PROVEN_ONCHAIN`
  - TipJar split execution mechanics (sampled txs)
  - Cross-chain TipJar execution activity (Base/Arb/Eth)
  - SUMR cap and current supply snapshot
  - stSUMR non-transferability source checks
  - SummerStaking key constant presence
  - GRM RewardAdded exists (SUMR token)

- `SUPPORTED_BUT_PARTIAL`
  - "20% to stakers" and payout cadence claims (forum + partial funding-path tx evidence)
  - Full end-to-end payout settlement proof (missing in this artifact set)

- `CORRECTED_PREVIOUS_ERRORS`
  - Removed/overturned "Treasury's ONLY fee-token outflow" statement.
  - Removed/overturned "no RewardAdded events found" statement.
  - Explicitly separated on-chain proof from governance/forum and API-derived evidence.

---

## Open Evidence Gaps

1. Full payout lifecycle proof per cycle (proposal -> treasury execution -> bridge receipts -> Merkl distribution contract funding -> claimant settlement tx traces) is not fully assembled here.
2. Fee-rate claim precision (~0.66% vs observed realized run-rate) requires reproducible vault-level on-chain computation, not only API-derived aggregates.
