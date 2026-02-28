# Payout Chain Proof (SIP3.13 / SIP3.13.1)

This note links proposal claims to executed on-chain calldata and observed claimant-settlement activity.

## SIP3.13 (Topic 600)

- Forum claim source: `forum_payout_claims.csv` (topic 600, treasury transfer 5,953.65368 USDC).
- On-chain execute tx: `0x5aa10ad32d3d6a3d15d614954dbbe960da2f4376301e28b39b063d485dc15941`.
- Reconstructed on-chain campaign (from `NewCampaign` receipt log):
  - campaign ID: `0x55ba34a59f5c428b64e44a41ce7a674bff92870a561d69ea25592ed24ec908c0`
  - reward token: USDC (`0x833589...`)
  - amount: 5,833.985241
  - campaign window: 2025-12-11 00:00:00 UTC -> 2025-12-31 23:59:59 UTC
- Funding split in tx token transfers:
  - to distributor: 5,833.985241 USDC
  - to Merkl fee recipient: 119.668439 USDC
- Settlement activity evidence:
  - USDC `Claimed` event extract: `payout_chain_sip3_13_claimed_usdc_events.csv`
  - source snapshot: `base_rpc_distributor_claimed_usdc_40757499_41932732.json`

## SIP3.13.1 (Topic 698)

- Forum claim source: `forum_payout_claims.csv` (topic 698).
- On-chain execute tx: `0x30643401cafbc331687f312b4fab670470553419ea3c2cef510f48e00c488e54`.
- Reconstructed on-chain campaign (from `NewCampaign` receipt log):
  - campaign ID: `0x33b711f462991e30d2531193b02dbda4f0d2fd596a4c06d8a01701c6e0604fea`
  - reward token: LVUSDC (`0x98C49e...`)
  - amount: 8,301.739885
  - campaign window: 2026-01-01 00:00:00 UTC -> 2026-01-31 23:59:59 UTC
- Funding path in tx token transfers includes:
  - USDC transfer from treasury to LVUSDC vault
  - LVUSDC transfer to distributor + LVUSDC transfer to fee recipient
- Post-execution claim status snapshot:
  - LVUSDC `Claimed`: 0 events, total 0.0
  - USDC `Claimed`: 8 events, total 6.056295
  - aBasUSDC `Claimed`: 29 events, total 610.703749

## Attribution Caveat

`Claimed(user, token, amount)` events do not include campaign ID. Therefore:
- token+time settlement activity is proven,
- campaign IDs are now reconstructed from receipt logs,
- but claimant settlement attribution remains token-scoped without campaign ID in `Claimed` events.

See machine-readable summaries:
- `payout_chain_sip3_13_summary.json`
- `payout_chain_sip3_13_1_summary.json`
