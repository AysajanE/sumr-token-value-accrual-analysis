---
title: SUMR Investor Executive Summary
---

# Executive Summary

Classification remains **RESTRICTED**: value accrual is real on-chain, but full institutional attribution confidence is still bounded.

Why the mechanism can work:

1. The mechanism works only if fee productivity remains near or above a 0.50% annualized-on-TVL floor (verified lens currently 0.647%, above that floor) and governance routes a stable, auditable share of fees to stakers.
2. Bounded realization ratio (14.10%): conservative share of claimed distributions directly evidenced on-chain via source-of-funds mapping. This is an evidence-coverage statistic, not a missing-funds claim; underwriting target remains >=80% for >=60 consecutive days.
3. At $0.003319, SUMR trades at 0.771x of modeled reward-emission break-even ($0.004305), about 22.90% below the level where expected annual staker cash distributions would equal modeled annual reward emissions in USD terms; this is a sustainability signal, not a full valuation model.

Kill switches (explicit invalidation triggers):

1. Fee productivity falls below 0.30% annualized for 90 consecutive days.
2. Governance controls are not hardened (no published privileged role-member map and no effective routing/upgrade timelocks).
3. Evidence coverage remains below 80% for 60 consecutive days with unresolved discrepancy tickets.
4. Newly liquid supply accelerates without offsetting mitigation (lock extensions, emission reductions, or buyback/sink policy).

Key blockers to institutional underwriting (current):

1. Attribution quality is below high-confidence threshold (>=80% for >=60 consecutive days) and open discrepancy tickets remain.
2. Dilution and newly liquid supply overhang remain large versus modeled staker cash distributions.
3. Governance/control transparency is incomplete for privileged roles and routing constraints.

> **What you're underwriting (compact):** Fee persistence plus governance routing to holders, at a discount to modeled reward-emission break-even, with known risks: thin liquidity, holder concentration, unlock overhang, and control risk.

# Current Snapshot

| Item | Value |
| --- | --- |
| Reference price | $0.003319 |
| Model entry position (1,000,000 SUMR) | $3,319.00 |
| Circulating supply (on-chain totalSupply snapshot) | 977,149,629.41 SUMR |
| Market cap at reference price | $3,243,159.62 |
| Break-even price | $0.004305 |
| Price to break-even | 0.771x |
| Lazy Summer TVL (verified baseline) | $47,907,854.00 |
| TVL drawdown from peak | 75.64% |
| Fees, last 30 days (verified baseline) | $29,799.00 |
| Fee productivity (90d annualized fees / 90d avg TVL, verified lens) | 0.647% |
| Fee productivity (30d annualized fees / latest TVL, live lens) | 0.757% |
| Fee trend vs prior 30 days (live external) | -34.18% |

![TVL and Fees Trend](../results/charts/investor_tvl_fees_trend.png)

# Verified vs External Data Reconciliation

This table reconciles frozen verification baselines versus live external snapshots to avoid source mixing.
Fee productivity lenses: verified uses 90d annualized fees / 90d average TVL; live uses 30d annualized fees / latest TVL.

| Metric | Verified baseline | External snapshot | Delta vs verified | Valuation source-of-truth |
| --- | --- | --- | --- | --- |
| Lazy Summer TVL (USD) | 47,907,854.00 | 47,907,854.00 | 0.00% | Use verified baseline for underwriting; external used for peer context only. |
| Lazy Summer Fees 30d (USD) | 29,799.00 | 30,276.00 | 1.60% | Use verified baseline for valuation narratives; external used for comparables and market-share context. |

# Value Accrual and Evidence Quality

Observed economic split remains 70% depositors / 20% stakers / 10% treasury. Mechanism existence is supported by routing and payout evidence, but campaign attribution remains bounded.

![Campaign Realization Quality](../results/charts/investor_campaign_realization.png)

