#!/usr/bin/env bash
set -euo pipefail

# ------------------------------------------------------------------------------
# SUMR update-cycle audit / review / fix chain
#
# Phases:
#   Phase A: Dual independent audits (Codex + Claude, non-interactive)
#   Phase B: Triage and gate decision (deduplicate + severity verdicting)
#   Phase C: Codex remediation loop (optional), then re-audit
#
# Design goals:
# - Prioritize integrity and data quality over enterprise-heavy test bureaucracy.
# - Keep raw logs under ai/logs (gitignored).
# - Persist only important public artifacts under results/proofs/update_runs/<RUN_TAG>.
# - Auto-commit after each phase step (optional, enabled by default).
#
# Usage:
#   ./automation/run_update_cycle_audit.sh
#   RUN_TAG=2026-03-04-independent ./automation/run_update_cycle_audit.sh
#   PHASE_C_ENABLED=0 ./automation/run_update_cycle_audit.sh
#   DRY_RUN=1 AUTO_COMMIT=0 ./automation/run_update_cycle_audit.sh
#
# Key env vars:
#   DRY_RUN=0
#   AUTO_COMMIT=1
#   ENFORCE_CLEAN_WORKTREE=1
#
#   PHASE_A_ENABLED=1
#   PHASE_B_ENABLED=1
#   PHASE_C_ENABLED=1
#   PHASE_C_MAX_ITERATIONS=3
#   PHASE_C_FIX_MODE=fresh|resume    (default: fresh)
#
#   GATE_FAIL_SEVERITIES=critical,high
#   GATE_FAIL_VERDICTS=fail,blocked,conditional_pass
#   GATE_FAILURE_EXIT_CODE=42
#
#   CODEX_MODEL=gpt-5.3-codex
#   CODEX_SANDBOX=workspace-write
#   CODEX_NETWORK_ACCESS=1
#   CODEX_APPROVAL=never
#   CODEX_TIMEOUT_SEC=5400
#   CODEX_REASONING_EFFORT=xhigh
#
#   CLAUDE_MODEL=opus
#   CLAUDE_PERMISSION_MODE=dontAsk
#   CLAUDE_EFFORT=high
#   CLAUDE_TIMEOUT_SEC=5400
#   CLAUDE_DANGEROUS_SKIP_PERMISSIONS=0
# ------------------------------------------------------------------------------

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RUN_DATE="${RUN_DATE:-$(date -u +%F)}"
RUN_STAMP="${RUN_STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
RUN_TAG="${RUN_TAG:-${RUN_DATE}-independent}"

SNAPSHOT_DIR="${SNAPSHOT_DIR:-data/snapshots/external_review/${RUN_TAG}}"
EVIDENCE_DIR="${EVIDENCE_DIR:-results/proofs/evidence_${RUN_TAG}}"
TABLES_DIR="${TABLES_DIR:-results/tables}"
CHARTS_DIR="${CHARTS_DIR:-results/charts}"
TRACKED_RUN_DIR="${TRACKED_RUN_DIR:-results/proofs/update_runs/${RUN_TAG}}"

PLAYBOOK_PATH="${PLAYBOOK_PATH:-docs/update_cycle_playbook.md}"
EXEC_TEMPLATE_PATH="${EXEC_TEMPLATE_PATH:-ai/prompts/update_cycle_implementation_prompt.md}"
FALLBACK_EXEC_TEMPLATE_PATH="${FALLBACK_EXEC_TEMPLATE_PATH:-automation/prompts/update_cycle_implementation_prompt.md}"
AUDIT_TEMPLATE_PATH="${AUDIT_TEMPLATE_PATH:-automation/prompts/update_cycle_implementation_audit_prompt.md}"

AUDIT_SCHEMA_PATH="${AUDIT_SCHEMA_PATH:-automation/schemas/update_audit_report.schema.json}"
FIX_SCHEMA_PATH="${FIX_SCHEMA_PATH:-automation/schemas/update_fix_report.schema.json}"

LOG_ROOT="${LOG_ROOT:-ai/logs/update_cycle/${RUN_TAG}/${RUN_STAMP}/audit}"
PROMPT_DIR="$LOG_ROOT/prompts"
REPORT_DIR="$LOG_ROOT/reports"
TRACE_DIR="$LOG_ROOT/traces"

DRY_RUN="${DRY_RUN:-0}"
AUTO_COMMIT="${AUTO_COMMIT:-1}"
ENFORCE_CLEAN_WORKTREE="${ENFORCE_CLEAN_WORKTREE:-1}"

PHASE_A_ENABLED="${PHASE_A_ENABLED:-1}"
PHASE_B_ENABLED="${PHASE_B_ENABLED:-1}"
PHASE_C_ENABLED="${PHASE_C_ENABLED:-1}"
PHASE_C_MAX_ITERATIONS="${PHASE_C_MAX_ITERATIONS:-3}"
PHASE_C_STOP_ON_NO_CHANGE="${PHASE_C_STOP_ON_NO_CHANGE:-1}"
PHASE_C_FIX_MODE="${PHASE_C_FIX_MODE:-fresh}"

GATE_FAIL_SEVERITIES="${GATE_FAIL_SEVERITIES:-critical,high}"
GATE_FAIL_VERDICTS="${GATE_FAIL_VERDICTS:-fail,blocked,conditional_pass}"
GATE_FAILURE_EXIT_CODE="${GATE_FAILURE_EXIT_CODE:-42}"

