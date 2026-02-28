<action_plan>
META

* Scope: Build a reproducible, on-chain-verifiable pipeline to test whether SUMR accrues value via (i) fee generation in Lazy Summer vaults, (ii) fee routing (“tips”) and split to stakers, and (iii) realized staker distributions (USDC-denominated rewards) net of emissions/dilution—plus sanity-check the article’s major market-context claims.
* Confidence score: 0.78 (high confidence on *how* to validate; moderate uncertainty on exact contract/event names until you pull ABIs and confirm the deployed module versions).
* Perspective: Skeptical investor / forensic analyst. Treat docs and dashboards as hypotheses; treat chain state + decoded logs as ground truth.

---

0. INVESTIGATION DESIGN (WHAT MATTERS, WHAT “PROVES” IT)
   0.1 Core claims/mechanisms to validate (investment-relevant)
   A. Fee engine exists and produces measurable fees: “~0.66% annually on vault deposits” (effective fee rate; vault-specific variation). Source hypothesis: [Summer.fi Docs 2026](https://docs.summer.fi/lazy-summer-protocol/governance/tip-streams "Tip Streams | Summer.fi Knowledge Base"), [DefiLlama 2026](https://defillama.com/protocol/lazy-summer-protocol "Lazy Summer Protocol - DefiLlama")
   B. Fee routing/split: “20% of tips go to SUMR stakers” (share stability over time; governance mutability). Source hypothesis: [DefiLlama 2026](https://defillama.com/protocol/lazy-summer-protocol "Lazy Summer Protocol - DefiLlama")
   C. Real distributions to stakers: “paid as USDC” (actually USDC-denominated vault tokens; monthly cadence; realized value). Source hypothesis: [Summer.fi Docs 2026](https://docs.summer.fi/lazy-summer-protocol/governance/usdsumr-token/staking "Staking | Summer.fi Knowledge Base")
   D. Staking mechanics are real and binding: lock choices (0–~3y), early exit penalty (≤20% linearly decaying), and reward components (revenue rewards + emissions). Source hypothesis: [Summer.fi Docs 2026](https://docs.summer.fi/lazy-summer-protocol/governance/usdsumr-token/staking "Staking | Summer.fi Knowledge Base")
   E. Token supply constraints: max supply = 1B; confirm mint controls and actual minted supply. Source hypothesis: [BaseScan 2026](https://basescan.org/token/0x194f360d130f2393a5e9f3117a6a1b78abea1624 "SUMR Token Contract")

0.2 Secondary/context claims (lower investment relevance, but part of article credibility)
F. “DeFi lending TVL ~ $58B (ATH?)” — validate with time series. Source hypothesis: [DefiLlama 2026](https://preview.dl.llama.fi/protocols/Lending "Lending Protocols Rankings - DefiLlama")
G. “Lazy Summer peaked ~$190M in Nov 2024; current TVL ~$63M” — verify peak value/date and scope (Lazy Summer vs Summer.fi). Source hypothesis: [DefiLlama 2026](https://defillama.com/protocol/lazy-summer-protocol "Lazy Summer Protocol - DefiLlama"), [Summer.fi 2025](https://outposts.io/article/summerfi-surpasses-dollar190m-tvl-across-multiple-chains-ebc38411-7596-4438-8e57-a019780fe159 "Summer.fi Surpasses $190M TVL Across Multiple Chains")
H. “DeFi borrow/lending grew 15B → 120B+ over 2024–2025” — only testable once metric is defined; you’ll compute multiple candidates (TVL, supplied, borrowed).
I. “Euler exploded 940% YoY” — validate time window (YoY vs YTD) using a protocol TVL series. Source hypothesis: [DWF Labs 2025](https://www.dwf-labs.com/research/lending-markets-defis-fastest-horse "Are Lending Markets DeFi’s Fastest-Growing Sector?")
J. Coinbase/Morpho $1B+ originations + EF 2,400 ETH — verify on-chain where possible (addresses/markets) and reconcile with public statements. Source hypothesis: [Morpho 2025](https://morpho.org/blog/morpho-effect-september-2025/ "Morpho Effect: September 2025"), [Nguyen 2025](https://cryptobriefing.com/ethereum-foundation-deposit-morpho-vaults/ "Ethereum Foundation deposits 2,400 ETH and $6 million in stablecoins into Morpho vaults")

0.3 What would “definitively” prove/disprove SUMR value accrual

* Prove (strong): On-chain logs show (i) fees accrue to protocol-controlled addresses/modules, (ii) ~20% of those fees (or a governance-defined share) is routed into a revenue-reward module for stakers, and (iii) stakers can and do claim USDC-denominated value consistently, with transparent accounting of undistributed accruals.
* Disprove (strong): Fees exist but do not route to stakers; or routing exists but distributions are negligible/irregular; or distributions are dominated by inflationary emissions (i.e., “revenue” is marketing but economically minor); or key parameters can be changed unilaterally without credible constraints.

---

1. DATA COLLECTION STRATEGY (SOURCES, DATA POINTS, GRANULARITY, METHODS)

1.0 Build a “Contract Registry” first (non-negotiable prerequisite)
Goal: a canonical list of all addresses and ABIs required for: vault TVL, fee/tip accrual, treasury, staking, revenue rewards, and reward vault tokens.

1.0.1 Seed addresses (known)

* SUMR token (Base): 0x194f360d130f2393a5e9f3117a6a1b78abea1624 from [BaseScan 2026](https://basescan.org/token/0x194f360d130f2393a5e9f3117a6a1b78abea1624 "SUMR Token Contract")

1.0.2 Discover all remaining addresses (repeatable multi-method)
Use at least 2 independent methods per address class:

(1) Official docs/config

* Staking V2, revenue reward vault token(s), governance/tip streams: [Summer.fi Docs 2026](https://docs.summer.fi/lazy-summer-protocol/governance/usdsumr-token/staking "Staking | Summer.fi Knowledge Base"), [Summer.fi Docs 2026](https://docs.summer.fi/lazy-summer-protocol/governance/tip-streams "Tip Streams | Summer.fi Knowledge Base")
  Practical extraction: scrape the docs page HTML for “0x…”, and/or inspect Summer.fi front-end network calls that return JSON configs (vault list, addresses). Store raw snapshots with timestamps.

(2) DeFiLlama protocol adapters + API outputs

* Pull protocol metadata + chain breakdown for “lazy-summer-protocol” and “summerfi”. Source: [DefiLlama 2026](https://defillama.com/protocol/lazy-summer-protocol "Lazy Summer Protocol - DefiLlama"), [DefiLlama 2026](https://defillama.com/protocol/summerfi "Summer.fi - DefiLlama")
  Extraction method:
* DeFiLlama API (typical patterns):

  * TVL: [https://api.llama.fi/protocol/](https://api.llama.fi/protocol/)<slug>
  * Fees/Revenue: [https://api.llama.fi/summary/fees/](https://api.llama.fi/summary/fees/)<slug> (and/or overview endpoints)
* If DeFiLlama doesn’t list vault addresses directly, use their adapter repository (GitHub) to find address lists (manual step).

(3) On-chain discovery via deployers/factories (ground truth)

* Identify contract deployer(s) from BaseScan “Contract Creator” for known module addresses (start with SUMR token; then pivot).
* Search BaseScan “Internal Txns” and “Contract Creation” from those deployers for patterns (factories, vault deployments).
* If there is a “VaultFactory” contract: pull events like VaultCreated/PoolCreated and enumerate vaults.

Deliverable: contract_registry.csv with columns:

* chain, address, label (e.g., “StakingV2”, “RevenueRewardDistributor”, “TipStream”, “VaultShareToken”, “Vault”, “Treasury”, “LV-USDC token”, “USDC”), abi_source, abi_hash, discovered_by (docs/llama/onchain), first_seen_block, notes.

1.0.3 ABIs (how to get them, reliably)

* Explorers: BaseScan (Etherscan-compatible) “getabi” API for verified contracts.
* If unverified:

  * Obtain ABI from Summer’s repo/config/subgraph (if available), or
  * Use 4byte signatures + manual decoding (last resort), or
  * Use Tenderly contract decoding if you have it.
    QC: store ABI JSON blobs and compute hash; your downstream decoding must reference ABI hash (reproducibility).

---

1.1 Claim A: “~0.66% annual fee on vault deposits” (effective fee rate)
Hypothesis: Fees are implemented via “Tip Streams” / AUM-based fees, varying by vault type. Source hypothesis: [Summer.fi Docs 2026](https://docs.summer.fi/lazy-summer-protocol/governance/tip-streams "Tip Streams | Summer.fi Knowledge Base")

1.1.1 Data sources
On-chain (primary):

* Vault contracts (ERC-4626 style likely): functions like totalAssets(), totalSupply(), convertToAssets(), convertToShares(), asset()
* Vault share token Transfer events
* TipStream/FeeCollector contract events (exact names TBD via ABI)
* Treasury address token receipts (as fallback signal)
  Off-chain (secondary):
* DeFiLlama fees/revenue series for cross-check: [DefiLlama 2026](https://defillama.com/protocol/lazy-summer-protocol "Lazy Summer Protocol - DefiLlama")

1.1.2 Specific data points to collect
Per vault (per chain):

* vault_address, share_token_address (if separate), underlying_asset_address
* totalAssets at daily close (end-of-day block)
* totalSupply at daily close
* share_price = totalAssets / totalSupply (adjust decimals)
* fee/tip accrual events (decode from TipStream or detect minting to fee recipients):

  * If fee is minted shares: Transfer(from=0x0, to=fee_address, value=shares_minted)
  * If fee is transfer of underlying: ERC20 Transfer(from=vault, to=fee_address, value=asset_amount)
* fee recipient addresses (tip stream, treasury, distributor, stakers module)

1.1.3 Granularity, frequency, time windows

* Event-level ingestion: block-by-block (incremental), with 20–50 confirmations buffer.
* Daily snapshots: compute TVL/AUM and cumulative fee accrual per UTC day (also store America/Toronto day if you care about “monthly” cadence alignment).
* Time window:

  * Minimum: from first vault deployment OR last 12 months
  * Prefer: full history since protocol launch (to test stability and detect parameter changes)

1.1.4 Extraction methods/tools
Option 1 (most control, highest reliability): Direct RPC + getLogs

* Use Base archive node (Alchemy/QuickNode/Ankr; must support eth_call at historical blocks).
* web3.py or ethers.js:

  * eth_getLogs for Transfer + TipStream events
  * eth_call for totalAssets()/totalSupply() at specific blocks

Option 2 (faster start): Dune or Flipside

* Use chain tables for Base + any other chains where vaults exist.
* Write SQL to:

  * extract Transfer mints to fee addresses
  * compute daily AUM snapshots using contract calls if supported, or approximate via token balances
    QC: always reconcile with a direct RPC spot-check for random days.

Option 3: Subgraph (if exists)

* If Summer/third-party subgraph exists, use it for event decoding and join logic, but do not treat it as ground truth without spot-checks.

1.1.5 Core computed metrics

* Daily_AUM_USD(vault) = totalAssets * price(underlying_asset)
* Daily_Fees_USD(vault) = value of fee transfers/mints attributable to that day
* Effective_Fee_Rate_Annualized(vault, period) =
  (sum(Daily_Fees_USD) / avg(Daily_AUM_USD)) * (365 / days_in_period)
* Weighted_Avg_Effective_Fee_Rate(period) =
  sum(fees_usd) / sum(avg_aum_usd) * annualization

Pass/fail test vs claim:

* “~0.66%” holds if weighted average is within a tight band (e.g., 0.5%–0.8%) over a long enough window (≥90 days), with vault-level variation explainable by documented schedules.

---

1.2 Claim B/C: “20% of tips go to SUMR stakers as USDC (denominated LV tokens), monthly”
Hypothesis: A defined share of protocol tips routes to a staker rewards module; the payout asset is a USDC-denominated vault token that compounds, distributed monthly. Source hypothesis: [DefiLlama 2026](https://defillama.com/protocol/lazy-summer-protocol "Lazy Summer Protocol - DefiLlama"), [Summer.fi Docs 2026](https://docs.summer.fi/lazy-summer-protocol/governance/usdsumr-token/staking "Staking | Summer.fi Knowledge Base")

1.2.1 Data sources
On-chain (primary):

* TipStream/FeeCollector contract(s): identify total tips accrued and distribution splits
* Treasury address: receives its share (if any)
* Staking contract + reward distributor contracts:

  * events for revenue reward deposits, reward claims, reward period updates
* Reward asset contract(s):

  * USDC token(s) used
  * LV-USDC token(s) used for “USDC-denominated vault rewards”
    Off-chain (secondary):
* DeFiLlama “token holder revenue” series, if available
* Summer docs for cadence definitions

1.2.2 Specific data points to collect
For each distribution cycle (monthly by docs; verify in practice):

* Total protocol tips accrued in cycle (USD)
* Amount routed to stakers module in cycle (USD)
* Amount routed to treasury in cycle (USD)
* Any undistributed accrual carried forward (balances in distributor contract)
* Reward asset details:

  * reward_token_address (LV-USDC or USDC)
  * reward_token decimals
  * conversion to USDC at distribution time:

    * If LV token: use convertToAssets() / pricePerShare at block
* Staker-level claims:

  * addresses claiming
  * amount claimed
  * claim timestamp/block
* Staking positions outstanding:

  * total staked SUMR, by lock duration bucket
  * “boost” multipliers (if any) implied by lock length

1.2.3 Granularity, frequency, time windows

* Event-level ingestion: continuous
* Aggregations:

  * Daily: tips accrued; staker rewards accrued; claims made
  * Monthly: “distribution cycle” rollups aligned to actual on-chain distribution events (do not assume calendar month; infer from deposit events)
* Time window:

  * From staking V2 launch block to present (minimum)
  * Ideally full staking history if V1 existed (label versions separately)

1.2.4 Extraction methods/tools

* Decode staking contract ABI from BaseScan (or chain-specific explorer).
* Pull logs for key events (names TBD until ABI is pulled); typical patterns to look for:

  * RewardAdded / RevenueDeposited / NotifyRewardAmount
  * RewardPaid / Claimed
  * Locked / Withdrawn / EarlyExit
  * PenaltyPaid
* If rewards are streamed continuously rather than discrete deposits: compute balance deltas of distributor contract in reward token.

1.2.5 Core computed metrics (value accrual)

* Staker_Revenue_USD(period) = sum(value of revenue rewards deposited or claimed in period)
* Protocol_Tips_USD(period) = sum(total tips in period (all fee recipients))
* Staker_Share_of_Tips(period) = Staker_Revenue_USD / Protocol_Tips_USD
* Revenue_APR_on_Staked_SUMR(period) =
  (Staker_Revenue_USD / avg(Staked_SUMR * SUMR_Price_USD)) * annualization
* Revenue_per_Staked_SUMR(period) =
  Staker_Revenue_USD / avg(Staked_SUMR)

Pass/fail tests:

* “20%” holds if Staker_Share_of_Tips is ~0.20 across multiple cycles, with deviations explainable by:

  * timing (accrual vs distribution lag),
  * governance parameter changes (must be detectable on-chain),
  * multi-chain accounting differences.
* “as USDC” holds if reward token’s underlying is USDC and claims are denominated in USDC value (even if paid as LV-USDC). You’ll show this by redeemability math (convertToAssets) at claim blocks.

---

1.3 Claim D: Staking mechanics (locks, penalties, rewards)
Hypothesis: Locks 0–~3 years; early exit penalty up to 20%, linearly decreasing; rewards include emissions + revenue rewards. Source hypothesis: [Summer.fi Docs 2026](https://docs.summer.fi/lazy-summer-protocol/governance/usdsumr-token/staking "Staking | Summer.fi Knowledge Base")

1.3.1 Data sources
On-chain:

* Staking contract state + events
* SUMR token Transfer events (stake in/out)
* Penalty recipient address (treasury/burn/etc.)

1.3.2 Data points

* Lock creation: amount, lock_start, lock_end
* Early withdraw: withdraw_time, penalty_amount, net_amount
* Total locked by duration buckets (0–1m, 1–6m, 6–12m, 1–2y, 2–3y)
* Reward emissions schedule:

  * emission token (likely SUMR)
  * minted/distributed per period
  * whether emissions are additional to revenue rewards
* Penalty function validation:

  * For a sample of early exits, compute implied penalty rate = penalty / principal and compare to linear decay formula from docs

1.3.3 Granularity/frequency

* Event-level ingestion; daily and monthly rollups
* Keep full position history (you need it for boost-weighted reward accounting)

1.3.4 Extraction methods

* ABI decode; if contract is proxy-upgradeable, also record implementation addresses and upgrade events.
* For verifying penalty math: re-simulate penalty function by calling view functions at historical blocks (if exposed) OR derive by comparing event fields.

---

1.4 Claim E: Max supply 1B; mint controls
Hypothesis: maxSupply = 1e27 in raw units (1B * 1e18), with constrained minting; verify actual minted and whether mint can exceed cap. Source hypothesis: [BaseScan 2026](https://basescan.org/token/0x194f360d130f2393a5e9f3117a6a1b78abea1624 "SUMR Token Contract")

1.4.1 Data sources
On-chain:

* SUMR contract read calls: decimals(), totalSupply(), maxSupply() (or equivalent)
* SUMR contract source code (if verified) for mint/burn roles and caps
* Events: Transfer(from=0x0, …) for mints; Transfer(to=0x0, …) for burns (if burn implemented)

1.4.2 Data points

* totalSupply time series (daily)
* Mint events (who minted, how much)
* Role admin addresses (owner, minter, governance timelock)
* Any supply schedule constraints (cliffs, vesting contracts) — discovered via large holders and known vesting addresses

1.4.3 Methods

* Use BaseScan “Read Contract” endpoints or RPC eth_call for the state.
* Validate cap enforcement:

  * If maxSupply is stored: check mint function requires totalSupply + amount ≤ maxSupply
  * If upgradeable: verify implementation code versions; treat upgrades as a key risk

---

1.5 Claim G: TVL peak and “current TVL” (scope hygiene: Lazy Summer vs Summer.fi)
Hypothesis: article mixes scopes; you’ll independently compute TVL from on-chain and reconcile to DeFiLlama time series and Summer milestone post. Source hypothesis: [DefiLlama 2026](https://defillama.com/protocol/lazy-summer-protocol "Lazy Summer Protocol - DefiLlama"), [DefiLlama 2026](https://defillama.com/protocol/summerfi "Summer.fi - DefiLlama"), [Summer.fi 2025](https://outposts.io/article/summerfi-surpasses-dollar190m-tvl-across-multiple-chains-ebc38411-7596-4438-8e57-a019780fe159 "Summer.fi Surpasses $190M TVL Across Multiple Chains")

1.5.1 Data sources

* On-chain: same vault totalAssets snapshots as in 1.1
* DeFiLlama TVL series: API protocol endpoints
* Summer milestone claim: treat as a stated figure; verify against computed TVL and llama

1.5.2 Data points

* Daily TVL_USD by vault and by chain
* Aggregated:

  * Lazy Summer TVL (sum of vaults included in Lazy Summer)
  * Summer.fi broader TVL (include all Summer deployments—must define inclusion rules)
* Peak TVL value + date (max over series)

1.5.3 Methods

* Define “TVL inclusion rules” explicitly:

  * Include only assets held in vault contracts and strategies (if assets move to strategy addresses, you must include them; otherwise you will undercount).
  * If strategy assets are in external protocols, you may need to value the vault’s claim token rather than raw holdings (ERC-4626 totalAssets should already reflect this if properly implemented).
* Cross-check:

  * Compare computed TVL to DeFiLlama daily TVL. Differences >2–5% require explanation (pricing sources, included chains, strategy accounting).

---

1.6 Context claims F/H/I/J (optional but recommended for article credibility scoring)
These won’t change SUMR mechanics, but they inform whether you trust the marketing.

1.6.1 DeFi lending TVL ~$58B and ATH (Claim 1)

* Source: [DefiLlama 2026](https://preview.dl.llama.fi/protocols/Lending "Lending Protocols Rankings - DefiLlama")
  Data:
* Daily “lending protocols category TVL” series (via DeFiLlama)
  Tests:
* Verify latest value near 58B on the relevant date.
* ATH test: compute max historical TVL; if current equals max within tolerance, ATH is true; otherwise false.

1.6.2 “15B → 120B+” lending growth (Claim 8)
Problem: metric undefined. Your plan:

* Compute three candidate metrics:

  1. Lending TVL (collateral supplied)
  2. Total supplied (if aggregator provides)
  3. Total borrowed/outstanding loans
* For each, build 2024-01-01 → present time series and see if any plausibly matches 15B → 120B.

1.6.3 Euler “940% YoY” (Claim 9)

* Use DeFiLlama Euler TVL series:

  * Compute YTD growth (Jan 1 → current)
  * Compute YoY growth (same date last year → current)
* If 940% matches YTD not YoY, mark as misleading.

1.6.4 Coinbase/Morpho $1B+; EF 2,400 ETH (Claims 10/11)
On-chain verification approach:

* Identify the specific Morpho markets/vaults referenced in [Morpho 2025](https://morpho.org/blog/morpho-effect-september-2025/ "Morpho Effect: September 2025") and the EF deposit report [Nguyen 2025](https://cryptobriefing.com/ethereum-foundation-deposit-morpho-vaults/ "Ethereum Foundation deposits 2,400 ETH and $6 million in stablecoins into Morpho vaults").
* Identify the publicly known Coinbase and EF addresses used (often disclosed in statements or can be inferred from the deposit tx hash in articles).
* Validate:

  * EF: a single deposit tx of ~2,400 ETH into a Morpho vault contract.
  * Coinbase: cumulative originated loan volume is harder; you’ll approximate by summing on-chain borrow events attributable to Coinbase’s program address/market over stated window. If you can’t identify addresses unambiguously, label as “not independently verifiable with high confidence.”

---

2. DATA VALIDATION & VERIFICATION (CROSS-SOURCE CHECKS, INTEGRITY, DISCREPANCIES, QC)

2.1 Cross-referencing strategy (minimum required)
For each core metric, require at least two independent computations:

* TVL:

  * On-chain computed (totalAssets * price) vs DeFiLlama daily TVL
* Fees:

  * On-chain fee transfers/mints vs DeFiLlama annualized fees (directional) and vs docs’ stated fee params
* Staker revenue:

  * On-chain reward deposits/claims vs DeFiLlama “token holder revenue” (if available) vs any protocol dashboards
* Supply:

  * On-chain totalSupply vs explorer token tracker vs any tokenomics post

2.2 Data integrity methods

* Chain reorg handling (Base):

  * Ingest with confirmation depth (e.g., 50–200 blocks), then finalize.
* Deduplication:

  * Unique key = (tx_hash, log_index, chain_id)
* Decimal correctness:

  * Store raw integers + decimals; never store only float.
* ABI/version control:

  * If proxy contracts exist: record implementation addresses and upgrade blocks; decode events using correct ABI for that interval.

2.3 Handling discrepancies (a strict playbook)
When on-chain and DeFiLlama disagree:

1. Check scope: which chains/vaults included?
2. Check pricing: which oracle/pricer? Compare:

   * Chainlink (if available)
   * DeFiLlama price API
   * DEX TWAP (Uniswap v3) for volatile assets
3. Check strategy accounting:

   * Does totalAssets reflect external strategy positions?
   * If not, you must include strategy-held assets addresses.
4. Check timing:

   * End-of-day block vs DeFiLlama timestamp cutoffs.
     If still unresolved:

* Create a discrepancy ticket: metric, date range, magnitude, suspected cause, evidence. Don’t “average it away.”

2.4 Quality control checkpoints (stop/go gates)
Gate 1: Contract registry completeness

* You can reproduce:

  * full vault list
  * staking module address
  * reward token addresses
  * treasury address(es)
    Gate 2: Event decode accuracy
* Randomly sample 20 events across modules and verify decoded fields against explorer UI.
  Gate 3: TVL reconciliation
* On-chain TVL vs DeFiLlama within ≤5% over the last 30 days, or you can explicitly explain the gap.
  Gate 4: Fee reconciliation
* Effective fee rate computed from on-chain is stable and matches docs/claims within reasonable bounds.
  Gate 5: Staker revenue traceability
* Every dollar of “staker revenue” you report is tied to a transaction log and valued at a defensible price source.

---

3. MODELING APPROACH (SCENARIOS, FINANCIAL MODELS, SENSITIVITY, BENCHMARKS)

3.1 What you are modeling (keep it honest)
You are not “valuing SUMR” in the abstract; you are modeling:

* expected cash-equivalent value distributed to stakers (USDC-denominated),
* plus (optionally) emissions (inflationary, not “value” unless funded),
* under different TVL/fee/parameter regimes.

3.2 Scenario set (minimum)
Base scenarios should vary the three drivers that actually matter:

1. TVL level and growth

* Current TVL (your computed baseline)
* Downcase: 0.5× current
* Upcase: 2×, 5× current
* Optional: logistic adoption curve (fast growth then plateau)

2. Effective fee rate (annualized)

* 0.30% (ETH vault style mentioned in docs)
* 0.66% (claimed average)
* 1.00% (stable vault style)
* Stress: fees compress to 0.10% under competitive pressure

3. Staker share of tips

* 10%, 20%, 30%
* Regime shift: governance reduces share to 0% (tail risk)

Also vary:
4) Staking participation rate (staked SUMR / circulating SUMR)

* 10%, 30%, 60%
  Why it matters: revenue per staked token rises if fewer stake (but price dynamics may respond).

5. Distribution asset yield (if LV-USDC compounds)

* Use realized LV-USDC share price growth from on-chain data as the “yield,” not a static assumption.

3.3 Financial models to apply
A) Trailing cashflow and yield metrics (most defensible)

* TTM Staker Revenue (USD)
* Revenue yield on token:

  * Revenue_Yield_on_FDV = TTM_Staker_Revenue / (MaxSupply * SUMR_Price)
  * Revenue_Yield_on_MCap = TTM_Staker_Revenue / (CirculatingSupply * SUMR_Price)
* Revenue yield to stakers:

  * Revenue_APR_on_Staked_Value = TTM_Staker_Revenue / (AvgStakedSUMR * SUMR_Price)

B) Forward projection (transparent, not overfit)

* Project Staker_Revenue_t = TVL_t * FeeRate_t * StakerShare_t
* Use scenario TVL trajectories + fee regimes; keep it simple.

C) DCF-style valuation (optional; label as “model-based”)

* Treat staker cashflows as “dividends”
* Discount rate: 20%–50% (DeFi risk premium; you can justify a range rather than pick one)
* Terminal growth: 0%–5% (stress test)
  Output: implied value per staked token (not necessarily spot market price).

3.4 Sensitivity analysis (what to report, explicitly)

* Tornado chart variables:

  * TVL
  * effective fee rate
  * staker share
  * staking ratio
  * token price (for APR-on-staked-value metric)
* Key elasticities:

  * d(Staker_Revenue)/d(TVL) is linear, but the “market multiple” is not—show both.

3.5 Comparative benchmarking methodology (to contextualize)
Compare SUMR against a small set of revenue-share / fee-switch / buyback tokens (pick 5–8; e.g., AAVE (if fee switch active), GMX, MKR/SKY if applicable, etc.). Use consistent metrics:

* Protocol fees (gross)
* Protocol revenue (net to protocol)
* Tokenholder/staker revenue (directly accrued)
* Tokenholder revenue / TVL
* Tokenholder revenue / MCap
  Data sources:
* DeFiLlama fees/revenue dashboards for each protocol (consistent methodology)
* On-chain verification for SUMR; for others, accept DeFiLlama as baseline unless you also index them.

Important: because the SUMR article had inconsistent “TVL” definitions, your benchmark must include a definitions appendix:

* TVL definition used
* whether borrowed is included/excluded
* valuation source

---

4. PARAMETERS & ASSUMPTIONS (TRACK, JUSTIFY, CONSTRAINTS, RISKS)

4.1 Key variables to track (and expected ranges)
Protocol activity:

* TVL_USD (daily): expect high variance; track by chain and vault
* Effective fee rate (annualized): likely 0.3%–1.0% depending on vaults
* Tips accrued vs distributed: distribution lag can create temporary divergence
  Staking:
* Staked_SUMR (daily)
* Lock-weighted stake (if boosts): effective staking weight
* Early exit penalties collected (USD/month)
  Token:
* Total supply, circulating supply (define methodology), emissions rate
* SUMR price, liquidity, volume, slippage (DEX + CEX if any)
  Rewards:
* Revenue rewards paid (USD) vs emission rewards paid (USD)
* Reward asset NAV (LV-USDC share price)

4.2 Explicit assumptions (don’t bury them)
A1) Pricing

* Stablecoins priced at $1 unless depeg evidence exists (you should still monitor).
* For volatile assets (ETH): use a single primary oracle (Chainlink if available) and a secondary (DEX TWAP). Record the source.

A2) Revenue definition

* “Protocol tips/fees” are what you can trace on-chain to fee collector modules.
* “Revenue to stakers” is only what is deposited/claimable in the revenue rewards module, valued at NAV.

A3) Governance stability

* You must assume some persistence of staker share and fee schedules for forward modeling.
* But you also must measure and report parameter change frequency (if governance changes often, forward projections deserve a haircut).

A4) Multi-chain accounting

* If vaults exist on multiple chains, you either:

  * aggregate all chains (preferred), or
  * isolate Base-only if SUMR staking is Base-only (state this clearly).

4.3 Dependencies/constraints (operational)

* Archive node access: required for historical eth_call at daily snapshot blocks.
* ABI availability: if unverified, decoding costs rise sharply.
* Rate limits: BaseScan + RPC; plan batching and caching.

4.4 Risk factors (must be baked into interpretation)
Economic:

* Fee compression under competition (effective fee rate drops)
* TVL volatility (TVL down → revenue down)
* Emissions dilution: high emissions can overwhelm revenue accrual in “total rewards”
  Governance:
* Staker share can be changed (parameter risk)
* Treasury custody and spending (if treasury receives meaningful share)
  Smart contract:
* Upgradeability risk (proxy upgrades)
* Integration risk with underlying strategies
  Market:
* SUMR liquidity/exit risk (yield is irrelevant if you can’t trade)
  Operational:
* Data visibility: if some flows happen off-chain or via opaque contracts, your confidence drops

---

5. ANALYSIS METHODOLOGY (WORKFLOW, KPIs, VISUALS, INTERPRETATION)

5.1 Step-by-step workflow (end-to-end runbook)
Step 1 — Build contract registry (Section 1.0)

* Output: contract_registry.csv + ABI folder + discovery notes

Step 2 — Stand up the data pipeline

* Storage: Postgres (local) or BigQuery/Snowflake (team)
* Tables (minimum):

  * raw_logs(chain, block, tx_hash, log_index, address, topic0.., data)
  * decoded_events(event_type, fields_json, chain, block_time, tx_hash)
  * daily_snapshots(vault, date, totalAssets, totalSupply, tvl_usd, share_price, fee_usd, staker_rev_usd, etc.)
  * prices(asset, timestamp, price, source)
* Scheduling: Dagster/Airflow cron daily; plus incremental log ingestion every N minutes.

Step 3 — Compute vault TVL (daily)

* For each vault:

  * get end-of-day block number
  * eth_call totalAssets/totalSupply at that block
  * price underlying asset
  * compute tvl_usd
* Aggregate by chain and total.

Step 4 — Compute realized fees/tips (daily)

* For each vault, compute fee_usd via one of:
  A) TipStream events (preferred if available)
  B) Minted shares to fee addresses (Transfer from 0x0)
  C) Underlying transfers to fee addresses
* Convert to USD at time of event.

Step 5 — Compute staker revenue flows (daily + monthly)

* Identify revenue reward deposit events OR distributor balance deltas
* Value reward asset:

  * If USDC: amount
  * If LV-USDC: amount * NAV (convertToAssets)
* Compute:

  * revenue deposited
  * revenue claimed
  * unclaimed balance

Step 6 — Compute staking state + penalties

* Total staked SUMR, lock distribution, weighted stake
* Early exits and penalty amounts; penalty destination

Step 7 — Reconcile and validate

* Compare your computed series to:

  * DeFiLlama TVL/fees/revenue series (directional + level)
  * Any official dashboards
* Resolve discrepancies via the playbook (Section 2.3)

Step 8 — Produce investor-facing KPIs and a credibility scorecard
KPIs (minimum):

* TVL (current, 30d avg, peak, drawdown)
* Effective fee rate: weighted avg + by vault
* Total tips/fees (monthly, TTM)
* Staker share of tips (monthly)
* Staker revenue (monthly, TTM)
* Revenue yield:

  * on staked value
  * on circulating mcap
  * on FDV
* Emissions vs revenue composition:

  * revenue_rewards_usd / total_rewards_usd
* Distribution reliability:

  * days between revenue deposit events
  * variance of monthly payouts
* Concentration:

  * top 10 stakers share of staked weight
* Governance risk proxy:

  * count parameter changes per quarter (if on-chain events exist)

Step 9 — Scenario modeling + sensitivity

* Implement scenarios in a separate notebook/module (don’t mix with raw data jobs).
* Output: scenario tables + plots for:

  * projected staker revenue
  * implied revenue yield under TVL/fee regimes
  * break-even TVL needed to hit target yield (e.g., 10% revenue yield on mcap)

Step 10 — Write the final validation report (with evidence appendix)
Structure:

* Executive summary: does SUMR have *real* value accrual today?
* Methods: data sources, chain data, ABIs, pricing
* Results: metrics + charts
* Stress tests: scenarios
* Risks: governance/upgradeability/emissions/liquidity
* Appendix:

  * contract registry
  * key tx hashes proving distributions
  * reconciliation tables vs DeFiLlama

5.2 Visualization/reporting approach (practical)
Charts (no fluff):

* TVL over time (Lazy Summer vs Summer.fi if you can define both)
* Effective fee rate over time (weighted) + per-vault distribution (box/violin)
* Tips accrued vs staker revenue deposited (two lines; highlight the 20% hypothesis)
* Monthly staker revenue (bar) + cumulative
* Revenue yield on mcap (time series)
* Emissions vs revenue (stacked area)
* Staked SUMR and lock distribution over time

Dashboards:

* Metabase/Superset/Looker Studio for interactive exploration
* A “red flag” panel:

  * staker share deviates materially from 20% for >2 cycles
  * no revenue deposits for >45 days
  * upgrade event occurred
  * treasury share spikes unexpectedly

5.3 How to interpret results (decision rules)
Interpretation should be conditional and explicit:

* If (TTM staker revenue / mcap) is <1–2% and emissions dominate rewards: value accrual exists but is economically weak today.
* If staker share is unstable and changes without clear governance constraints: treat forward projections as low-confidence.
* If effective fee rate is far from 0.66% or concentrated in one vault: the “average fee” marketing claim is fragile.
* If the pipeline shows consistent fee generation, stable routing, and meaningful staker revenue vs mcap (e.g., >5–10% annualized revenue yield): the value accrual proposition is materially supported (subject to risks).

---

6. DELIVERABLES (WHAT YOU SHOULD HAVE AT THE END)
   6.1 Reproducible artifacts

* contract_registry.csv + ABI bundle + discovery memo
* ETL pipeline (repo) + schema + job schedules
* “Evidence notebook” that reproduces:

  * fee rate calculation
  * staker share calculation
  * sample tx proofs of revenue distributions
* Final report (PDF/markdown) with clear pass/fail verdicts per claim

6.2 Minimal “proof pack” for skeptical readers
Include 5–10 concrete on-chain proofs:

* 2–3 tx hashes showing fees accruing to tip stream/fee collector
* 2–3 tx hashes showing revenue deposited into the staker reward module
* 1–2 tx hashes showing staker claims (reward paid)
* 1 tx hash showing early withdrawal penalty mechanics
  Each proof must include:
* decoded event fields,
* USD valuation method at that block,
* link to explorer page.

---

7. RECOMMENDED TOOL STACK (TO EXECUTE WITHOUT HEROICS)
   Indexing & compute:

* Python: web3.py + pandas + SQLAlchemy
* Node (optional): ethers.js
* Scheduler: Dagster or Airflow
* DB: Postgres (start), BigQuery/Snowflake (scale)

Data sources:

* Explorer APIs: BaseScan (Etherscan-compatible) for ABIs and contract metadata: [BaseScan 2026](https://basescan.org/token/0x194f360d130f2393a5e9f3117a6a1b78abea1624 "SUMR Token Contract")
* RPC: Base archive endpoint (Alchemy/QuickNode/Ankr; pick one with historical state reads)
* Aggregators:

  * DeFiLlama protocol/fees endpoints: [DefiLlama 2026](https://defillama.com/protocol/lazy-summer-protocol "Lazy Summer Protocol - DefiLlama")
  * DeFiLlama lending category series: [DefiLlama 2026](https://preview.dl.llama.fi/protocols/Lending "Lending Protocols Rankings - DefiLlama")
* Analyst platforms (for cross-checking):

  * Dune (Base tables)
  * Flipside (if Base coverage is sufficient)

Documentation baselines (hypotheses, not proof):

* Tip Streams: [Summer.fi Docs 2026](https://docs.summer.fi/lazy-summer-protocol/governance/tip-streams "Tip Streams | Summer.fi Knowledge Base")
* Staking: [Summer.fi Docs 2026](https://docs.summer.fi/lazy-summer-protocol/governance/usdsumr-token/staking "Staking | Summer.fi Knowledge Base")
* Token docs: [Summer.fi Docs 2026](https://docs.summer.fi/lazy-summer-protocol/governance/usdsumr-token "SUMR Token | Summer.fi Knowledge Base")

---

8. COMMON FAILURE MODES (PLAN FOR THEM UP FRONT)

* Missing vault list → you undercount TVL/fees. Fix: three-source vault discovery + factory events.
* Fees accrue “silently” via share price rather than explicit transfers → you miss revenue. Fix: detect fee shares minted to fee addresses; also examine share price vs underlying performance.
* Reward asset is a vault token with changing NAV → you misvalue rewards. Fix: value at claim/deposit block using convertToAssets or pricePerShare.
* Upgrade events change behavior → you mix regimes. Fix: version your analyses by implementation block ranges.
* “20% of tips” is defined in DeFiLlama methodology but not enforced on-chain → your computed share won’t match. Fix: treat DeFiLlama as hypothesis; report actual realized share and whether it is parameterized.

---

9. FINAL OUTPUT YOU SHOULD PRODUCE (WHAT A READER CAN ACT ON)
   At completion, you should be able to answer, with evidence:
10. What is the realized (not assumed) effective fee rate by vault and in aggregate?
11. What fraction of realized fees ends up as staker revenue, and is it stable over time?
12. What is the realized staker revenue (USDC-equivalent) per month and per staked SUMR?
13. How much of “staking rewards” is genuine revenue vs inflationary emissions?
14. Under reasonable TVL/fee scenarios, what revenue yield does SUMR imply relative to its mcap/FDV—and how sensitive is that to governance and TVL volatility?
    </action_plan>