![Source-of-Funds Monthly Comparison](../results/charts/investor_source_of_funds_monthly.png)

# Supply and dilution: (i) vesting/unlocks, (ii) reward emissions, and (iii) implied sell-pressure (scenario-based)

Dilution remains central because investor return is net of newly liquid supply pressure and reward-emission policy.

## Supply and Dilution Waterfall (vesting/unlocks context)

| Bucket | Tokens | Notes |
| --- | --- | --- |
| Max supply hard cap | 1,000,000,000.00 | Contract-level cap |
| Current on-chain total supply | 977,149,629.41 | Minted supply snapshot |
| Remaining mintable to cap | 22,850,370.59 | Max supply minus on-chain supply |
| Modeled circulating at TTE | 433,713,512.00 | Tokenomics sheet model input |
| Modeled non-circulating/unvested | 566,286,488.00 | 1B minus modeled circulating |
| On-chain treasury wallet balance | 89,936,035.23 | Address map treasury wallet |
| On-chain distributor balance | 35,646,038.72 | Address map distributor pipeline |

## Monthly Newly Liquid Supply Schedule (next 12 months)

| Period | Date | Monthly newly liquid SUMR | Cumulative newly liquid % of max supply |
| --- | --- | --- | --- |
| TGE + 13 | 2026-02-28 | 21,273,821 | 46.01% |
| TGE + 14 | 2026-03-28 | 19,162,621 | 47.93% |
| TGE + 15 | 2026-04-28 | 18,838,621 | 49.81% |
| TGE + 16 | 2026-05-28 | 18,838,621 | 51.70% |
| TGE + 17 | 2026-06-28 | 23,591,170 | 54.06% |
| TGE + 18 | 2026-07-28 | 23,391,170 | 56.40% |
| TGE + 19 | 2026-08-28 | 23,391,170 | 58.73% |
| TGE + 20 | 2026-09-28 | 23,391,170 | 61.07% |
| TGE + 21 | 2026-10-28 | 23,391,170 | 63.41% |
| TGE + 22 | 2026-11-28 | 23,391,170 | 65.75% |
| TGE + 23 | 2026-12-28 | 23,391,170 | 68.09% |
| TGE + 24 | 2027-01-28 | 23,391,170 | 70.43% |

Destination split from modeled newly-liquid supply schedule:

| Destination category | Next 12 months SUMR | Next 24 months SUMR |
| --- | --- | --- |
| Community | 39,120,392 | 93,750,980 |
| Stakeholders | 59,613,996 | 119,227,992 |
| Core TB/MB | 125,000,004 | 125,000,004 |
| Core TB | 34,714,296 | 36,027,072 |
| Core unallocated | 6,994,356 | 6,994,356 |
| Foundation | 0 | 0 |

Estimated annual cash distributions to stakers (USD): $8,919.24 (8.9k, low) to $63,238.37 (63.2k, high).
(Note: protocol-side outflow, staker-side inflow.)

## Net Dilution Pressure vs Expected Staker Cash Distribution

| Horizon | Modeled newly liquid SUMR (unlocks + scheduled emissions) | Implied USD value | Ratio vs lower cashflow ($8,919.24) | Ratio vs upper cashflow ($63,238.37) |
| --- | --- | --- | --- | --- |
| Next 12 months | 265,443,044 | $881,005.46 | 98.78x | 13.93x |
| Next 24 months | 381,000,404 | $1,264,540.34 | 141.78x | 20.00x |

The ratio NewlyLiquidSupply_USD (unlocks + scheduled emissions) / Cash_to_Stakers tests whether supply expansion is plausibly offset by distributable cashflow.
Current modeled ratios remain in double digits across both 12- and 24-month horizons, implying cashflow is presently too small to absorb dilution without TVL/fee growth or explicit supply-control measures.

## Break-Even Definition and Inputs

Break-even is defined as:

$$
P_{\text{break-even}} = \frac{C_{\text{stakers}}}{E_{\text{SUMR}}}
$$

- C_stakers (annual cash distributions to stakers): lower $8,919.24, upper $63,238.37 (staker inflow sign convention).
- E_SUMR (annual reward emissions to stakers used in incentive distribution): lower bound 2,071,913 SUMR/year, upper bound 14,690,091 SUMR/year.
- E_SUMR is not total vesting unlocks. Newly liquid supply from vesting/unlocks is modeled separately in the dilution schedule above.
- Break-even is a sustainability threshold under stated assumptions, not an intrinsic valuation model.
- Emission routing is governance-sensitive and not immutable.
- Attribution remains bounded; treat break-even as a bounded range, not a single hard floor.

# Staking Economics

Rewards are distributed pro rata to weighted stake, not raw stake.

| Assumption item | Value |
| --- | --- |
| Investor tokens | 1,000,000 SUMR |
| Reward allocation basis | pro-rata weighted stake (not raw stake) |
| Base assumed investor multiplier | 4.0144x |
| Base assumed weighted investor stake | 4,014,355.52 weighted SUMR |
| Total network weighted stake (snapshot) | 553,667,684.76 weighted SUMR |
| Investor weighted share (base) | 0.73% |
| Raw staking participation (network) | 14.11% |
| No lock weighted share | 0.18% |
| Long lock weighted share | 1.26% |

Base-case APR sensitivity:

| Staking participation | APR (lower bound) | APR (upper bound) |
| --- | --- | --- |
| 10.00% | 1.83% | 12.94% |
| 30.00% | 0.61% | 4.31% |
| 60.00% | 0.30% | 2.16% |

![Staking Lockup Distribution](../results/charts/investor_staking_lockup_distribution.png)

# Liquidity and Market Structure

| Item | Value |
| --- | --- |
| Aggregate observed DEX reserve liquidity | $127,601.27 |
| Aggregate observed DEX volume, 30 days | $2,490,561.34 |
| Top holder share of supply | 15.74% |
| Top 10 holders share of supply | 74.02% |
| Top 10 stakers share of staked supply | 69.29% |
| Staked SUMR unlocking in 90 days | 23.35% |
| Staked SUMR unlocking in 365 days | 33.61% |

![External Peer Benchmarks](../results/charts/investor_external_peer_benchmarks.png)

Peer benchmarks are directional and snapshot-based (DeFiLlama/TokenTerminal-style aggregation), used for order-of-magnitude context rather than strict accounting comparability.

# On-Chain Address Map (Investor-Facing)

| Entity role | Chain | Address (short) | Confidence | Notes |
| --- | --- | --- | --- | --- |
| Fee collector (TipJar) | Base | `0xad30...a374` | High | TipJar |
| Distributor proxy | Base | `0x3ef3...d9ae` | High | ERC1967Proxy |
| Distributor implementation | Base | `0x6445...d6e6` | High | Distributor |
| Treasury wallet | Base | `0x447b...3796` | Low | Manifest evidence |
| Tipstream safe custody | Base | `0xb0f5...18f2` | High | SafeProxy |
| Distribution creator/deployer | Base | `0x9f76...1a12` | Low | Creator mapping |
| Access manager module | Base | `0xf389...9694` | High | Access manager |

Full raw addresses and provenance fields are in results/tables/investor_onchain_address_map_latest.csv.
Coverage note: this map is in-scope on-chain infrastructure mapping and is not yet a complete consolidated off-chain custody map.

# Governance, Security, and Control Risk

| Security control signal | Current reading |
| --- | --- |
| Named audit provider keyword hits | chainsecurity |
| Audit links discovered | 12 |
| Bug bounty mention present | True |
| Immunefi links detected | 2 |
| Incident history | Arbitrum USDC Vault Post-Mortem: What Happened and What Comes Next |
| Incident postmortem published | 2025-12-02 |
| Proxy contracts in mapped surface | 2 |
| Admin authority module | `0xf389bcea078acd9516414f5dabe3ddd5f7e39694` |