CODEX_MODEL="${CODEX_MODEL:-gpt-5.3-codex}"
CODEX_SANDBOX="${CODEX_SANDBOX:-workspace-write}"
CODEX_NETWORK_ACCESS="${CODEX_NETWORK_ACCESS:-1}"
CODEX_APPROVAL="${CODEX_APPROVAL:-never}"
CODEX_TIMEOUT_SEC="${CODEX_TIMEOUT_SEC:-5400}"
CODEX_REASONING_EFFORT="${CODEX_REASONING_EFFORT:-xhigh}"

CLAUDE_MODEL="${CLAUDE_MODEL:-opus}"
CLAUDE_PERMISSION_MODE="${CLAUDE_PERMISSION_MODE:-dontAsk}"
CLAUDE_EFFORT="${CLAUDE_EFFORT:-high}"
CLAUDE_TIMEOUT_SEC="${CLAUDE_TIMEOUT_SEC:-5400}"
CLAUDE_DANGEROUS_SKIP_PERMISSIONS="${CLAUDE_DANGEROUS_SKIP_PERMISSIONS:-0}"

PHASE_A_PROMPT_CODEX="$PROMPT_DIR/phase_a_codex_prompt.md"
PHASE_A_PROMPT_CLAUDE="$PROMPT_DIR/phase_a_claude_prompt.md"
PHASE_C_PROMPT="$PROMPT_DIR/phase_c_fix_prompt.md"

CODEX_REPORT_PATH="$REPORT_DIR/phase_a_codex_report.json"
CLAUDE_REPORT_PATH="$REPORT_DIR/phase_a_claude_report.json"
TRIAGE_JSON_PATH="$REPORT_DIR/phase_b_triage.json"
TRIAGE_MD_PATH="$REPORT_DIR/phase_b_triage.md"
PHASE_C_FIX_REPORT_PATH="$REPORT_DIR/phase_c_fix_report.json"
SUMMARY_PATH="$REPORT_DIR/audit_summary.md"

CODEX_STDOUT_LOG="$TRACE_DIR/phase_a_codex.stdout.log"
CODEX_STDERR_LOG="$TRACE_DIR/phase_a_codex.stderr.log"
CLAUDE_STDOUT_LOG_RAW="$TRACE_DIR/phase_a_claude.stdout.raw.log"
CLAUDE_STDERR_LOG="$TRACE_DIR/phase_a_claude.stderr.log"
PHASE_C_STDOUT_LOG="$TRACE_DIR/phase_c_fix.stdout.log"
PHASE_C_STDERR_LOG="$TRACE_DIR/phase_c_fix.stderr.log"

CODEX_TRACKED_BEFORE="$TRACE_DIR/phase_a_codex.tracked.before.tsv"
CODEX_TRACKED_AFTER="$TRACE_DIR/phase_a_codex.tracked.after.tsv"
CODEX_TRACKED_DELTA="$TRACE_DIR/phase_a_codex.tracked.delta.txt"

CLAUDE_TRACKED_BEFORE="$TRACE_DIR/phase_a_claude.tracked.before.tsv"
CLAUDE_TRACKED_AFTER="$TRACE_DIR/phase_a_claude.tracked.after.tsv"
CLAUDE_TRACKED_DELTA="$TRACE_DIR/phase_a_claude.tracked.delta.txt"

TRIAGE_GATE_STATUS="unknown"
TRIAGE_GATE_REASON="not_evaluated"
PHASE_C_ITERATIONS_RUN=0
CODEX_AUDIT_VERDICT="unknown"
CLAUDE_AUDIT_VERDICT="unknown"

TRACKED_CODEX_AUDIT_JSON="$TRACKED_RUN_DIR/audit_phase_a_codex_${RUN_STAMP}.json"
TRACKED_CODEX_AUDIT_LATEST="$TRACKED_RUN_DIR/audit_phase_a_codex_latest.json"
TRACKED_CLAUDE_AUDIT_JSON="$TRACKED_RUN_DIR/audit_phase_a_claude_${RUN_STAMP}.json"
TRACKED_CLAUDE_AUDIT_LATEST="$TRACKED_RUN_DIR/audit_phase_a_claude_latest.json"
TRACKED_TRIAGE_JSON="$TRACKED_RUN_DIR/audit_phase_b_triage_${RUN_STAMP}.json"
TRACKED_TRIAGE_JSON_LATEST="$TRACKED_RUN_DIR/audit_phase_b_triage_latest.json"
TRACKED_TRIAGE_MD="$TRACKED_RUN_DIR/audit_phase_b_triage_${RUN_STAMP}.md"
TRACKED_TRIAGE_MD_LATEST="$TRACKED_RUN_DIR/audit_phase_b_triage_latest.md"
TRACKED_PHASE_C_FIX_JSON="$TRACKED_RUN_DIR/audit_phase_c_fix_${RUN_STAMP}.json"
TRACKED_PHASE_C_FIX_LATEST="$TRACKED_RUN_DIR/audit_phase_c_fix_latest.json"
TRACKED_SUMMARY="$TRACKED_RUN_DIR/audit_summary_${RUN_STAMP}.md"
TRACKED_SUMMARY_LATEST="$TRACKED_RUN_DIR/audit_summary_latest.md"

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

assert_claude_effort() {
  case "$CLAUDE_EFFORT" in
    low|medium|high)
      ;;
    "")
      die "CLAUDE_EFFORT must be set (recommended: high for opus)"
      ;;
    *)
      die "CLAUDE_EFFORT must be one of: low, medium, high (received '$CLAUDE_EFFORT')"
      ;;
  esac
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
    die "Tracked changes present before audit. Commit/stash first or set ENFORCE_CLEAN_WORKTREE=0."
  fi
}

