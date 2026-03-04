#!/usr/bin/env bash
set -euo pipefail

# ------------------------------------------------------------------------------
# SUMR update-cycle execution runner (Codex-driven, step-by-step)
#
# Core workflow:
# - One Codex execution call per playbook step.
# - One auto-commit per completed step.
# - Step prompt is rendered from the execution template with step-specific context.
#
# This script intentionally does NOT run Claude during execution.
# Claude is used only in the separate audit/review phase.
#
# Usage examples:
#   ./automation/run_update_cycle_execution.sh
#   RUN_TAG=2026-03-04-independent ./automation/run_update_cycle_execution.sh
#   MODE=monitoring START_STEP=5 END_STEP=10 ./automation/run_update_cycle_execution.sh
#   DRY_RUN=1 AUTO_COMMIT=0 ./automation/run_update_cycle_execution.sh
#
# Key env vars:
#   MODE=full|monitoring
#   START_STEP=0
#   END_STEP=10
#   AUTO_COMMIT=1
#   DRY_RUN=0
#   ENFORCE_CLEAN_WORKTREE=1
#   ALLOW_PARTIAL_STEP=0
#
#   CODEX_MODEL=gpt-5.3-codex
#   CODEX_SANDBOX=workspace-write
#   CODEX_NETWORK_ACCESS=1
#   CODEX_APPROVAL=never
#   CODEX_TIMEOUT_SEC=7200
#   CODEX_REASONING_EFFORT=xhigh
#
#   PLAYBOOK_PATH=docs/update_cycle_playbook.md
#   EXEC_TEMPLATE_PATH=ai/prompts/update_cycle_implementation_prompt.md
#   FALLBACK_EXEC_TEMPLATE_PATH=automation/prompts/update_cycle_implementation_prompt.md
#   EXEC_SCHEMA_PATH=automation/schemas/update_execution_report.schema.json
# ------------------------------------------------------------------------------

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RUN_DATE="${RUN_DATE:-$(date -u +%F)}"
RUN_STAMP="${RUN_STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
RUN_TAG="${RUN_TAG:-${RUN_DATE}-independent}"

MODE="${MODE:-full}"
START_STEP="${START_STEP:-0}"
END_STEP="${END_STEP:-10}"
AUTO_COMMIT="${AUTO_COMMIT:-1}"
DRY_RUN="${DRY_RUN:-0}"
ENFORCE_CLEAN_WORKTREE="${ENFORCE_CLEAN_WORKTREE:-1}"
RUN_IMPORTANT_GATES="${RUN_IMPORTANT_GATES:-1}"
ALLOW_PARTIAL_STEP="${ALLOW_PARTIAL_STEP:-0}"

CODEX_MODEL="${CODEX_MODEL:-gpt-5.3-codex}"
CODEX_SANDBOX="${CODEX_SANDBOX:-workspace-write}"
CODEX_NETWORK_ACCESS="${CODEX_NETWORK_ACCESS:-1}"
CODEX_APPROVAL="${CODEX_APPROVAL:-never}"
CODEX_TIMEOUT_SEC="${CODEX_TIMEOUT_SEC:-7200}"
CODEX_REASONING_EFFORT="${CODEX_REASONING_EFFORT:-xhigh}"

PLAYBOOK_PATH="${PLAYBOOK_PATH:-docs/update_cycle_playbook.md}"
EXEC_TEMPLATE_PATH="${EXEC_TEMPLATE_PATH:-ai/prompts/update_cycle_implementation_prompt.md}"
FALLBACK_EXEC_TEMPLATE_PATH="${FALLBACK_EXEC_TEMPLATE_PATH:-automation/prompts/update_cycle_implementation_prompt.md}"
EXEC_SCHEMA_PATH="${EXEC_SCHEMA_PATH:-automation/schemas/update_execution_report.schema.json}"

