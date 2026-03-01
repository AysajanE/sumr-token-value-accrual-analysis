# SUMR Token Value Accrual Analysis

Forensic due-diligence repository for testing whether SUMR (Summer.fi / Lazy Summer Protocol) has real on-chain value accrual from fees to staker economics.

## Current Status

- Latest investor memo in repo: [paper/investor_executive_summary.md](paper/investor_executive_summary.md)
- Memo as-of monitoring observation: `2026-02-25`
- Verified evidence baseline window used by the memo: through `2026-02-09`
- Current memo classification: `CONDITIONAL` (not a full underwriting pass)

This repository is evidence-first: it distinguishes on-chain execution evidence from governance/forum statements and API-derived context.

## What Is In This Public Repo

- Source code: `src/`
- Build orchestration: `Makefile`, `workflow/`
- Methodology docs (selected): `docs/`
- Curated proof artifacts and scorecard:
  - `results/proofs/`
  - `results/scorecard.md`
- Narrative reports in markdown:
  - `paper/report.md`
  - `paper/comprehensive_value_accrual_report.md`
  - `paper/investor_executive_summary.md`

## What Is Deliberately Excluded

See [PUBLIC_REPO_GUIDE.md](PUBLIC_REPO_GUIDE.md) for policy details. In short, this repo excludes:

- Internal working logs and drafts (`ai/`, most of `docs/`, `tmp/`)
- Raw large snapshot dumps (`data/snapshots/**`)
- Generated working artifacts (`results/charts/`, `results/tables/`)
- Generated PDF/LaTeX build files in `paper/`

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Fill BASE_RPC_URL, BASESCAN_API_KEY
```

## Practical Workflows

### 1) Review Existing Public Evidence (no regeneration required)

- Read verdicts: [results/scorecard.md](results/scorecard.md)
- Read proof taxonomy and anchors: [results/proofs/proof_pack.md](results/proofs/proof_pack.md)
- Read investor narrative: [paper/investor_executive_summary.md](paper/investor_executive_summary.md)

### 2) Extend / Re-run Analysis Locally (requires local snapshot regeneration)

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

Important:
- Public repo excludes raw snapshot inputs and generated tables/charts.
- For strict reproducibility of a specific run, regenerate local snapshots first and then rebuild evidence/workflow artifacts.

## Notebook Guide

The `notebooks/` directory is now implemented as an interactive due-diligence workflow.
All notebooks use shared helpers in `notebooks/notebook_utils.py` for path setup, snapshot loading, and common metrics.

### Interactive Run

```bash
source .venv/bin/activate
jupyter notebook
```

Open and run in order:

1. `notebooks/01_contract_discovery.ipynb`
2. `notebooks/02_vault_tvl.ipynb`
3. `notebooks/03_fee_analysis.ipynb`
4. `notebooks/04_staker_revenue.ipynb`
5. `notebooks/05_staking_mechanics.ipynb`
6. `notebooks/06_supply_analysis.ipynb`
7. `notebooks/07_context_claims.ipynb`
8. `notebooks/08_scenario_modeling.ipynb`
9. `notebooks/09_reconciliation.ipynb`

### Notebook Coverage

| Notebook | Focus | Data mode |
| --- | --- | --- |
| `01_contract_discovery.ipynb` | Registry seed + ABI coverage checks | Local artifacts, optional live ABI fetch |
| `02_vault_tvl.ipynb` | TVL/fees trend monitoring + fee productivity | Live DeFiLlama refresh + local snapshot analysis |
| `03_fee_analysis.ipynb` | Fee-rate consistency checks vs 0.66% framing | Live DeFiLlama refresh + deterministic checks |
| `04_staker_revenue.ipynb` | Campaign realization and source-of-funds quality | Evidence artifacts, optional refresh pipeline |
| `05_staking_mechanics.ipynb` | Staking contract-mechanics verification | Evidence artifacts, optional live RPC reads |
| `06_supply_analysis.ipynb` | Supply/cap state + optional unlock-path view | Evidence artifacts, optional live RPC reads |
| `07_context_claims.ipynb` | Macro/peer context claim verification | Live external API context |
| `08_scenario_modeling.ipynb` | Scenario matrix and sensitivity visualization | Latest TVL + pinned supply assumptions |
| `09_reconciliation.ipynb` | Cross-source consistency gates | Evidence + latest API snapshot |

### Expected Outputs By Notebook

1. `01_contract_discovery.ipynb`: registry table, ABI coverage table, ABI function-count and availability charts.
2. `02_vault_tvl.ipynb`: Lazy Summer vs Summer.fi TVL trend chart, Lazy daily-fees chart, 90d fee-productivity summary table.
3. `03_fee_analysis.ipynb`: 30d/90d fee-rate consistency tables, daily-fee trend chart, daily-fee distribution chart, consistency verdict cell.
4. `04_staker_revenue.ipynb`: campaign realization table, stacked claimed-vs-residual chart, residual-ratio chart, aggregate realization summary.
5. `05_staking_mechanics.ipynb`: staking-mechanics check matrix, pass/fail bar chart, optional live stSUMR state table.
6. `06_supply_analysis.ipynb`: supply snapshot table, minted-vs-remaining pie chart, optional unlock schedule table/chart (if local table exists).
7. `07_context_claims.ipynb`: lending-context summary table, top-lending TVL chart, Lazy-vs-Summer scope chart, claim interpretation table.
8. `08_scenario_modeling.ipynb`: scenario matrix preview table, sensitivity heatmap, illustrative 3-case position-yield chart.
9. `09_reconciliation.ipynb`: reconciliation results table, pass/fail chart, overall PASS/PARTIAL gating summary.

### Optional Headless Validation

```bash
python -m pip install nbformat nbconvert nbclient
python - <<'PY'
import nbformat
from nbclient import NotebookClient
from pathlib import Path

root = Path.cwd()
for path in sorted((root / "notebooks").glob("[0-9][0-9]_*.ipynb")):
    nb = nbformat.read(path, as_version=4)
    NotebookClient(
        nb,
        timeout=600,
        kernel_name="python3",
        resources={"metadata": {"path": str(root)}},
    ).execute()
    print("OK", path.name)
PY
```

Notes:
- Some cells are intentionally toggle-based (`RUN_*` flags) so users can choose between fast local artifact analysis and live refresh paths.
- Live on-chain cells require `BASE_RPC_URL` in `.env`.
- External API notebooks require network access.

## Pipeline Maturity Notes

Actively used lane:
- Deterministic evidence building from frozen snapshots (`src/analysis/evidence.py`)
- v2 workflow outputs (`src/analysis/v2_workflow.py`)
- Monitoring snapshots (`src/analysis/monitor_cycle.py`)
- Investor/comprehensive narrative generation (`src/analysis/*report*`, `investor_*`)

Scaffold/partial modules still contain `NotImplementedError` stubs:
- `src/indexing/events.py`
- `src/indexing/snapshots.py`
- `src/processing/fees.py`
- `src/processing/revenue.py`
- `src/processing/staking.py`
- `src/analysis/benchmarks.py`
- parts of multi-source discovery in `src/registry/discover.py`

## Research Questions

1. Is fee generation persistent and measurable at the protocol level?
2. Does routing to stakers hold under execution evidence, not only forum claims?
3. How much of nominal inflow is actually realized by stakers (realization quality)?
4. Are staker economics dominated by real cashflow or token emissions/dilution?
5. Under sensitivity assumptions, when does the investment case cross into investable quality?