snapshot_tracked_hashes() {
  local out_file="$1"
  : > "$out_file"
  while IFS= read -r -d '' f; do
    local hash="__MISSING__"
    if [[ -f "$f" || -L "$f" ]]; then
      hash="$(shasum -a 256 "$f" | awk '{print $1}')"
    elif [[ -d "$f" ]]; then
      hash="__DIR__"
    fi
    printf '%s\t%s\n' "$f" "$hash" >> "$out_file"
  done < <(git ls-files -z)
  sort -u "$out_file" -o "$out_file"
}

write_snapshot_delta() {
  local before="$1"
  local after="$2"
  local delta_out="$3"

  awk -F '\t' '
    NR==FNR { before[$1]=$2; next }
    { after[$1]=$2 }
    END {
      for (k in after) if (!(k in before) || before[k] != after[k]) print k
      for (k in before) if (!(k in after)) print k
    }
  ' "$before" "$after" | sort -u > "$delta_out"
}

assert_no_tracked_mutation() {
  local before="$1"
  local after="$2"
  local delta_out="$3"
  local label="$4"

  write_snapshot_delta "$before" "$after" "$delta_out"
  if [[ -s "$delta_out" ]]; then
    echo "Tracked file mutation detected after ${label}:" >&2
    sed -n '1,120p' "$delta_out" >&2
    die "${label} modified tracked files unexpectedly"
  fi
}

validate_audit_report() {
  local report_path="$1"
  local expected_agent="$2"

  python - "$report_path" "$expected_agent" <<'PY'
import json
import sys

report_path, expected_agent = sys.argv[1:]
with open(report_path, "r", encoding="utf-8") as f:
    obj = json.load(f)

required_top = [
    "phase",
    "agent",
    "verdict",
    "summary",
    "findings",
    "checks",
    "commands_run",
    "artifacts",
    "limitations",
    "next_actions",
]
missing = [k for k in required_top if k not in obj]
if missing:
    raise SystemExit(f"Missing top-level fields: {missing}")

if obj.get("agent") != expected_agent:
    raise SystemExit(f"Expected agent '{expected_agent}' but got '{obj.get('agent')}'")

allowed_verdicts = {"pass", "pass_with_minor", "conditional_pass", "fail", "blocked"}
if obj.get("verdict") not in allowed_verdicts:
    raise SystemExit(f"Invalid verdict: {obj.get('verdict')}")

if not isinstance(obj.get("findings"), list):
    raise SystemExit("findings must be a list")
if not isinstance(obj.get("checks"), list):
    raise SystemExit("checks must be a list")

allowed_sev = {"critical", "high", "medium", "low", "info"}
for i, finding in enumerate(obj["findings"], start=1):
    req = ["id", "severity", "title", "description", "impact", "evidence", "recommendation", "file_refs"]
    m = [k for k in req if k not in finding]
    if m:
        raise SystemExit(f"finding[{i}] missing keys: {m}")
    if finding["severity"] not in allowed_sev:
        raise SystemExit(f"finding[{i}] invalid severity: {finding['severity']}")
    if not isinstance(finding["file_refs"], list):
        raise SystemExit(f"finding[{i}].file_refs must be a list")

for i, chk in enumerate(obj["checks"], start=1):
    req = ["name", "status", "details"]
    m = [k for k in req if k not in chk]
    if m:
        raise SystemExit(f"check[{i}] missing keys: {m}")
    if chk["status"] not in {"pass", "fail", "not_run"}:
        raise SystemExit(f"check[{i}] invalid status: {chk['status']}")

for key in ["commands_run", "artifacts", "limitations", "next_actions"]:
    if not isinstance(obj[key], list):
        raise SystemExit(f"{key} must be a list")
PY
}

validate_fix_report() {
  local report_path="$1"

  python - "$report_path" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, "r", encoding="utf-8") as f:
    obj = json.load(f)

required = [
    "phase",
    "iteration",
    "status",
    "summary",
    "fixed_items",
    "remaining_items",
    "commands_run",
    "artifacts",
    "risks",
    "next_actions",
]
missing = [k for k in required if k not in obj]
if missing:
    raise SystemExit(f"Missing fix report fields: {missing}")

if obj["status"] not in {"fixed", "partial", "blocked", "no_change"}:
    raise SystemExit(f"Invalid fix status: {obj['status']}")

for k in ["fixed_items", "remaining_items", "commands_run", "artifacts", "risks", "next_actions"]:
    if not isinstance(obj[k], list):
        raise SystemExit(f"{k} must be a list")
PY
}

build_prompt_from_template() {
  local template_path="$1"
  local out_path="$2"
  local agent_name="$3"

  python - "$template_path" "$out_path" "$agent_name" <<'PY'
import os
from pathlib import Path
import sys

template_path, out_path, agent_name = sys.argv[1:]
text = Path(template_path).read_text(encoding="utf-8")
playbook = Path(os.environ["PLAYBOOK_PATH"]).read_text(encoding="utf-8")

replacements = {
    "{{UPDATE_CYCLE_PLAYBOOK}}": playbook,
    "{{PLAYBOOK_STEP}}": playbook,
    "{{RUN_TAG}}": os.environ.get("RUN_TAG", ""),
    "{{SNAPSHOT_DIR}}": os.environ.get("SNAPSHOT_DIR", ""),
    "{{EVIDENCE_DIR}}": os.environ.get("EVIDENCE_DIR", ""),
    "{{TABLES_DIR}}": os.environ.get("TABLES_DIR", ""),
    "{{CHARTS_DIR}}": os.environ.get("CHARTS_DIR", ""),
    "{{TRACKED_RUN_DIR}}": os.environ.get("TRACKED_RUN_DIR", ""),
    "{{AGENT_NAME}}": agent_name,
    "{{RUN_STAMP}}": os.environ.get("RUN_STAMP", ""),
}

for k, v in replacements.items():
    text = text.replace(k, v)

Path(out_path).parent.mkdir(parents=True, exist_ok=True)
Path(out_path).write_text(text, encoding="utf-8")
PY
}

