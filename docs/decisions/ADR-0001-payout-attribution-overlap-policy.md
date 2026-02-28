# ADR-0001 — Policy for `PAYOUT-ATTRIB-OVERLAP-SIP3.13`

Date: 2026-02-09 (UTC)
Status: Accepted
Owner: analysis-attribution

## Context

Current attribution method is deterministic but token-window scoped because distributor `Claimed(user, token, amount)` events do not include campaign ID.

For SIP3.13, we observe prior same-token funding to the distributor before execution.
This creates structural overlap risk when attributing post-exec USDC claims to a specific campaign.

Evidence references:
- `results/proofs/evidence_2026-02-09-independent/payout_attribution_summary.json`
- `results/proofs/evidence_2026-02-09-independent/payout_attribution_cycle_table.csv`
- `results/proofs/evidence_2026-02-09-independent/base_treasury_fee_token_outflows.csv`

## Decision

Set policy for `PAYOUT-ATTRIB-OVERLAP-SIP3.13` terminal state to `ACCEPTED_RISK`, not `RESOLVED`, unless one of the following becomes available:

1. campaign-exact claim identifiers in on-chain claim events; or
2. deterministic, campaign-specific claim mapping source with cryptographic linkage.

Until then:
- keep attribution confidence for affected cycles at most `PARTIAL`/`BOUNDED` per model rules,
- disclose residual uncertainty in report conclusions,
- allow scenario workflow to remain blocked if gate requires `EXACT/BOUNDED` and overlap prevents pass.

## Consequences

Positive:
- avoids false precision and overclaiming campaign-exact attribution.
- keeps investor-facing report integrity aligned with current evidence limits.

Tradeoff:
- scenario progression can remain blocked until better attribution primitives exist.

## Review Trigger

Revisit this ADR if protocol upgrades claim events or a new verified data source enables exact campaign mapping.