# Scenario Outlook at Lower Entry Price

All scenario outputs in this section assume 1,000,000 SUMR at entry $0.003319 (initial cost $3,319.00).
Figures should be interpreted relative to this entry cost.

Model probability weights: Downside 26.67%, Base 24.47%, Upside 48.86%.

Lower-bound probability-weighted outcomes:

| Horizon | Expected value | Expected PnL | Annualized |
| --- | --- | --- | --- |
| 1 year | $3,649.54 | $330.54 | 9.96% |
| 2 years | $3,991.14 | $672.14 | 9.66% |
| 3 years | $4,343.78 | $1,024.78 | 9.38% |

Upper-bound probability-weighted outcomes:

| Horizon | Expected value | Expected PnL | Annualized |
| --- | --- | --- | --- |
| 1 year | $3,987.71 | $668.71 | 20.15% |
| 2 years | $4,734.77 | $1,415.77 | 19.44% |
| 3 years | $5,560.19 | $2,241.19 | 18.77% |

![Probability-Weighted Outcome Paths](../results/charts/investor_probability_weighted_pnl_paths.png)

![Scenario Yield Heatmap](../results/charts/investor_scenario_yield_heatmap.png)

## Upside Plausibility Evidence Block

| Indicator | Current reading | Directional interpretation |
| --- | --- | --- |
| TVL drawdown from peak | -75.64% | Weak for upside |
| TVL change, last 30d | -24.65% | Weak for upside |
| TVL change, last 90d | -42.52% | Weak for upside |
| Fees change, latest 30d vs prior 30d | -34.18% | Weak for upside |
| Fee productivity (30d annualized fees / latest TVL) | 0.757% | Live run-rate lens; directly comparable to current TVL scale |
| Assumed holders-revenue yield on TVL | 0.151% | Still modest without re-acceleration |

Conclusion: upside convexity exists in the model, but current live leading indicators do not yet justify de-risking the downside case.

# Treasury Stress Context

Treasury context should be treated as scenario-sensitive support, not a primary valuation pillar.
Runway interpretation is explicitly provisional: treasury mapping is not yet fully comprehensive across all potential custody surfaces.

![Treasury Runway Stress Case](../results/charts/investor_treasury_runway_base_opex.png)

# Practical Underwriting Framework

## Underwriting upgrades required to move from conditional to investable

1. Evidence coverage: bounded realization ratio >=80% for >=60 consecutive days, with discrepancy tickets closed or explicitly documented.
2. Unit economics persistence: fee productivity >=0.50% annualized for >=90 days, measured as 90d annualized fees divided by 90d average TVL.
3. Governance constraints: published privileged role-member list, effective upgrade/routing timelocks, and on-chain auditable revenue-routing policy.
4. Liquidity/treasury resilience: stable reserve and market depth sufficient to support downside runway, or a disclosed and credible backstop.

## Kill-Switch Signals

1. Fee productivity falls below 0.30% annualized for 90 consecutive days.
2. Governance controls are not hardened (no published privileged role-member map and no effective routing/upgrade timelocks).
3. Evidence coverage remains below 80% for 60 consecutive days with unresolved discrepancy tickets.
4. Newly liquid supply accelerates without offsetting mitigation (lock extensions, emission reductions, or buyback/sink policy).

# Final Classification

At $0.003319, SUMR offers asymmetric optionality: if governance reliably routes fees to stakers and TVL stabilizes or grows, modeled break-even economics and scenario returns become plausible.
However, the token remains a **restricted candidate** because (i) evidence coverage is not yet institutional-grade, (ii) liquidity and holder concentration remain high-risk, and (iii) unlock/dilution dynamics can dominate price action independent of fundamentals.

This document is research and underwriting support material, not investment advice.