write_stub_report() {
  local agent="$1"
  local out_path="$2"

  cat > "$out_path" <<EOF_STUB
{
  "phase": "update_cycle",
  "agent": "${agent}",
  "verdict": "pass",
  "summary": "DRY_RUN enabled: live ${agent} audit skipped.",
  "findings": [],
  "checks": [
    {
      "name": "dry_run_mode",
      "status": "not_run",
      "details": "Live audit skipped because DRY_RUN=1"
    }
  ],
  "commands_run": [],
  "artifacts": [],
  "limitations": ["DRY_RUN mode does not execute real audits."],
  "next_actions": ["Run without DRY_RUN for live audit evidence."]
}
EOF_STUB
}

normalize_claude_output() {
  local raw_path="$1"
  local normalized_path="$2"

  python - "$raw_path" "$normalized_path" <<'PY'
import json
import sys
from pathlib import Path

raw_path, out_path = sys.argv[1:]
raw = Path(raw_path).read_text(encoding="utf-8", errors="replace")
lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
if not lines:
    raise SystemExit("Claude raw output is empty")

envelope = None
for ln in reversed(lines):
    try:
        envelope = json.loads(ln)
        break
    except Exception:
        continue

if envelope is None:
    raise SystemExit("No JSON envelope found in Claude output")

report = None
if isinstance(envelope, dict):
    report = envelope.get("structured_output")
    if report is None and isinstance(envelope.get("result"), str):
        txt = envelope.get("result", "").strip()
        if txt:
            try:
                report = json.loads(txt)
            except Exception:
                report = None
    if report is None and {"phase", "agent", "verdict", "findings"}.issubset(envelope.keys()):
        report = envelope

if not isinstance(report, dict):
    raise SystemExit("Could not extract structured report from Claude output")

Path(out_path).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
PY
}

copy_phase_a_artifacts_to_tracked() {
  cp "$CODEX_REPORT_PATH" "$TRACKED_CODEX_AUDIT_JSON"
  cp "$CODEX_REPORT_PATH" "$TRACKED_CODEX_AUDIT_LATEST"
  cp "$CLAUDE_REPORT_PATH" "$TRACKED_CLAUDE_AUDIT_JSON"
  cp "$CLAUDE_REPORT_PATH" "$TRACKED_CLAUDE_AUDIT_LATEST"
}

copy_phase_b_artifacts_to_tracked() {
  cp "$TRIAGE_JSON_PATH" "$TRACKED_TRIAGE_JSON"
  cp "$TRIAGE_JSON_PATH" "$TRACKED_TRIAGE_JSON_LATEST"
  cp "$TRIAGE_MD_PATH" "$TRACKED_TRIAGE_MD"
  cp "$TRIAGE_MD_PATH" "$TRACKED_TRIAGE_MD_LATEST"
}

copy_phase_c_artifacts_to_tracked() {
  cp "$PHASE_C_FIX_REPORT_PATH" "$TRACKED_PHASE_C_FIX_JSON"
  cp "$PHASE_C_FIX_REPORT_PATH" "$TRACKED_PHASE_C_FIX_LATEST"
}

auto_commit_step() {
  local step_label="$1"

  if [[ "$AUTO_COMMIT" != "1" ]]; then
    info "Auto-commit disabled for ${step_label}."
    return 0
  fi
  if [[ "$DRY_RUN" == "1" ]]; then
    info "DRY_RUN enabled; skipping auto-commit for ${step_label}."
    return 0
  fi

  git add -A -- . ':(exclude)ai/**' ':(exclude)tmp/**'

  if git diff --cached --quiet --ignore-submodules --; then
    info "No eligible tracked changes to commit for ${step_label}."
    return 0
  fi

  local msg="chore(update): ${RUN_TAG} ${step_label} (${RUN_STAMP})"
  git commit -m "$msg" >/dev/null
  info "Auto-commit created for ${step_label}: $(git rev-parse --short HEAD)"
}

run_codex_audit() {
  build_prompt_from_template "$AUDIT_TEMPLATE_PATH" "$PHASE_A_PROMPT_CODEX" "codex"
  snapshot_tracked_hashes "$CODEX_TRACKED_BEFORE"

  if [[ "$DRY_RUN" == "1" ]]; then
    write_stub_report "codex" "$CODEX_REPORT_PATH"
    : > "$CODEX_STDOUT_LOG"
    : > "$CODEX_STDERR_LOG"
  else
    local cmd=(codex -a "$CODEX_APPROVAL" exec --skip-git-repo-check -C "." -o "$CODEX_REPORT_PATH" --output-schema "$AUDIT_SCHEMA_PATH")
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

    info "Running Codex audit (model=${CODEX_MODEL}, sandbox=${CODEX_SANDBOX}, approval=${CODEX_APPROVAL})"
    if ! run_with_timeout "$CODEX_TIMEOUT_SEC" "${cmd[@]}" < "$PHASE_A_PROMPT_CODEX" > >(tee "$CODEX_STDOUT_LOG") 2> >(tee "$CODEX_STDERR_LOG" >&2); then
      die "Codex phase A audit failed. See $CODEX_STDERR_LOG"
    fi
  fi

  validate_audit_report "$CODEX_REPORT_PATH" "codex"
  CODEX_AUDIT_VERDICT="$(python - "$CODEX_REPORT_PATH" <<'PY'
import json
import sys
print(str(json.load(open(sys.argv[1], "r", encoding="utf-8")).get("verdict", "unknown")))
PY
)"

  snapshot_tracked_hashes "$CODEX_TRACKED_AFTER"
  assert_no_tracked_mutation "$CODEX_TRACKED_BEFORE" "$CODEX_TRACKED_AFTER" "$CODEX_TRACKED_DELTA" "Codex audit"
}

