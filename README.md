# SUMR Token Value Accrual Analysis

Forensic, evidence-first due-diligence repository for testing whether SUMR (Summer.fi / Lazy Summer Protocol) has real on-chain value accrual from protocol fees to staker economics.

This repository is designed to separate hard execution evidence from softer narrative layers such as governance posts, documentation claims, or API summaries. The aim is not generic token commentary. The aim is to determine whether the value-accrual story survives contact with on-chain data.

## Current status

- Latest investor memo: `paper/investor_executive_summary.md`
- Memo observation date: `2026-02-25`
- Verified evidence baseline used by the memo: through `2026-02-09`
- Current memo classification: `CONDITIONAL`

## Core question

Does SUMR have economically meaningful, verifiable value accrual for stakers, or is the story primarily narrative?

The analysis looks for concrete evidence that:

- protocol fees are real and measurable
- value routes to protocol-controlled destinations as claimed
- stakers receive durable, nontrivial economic benefit

## What is in the public repo

- `src/`: analysis and pipeline code
- `docs/`: selected methodology and dependency documentation
- `results/proofs/`: proof artifacts and update-run outputs
- `results/scorecard.md`: public-facing verdict summary
- `paper/`: narrative reports and investor-facing writeups
- `automation/`: update-chain scripts for execution, audit, review, and fix cycles

## What is deliberately excluded

See `PUBLIC_REPO_GUIDE.md` for policy details. In short, the public repo excludes:

- internal working logs and drafts
- large raw snapshot dumps
- generated working tables and charts that are meant to be rebuilt locally
- PDF / LaTeX build outputs

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill in the required Base RPC and BaseScan credentials before regenerating data.

## Practical ways to use the repo

### 1. Review the public evidence only

Start here if you want the verdict without regenerating the pipeline:

- `results/scorecard.md`
- `results/proofs/proof_pack.md`
- `paper/investor_executive_summary.md`

### 2. Re-run the analysis locally

```bash
make help
make registry
make snapshot
make refresh_claims
make refresh_lvusdc_nav
make evidence
make v2_workflow
make monitor_cycle
make report
```

For strict reproducibility of a particular run, regenerate local snapshots first, then rebuild evidence artifacts.

### 3. Run the automated update chain

```bash
RUN_TAG="$(date -u +%F)-independent" ./automation/run_update_cycle_chain.sh
RUN_TAG="$(date -u +%F)-independent" ./automation/run_update_cycle_execution.sh
RUN_TAG="$(date -u +%F)-independent" ./automation/run_update_cycle_audit.sh
```

Detailed logs remain gitignored; public reproducibility outputs are written under `results/proofs/update_runs/<RUN_TAG>/`.

## Notebook workflow

The notebooks form an interactive due-diligence sequence:

1. `notebooks/01_contract_discovery.ipynb`
2. `notebooks/02_vault_tvl.ipynb`
3. `notebooks/03_fee_analysis.ipynb`
4. `notebooks/04_staker_revenue.ipynb`
5. `notebooks/05_staking_mechanics.ipynb`
6. `notebooks/06_supply_analysis.ipynb`
7. `notebooks/07_context_claims.ipynb`
8. `notebooks/08_scenario_modeling.ipynb`
9. `notebooks/09_reconciliation.ipynb`

## Why this repo matters

This project signals:

- rigorous on-chain due diligence rather than surface-level token commentary
- explicit evidence handling and reproducibility boundaries
- the ability to turn ambiguous protocol claims into structured investigative workflows
