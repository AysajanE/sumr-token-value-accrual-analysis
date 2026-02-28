# SUMR Token Value Accrual Analysis

Forensic, on-chain verification of whether the SUMR token (Summer.fi / Lazy Summer Protocol) has real value accrual through fee generation and staker revenue distribution.

## Background

Summer.fi's Lazy Summer Protocol claims SUMR is a revenue-share token: vaults generate fees (~0.66% AUM annually), and 20% of those fees flow to SUMR stakers as USDC-denominated rewards. This project independently verifies those claims using on-chain data.

## Structure

```
paper/          Final validation report
src/            Python modules (registry, indexing, processing, analysis, reconciliation)
notebooks/      Exploratory Jupyter notebooks (01–09, matching validation plan steps)
data/           Contract registry, ABIs, indexed events, API snapshots
results/        Charts, tables, proof pack, scorecard
docs/           Fact-check report, validation plan, definitions
ai/             Prompts and agent logs
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Fill in BASE_RPC_URL, BASESCAN_API_KEY
```

## Usage

```bash
make help       # List all targets
make registry   # Discover and catalog contracts
make snapshot   # Pull DeFiLlama API snapshots
make index      # Index on-chain events
make analyze    # Compute KPIs and scenarios
make evidence   # Build deterministic evidence pack from frozen snapshots
make refresh_claims # Refresh post-exec claim snapshots + receipt proofs
make v2_workflow # Build v2 closure workflow + gate-passed KPIs + gate-validated scenarios
make monitor_cycle # Run full monitoring cycle and append a status snapshot
make report     # Generate final validation report
```

## Public Push Hygiene

This repository intentionally excludes internal logs, draft feedback artifacts, and large raw snapshots from public GitHub pushes. See `PUBLIC_REPO_GUIDE.md` for the current include/exclude policy and pre-push checks.

## Key Questions

1. What is the realized effective fee rate by vault and in aggregate?
2. What fraction of realized fees ends up as staker revenue, and is it stable?
3. What is the realized staker revenue (USDC-equivalent) per month and per staked SUMR?
4. How much of "staking rewards" is genuine revenue vs inflationary emissions?
5. Under reasonable scenarios, what revenue yield does SUMR imply relative to mcap/FDV?
