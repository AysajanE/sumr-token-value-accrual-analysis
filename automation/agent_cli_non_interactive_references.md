# Agent CLI Non-Interactive References

Last verified: 2026-03-04 UTC

This note records the primary references used to configure non-interactive Codex + Claude CLI automation safely.

## Primary Sources

- OpenAI Codex CLI docs (official):
  - https://developers.openai.com/codex/cli
  - Relevant options confirmed: `exec`, `-a/--ask-for-approval`, `--skip-git-repo-check`, `-C`, `-o/--output-last-message`, `--output-schema`, `-s/--sandbox`.

- Anthropic Claude Code CLI reference (official):
  - https://docs.anthropic.com/en/docs/claude-code/cli-reference
  - Relevant options confirmed: `-p/--print`, `--output-format json`, `--json-schema`, `--permission-mode`, `--effort`, `--dangerously-skip-permissions`, `auth status --json`.

## Local CLI Verification (this machine)

Checked locally in this environment:

- `codex --version` => `codex-cli 0.107.0`
- `codex --help` and `codex exec --help` show required non-interactive flags.
- `codex login status` works for auth preflight.

- `claude --version` => `2.1.68 (Claude Code)`
- `claude --help` shows required non-interactive and permission flags.
- `claude auth status --json` works for auth preflight.

## Automation Policy Applied

- Non-interactive mode only.
- Explicit schema-constrained outputs for audit/fix phases.
- Auto-commit is enabled by default but excludes `ai/logs/**`.
- Phase C remediation is iterative and bounded (`PHASE_C_MAX_ITERATIONS`).
- Integrity and reproducibility artifacts are committed under `results/proofs/update_runs/<RUN_TAG>/`.