SEED_PREVIOUS_SNAPSHOT="${SEED_PREVIOUS_SNAPSHOT:-1}"
PREV_SNAPSHOT_DIR="${PREV_SNAPSHOT_DIR:-}"
REFRESH_FROM_BLOCK="${REFRESH_FROM_BLOCK:-41932733}"
REFRESH_CHUNK_SIZE="${REFRESH_CHUNK_SIZE:-10000}"
REFRESH_RPC_URL="${REFRESH_RPC_URL:-${BASE_RPC_URL:-https://base.drpc.org}}"
BASE_RPC_URL_EFFECTIVE="${BASE_RPC_URL:-$REFRESH_RPC_URL}"

SNAPSHOT_DIR="${SNAPSHOT_DIR:-data/snapshots/external_review/${RUN_TAG}}"
EVIDENCE_DIR="${EVIDENCE_DIR:-results/proofs/evidence_${RUN_TAG}}"
TABLES_DIR="${TABLES_DIR:-results/tables}"
CHARTS_DIR="${CHARTS_DIR:-results/charts}"
TRACKED_RUN_DIR="${TRACKED_RUN_DIR:-results/proofs/update_runs/${RUN_TAG}}"

LOG_ROOT="${LOG_ROOT:-ai/logs/update_cycle/${RUN_TAG}/${RUN_STAMP}}"
STEP_LOG_DIR="$LOG_ROOT/execution"
PROMPT_DIR="$STEP_LOG_DIR/prompts"
TRACE_DIR="$STEP_LOG_DIR/traces"

STEP_TSV="$TRACKED_RUN_DIR/execution_steps_${RUN_STAMP}.tsv"
MANIFEST_JSON="$TRACKED_RUN_DIR/execution_manifest_${RUN_STAMP}.json"
MANIFEST_LATEST_JSON="$TRACKED_RUN_DIR/execution_manifest_latest.json"
SUMMARY_MD="$TRACKED_RUN_DIR/execution_summary_${RUN_STAMP}.md"
SUMMARY_LATEST_MD="$TRACKED_RUN_DIR/execution_summary_latest.md"
RUNTIME_CONTEXT_JSON="$TRACKED_RUN_DIR/runtime_context_${RUN_STAMP}.json"
RUNTIME_CONTEXT_LATEST_JSON="$TRACKED_RUN_DIR/runtime_context_latest.json"
STEP_REPORT_DIR="$TRACKED_RUN_DIR/execution_reports_${RUN_STAMP}"
STEP_REPORT_LATEST_DIR="$TRACKED_RUN_DIR/execution_reports_latest"

OVERALL_STATUS="RUNNING"
FAILED_STEP=""
LAST_STEP_LOG_PATH=""
LAST_STEP_REPORT_PATH=""
LAST_STEP_STATUS=""

info() { echo "==> $*"; }
die() { echo "ERROR: $*" >&2; exit 1; }
need_cmd() { command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"; }

assert_binary_flag() {
  local value="$1"
  local name="$2"
  [[ "$value" =~ ^(0|1)$ ]] || die "$name must be 0 or 1 (received '$value')"
}

assert_codex_reasoning_effort() {
  case "$CODEX_REASONING_EFFORT" in
    minimal|low|medium|high|xhigh)
      ;;
    "")
      die "CODEX_REASONING_EFFORT must be set (recommended: xhigh for gpt-5.3-codex)"
      ;;
    *)
      die "CODEX_REASONING_EFFORT must be one of: minimal, low, medium, high, xhigh (received '$CODEX_REASONING_EFFORT')"
      ;;
  esac
}

utc_now() {
  date -u +%Y-%m-%dT%H:%M:%SZ
}

run_with_timeout() {
  local timeout_sec="$1"
  shift

  if [[ "$timeout_sec" =~ ^[0-9]+$ ]] && [[ "$timeout_sec" -gt 0 ]]; then
    if command -v timeout >/dev/null 2>&1; then
      timeout "$timeout_sec" "$@"
      return $?
    fi
    if command -v gtimeout >/dev/null 2>&1; then
      gtimeout "$timeout_sec" "$@"
      return $?
    fi
  fi

  "$@"
}

ensure_git_identity() {
  git config user.email >/dev/null 2>&1 || git config user.email "codex-bot@localhost"
  git config user.name >/dev/null 2>&1 || git config user.name "codex-bot"
}

