# AGENTS.md — SUMR Token Value Accrual Analysis

## Project Purpose

Skeptical, forensic due-diligence analysis of the SUMR token (Summer.fi / Lazy Summer Protocol). Goal: verify on-chain whether SUMR has real value accrual via fees → staker revenue, or whether it's primarily a marketing narrative.

## Repo Layout

- `src/` — Python package organized by pipeline stage: `registry` → `indexing` → `processing` → `analysis` → `reconciliation`
- `notebooks/` — Numbered 01–09 matching the validation plan workflow steps
- `data/` — Contract registry, ABIs, indexed events (.parquet), API snapshots, prices. Raw data is .gitignored; regenerate via `make`
- `results/` — Charts, tables, proof pack, scorecard. All reproducible from `data/` + `src/`
- `docs/` — Fact-check report, validation plan, definitions, decision records
- `paper/` — Final validation report
- `ai/` — Prompts and agent session logs

## Key Contracts (Base chain, chain ID 8453)

| Label | Address | Notes |
|-------|---------|-------|
| SUMR Token | `0x194f360d130f2393a5e9f3117a6a1b78abea1624` | ERC-20, max supply 1B (1e27 raw) |
| stSUMR (Staked SUMR) | `0x7cc488f2681cfc2a5e8a00184bfa94ea6d520d1c` | Staking V2 contract |

Additional addresses (vaults, tip streams, reward distributors, treasury) must be discovered — see `data/contracts/registry.csv` and notebook `01_contract_discovery.ipynb`.

## Key Numbers (as of Feb 2026)

- SUMR price: ~$0.004–0.01
- SUMR max supply: 1B, total supply: ~976M
- Lazy Summer TVL (DeFiLlama): ~$45.7M
- Summer.fi TVL (broader): ~$83.2M
- All-time fees: ~$678K
- 30d fees: ~$44K → annualized ~$530K
- Fee split: 20% stakers, 10% treasury, 70% depositors
- Effective average fee: ~0.66% AUM (varies: 0.3% ETH vault, 1.0% stablecoin vaults)

## Key Data Sources

| Source | URL / Endpoint | Usage |
|--------|---------------|-------|
| DeFiLlama TVL | `https://api.llama.fi/protocol/lazy-summer-protocol` | TVL time series, chain breakdown |
| DeFiLlama Fees | `https://api.llama.fi/summary/fees/lazy-summer-protocol` | Fee/revenue/holder-revenue series |
| DeFiLlama (Summer.fi) | `https://api.llama.fi/protocol/summer.fi` | Broader TVL for scope comparison |
| BaseScan | `https://api.basescan.org/api` | ABIs, contract source, token info |
| Base RPC | Via `BASE_RPC_URL` in `.env` | `eth_getLogs`, `eth_call` at historical blocks |
| Summer.fi Docs | `https://docs.summer.fi/lazy-summer-protocol/governance/` | Tip streams, staking, token docs |

## Conventions

- **Directories with `$` in path**: Use single quotes in bash to avoid shell interpolation
- **Decimals**: Store raw integer values + decimals separately; never store only float
- **Timestamps**: UTC throughout; store both block number and UTC datetime
- **Dedup key**: `(tx_hash, log_index, chain_id)` for all indexed events
- **Pricing**: Primary = Chainlink (if available), secondary = DeFiLlama price API
- **File formats**: `.parquet` for indexed events, `.csv` for registry/proofs, `.json` for ABIs and API snapshots

## Running the Pipeline

```bash
cp .env.example .env        # Fill in RPC URL and API keys
pip install -r requirements.txt
make registry                # Step 1: Build contract registry
make snapshot                # Pull DeFiLlama API snapshots
make index                   # Index on-chain events
make analyze                 # Compute metrics, scenarios
make report                  # Generate final report
```

## What Proves / Disproves Value Accrual

**Proves (strong):** On-chain logs show (i) fees accrue to protocol-controlled addresses, (ii) ~20% routes to staker reward module, (iii) stakers claim USDC-denominated value consistently.

**Disproves (strong):** Fees exist but don't route to stakers; or routing exists but distributions are negligible/irregular; or distributions are dominated by inflationary emissions; or key parameters can change unilaterally.