run_claude_audit() {
  build_prompt_from_template "$AUDIT_TEMPLATE_PATH" "$PHASE_A_PROMPT_CLAUDE" "claude"
  snapshot_tracked_hashes "$CLAUDE_TRACKED_BEFORE"

  if [[ "$DRY_RUN" == "1" ]]; then
    write_stub_report "claude" "$CLAUDE_REPORT_PATH"
    : > "$CLAUDE_STDOUT_LOG_RAW"
    : > "$CLAUDE_STDERR_LOG"
  else
    local schema_inline
    schema_inline="$(python - "$AUDIT_SCHEMA_PATH" <<'PY'
import json
import sys
print(json.dumps(json.load(open(sys.argv[1], "r", encoding="utf-8"))))
PY
)"

    local cmd=(claude -p --output-format json --json-schema "$schema_inline" --permission-mode "$CLAUDE_PERMISSION_MODE" --model "$CLAUDE_MODEL")
    [[ -n "$CLAUDE_EFFORT" ]] && cmd+=(--effort "$CLAUDE_EFFORT")
    if [[ "$CLAUDE_DANGEROUS_SKIP_PERMISSIONS" == "1" ]]; then
      cmd+=(--dangerously-skip-permissions)
    fi

    info "Running Claude audit (model=${CLAUDE_MODEL}, permission_mode=${CLAUDE_PERMISSION_MODE})"
    local claude_rc=0
    set +e
    run_with_timeout "$CLAUDE_TIMEOUT_SEC" "${cmd[@]}" < "$PHASE_A_PROMPT_CLAUDE" > "$CLAUDE_STDOUT_LOG_RAW" 2> >(tee "$CLAUDE_STDERR_LOG" >&2)
    claude_rc=$?
    set -e

    if [[ "$claude_rc" -ne 0 ]]; then
      info "Claude exited non-zero (rc=${claude_rc}); attempting output normalization."
    fi

    normalize_claude_output "$CLAUDE_STDOUT_LOG_RAW" "$CLAUDE_REPORT_PATH"
  fi

  validate_audit_report "$CLAUDE_REPORT_PATH" "claude"
  CLAUDE_AUDIT_VERDICT="$(python - "$CLAUDE_REPORT_PATH" <<'PY'
import json
import sys
print(str(json.load(open(sys.argv[1], "r", encoding="utf-8")).get("verdict", "unknown")))
PY
)"

  snapshot_tracked_hashes "$CLAUDE_TRACKED_AFTER"
  assert_no_tracked_mutation "$CLAUDE_TRACKED_BEFORE" "$CLAUDE_TRACKED_AFTER" "$CLAUDE_TRACKED_DELTA" "Claude audit"
}