ensure_clean_worktree() {
  [[ "$ENFORCE_CLEAN_WORKTREE" == "1" ]] || return 0

  local tracked_status
  tracked_status="$(git status --porcelain --untracked-files=no)"
  if [[ -n "$tracked_status" ]]; then
    die "Tracked changes present before execution. Commit/stash first or set ENFORCE_CLEAN_WORKTREE=0."
  fi
}

should_run_step() {
  local step="$1"

  [[ "$step" =~ ^[0-9]+$ ]] || return 1
  if (( step < START_STEP || step > END_STEP )); then
    return 1
  fi

  if [[ "$MODE" == "full" ]]; then
    return 0
  fi

  case "$step" in
    0|1|5|6|8|9|10)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

step_name_for() {
  local step_id="$1"
  case "$step_id" in
    0) echo "setup_context" ;;
    1) echo "refresh_defillama" ;;
    2) echo "refresh_blockscout" ;;
    3) echo "refresh_forum_and_transactions" ;;
    4) echo "refresh_supply_and_manifest" ;;
    5) echo "refresh_claims_and_nav" ;;
    6) echo "build_evidence_and_v2" ;;
    7) echo "build_scenarios" ;;
    8) echo "freeze_and_monitor" ;;
    9) echo "report_generation" ;;
    10) echo "quality_gates" ;;
    *) echo "unknown_step" ;;
  esac
}

record_step() {
  local step_id="$1"
  local step_name="$2"
  local status="$3"
  local started_utc="$4"
  local finished_utc="$5"
  local log_path="$6"
  local commit_ref="$7"
  local report_path="$8"

  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$step_id" "$step_name" "$status" "$started_utc" "$finished_utc" "$log_path" "$commit_ref" "$report_path" \
    >> "$STEP_TSV"
}

commit_after_step() {
  local step_id="$1"
  local step_name="$2"

  if [[ "$AUTO_COMMIT" != "1" ]]; then
    echo "disabled"
    return 0
  fi
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "dry_run"
    return 0
  fi

  git add -A -- . ':(exclude)ai/**' ':(exclude)tmp/**'

  if git diff --cached --quiet --ignore-submodules --; then
    echo "no_changes"
    return 0
  fi

  local msg="data(update): ${RUN_TAG} step ${step_id} ${step_name} (${RUN_STAMP})"
  git commit -m "$msg" >/dev/null
  local sha
  sha="$(git rev-parse --short HEAD)"
  echo "==> Auto-commit created: ${sha}" >&2
  echo "$sha"
}

write_runtime_context() {
  python - "$RUNTIME_CONTEXT_JSON" "$RUNTIME_CONTEXT_LATEST_JSON" <<'PY'
import json
import os
from pathlib import Path
from datetime import datetime, timezone

out_path = Path(__import__('sys').argv[1])
latest_path = Path(__import__('sys').argv[2])
out_path.parent.mkdir(parents=True, exist_ok=True)

payload = {
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "run": {
        "run_date": os.environ.get("RUN_DATE"),
        "run_stamp": os.environ.get("RUN_STAMP"),
        "run_tag": os.environ.get("RUN_TAG"),
        "mode": os.environ.get("MODE"),
        "start_step": int(os.environ.get("START_STEP", "0")),
        "end_step": int(os.environ.get("END_STEP", "10")),
        "dry_run": os.environ.get("DRY_RUN") == "1",
        "auto_commit": os.environ.get("AUTO_COMMIT") == "1",
    },
    "paths": {
        "snapshot_dir": os.environ.get("SNAPSHOT_DIR"),
        "evidence_dir": os.environ.get("EVIDENCE_DIR"),
        "tables_dir": os.environ.get("TABLES_DIR"),
        "charts_dir": os.environ.get("CHARTS_DIR"),
        "tracked_run_dir": os.environ.get("TRACKED_RUN_DIR"),
        "log_root": os.environ.get("LOG_ROOT"),
        "playbook_path": os.environ.get("PLAYBOOK_PATH"),
        "execution_template_path": os.environ.get("EXEC_TEMPLATE_PATH"),
    },
    "refresh": {
        "from_block": int(os.environ.get("REFRESH_FROM_BLOCK", "0")),
        "chunk_size": int(os.environ.get("REFRESH_CHUNK_SIZE", "0")),
        "rpc_url": os.environ.get("REFRESH_RPC_URL"),
        "base_rpc_url_effective": os.environ.get("BASE_RPC_URL_EFFECTIVE"),
    },
    "codex": {
        "model": os.environ.get("CODEX_MODEL"),
        "reasoning_effort": os.environ.get("CODEX_REASONING_EFFORT"),
        "sandbox": os.environ.get("CODEX_SANDBOX"),
        "network_access": os.environ.get("CODEX_NETWORK_ACCESS") == "1",
        "approval": os.environ.get("CODEX_APPROVAL"),
        "timeout_sec": int(os.environ.get("CODEX_TIMEOUT_SEC", "0")),
    },
    "git": {
        "branch": os.popen("git rev-parse --abbrev-ref HEAD").read().strip(),
        "head": os.popen("git rev-parse HEAD").read().strip(),
    },
}

out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
latest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
}

