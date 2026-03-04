# Public Repository Guide

This repository is configured for a public GitHub push with a strict policy:

- Keep source code, reproducible methods, and selected stable documentation.
- Exclude internal feedback notes, agent logs, local scratch files, and generated artifacts.
- Exclude raw large snapshots that are reproducible from pipeline commands.

## Included by default

- `src/`
- `workflow/`
- `notebooks/`
- `data/contracts/`
- `results/proofs/`
- `results/scorecard.md`
- `README.md`, `Makefile`, `requirements.txt`
- Selected docs:
  - `docs/dependency_graph.md`
  - `docs/definitions.md`
  - `docs/fact_check_report.md`
  - `docs/validation_plan.md`
  - `docs/validation_plan_v2.md`
  - `docs/decisions/ADR-0001-payout-attribution-overlap-policy.md`

## Excluded by default

- `ai/` (internal agent logs/prompts)
- `tmp/` (local scratch)
- `data/snapshots/**` (raw API/external snapshots)
- `data/indexed/`, `data/prices/`
- `results/charts/`, `results/tables/`
- `paper/*.aux`, `paper/*.log`, `paper/*.out`, `paper/*.toc`, `paper/*.tex`, `paper/*.pdf`
- Most of `docs/` except the allowlisted files above

## Pre-push checks

Run before every public push:

```bash
git status --short
git diff --cached --name-only
git check-ignore -v docs/feedback_on_executive_summary_report_2026-02-27_v2.md ai/logs/01_onchain_architecture.md data/snapshots/investor_external/latest_manifest.json paper/investor_executive_summary.pdf
```

If any excluded file is staged, unstage it and adjust `.gitignore` before pushing.