build_phase_b_triage() {
  python - "$CODEX_REPORT_PATH" "$CLAUDE_REPORT_PATH" "$TRIAGE_JSON_PATH" "$TRIAGE_MD_PATH" "$GATE_FAIL_SEVERITIES" "$GATE_FAIL_VERDICTS" <<'PY'
import json
import sys
from datetime import datetime, timezone

codex_path, claude_path, triage_json_path, triage_md_path, gate_sev_csv, gate_verdict_csv = sys.argv[1:]

with open(codex_path, "r", encoding="utf-8") as f:
    codex = json.load(f)
with open(claude_path, "r", encoding="utf-8") as f:
    claude = json.load(f)

reports = [codex, claude]

sev_rank = {"critical": 5, "high": 4, "medium": 3, "low": 2, "info": 1}
def norm(s):
    return " ".join(str(s or "").lower().split())

agg = {}
for report in reports:
    agent = str(report.get("agent", "unknown"))
    for finding in report.get("findings", []):
        title = str(finding.get("title", "untitled")).strip()
        refs = sorted({str(x).strip() for x in finding.get("file_refs", []) if str(x).strip()})
        key = f"{norm(title)}|{','.join(norm(r) for r in refs)}"
        if key == "|":
            key = f"{norm(title)}|{norm(finding.get('description', ''))[:160]}"
        if key not in agg:
            agg[key] = {
                "title": title,
                "severity": finding.get("severity", "info"),
                "description": str(finding.get("description", "")).strip(),
                "impact": str(finding.get("impact", "")).strip(),
                "evidence": set(),
                "recommendation": set(),
                "file_refs": set(refs),
                "source_agents": set(),
            }
        item = agg[key]
        sev = finding.get("severity", "info")
        if sev_rank.get(sev, 1) > sev_rank.get(item["severity"], 1):
            item["severity"] = sev
        item["source_agents"].add(agent)
        item["evidence"].add(str(finding.get("evidence", "")).strip())
        item["recommendation"].add(str(finding.get("recommendation", "")).strip())
        for r in refs:
            item["file_refs"].add(r)

fix_queue = []
for idx, item in enumerate(sorted(agg.values(), key=lambda x: (-sev_rank.get(x["severity"], 1), x["title"])), start=1):
    fix_queue.append({
        "id": f"F-{idx:03d}",
        "severity": item["severity"],
        "title": item["title"],
        "description": item["description"],
        "impact": item["impact"],
        "source_agents": sorted(item["source_agents"]),
        "file_refs": sorted(item["file_refs"]),
        "evidence_samples": [x for x in sorted(item["evidence"]) if x][:3],
        "recommendations": [x for x in sorted(item["recommendation"]) if x][:3],
    })

fail_sev = {x.strip().lower() for x in gate_sev_csv.split(",") if x.strip()}
fail_verdict = {x.strip().lower() for x in gate_verdict_csv.split(",") if x.strip()}

fail_by_severity = any(str(f["severity"]).lower() in fail_sev for f in fix_queue)
fail_by_verdict = any(str(r.get("verdict", "")).lower() in fail_verdict for r in reports)
both_audits_pass = all(str(r.get("verdict", "")).lower() == "pass" for r in reports)

if both_audits_pass:
    gate_status = "pass"
    gate_reason = "both_audits_passed"
else:
    gate_status = "fail"
    if fail_by_severity and fail_by_verdict:
        gate_reason = "awaiting_both_pass__severity_and_verdict_triggered"
    elif fail_by_severity:
        gate_reason = "awaiting_both_pass__severity_triggered"
    elif fail_by_verdict:
        gate_reason = "awaiting_both_pass__verdict_triggered"
    else:
        gate_reason = "awaiting_both_pass"

triage = {
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "source_reports": {
        "codex": codex_path,
        "claude": claude_path,
    },
    "agent_verdicts": [
        {"agent": str(codex.get("agent")), "verdict": str(codex.get("verdict")), "summary": str(codex.get("summary", ""))},
        {"agent": str(claude.get("agent")), "verdict": str(claude.get("verdict")), "summary": str(claude.get("summary", ""))},
    ],
    "totals": {
        "raw_findings": len(codex.get("findings", [])) + len(claude.get("findings", [])),
        "unique_findings": len(fix_queue),
    },
    "gate": {
        "both_audits_pass_required": True,
        "both_audits_pass": both_audits_pass,
        "status": gate_status,
        "reason": gate_reason,
        "severity_policy_is_advisory": True,
        "fail_severities": sorted(fail_sev),
        "fail_verdicts": sorted(fail_verdict),
        "failed_by_severity": fail_by_severity,
        "failed_by_verdict": fail_by_verdict,
    },
    "fix_queue": fix_queue,
}

with open(triage_json_path, "w", encoding="utf-8") as f:
    json.dump(triage, f, indent=2)
    f.write("\n")

md = []
md.append("# Update Cycle Audit Triage")
md.append("")
md.append(f"- Generated (UTC): {triage['generated_at_utc']}")
md.append(f"- Gate status: {gate_status}")
md.append(f"- Gate reason: {gate_reason}")
md.append(f"- Both audits pass required: {triage['gate']['both_audits_pass_required']}")
md.append(f"- Both audits pass observed: {triage['gate']['both_audits_pass']}")
md.append("")
md.append("## Agent Verdicts")
md.append("")
for item in triage["agent_verdicts"]:
    md.append(f"- {item['agent']}: {item['verdict']} - {item['summary']}")
md.append("")
md.append("## Deduplicated Fix Queue")
md.append("")
if not fix_queue:
    md.append("No findings from either auditor.")
else:
    for f in fix_queue:
        md.append(f"### {f['id']} [{f['severity']}] {f['title']}")
        md.append(f"- Source agents: {', '.join(f['source_agents']) or '(none)'}")
        md.append(f"- File refs: {', '.join(f['file_refs']) or '(none)'}")
        if f['evidence_samples']:
            for ev in f['evidence_samples']:
                md.append(f"- Evidence: {ev}")
        if f['recommendations']:
            for rec in f['recommendations']:
                md.append(f"- Recommendation: {rec}")
        md.append("")

with open(triage_md_path, "w", encoding="utf-8") as f:
    f.write("\n".join(md) + "\n")

print(json.dumps({"status": gate_status, "reason": gate_reason}))
PY

  TRIAGE_GATE_STATUS="$(python - "$TRIAGE_JSON_PATH" <<'PY'
import json,sys
print(json.load(open(sys.argv[1], "r", encoding="utf-8"))["gate"]["status"])
PY
)"
  TRIAGE_GATE_REASON="$(python - "$TRIAGE_JSON_PATH" <<'PY'
import json,sys
print(json.load(open(sys.argv[1], "r", encoding="utf-8"))["gate"]["reason"])
PY
)"
}

build_phase_c_fix_prompt() {
  local iteration="$1"

  python - "$EXEC_TEMPLATE_PATH" "$PHASE_C_PROMPT" "$iteration" <<'PY'
import os
from pathlib import Path
import sys

template_path, out_path, iteration = sys.argv[1:]
text = Path(template_path).read_text(encoding="utf-8")
playbook = Path(os.environ["PLAYBOOK_PATH"]).read_text(encoding="utf-8")
triage_json = os.environ["TRIAGE_JSON_PATH"]
triage_md = os.environ["TRIAGE_MD_PATH"]
run_tag = os.environ["RUN_TAG"]

context = f"""
Phase C remediation iteration: {iteration}
Run tag: {run_tag}

Primary remediation input:
- {triage_json}
- {triage_md}

Remediation requirements:
1. Fix all CRITICAL/HIGH findings first, then MEDIUM, then LOW/INFO.
2. Preserve integrity rules from the playbook. Do not fabricate data.
3. Update code/data artifacts needed for this repo's update-cycle outputs.
4. Run only practical, high-signal verification commands for this side-project context.
5. Keep detailed command/evidence references in your structured response.
6. If an item cannot be fixed now, leave it in remaining_items with concrete blocker.
""".strip()

text = text.replace("{{PLAYBOOK_STEP}}", playbook)
text = text.replace("{{CONTEXT}}", context)

Path(out_path).parent.mkdir(parents=True, exist_ok=True)
Path(out_path).write_text(text, encoding="utf-8")
PY
}