write_manifest() {
  local exit_code="$1"

  python - "$STEP_TSV" "$MANIFEST_JSON" "$MANIFEST_LATEST_JSON" "$SUMMARY_MD" "$SUMMARY_LATEST_MD" "$OVERALL_STATUS" "$FAILED_STEP" "$exit_code" <<'PY'
import csv
import json
import os
from pathlib import Path
from datetime import datetime, timezone

step_tsv, manifest_path, manifest_latest_path, summary_md, summary_latest_md, overall_status, failed_step, exit_code = __import__('sys').argv[1:]
rows = []
if Path(step_tsv).exists():
    with open(step_tsv, "r", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t")
        for row in reader:
            if len(row) != 8:
                continue
            if row[0] == "step_id":
                continue
            rows.append({
                "step_id": row[0],
                "step_name": row[1],
                "status": row[2],
                "started_utc": row[3],
                "finished_utc": row[4],
                "log_path": row[5],
                "auto_commit": row[6],
                "report_path": row[7],
            })

payload = {
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "run": {
        "run_date": os.environ.get("RUN_DATE"),
        "run_stamp": os.environ.get("RUN_STAMP"),
        "run_tag": os.environ.get("RUN_TAG"),
        "mode": os.environ.get("MODE"),
        "dry_run": os.environ.get("DRY_RUN") == "1",
        "auto_commit": os.environ.get("AUTO_COMMIT") == "1",
        "start_step": int(os.environ.get("START_STEP", "0")),
        "end_step": int(os.environ.get("END_STEP", "10")),
    },
    "status": {
        "overall": overall_status,
        "failed_step": failed_step or None,
        "exit_code": int(exit_code),
    },
    "paths": {
        "snapshot_dir": os.environ.get("SNAPSHOT_DIR"),
        "evidence_dir": os.environ.get("EVIDENCE_DIR"),
        "tables_dir": os.environ.get("TABLES_DIR"),
        "charts_dir": os.environ.get("CHARTS_DIR"),
        "tracked_run_dir": os.environ.get("TRACKED_RUN_DIR"),
        "log_root": os.environ.get("LOG_ROOT"),
    },
    "steps": rows,
}

manifest_p = Path(manifest_path)
manifest_p.parent.mkdir(parents=True, exist_ok=True)
manifest_p.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
Path(manifest_latest_path).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

lines = []
lines.append("# Update Cycle Execution Summary")
lines.append("")
lines.append(f"- Run tag: {os.environ.get('RUN_TAG')}")
lines.append(f"- Run stamp (UTC): {os.environ.get('RUN_STAMP')}")
lines.append(f"- Mode: {os.environ.get('MODE')}")
lines.append(f"- Overall status: {overall_status}")
if failed_step:
    lines.append(f"- Failed step: {failed_step}")
lines.append("")
lines.append("| Step | Name | Status | Auto-Commit |")
lines.append("|---|---|---|---|")
for item in rows:
    lines.append(
        f"| {item['step_id']} | {item['step_name']} | {item['status']} | {item['auto_commit']} |"
    )
lines.append("")
lines.append(f"- Snapshot dir: `{os.environ.get('SNAPSHOT_DIR')}`")
lines.append(f"- Evidence dir: `{os.environ.get('EVIDENCE_DIR')}`")
lines.append(f"- Logs root (gitignored): `{os.environ.get('LOG_ROOT')}`")

Path(summary_md).write_text("\n".join(lines) + "\n", encoding="utf-8")
Path(summary_latest_md).write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
}

extract_playbook_section() {
  local step_id="$1"
  python - "$PLAYBOOK_PATH" "$step_id" <<'PY'
import re
import sys
from pathlib import Path

playbook_path = Path(sys.argv[1])
step_id = int(sys.argv[2])
lines = playbook_path.read_text(encoding="utf-8").splitlines()


def find_index(pattern):
    rx = re.compile(pattern)
    for i, line in enumerate(lines):
        if rx.search(line):
            return i
    return -1


def next_heading(start_idx, patterns):
    regexes = [re.compile(p) for p in patterns]
    for i in range(start_idx + 1, len(lines)):
        line = lines[i]
        if any(rx.search(line) for rx in regexes):
            return i
    return len(lines)

if step_id <= 9:
    start = find_index(rf"^## Step {step_id}:")
    if start < 0:
        raise SystemExit(f"Could not find playbook section for Step {step_id}")
    end = next_heading(start, [r"^## Step [0-9]+:", r"^## [0-9]+\)"])
else:
    start = find_index(r"^## 7\) Quality Gates")
    if start < 0:
        raise SystemExit("Could not find playbook quality gates section")
    end = next_heading(start, [r"^## 8\)"])

section = "\n".join(lines[start:end]).strip()
print(section)
PY
}

build_step_context() {
  local step_id="$1"
  local step_name="$2"
  local step_section="$3"

  cat <<EOF
Step assignment:
- step_id: ${step_id}
- step_name: ${step_name}
- run_mode: ${MODE}
- run_tag: ${RUN_TAG}
- snapshot_dir: ${SNAPSHOT_DIR}
- evidence_dir: ${EVIDENCE_DIR}
- tables_dir: ${TABLES_DIR}
- charts_dir: ${CHARTS_DIR}
- prev_snapshot_dir: ${PREV_SNAPSHOT_DIR:-<none>}
- seed_previous_snapshot: ${SEED_PREVIOUS_SNAPSHOT}
- refresh_from_block: ${REFRESH_FROM_BLOCK}
- refresh_chunk_size: ${REFRESH_CHUNK_SIZE}
- refresh_rpc_url: ${REFRESH_RPC_URL}
- base_rpc_url_effective: ${BASE_RPC_URL_EFFECTIVE}

Execution boundaries:
1. Execute ONLY this assigned step. Do not execute future numbered steps.
2. Keep all commands rooted at repo root: ${ROOT}
3. Respect integrity rules; do not hand-edit generated artifacts.
4. If the step cannot be fully completed, set status to "partial" or "blocked" with concrete blockers.
5. Include exact commands and concrete artifact paths in the structured report.

Assigned playbook section (execute this scope):

<assigned_step_section>
${step_section}
</assigned_step_section>
EOF
}

render_step_prompt() {
  local step_id="$1"
  local step_name="$2"
  local prompt_path="$3"
  local step_section="$4"

  local step_context
  step_context="$(build_step_context "$step_id" "$step_name" "$step_section")"

  python - "$EXEC_TEMPLATE_PATH" "$PLAYBOOK_PATH" "$prompt_path" "$step_context" <<'PY'
import sys
from pathlib import Path

template_path, playbook_path, prompt_path, context = sys.argv[1:]

template = Path(template_path).read_text(encoding="utf-8")
playbook = Path(playbook_path).read_text(encoding="utf-8")

text = template.replace("{{PLAYBOOK_STEP}}", playbook)
text = text.replace("{{CONTEXT}}", context)

Path(prompt_path).parent.mkdir(parents=True, exist_ok=True)
Path(prompt_path).write_text(text, encoding="utf-8")
PY
}

write_stub_execution_report() {
  local step_id="$1"
  local step_name="$2"
  local report_path="$3"

  cat > "$report_path" <<EOF
{
  "phase": "execution_step",
  "step_id": ${step_id},
  "step_name": "${step_name}",
  "status": "complete",
  "summary": "DRY_RUN enabled: live codex execution skipped.",
  "commands_run": [],
  "files_created": [],
  "files_modified": [],
  "validation_checks": [
    {
      "name": "dry_run_mode",
      "status": "not_run",
      "details": "Live codex step execution skipped because DRY_RUN=1"
    }
  ],
  "artifacts": [],
  "blockers": [],
  "next_actions": [
    "Run without DRY_RUN for real execution."
  ]
}
EOF
}

validate_execution_report() {
  local report_path="$1"
  local expected_step_id="$2"
  local expected_step_name="$3"

  python - "$report_path" "$expected_step_id" "$expected_step_name" <<'PY'
import json
import sys

report_path, expected_step_id, expected_step_name = sys.argv[1:]
expected_step_id = int(expected_step_id)
obj = json.load(open(report_path, "r", encoding="utf-8"))

required = [
    "phase",
    "step_id",
    "step_name",
    "status",
    "summary",
    "commands_run",
    "files_created",
    "files_modified",
    "validation_checks",
    "artifacts",
    "blockers",
    "next_actions",
]
missing = [k for k in required if k not in obj]
if missing:
    raise SystemExit(f"Execution report missing fields: {missing}")

if int(obj["step_id"]) != expected_step_id:
    raise SystemExit(f"Execution report step_id mismatch: expected {expected_step_id}, got {obj['step_id']}")

if obj["status"] not in {"complete", "partial", "blocked"}:
    raise SystemExit(f"Invalid execution status: {obj['status']}")

for k in ["commands_run", "files_created", "files_modified", "validation_checks", "artifacts", "blockers", "next_actions"]:
    if not isinstance(obj[k], list):
        raise SystemExit(f"{k} must be a list")

for i, check in enumerate(obj["validation_checks"], start=1):
    if not isinstance(check, dict):
        raise SystemExit(f"validation_checks[{i}] must be object")
    for req in ["name", "status", "details"]:
        if req not in check:
            raise SystemExit(f"validation_checks[{i}] missing '{req}'")
    if check["status"] not in {"pass", "fail", "not_run"}:
        raise SystemExit(f"validation_checks[{i}] invalid status '{check['status']}'")
PY
}

execution_status_from_report() {
  local report_path="$1"
  python - "$report_path" <<'PY'
import json
import sys
print(json.load(open(sys.argv[1], "r", encoding="utf-8")).get("status", "blocked"))
PY
}

run_step_with_codex() {
  local step_id="$1"
  local step_name="$2"

  local safe_name
  safe_name="$(printf '%s' "$step_name" | tr ' ' '_' | tr -cd '[:alnum:]_-')"

  local prompt_path="$PROMPT_DIR/step${step_id}_${safe_name}.prompt.md"
  local stdout_log="$TRACE_DIR/step${step_id}_${safe_name}.codex.stdout.log"
  local stderr_log="$TRACE_DIR/step${step_id}_${safe_name}.codex.stderr.log"
  local report_path="$STEP_REPORT_DIR/step${step_id}_${safe_name}.report.json"
  local report_latest_path="$STEP_REPORT_LATEST_DIR/step${step_id}_${safe_name}.report.json"

  local step_section
  step_section="$(extract_playbook_section "$step_id")"
  render_step_prompt "$step_id" "$step_name" "$prompt_path" "$step_section"

  if [[ "$DRY_RUN" == "1" ]]; then
    write_stub_execution_report "$step_id" "$step_name" "$report_path"
    : > "$stdout_log"
    : > "$stderr_log"
  else
    local cmd=(codex -a "$CODEX_APPROVAL" exec --skip-git-repo-check -C "." -o "$report_path" --output-schema "$EXEC_SCHEMA_PATH")
    [[ -n "$CODEX_MODEL" ]] && cmd+=(-m "$CODEX_MODEL")
    [[ -n "$CODEX_SANDBOX" ]] && cmd+=(-s "$CODEX_SANDBOX")
    if [[ "$CODEX_SANDBOX" == "workspace-write" ]]; then
      if [[ "$CODEX_NETWORK_ACCESS" == "1" ]]; then
        cmd+=(-c "sandbox_workspace_write.network_access=true")
      else
        cmd+=(-c "sandbox_workspace_write.network_access=false")
      fi
    fi
    [[ -n "$CODEX_REASONING_EFFORT" ]] && cmd+=(-c "model_reasoning_effort=\"$CODEX_REASONING_EFFORT\"")
    cmd+=(-)

    echo "==> Running Codex execution for step ${step_id} (${step_name})" >&2
    if ! run_with_timeout "$CODEX_TIMEOUT_SEC" "${cmd[@]}" < "$prompt_path" > >(tee "$stdout_log") 2> >(tee "$stderr_log" >&2); then
      die "Codex execution failed for step ${step_id}. See ${stderr_log}"
    fi
  fi

  validate_execution_report "$report_path" "$step_id" "$step_name"
  cp "$report_path" "$report_latest_path"

  local status
  status="$(execution_status_from_report "$report_path")"

  if [[ "$status" == "blocked" ]]; then
    die "Step ${step_id} reported status=blocked in execution report"
  fi

  if [[ "$status" == "partial" && "$ALLOW_PARTIAL_STEP" != "1" ]]; then
    die "Step ${step_id} reported status=partial and ALLOW_PARTIAL_STEP=0"
  fi

  LAST_STEP_LOG_PATH="$stdout_log"
  LAST_STEP_REPORT_PATH="$report_path"
  LAST_STEP_STATUS="$status"
}

run_step() {
  local step_id="$1"
  local step_name="$2"

  if ! should_run_step "$step_id"; then
    info "Skipping step ${step_id} (${step_name}) due to MODE/START_STEP/END_STEP filters."
    return 0
  fi

  if [[ "$step_id" == "10" && "$RUN_IMPORTANT_GATES" != "1" ]]; then
    info "Skipping step 10 (quality gates) because RUN_IMPORTANT_GATES=0"
    return 0
  fi

  local started_utc
  started_utc="$(utc_now)"
  info "Running step ${step_id}: ${step_name}"

  run_step_with_codex "$step_id" "$step_name"

  local finished_utc
  finished_utc="$(utc_now)"

  local commit_ref
  commit_ref="$(commit_after_step "$step_id" "$step_name")"

  local status_record="PASSED"
  if [[ "$LAST_STEP_STATUS" == "partial" ]]; then
    status_record="PARTIAL"
  fi

  record_step "$step_id" "$step_name" "$status_record" "$started_utc" "$finished_utc" "$LAST_STEP_LOG_PATH" "$commit_ref" "$LAST_STEP_REPORT_PATH"
}

on_exit() {
  local rc="$1"

  if [[ "$OVERALL_STATUS" == "RUNNING" ]]; then
    if [[ "$rc" -eq 0 ]]; then
      OVERALL_STATUS="SUCCESS"
    else
      OVERALL_STATUS="FAILED"
    fi
  fi

  write_manifest "$rc"
}

preflight() {
  need_cmd git
  need_cmd python

  assert_binary_flag "$AUTO_COMMIT" "AUTO_COMMIT"
  assert_binary_flag "$DRY_RUN" "DRY_RUN"
  assert_binary_flag "$ENFORCE_CLEAN_WORKTREE" "ENFORCE_CLEAN_WORKTREE"
  assert_binary_flag "$RUN_IMPORTANT_GATES" "RUN_IMPORTANT_GATES"
  assert_binary_flag "$ALLOW_PARTIAL_STEP" "ALLOW_PARTIAL_STEP"
  assert_binary_flag "$SEED_PREVIOUS_SNAPSHOT" "SEED_PREVIOUS_SNAPSHOT"
  assert_binary_flag "$CODEX_NETWORK_ACCESS" "CODEX_NETWORK_ACCESS"

  [[ "$MODE" == "full" || "$MODE" == "monitoring" ]] || die "MODE must be full or monitoring"
  [[ "$START_STEP" =~ ^[0-9]+$ ]] || die "START_STEP must be numeric"
  [[ "$END_STEP" =~ ^[0-9]+$ ]] || die "END_STEP must be numeric"
  (( START_STEP <= END_STEP )) || die "START_STEP must be <= END_STEP"
  assert_codex_reasoning_effort

  [[ -f "$PLAYBOOK_PATH" ]] || die "Missing playbook: $PLAYBOOK_PATH"
  if [[ ! -f "$EXEC_TEMPLATE_PATH" ]]; then
    if [[ -f "$FALLBACK_EXEC_TEMPLATE_PATH" ]]; then
      info "Execution template not found at '$EXEC_TEMPLATE_PATH'; using fallback '$FALLBACK_EXEC_TEMPLATE_PATH'"
      EXEC_TEMPLATE_PATH="$FALLBACK_EXEC_TEMPLATE_PATH"
    else
      die "Missing execution template at '$EXEC_TEMPLATE_PATH' and fallback '$FALLBACK_EXEC_TEMPLATE_PATH'"
    fi
  fi
  [[ -f "$EXEC_SCHEMA_PATH" ]] || die "Missing execution schema: $EXEC_SCHEMA_PATH"

  mkdir -p "$TRACKED_RUN_DIR" "$STEP_LOG_DIR" "$PROMPT_DIR" "$TRACE_DIR" "$STEP_REPORT_DIR" "$STEP_REPORT_LATEST_DIR"
  printf 'step_id\tstep_name\tstatus\tstarted_utc\tfinished_utc\tlog_path\tauto_commit\treport_path\n' > "$STEP_TSV"

  ensure_git_identity
  ensure_clean_worktree

  if [[ "$DRY_RUN" != "1" ]]; then
    need_cmd codex
    codex login status >/dev/null 2>&1 || die "Codex auth required (run: codex login)"
  fi

  write_runtime_context

  info "Execution run context"
  info "RUN_TAG=${RUN_TAG}"
  info "MODE=${MODE}"
  info "START_STEP=${START_STEP} END_STEP=${END_STEP}"
  info "SNAPSHOT_DIR=${SNAPSHOT_DIR}"
  info "EVIDENCE_DIR=${EVIDENCE_DIR}"
  info "TRACKED_RUN_DIR=${TRACKED_RUN_DIR}"
  info "LOG_ROOT=${LOG_ROOT}"
  info "EXEC_TEMPLATE_PATH=${EXEC_TEMPLATE_PATH}"
  info "CODEX_MODEL=${CODEX_MODEL} CODEX_REASONING_EFFORT=${CODEX_REASONING_EFFORT} CODEX_SANDBOX=${CODEX_SANDBOX} CODEX_NETWORK_ACCESS=${CODEX_NETWORK_ACCESS}"
}

trap 'on_exit $?' EXIT

export RUN_DATE RUN_STAMP RUN_TAG MODE START_STEP END_STEP AUTO_COMMIT DRY_RUN
export SNAPSHOT_DIR EVIDENCE_DIR TABLES_DIR CHARTS_DIR TRACKED_RUN_DIR LOG_ROOT
export PLAYBOOK_PATH EXEC_TEMPLATE_PATH
export REFRESH_FROM_BLOCK REFRESH_CHUNK_SIZE REFRESH_RPC_URL BASE_RPC_URL_EFFECTIVE
export CODEX_MODEL CODEX_REASONING_EFFORT CODEX_SANDBOX CODEX_NETWORK_ACCESS CODEX_APPROVAL CODEX_TIMEOUT_SEC

preflight

run_step 0 "$(step_name_for 0)"
run_step 1 "$(step_name_for 1)"
run_step 2 "$(step_name_for 2)"
run_step 3 "$(step_name_for 3)"
run_step 4 "$(step_name_for 4)"
run_step 5 "$(step_name_for 5)"
run_step 6 "$(step_name_for 6)"
run_step 7 "$(step_name_for 7)"
run_step 8 "$(step_name_for 8)"
run_step 9 "$(step_name_for 9)"
run_step 10 "$(step_name_for 10)"

OVERALL_STATUS="SUCCESS"
info "Update cycle execution completed successfully for RUN_TAG=${RUN_TAG}."
