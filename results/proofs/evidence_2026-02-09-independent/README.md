# Evidence Tables (2026-02-09-independent)

Generated deterministically from JSON snapshots in `data/snapshots/external_review/2026-02-09-independent`.

- `kpi_summary.json`: DeFiLlama-derived TVL/fees snapshot metrics.
- `defillama_context_summary.json`: scope separation and chain coverage context.
- `grm_rewardAdded_events.csv`: RewardAdded logs for GovernanceRewardsManager V2 (topic-filtered).
- `base_treasury_fee_token_inflows.csv`: Base treasury inflows for USDC/EURC/USDT/WETH.
- `base_treasury_fee_token_outflows.csv`: Base treasury outflows for USDC/EURC/USDT/WETH.
- `eth_treasury_fee_token_inflows.csv`: Ethereum treasury inflows for USDC/EURC/USDT/WETH.
- `eth_treasury_fee_token_outflows.csv`: Ethereum treasury outflows for USDC/EURC/USDT/WETH.
- `treasury_fee_token_net_flow_monthly.csv`: monthly inflow/outflow/net by chain and token.
- `treasury_flow_summary.json`: inflow/outflow totals by chain and token.
- `forum_payout_claims.csv`: SIP3.13 and SIP3.13.1 payout/revenue claims parsed from forum JSON.
- `*_method_counts.csv`: TipJar tx method counts per chain from Blockscout snapshots.
- `payout_chain_sip3_13_summary.json`: decoded proposal execution, receipt-based campaign reconstruction, claimant settlements, and canonical deposited/claimed/unclaimed revenue metrics for SIP3.13.
- `payout_chain_sip3_13_1_summary.json`: decoded proposal execution, receipt-based campaign reconstruction, post-execution claim status, and canonical deposited/claimed/unclaimed revenue metrics for SIP3.13.1.
- `payout_attribution_summary.json`: campaign attribution metrics including canonical deposited/claimed/unclaimed values and attribution confidence class.
- `payout_attribution_cycle_table.csv`: cycle-level attribution table with confidence class and residual per campaign.
- `staker_revenue_canonical_summary.json`: canonical deposited/claimed/unclaimed staker revenue aggregates by cycle and token.
- `source_of_funds_monthly_comparison.csv`: monthly fee-aligned inflow vs staker payout outflow comparison (base treasury).
- `source_of_funds_summary.json`: source-of-funds status (`PROVEN`/`BOUNDED`/`UNKNOWN`) with explicit basis and token-level coverage.
- `payout_attribution_gate.json`: scenario-readiness gate based on confidence class and residual threshold.
- `payout_attribution_*_claim_events.csv`: claimant-flow events considered by the attribution model.
- `discrepancy_tickets.json` / `discrepancy_tickets.csv`: machine-readable reconciliation discrepancies (fee + payout routing).
- `emissions_vs_revenue_decomposition.json` / `emissions_vs_revenue_decomposition_table.csv`: emissions-vs-revenue decomposition with on-chain formula basis and comparability notes.