run_phase_c_fix_iteration() {
  local iteration="$1"
  local before_head
  before_head="$(git rev-parse HEAD)"

  build_phase_c_fix_prompt "$iteration"

  if [[ "$DRY_RUN" == "1" ]]; then
    cat > "$PHASE_C_FIX_REPORT_PATH" <<EOF_FIX
{
  "phase": "phase_c",
  "iteration": ${iteration},
  "status": "no_change",
  "summary": "DRY_RUN enabled: no remediation executed.",
  "fixed_items": [],
  "remaining_items": [],
  "commands_run": [],
  "artifacts": [],
  "risks": ["DRY_RUN mode"],
  "next_actions": ["Run without DRY_RUN to execute remediation."]
}
EOF_FIX
  else
    local cmd=()
    if [[ "$PHASE_C_FIX_MODE" == "resume" && "$iteration" -gt 1 ]]; then
      cmd=(codex exec resume --last --skip-git-repo-check -C "." -o "$PHASE_C_FIX_REPORT_PATH")
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
      info "Running Phase C remediation iteration ${iteration} via Codex (resume mode)"
    else
      cmd=(codex -a "$CODEX_APPROVAL" exec --skip-git-repo-check -C "." -o "$PHASE_C_FIX_REPORT_PATH" --output-schema "$FIX_SCHEMA_PATH")
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
      info "Running Phase C remediation iteration ${iteration} via Codex (fresh mode)"
    fi

    if ! run_with_timeout "$CODEX_TIMEOUT_SEC" "${cmd[@]}" < "$PHASE_C_PROMPT" > >(tee "$PHASE_C_STDOUT_LOG") 2> >(tee "$PHASE_C_STDERR_LOG" >&2); then
      die "Phase C remediation failed at iteration ${iteration}. See $PHASE_C_STDERR_LOG"
    fi
  fi

  validate_fix_report "$PHASE_C_FIX_REPORT_PATH"
  copy_phase_c_artifacts_to_tracked
  auto_commit_step "phase-c remediation iteration ${iteration}"

  PHASE_C_ITERATIONS_RUN=$((PHASE_C_ITERATIONS_RUN + 1))

  local after_head
  after_head="$(git rev-parse HEAD)"
  if [[ "$PHASE_C_STOP_ON_NO_CHANGE" == "1" && "$after_head" == "$before_head" ]]; then
    info "Phase C iteration ${iteration}: no committed change detected."
    return 10
  fi

  return 0
}

run_phase_a() {
  [[ "$PHASE_A_ENABLED" == "1" ]] || {
    info "Skipping Phase A (PHASE_A_ENABLED=0)."
    return 0
  }

  run_codex_audit
  run_claude_audit
  copy_phase_a_artifacts_to_tracked
  auto_commit_step "phase-a dual-audit reports"
}

run_phase_b() {
  [[ "$PHASE_B_ENABLED" == "1" ]] || {
    info "Skipping Phase B (PHASE_B_ENABLED=0)."
    TRIAGE_GATE_STATUS="pass"
    TRIAGE_GATE_REASON="phase_b_disabled"
    return 0
  }

  build_phase_b_triage
  copy_phase_b_artifacts_to_tracked
  auto_commit_step "phase-b triage"
}

write_summary() {
  cat > "$SUMMARY_PATH" <<EOF_SUM
# Update Cycle Audit Summary

- Run tag: ${RUN_TAG}
- Run stamp (UTC): ${RUN_STAMP}
- Snapshot dir: ${SNAPSHOT_DIR}
- Evidence dir: ${EVIDENCE_DIR}
- Gate status: ${TRIAGE_GATE_STATUS}
- Gate reason: ${TRIAGE_GATE_REASON}
- Codex audit verdict: ${CODEX_AUDIT_VERDICT}
- Claude audit verdict: ${CLAUDE_AUDIT_VERDICT}
- Phase C iterations run: ${PHASE_C_ITERATIONS_RUN}
- Phase C fix mode: ${PHASE_C_FIX_MODE}

## Artifacts

- Codex Phase A report: ${CODEX_REPORT_PATH}
- Claude Phase A report: ${CLAUDE_REPORT_PATH}
- Phase B triage JSON: ${TRIAGE_JSON_PATH}
- Phase B triage MD: ${TRIAGE_MD_PATH}
- Phase C fix report: ${PHASE_C_FIX_REPORT_PATH}
- Raw logs root (gitignored): ${LOG_ROOT}

## Tracked reproducibility artifacts

- ${TRACKED_CODEX_AUDIT_LATEST}
- ${TRACKED_CLAUDE_AUDIT_LATEST}
- ${TRACKED_TRIAGE_JSON_LATEST}
- ${TRACKED_TRIAGE_MD_LATEST}
- ${TRACKED_PHASE_C_FIX_LATEST}
EOF_SUM

  cp "$SUMMARY_PATH" "$TRACKED_SUMMARY"
  cp "$SUMMARY_PATH" "$TRACKED_SUMMARY_LATEST"
}

