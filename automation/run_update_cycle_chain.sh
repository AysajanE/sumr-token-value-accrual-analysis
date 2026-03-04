#!/usr/bin/env bash
set -euo pipefail

# ------------------------------------------------------------------------------
# SUMR update-cycle chain runner
#
# Part 1: execution
#   - automation/run_update_cycle_execution.sh
# Part 2: audit/review/fix (Phase A/B/C)
#   - automation/run_update_cycle_audit.sh
#
# Usage:
#   ./automation/run_update_cycle_chain.sh
#   RUN_TAG=2026-03-04-independent ./automation/run_update_cycle_chain.sh
#   RUN_EXECUTION=0 RUN_AUDIT=1 ./automation/run_update_cycle_chain.sh
# ------------------------------------------------------------------------------

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RUN_DATE="${RUN_DATE:-$(date -u +%F)}"
RUN_TAG="${RUN_TAG:-${RUN_DATE}-independent}"
RUN_EXECUTION="${RUN_EXECUTION:-1}"
RUN_AUDIT="${RUN_AUDIT:-1}"

EXEC_SCRIPT="${EXEC_SCRIPT:-./automation/run_update_cycle_execution.sh}"
AUDIT_SCRIPT="${AUDIT_SCRIPT:-./automation/run_update_cycle_audit.sh}"

info() { echo "==> $*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

assert_binary_flag() {
  local value="$1"
  local name="$2"
  [[ "$value" =~ ^(0|1)$ ]] || die "$name must be 0 or 1 (received '$value')"
}

assert_executable_file() {
  local path="$1"
  [[ -f "$path" ]] || die "Missing required file: $path"
  [[ -x "$path" ]] || die "Required file is not executable: $path"
}

assert_binary_flag "$RUN_EXECUTION" "RUN_EXECUTION"
assert_binary_flag "$RUN_AUDIT" "RUN_AUDIT"
assert_executable_file "$EXEC_SCRIPT"
assert_executable_file "$AUDIT_SCRIPT"

info "Starting update-cycle chain"
info "RUN_TAG=${RUN_TAG} RUN_EXECUTION=${RUN_EXECUTION} RUN_AUDIT=${RUN_AUDIT}"

if [[ "$RUN_EXECUTION" == "1" ]]; then
  info "Running execution part"
  RUN_TAG="$RUN_TAG" "$EXEC_SCRIPT"
fi

if [[ "$RUN_AUDIT" == "1" ]]; then
  info "Running audit/review/fix part"
  RUN_TAG="$RUN_TAG" "$AUDIT_SCRIPT"
fi

info "Update-cycle chain completed successfully for RUN_TAG=${RUN_TAG}."
