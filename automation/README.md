# Update Cycle Automation

This folder contains the non-interactive automation chain for SUMR update rounds.

## Scripts

- `run_update_cycle_execution.sh`
  - Executes the playbook steps methodically (full or monitoring mode).
  - Auto-commits after each completed step.
  - Writes raw logs to `ai/logs/...` (gitignored).
  - Writes tracked reproducibility manifests to `results/proofs/update_runs/<RUN_TAG>/`.

- `run_update_cycle_audit.sh`
  - Runs Phase A (dual audit: Codex + Claude), Phase B triage, and optional Phase C remediation loop.
  - Auto-commits after each phase step.
  - Persists only important public audit artifacts in `results/proofs/update_runs/<RUN_TAG>/`.

- `run_update_cycle_chain.sh`
  - Orchestrates execution + audit/review/fix end-to-end.

## Prompt Templates

Used directly by the scripts:

- `automation/prompts/update_cycle_implementation_prompt.md` (Phase C remediation prompt)
- `automation/prompts/update_cycle_implementation_audit_prompt.md` (Phase A audit prompt)

Optional local override:
- Set `EXEC_TEMPLATE_PATH` / `AUDIT_TEMPLATE_PATH` to point to `ai/prompts/...` if you keep private prompt variants there.

## Schemas

- `schemas/update_audit_report.schema.json`
- `schemas/update_fix_report.schema.json`

## Default Behavior

- Integrity-first, reproducibility-focused.
- No enforced red/green test choreography.
- Practical/high-signal checks only.
- Gate policy fails on critical/high findings or fail-class verdicts.

## Typical Commands

```bash
# Full end-to-end round
RUN_TAG="$(date -u +%F)-independent" ./automation/run_update_cycle_chain.sh

# Execution only
RUN_TAG="$(date -u +%F)-independent" ./automation/run_update_cycle_execution.sh

# Audit only (no remediation)
RUN_TAG="$(date -u +%F)-independent" PHASE_C_ENABLED=0 ./automation/run_update_cycle_audit.sh

# Safe dry run
DRY_RUN=1 AUTO_COMMIT=0 ./automation/run_update_cycle_chain.sh
```

## Important Notes

- Run from repo root (scripts do this automatically).
- Keep `.env` populated before live runs (`BASE_RPC_URL`, optional `BASESCAN_API_KEY`).
- `ai/logs` stays gitignored by design.
- Public reproducibility artifacts are under `results/proofs/update_runs/`.