preflight() {
  need_cmd git
  need_cmd python
  need_cmd shasum

  assert_binary_flag "$DRY_RUN" "DRY_RUN"
  assert_binary_flag "$AUTO_COMMIT" "AUTO_COMMIT"
  assert_binary_flag "$ENFORCE_CLEAN_WORKTREE" "ENFORCE_CLEAN_WORKTREE"
  assert_binary_flag "$PHASE_A_ENABLED" "PHASE_A_ENABLED"
  assert_binary_flag "$PHASE_B_ENABLED" "PHASE_B_ENABLED"
  assert_binary_flag "$PHASE_C_ENABLED" "PHASE_C_ENABLED"
  assert_binary_flag "$PHASE_C_STOP_ON_NO_CHANGE" "PHASE_C_STOP_ON_NO_CHANGE"
  assert_binary_flag "$CLAUDE_DANGEROUS_SKIP_PERMISSIONS" "CLAUDE_DANGEROUS_SKIP_PERMISSIONS"
  assert_binary_flag "$CODEX_NETWORK_ACCESS" "CODEX_NETWORK_ACCESS"

  [[ "$PHASE_C_MAX_ITERATIONS" =~ ^[0-9]+$ ]] || die "PHASE_C_MAX_ITERATIONS must be numeric"
  [[ "$GATE_FAILURE_EXIT_CODE" =~ ^[0-9]+$ ]] || die "GATE_FAILURE_EXIT_CODE must be numeric"
  [[ "$PHASE_C_FIX_MODE" == "fresh" || "$PHASE_C_FIX_MODE" == "resume" ]] || die "PHASE_C_FIX_MODE must be fresh or resume"
  assert_codex_reasoning_effort
  assert_claude_effort

  [[ -f "$PLAYBOOK_PATH" ]] || die "Missing playbook: $PLAYBOOK_PATH"
  [[ -f "$AUDIT_TEMPLATE_PATH" ]] || die "Missing audit prompt template: $AUDIT_TEMPLATE_PATH"
  if [[ ! -f "$EXEC_TEMPLATE_PATH" ]]; then
    if [[ -f "$FALLBACK_EXEC_TEMPLATE_PATH" ]]; then
      info "Execution prompt template not found at '$EXEC_TEMPLATE_PATH'; using fallback '$FALLBACK_EXEC_TEMPLATE_PATH'"
      EXEC_TEMPLATE_PATH="$FALLBACK_EXEC_TEMPLATE_PATH"
    else
      die "Missing execution prompt template at '$EXEC_TEMPLATE_PATH' and fallback '$FALLBACK_EXEC_TEMPLATE_PATH'"
    fi
  fi
  [[ -f "$AUDIT_SCHEMA_PATH" ]] || die "Missing audit schema: $AUDIT_SCHEMA_PATH"
  [[ -f "$FIX_SCHEMA_PATH" ]] || die "Missing fix schema: $FIX_SCHEMA_PATH"

  mkdir -p "$PROMPT_DIR" "$REPORT_DIR" "$TRACE_DIR" "$TRACKED_RUN_DIR"

  ensure_git_identity
  ensure_clean_worktree

  if [[ "$DRY_RUN" == "1" ]]; then
    AUTO_COMMIT=0
    PHASE_C_ENABLED=0
    info "DRY_RUN enabled: disabling AUTO_COMMIT and PHASE_C remediation loop."
  else
    need_cmd codex
    need_cmd claude
    codex login status >/dev/null 2>&1 || die "Codex auth required (run: codex login)"
    claude auth status --json >/dev/null 2>&1 || die "Claude auth required (run: claude auth login)"
  fi

  info "Audit run context"
  info "RUN_TAG=${RUN_TAG}"
  info "SNAPSHOT_DIR=${SNAPSHOT_DIR}"
  info "EVIDENCE_DIR=${EVIDENCE_DIR}"
  info "TRACKED_RUN_DIR=${TRACKED_RUN_DIR}"
  info "LOG_ROOT=${LOG_ROOT}"
  info "CODEX_MODEL=${CODEX_MODEL} CODEX_REASONING_EFFORT=${CODEX_REASONING_EFFORT} CODEX_SANDBOX=${CODEX_SANDBOX} CODEX_NETWORK_ACCESS=${CODEX_NETWORK_ACCESS}"
  info "CLAUDE_MODEL=${CLAUDE_MODEL} CLAUDE_EFFORT=${CLAUDE_EFFORT} CLAUDE_PERMISSION_MODE=${CLAUDE_PERMISSION_MODE}"
  info "PHASE_C_ENABLED=${PHASE_C_ENABLED} PHASE_C_MAX_ITERATIONS=${PHASE_C_MAX_ITERATIONS} PHASE_C_FIX_MODE=${PHASE_C_FIX_MODE}"
}

export PLAYBOOK_PATH EXEC_TEMPLATE_PATH AUDIT_TEMPLATE_PATH
export RUN_TAG RUN_STAMP SNAPSHOT_DIR EVIDENCE_DIR TABLES_DIR CHARTS_DIR TRACKED_RUN_DIR
export TRIAGE_JSON_PATH TRIAGE_MD_PATH

preflight

run_phase_a
run_phase_b

if [[ "$TRIAGE_GATE_STATUS" != "pass" && "$PHASE_C_ENABLED" == "1" ]]; then
  info "Both-audit pass gate failed (${TRIAGE_GATE_REASON}). Starting Phase C remediation loop."

  for ((iter = 1; iter <= PHASE_C_MAX_ITERATIONS; iter++)); do
    local_rc=0
    run_phase_c_fix_iteration "$iter" || local_rc=$?

    if [[ "$local_rc" -eq 10 ]]; then
      info "Stopping Phase C loop early: no change detected in iteration ${iter}."
      break
    fi
    if [[ "$local_rc" -ne 0 ]]; then
      die "Phase C iteration ${iter} failed with rc=${local_rc}"
    fi

    run_phase_a
    run_phase_b

    if [[ "$TRIAGE_GATE_STATUS" == "pass" ]]; then
      info "Both audits passed after Phase C iteration ${iter}."
      break
    fi
  done
fi

write_summary
auto_commit_step "audit summary"

if [[ "$TRIAGE_GATE_STATUS" != "pass" ]]; then
  echo "Gate failed: ${TRIAGE_GATE_REASON}" >&2
  exit "$GATE_FAILURE_EXIT_CODE"
fi

info "Audit/review/fix chain completed successfully for RUN_TAG=${RUN_TAG}."
