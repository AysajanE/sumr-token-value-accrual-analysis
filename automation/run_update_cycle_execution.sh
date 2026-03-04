#!/usr/bin/env bash
set -euo pipefail

# ------------------------------------------------------------------------------
# SUMR update-cycle execution runner (integrity-first, non-enterprise mode)
#
# Purpose:
# - Run the update cycle methodically (playbook-aligned), with step-level logging.
# - Auto-commit after each completed step (optional, enabled by default).
# - Keep detailed raw logs in ai/logs (gitignored) and concise run artifacts in
#   results/proofs/update_runs/<RUN_TAG> (tracked for reproducibility).
#
# Usage examples:
#   ./automation/run_update_cycle_execution.sh
#   RUN_TAG=2026-03-04-independent ./automation/run_update_cycle_execution.sh
#   MODE=monitoring START_STEP=5 END_STEP=10 ./automation/run_update_cycle_execution.sh
#   DRY_RUN=1 AUTO_COMMIT=0 ./automation/run_update_cycle_execution.sh
#
# Key env vars:
#   MODE=full|monitoring          (default: full)
#   START_STEP=0                  (default: 0)
#   END_STEP=10                   (default: 10)
#   AUTO_COMMIT=1                 (default: 1)
#   DRY_RUN=0                     (default: 0)
#   ENFORCE_CLEAN_WORKTREE=1      (default: 1)
#   RUN_IMPORTANT_GATES=1         (default: 1)
#
#   RUN_DATE=YYYY-MM-DD           (default: current UTC date)
#   RUN_STAMP=YYYYmmddTHHMMSSZ    (default: current UTC timestamp)
#   RUN_TAG=<RUN_DATE>-independent
#
#   SNAPSHOT_DIR=data/snapshots/external_review/<RUN_TAG>
#   EVIDENCE_DIR=results/proofs/evidence_<RUN_TAG>
#   TABLES_DIR=results/tables
#   CHARTS_DIR=results/charts
#   TRACKED_RUN_DIR=results/proofs/update_runs/<RUN_TAG>
#
#   PREV_SNAPSHOT_DIR=<path>
#   SEED_PREVIOUS_SNAPSHOT=1      (default: 1)
#
#   REFRESH_FROM_BLOCK=41932733
#   REFRESH_CHUNK_SIZE=10000
#   REFRESH_RPC_URL=<BASE rpc url>
#   BASE_RPC_URL=<BASE rpc url>
#
#   INCLUDE_INVESTOR_PDF=0
#   COMMIT_FORCE_ADD_SNAPSHOT=0   (set 1 only if you intentionally commit ignored snapshots)
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
CHECK_RPC_HEALTH="${CHECK_RPC_HEALTH:-1}"

SEED_PREVIOUS_SNAPSHOT="${SEED_PREVIOUS_SNAPSHOT:-1}"
PREV_SNAPSHOT_DIR="${PREV_SNAPSHOT_DIR:-}"

REFRESH_FROM_BLOCK="${REFRESH_FROM_BLOCK:-41932733}"
REFRESH_CHUNK_SIZE="${REFRESH_CHUNK_SIZE:-10000}"
REFRESH_RPC_URL="${REFRESH_RPC_URL:-${BASE_RPC_URL:-https://base.drpc.org}}"
BASE_RPC_URL_EFFECTIVE="${BASE_RPC_URL:-$REFRESH_RPC_URL}"

INCLUDE_INVESTOR_PDF="${INCLUDE_INVESTOR_PDF:-0}"
COMMIT_FORCE_ADD_SNAPSHOT="${COMMIT_FORCE_ADD_SNAPSHOT:-0}"

SNAPSHOT_DIR="${SNAPSHOT_DIR:-data/snapshots/external_review/${RUN_TAG}}"
EVIDENCE_DIR="${EVIDENCE_DIR:-results/proofs/evidence_${RUN_TAG}}"
TABLES_DIR="${TABLES_DIR:-results/tables}"
CHARTS_DIR="${CHARTS_DIR:-results/charts}"
TRACKED_RUN_DIR="${TRACKED_RUN_DIR:-results/proofs/update_runs/${RUN_TAG}}"

LOG_ROOT="${LOG_ROOT:-ai/logs/update_cycle/${RUN_TAG}/${RUN_STAMP}}"
STEP_LOG_DIR="$LOG_ROOT/execution"

STEP_TSV="$TRACKED_RUN_DIR/execution_steps_${RUN_STAMP}.tsv"
MANIFEST_JSON="$TRACKED_RUN_DIR/execution_manifest_${RUN_STAMP}.json"
MANIFEST_LATEST_JSON="$TRACKED_RUN_DIR/execution_manifest_latest.json"
SUMMARY_MD="$TRACKED_RUN_DIR/execution_summary_${RUN_STAMP}.md"
SUMMARY_LATEST_MD="$TRACKED_RUN_DIR/execution_summary_latest.md"
RUNTIME_CONTEXT_JSON="$TRACKED_RUN_DIR/runtime_context_${RUN_STAMP}.json"
RUNTIME_CONTEXT_LATEST_JSON="$TRACKED_RUN_DIR/runtime_context_latest.json"
GATE_JSON="$TRACKED_RUN_DIR/quality_gates_${RUN_STAMP}.json"
GATE_LATEST_JSON="$TRACKED_RUN_DIR/quality_gates_latest.json"

OVERALL_STATUS="RUNNING"
FAILED_STEP=""

info() { echo "==> $*"; }
die() { echo "ERROR: $*" >&2; exit 1; }
need_cmd() { command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"; }

assert_binary_flag() {
  local value="$1"
  local name="$2"
  [[ "$value" =~ ^(0|1)$ ]] || die "$name must be 0 or 1 (received '$value')"
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

record_step() {
  local step_id="$1"
  local step_name="$2"
  local status="$3"
  local started_utc="$4"
  local finished_utc="$5"
  local log_path="$6"
  local commit_ref="$7"

  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$step_id" "$step_name" "$status" "$started_utc" "$finished_utc" "$log_path" "$commit_ref" \
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

  git add -A -- . ':(exclude)ai/logs/**' ':(exclude)tmp/**'

  if [[ "$COMMIT_FORCE_ADD_SNAPSHOT" == "1" && -d "$SNAPSHOT_DIR" ]]; then
    git add -f "$SNAPSHOT_DIR" || true
  fi

  if git diff --cached --quiet --ignore-submodules --; then
    echo "no_changes"
    return 0
  fi

  local msg="data(update): ${RUN_TAG} step ${step_id} ${step_name} (${RUN_STAMP})"
  git commit -m "$msg" >/dev/null
  local sha
  sha="$(git rev-parse --short HEAD)"
  info "Auto-commit created: ${sha}"
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
    },
    "refresh": {
        "from_block": int(os.environ.get("REFRESH_FROM_BLOCK", "0")),
        "chunk_size": int(os.environ.get("REFRESH_CHUNK_SIZE", "0")),
        "rpc_url": os.environ.get("REFRESH_RPC_URL"),
        "base_rpc_url_effective": os.environ.get("BASE_RPC_URL_EFFECTIVE"),
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
            if len(row) != 7:
                continue
            rows.append({
                "step_id": row[0],
                "step_name": row[1],
                "status": row[2],
                "started_utc": row[3],
                "finished_utc": row[4],
                "log_path": row[5],
                "auto_commit": row[6],
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
    "paths": {
        "snapshot_dir": os.environ.get("SNAPSHOT_DIR"),
        "evidence_dir": os.environ.get("EVIDENCE_DIR"),
        "tables_dir": os.environ.get("TABLES_DIR"),
        "charts_dir": os.environ.get("CHARTS_DIR"),
        "tracked_run_dir": os.environ.get("TRACKED_RUN_DIR"),
        "log_root": os.environ.get("LOG_ROOT"),
    },
    "status": {
        "overall": overall_status,
        "failed_step": failed_step or None,
        "exit_code": int(exit_code),
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

run_step() {
  local step_id="$1"
  local step_name="$2"
  local step_fn="$3"

  if ! should_run_step "$step_id"; then
    info "Skipping step ${step_id} (${step_name}) due to MODE/START_STEP/END_STEP filters."
    return 0
  fi

  local safe_name
  safe_name="$(printf '%s' "$step_name" | tr ' ' '_' | tr -cd '[:alnum:]_-')"
  local log_path="$STEP_LOG_DIR/step${step_id}_${safe_name}.log"
  local started_utc
  started_utc="$(utc_now)"

  info "Running step ${step_id}: ${step_name}"

  local rc=0
  set +e
  "$step_fn" > >(tee "$log_path") 2> >(tee -a "$log_path" >&2)
  rc=$?
  set -e

  local finished_utc
  finished_utc="$(utc_now)"

  if [[ "$rc" -ne 0 ]]; then
    record_step "$step_id" "$step_name" "FAILED" "$started_utc" "$finished_utc" "$log_path" "none"
    FAILED_STEP="${step_id}:${step_name}"
    OVERALL_STATUS="FAILED"
    die "Step ${step_id} failed. See log: ${log_path}"
  fi

  local commit_ref
  commit_ref="$(commit_after_step "$step_id" "$step_name")"
  record_step "$step_id" "$step_name" "PASSED" "$started_utc" "$finished_utc" "$log_path" "$commit_ref"
}

step_0_setup() {
  mkdir -p "$SNAPSHOT_DIR" "$EVIDENCE_DIR" "$TABLES_DIR" "$CHARTS_DIR" "$TRACKED_RUN_DIR" "$STEP_LOG_DIR"

  if [[ "$SEED_PREVIOUS_SNAPSHOT" == "1" && -n "$PREV_SNAPSHOT_DIR" && -d "$PREV_SNAPSHOT_DIR" ]]; then
    if [[ "$DRY_RUN" == "1" ]]; then
      echo "DRY_RUN: would seed snapshot from '$PREV_SNAPSHOT_DIR' to '$SNAPSHOT_DIR'."
    else
      info "Seeding snapshot directory from previous round: $PREV_SNAPSHOT_DIR"
      rsync -a "$PREV_SNAPSHOT_DIR"/ "$SNAPSHOT_DIR"/
    fi
  fi

  write_runtime_context

  if [[ "$DRY_RUN" == "1" ]]; then
    echo "DRY_RUN: skipping RPC health check."
    return 0
  fi

  if [[ "$CHECK_RPC_HEALTH" == "1" ]]; then
    python - <<'PY'
from web3 import Web3
import os

rpc = os.getenv("BASE_RPC_URL_EFFECTIVE")
if not rpc:
    raise SystemExit("BASE_RPC_URL_EFFECTIVE is not set")

w3 = Web3(Web3.HTTPProvider(rpc))
print("rpc_url:", rpc)
print("connected:", w3.is_connected())
if not w3.is_connected():
    raise SystemExit("RPC connectivity check failed")
print("latest_block:", w3.eth.block_number)
PY
  fi
}

step_1_refresh_defillama() {
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "DRY_RUN: would refresh DeFiLlama snapshot files and run make snapshot."
    return 0
  fi

  python - <<'PY'
import json
import os
import pathlib
import requests

snap_dir = os.getenv("SNAPSHOT_DIR")
if not snap_dir:
    raise SystemExit("SNAPSHOT_DIR is not set")

snap = pathlib.Path(snap_dir)
snap.mkdir(parents=True, exist_ok=True)

targets = {
    "defillama_protocol_lazy_summer.json": "https://api.llama.fi/protocol/lazy-summer-protocol",
    "defillama_protocol_summer_fi.json": "https://api.llama.fi/protocol/summer.fi",
    "defillama_fees_dailyFees_lazy_summer.json": "https://api.llama.fi/summary/fees/lazy-summer-protocol?dataType=dailyFees",
    "defillama_fees_dailyRevenue_lazy_summer.json": "https://api.llama.fi/summary/fees/lazy-summer-protocol?dataType=dailyRevenue",
}

for file_name, url in targets.items():
    r = requests.get(url, timeout=90)
    r.raise_for_status()
    path = snap / file_name
    path.write_text(json.dumps(r.json(), indent=2), encoding="utf-8")
    print("wrote", path)
PY

  make snapshot
}

step_2_refresh_blockscout() {
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "DRY_RUN: would refresh paginated Blockscout snapshots."
    return 0
  fi

  python - <<'PY'
import json
import os
import pathlib
import requests
import time

snap_dir = os.getenv("SNAPSHOT_DIR")
if not snap_dir:
    raise SystemExit("SNAPSHOT_DIR is not set")

snap = pathlib.Path(snap_dir)
snap.mkdir(parents=True, exist_ok=True)

def fetch_paginated(url: str):
    params = {}
    all_items = []
    while True:
        r = requests.get(url, params=params, timeout=90)
        r.raise_for_status()
        payload = r.json()
        items = payload.get("items") or []
        all_items.extend(items)
        nxt = payload.get("next_page_params")
        if not nxt:
            break
        params = nxt
        time.sleep(0.2)
    return {"items": all_items}

def fetch_single(url: str):
    r = requests.get(url, timeout=90)
    r.raise_for_status()
    return r.json()

targets = [
    ("base_blockscout_treasury_token_transfers_all.json", "https://base.blockscout.com/api/v2/addresses/0x447BF9d1485ABDc4C1778025DfdfbE8b894C3796/token-transfers", "paginated"),
    ("eth_blockscout_treasury_token_transfers_all.json", "https://eth.blockscout.com/api/v2/addresses/0x447BF9d1485ABDc4C1778025DfdfbE8b894C3796/token-transfers", "paginated"),
    ("base_blockscout_foundation_tipstream_token_transfers_all.json", "https://base.blockscout.com/api/v2/addresses/0xB0F53Fc4e15301147de9b3e49C3DB942E3F118F2/token-transfers", "paginated"),
    ("base_blockscout_tipjar_txs_all.json", "https://base.blockscout.com/api/v2/addresses/0xAd30bc7E40f13d88EDa608A5729d28151FcAA374/transactions", "paginated"),
    ("arb_blockscout_tipjar_txs_all.json", "https://arbitrum.blockscout.com/api/v2/addresses/0xBeB68a57dF8eD3CDAE8629C7c6E497eB1b6b1C47/transactions", "paginated"),
    ("eth_blockscout_tipjar_txs_all.json", "https://eth.blockscout.com/api/v2/addresses/0x2d1A2637c3E0c80f31A91d0b6dbC5a107988a401/transactions", "paginated"),
    ("base_blockscout_grm_rewardAdded_all.json", "https://base.blockscout.com/api/v2/addresses/0xDe61A0a49f48e108079bdE73caeA56E87FfeEF92/logs?topic=0xac24935fd910bc682b5ccb1a07b718cadf8cf2f6d1404c4f3ddc3662dae40e29", "paginated"),
    ("base_blockscout_stsumr_contract.json", "https://base.blockscout.com/api/v2/smart-contracts/0x7cc488f2681cfc2a5e8a00184bfa94ea6d520d1c", "single"),
    ("base_blockscout_summerstaking_contract.json", "https://base.blockscout.com/api/v2/smart-contracts/0xcA2e14c7C03C9961c296C89e2d2279F5F7DB15b4", "single"),
]

for file_name, url, mode in targets:
    payload = fetch_paginated(url) if mode == "paginated" else fetch_single(url)
    path = snap / file_name
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("wrote", path)
PY
}

step_3_refresh_forum_tx() {
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "DRY_RUN: would refresh forum and transaction snapshots."
    return 0
  fi

  python - <<'PY'
import json
import os
import pathlib
import requests

snap_dir = os.getenv("SNAPSHOT_DIR")
if not snap_dir:
    raise SystemExit("SNAPSHOT_DIR is not set")

snap = pathlib.Path(snap_dir)
snap.mkdir(parents=True, exist_ok=True)

targets = {
    "summer_forum_sip3_13.json": "https://forum.summer.fi/t/600.json",
    "summer_forum_sip3_13_1.json": "https://forum.summer.fi/t/698.json",
    "tx_0x5aa10ad32d3d6a3d15d614954dbbe960da2f4376301e28b39b063d485dc15941.json": "https://base.blockscout.com/api/v2/transactions/0x5aa10ad32d3d6a3d15d614954dbbe960da2f4376301e28b39b063d485dc15941",
    "tx_0x30643401cafbc331687f312b4fab670470553419ea3c2cef510f48e00c488e54.json": "https://base.blockscout.com/api/v2/transactions/0x30643401cafbc331687f312b4fab670470553419ea3c2cef510f48e00c488e54",
    "tx_0xd7cc4ae7ca3f8d3855c7c4d79f7c94745a95b96c0ac883078c1536d08d11616d.json": "https://base.blockscout.com/api/v2/transactions/0xd7cc4ae7ca3f8d3855c7c4d79f7c94745a95b96c0ac883078c1536d08d11616d",
}

for file_name, url in targets.items():
    r = requests.get(url, timeout=90)
    r.raise_for_status()
    path = snap / file_name
    path.write_text(json.dumps(r.json(), indent=2), encoding="utf-8")
    print("wrote", path)
PY
}

step_4_refresh_supply_and_manifest() {
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "DRY_RUN: would refresh supply snapshot and manifest metadata."
    return 0
  fi

  python - <<'PY'
import datetime
import hashlib
import json
import os
import pathlib
import requests

rpc = os.getenv("BASE_RPC_URL_EFFECTIVE")
if not rpc:
    raise SystemExit("BASE_RPC_URL_EFFECTIVE is not set")

snap_dir = os.getenv("SNAPSHOT_DIR")
if not snap_dir:
    raise SystemExit("SNAPSHOT_DIR is not set")

snap = pathlib.Path(snap_dir)
snap.mkdir(parents=True, exist_ok=True)

SUMR = "0x194f360d130f2393a5e9f3117a6a1b78abea1624"
decimals_sig = "0x313ce567"
total_sig = "0x18160ddd"
cap_sig = "0x355274ea"

def rpc_call(method, params):
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    r = requests.post(rpc, json=payload, timeout=90)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError(data["error"])
    return data["result"]

latest_block = int(rpc_call("eth_blockNumber", []), 16)

def eth_call(data):
    return int(rpc_call("eth_call", [{"to": SUMR, "data": data}, hex(latest_block)]), 16)

supply_payload = {
    "retrieved_utc": datetime.datetime.utcnow().isoformat() + "Z",
    "latest_block": latest_block,
    "sumr": {
        "address": SUMR,
        "decimals": eth_call(decimals_sig),
        "totalSupply_raw": str(eth_call(total_sig)),
        "cap_raw": str(eth_call(cap_sig)),
    },
}

supply_path = snap / "base_rpc_supply_and_receipts.json"
supply_path.write_text(json.dumps(supply_payload, indent=2), encoding="utf-8")
print("wrote", supply_path)

sources = {
    "defillama_protocol_lazy_summer.json": "https://api.llama.fi/protocol/lazy-summer-protocol",
    "defillama_protocol_summer_fi.json": "https://api.llama.fi/protocol/summer.fi",
    "defillama_fees_dailyFees_lazy_summer.json": "https://api.llama.fi/summary/fees/lazy-summer-protocol?dataType=dailyFees",
    "defillama_fees_dailyRevenue_lazy_summer.json": "https://api.llama.fi/summary/fees/lazy-summer-protocol?dataType=dailyRevenue",
    "base_blockscout_treasury_token_transfers_all.json": "https://base.blockscout.com/api/v2/addresses/0x447BF9d1485ABDc4C1778025DfdfbE8b894C3796/token-transfers",
    "eth_blockscout_treasury_token_transfers_all.json": "https://eth.blockscout.com/api/v2/addresses/0x447BF9d1485ABDc4C1778025DfdfbE8b894C3796/token-transfers",
    "base_blockscout_foundation_tipstream_token_transfers_all.json": "https://base.blockscout.com/api/v2/addresses/0xB0F53Fc4e15301147de9b3e49C3DB942E3F118F2/token-transfers",
    "base_blockscout_tipjar_txs_all.json": "https://base.blockscout.com/api/v2/addresses/0xAd30bc7E40f13d88EDa608A5729d28151FcAA374/transactions",
    "arb_blockscout_tipjar_txs_all.json": "https://arbitrum.blockscout.com/api/v2/addresses/0xBeB68a57dF8eD3CDAE8629C7c6E497eB1b6b1C47/transactions",
    "eth_blockscout_tipjar_txs_all.json": "https://eth.blockscout.com/api/v2/addresses/0x2d1A2637c3E0c80f31A91d0b6dbC5a107988a401/transactions",
    "base_blockscout_grm_rewardAdded_all.json": "https://base.blockscout.com/api/v2/addresses/0xDe61A0a49f48e108079bdE73caeA56E87FfeEF92/logs?topic=0xac24935fd910bc682b5ccb1a07b718cadf8cf2f6d1404c4f3ddc3662dae40e29",
    "base_blockscout_stsumr_contract.json": "https://base.blockscout.com/api/v2/smart-contracts/0x7cc488f2681cfc2a5e8a00184bfa94ea6d520d1c",
    "base_blockscout_summerstaking_contract.json": "https://base.blockscout.com/api/v2/smart-contracts/0xcA2e14c7C03C9961c296C89e2d2279F5F7DB15b4",
    "summer_forum_sip3_13.json": "https://forum.summer.fi/t/600.json",
    "summer_forum_sip3_13_1.json": "https://forum.summer.fi/t/698.json",
    "tx_0x5aa10ad32d3d6a3d15d614954dbbe960da2f4376301e28b39b063d485dc15941.json": "https://base.blockscout.com/api/v2/transactions/0x5aa10ad32d3d6a3d15d614954dbbe960da2f4376301e28b39b063d485dc15941",
    "tx_0x30643401cafbc331687f312b4fab670470553419ea3c2cef510f48e00c488e54.json": "https://base.blockscout.com/api/v2/transactions/0x30643401cafbc331687f312b4fab670470553419ea3c2cef510f48e00c488e54",
    "tx_0xd7cc4ae7ca3f8d3855c7c4d79f7c94745a95b96c0ac883078c1536d08d11616d.json": "https://base.blockscout.com/api/v2/transactions/0xd7cc4ae7ca3f8d3855c7c4d79f7c94745a95b96c0ac883078c1536d08d11616d",
    "base_rpc_supply_and_receipts.json": "BASE_RPC_URL",
}

entries = []
for file_name, url in sorted(sources.items()):
    path = snap / file_name
    if not path.exists():
        continue
    data = path.read_bytes()
    entries.append(
        {
            "file": file_name,
            "source_url": url,
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
        }
    )

manifest = {
    "as_of_utc": datetime.datetime.utcnow().isoformat() + "Z",
    "notes": [
        "Generated by automation/run_update_cycle_execution.sh (step 4).",
        "Includes static + dynamic snapshot checksum metadata.",
    ],
    "sources": entries,
}

manifest_path = snap / "manifest.json"
manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print("wrote", manifest_path, "entries:", len(entries))
PY
}

step_5_refresh_claims_nav() {
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "DRY_RUN: would run refresh_claims and refresh_lvusdc_nav."
    return 0
  fi

  make refresh_claims \
    REFRESH_SNAPSHOT_DIR="$SNAPSHOT_DIR" \
    REFRESH_FROM_BLOCK="$REFRESH_FROM_BLOCK" \
    REFRESH_CHUNK_SIZE="$REFRESH_CHUNK_SIZE" \
    REFRESH_RPC_URL="$REFRESH_RPC_URL"

  make refresh_lvusdc_nav \
    REFRESH_SNAPSHOT_DIR="$SNAPSHOT_DIR" \
    REFRESH_FROM_BLOCK="$REFRESH_FROM_BLOCK" \
    REFRESH_RPC_URL="$REFRESH_RPC_URL"
}

step_6_build_evidence_v2() {
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "DRY_RUN: would run evidence + v2_workflow."
    return 0
  fi

  make evidence \
    EVIDENCE_SNAPSHOT_DIR="$SNAPSHOT_DIR" \
    EVIDENCE_OUTPUT_DIR="$EVIDENCE_DIR"

  make v2_workflow \
    V2_EVIDENCE_DIR="$EVIDENCE_DIR" \
    V2_TABLES_DIR="$TABLES_DIR" \
    V2_CHARTS_DIR="$CHARTS_DIR"
}

step_7_build_scenarios() {
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "DRY_RUN: would run scenario generator with pinned assumptions."
    return 0
  fi

  local pin_path="$SNAPSHOT_DIR/scenario_assumptions_pin.json"
  if [[ ! -f "$pin_path" ]]; then
    if [[ -f "$TABLES_DIR/scenario_assumptions_latest.json" ]]; then
      cp "$TABLES_DIR/scenario_assumptions_latest.json" "$pin_path"
      info "seeded missing scenario pin from $TABLES_DIR/scenario_assumptions_latest.json"
    else
      die "Missing scenario assumptions pin: $pin_path"
    fi
  fi

  python -m src.analysis.scenarios \
    --kpi-path "$EVIDENCE_DIR/kpi_summary.json" \
    --supply-snapshot-path "$SNAPSHOT_DIR/base_rpc_supply_and_receipts.json" \
    --assumptions-pin-path "$pin_path" \
    --output-dir "$TABLES_DIR"
}

step_8_freeze_and_monitor() {
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "DRY_RUN: would run freeze_baseline and monitor_cycle."
    return 0
  fi

  make freeze_baseline

  python -m src.analysis.monitor_cycle \
    --snapshot-dir "$SNAPSHOT_DIR" \
    --evidence-dir "$EVIDENCE_DIR" \
    --tables-dir "$TABLES_DIR"
}

step_9_report_outputs() {
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "DRY_RUN: would run make report (and optional investor_pdf)."
    return 0
  fi

  make report

  if [[ "$INCLUDE_INVESTOR_PDF" == "1" ]]; then
    make investor_pdf
  fi
}

step_10_quality_gates() {
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "DRY_RUN: would run quality gates A-E."
    return 0
  fi

  python - "$RUN_TAG" "$TABLES_DIR" "$EVIDENCE_DIR" "$GATE_JSON" "$GATE_LATEST_JSON" <<'PY'
import json
from pathlib import Path
import sys
from datetime import datetime, timezone

run_tag, tables_dir, evidence_dir_default, out_path, latest_path = sys.argv[1:]
out_file = Path(out_path)
out_file.parent.mkdir(parents=True, exist_ok=True)

result = {
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "run_tag": run_tag,
    "gates": {},
    "overall_pass": True,
    "errors": [],
}

# Gate A
mon_path = Path(tables_dir) / "monitoring_latest.json"
if not mon_path.exists():
    result["gates"]["A_freshness_path_consistency"] = {
        "pass": False,
        "error": f"missing {mon_path}"
    }
    result["errors"].append("Gate A: monitoring_latest.json missing")
    monitoring = None
else:
    monitoring = json.loads(mon_path.read_text(encoding="utf-8"))
    snapshot_dir = str(monitoring.get("snapshot_dir", ""))
    evidence_dir = str(monitoring.get("evidence_dir", ""))
    observed_utc = monitoring.get("latest", {}).get("observed_utc")
    gate_a_pass = snapshot_dir.endswith(run_tag) and evidence_dir.endswith(run_tag)
    result["gates"]["A_freshness_path_consistency"] = {
        "pass": gate_a_pass,
        "snapshot_dir": snapshot_dir,
        "evidence_dir": evidence_dir,
        "observed_utc": observed_utc,
    }
    if not gate_a_pass:
        result["errors"].append("Gate A: monitoring paths do not end with current RUN_TAG")

# Gate B
assumptions_path = Path(tables_dir) / "scenario_assumptions_latest.json"
if not assumptions_path.exists():
    result["gates"]["B_assumptions_pinned"] = {
        "pass": False,
        "error": f"missing {assumptions_path}"
    }
    result["errors"].append("Gate B: scenario_assumptions_latest.json missing")
else:
    assumptions = json.loads(assumptions_path.read_text(encoding="utf-8"))
    status = assumptions.get("status")
    token_pinned = bool(
        assumptions.get("assumptions", {})
        .get("token_price_usd", {})
        .get("pinned")
    )
    supply_pinned = bool(
        assumptions.get("assumptions", {})
        .get("circulating_supply_tokens", {})
        .get("pinned")
    )
    gate_b_pass = token_pinned and supply_pinned and status in {"READY_PINNED", "READY"}
    result["gates"]["B_assumptions_pinned"] = {
        "pass": gate_b_pass,
        "status": status,
        "token_price_pinned": token_pinned,
        "supply_pinned": supply_pinned,
    }
    if not gate_b_pass:
        result["errors"].append("Gate B: scenario assumptions are not fully pinned")

# Gate C
evidence_dir = Path(evidence_dir_default)
if monitoring and monitoring.get("evidence_dir"):
    evidence_dir = Path(str(monitoring["evidence_dir"]))
required = [
    "kpi_summary.json",
    "payout_attribution_summary.json",
    "staker_revenue_canonical_summary.json",
    "source_of_funds_summary.json",
    "emissions_vs_revenue_decomposition.json",
    "discrepancy_tickets.json",
]
missing = [f for f in required if not (evidence_dir / f).exists()]
gate_c_pass = len(missing) == 0
result["gates"]["C_evidence_core_files"] = {
    "pass": gate_c_pass,
    "evidence_dir": str(evidence_dir),
    "missing": missing,
}
if not gate_c_pass:
    result["errors"].append("Gate C: missing evidence core files")

# Gate D
report_path = Path("paper/report.md")
if not report_path.exists():
    gate_d_pass = False
    result["gates"]["D_report_sync_markers"] = {
        "pass": False,
        "error": "missing paper/report.md"
    }
    result["errors"].append("Gate D: paper/report.md missing")
else:
    text = report_path.read_text(encoding="utf-8")
    gate_d_pass = "<!-- BEGIN AUTO_FACTS -->" in text and "<!-- END AUTO_FACTS -->" in text
    result["gates"]["D_report_sync_markers"] = {
        "pass": gate_d_pass,
        "path": str(report_path),
    }
    if not gate_d_pass:
        result["errors"].append("Gate D: report sync markers missing")

# Gate E
open_high_ticket_count = None
if monitoring:
    open_high_ticket_count = monitoring.get("latest", {}).get("open_high_ticket_count")
try:
    open_high_ticket_count = int(open_high_ticket_count or 0)
except Exception:
    open_high_ticket_count = -1
gate_e_pass = open_high_ticket_count == 0
result["gates"]["E_ticket_severity_visibility"] = {
    "pass": gate_e_pass,
    "open_high_ticket_count": open_high_ticket_count,
}
if not gate_e_pass:
    result["errors"].append("Gate E: open_high_ticket_count is non-zero")

result["overall_pass"] = all(g.get("pass", False) for g in result["gates"].values())
out_file.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
Path(latest_path).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

print(json.dumps({"overall_pass": result["overall_pass"], "errors": result["errors"]}, indent=2))
if not result["overall_pass"]:
    raise SystemExit(1)
PY
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
  need_cmd make
  need_cmd python
  need_cmd rsync

  assert_binary_flag "$AUTO_COMMIT" "AUTO_COMMIT"
  assert_binary_flag "$DRY_RUN" "DRY_RUN"
  assert_binary_flag "$ENFORCE_CLEAN_WORKTREE" "ENFORCE_CLEAN_WORKTREE"
  assert_binary_flag "$RUN_IMPORTANT_GATES" "RUN_IMPORTANT_GATES"
  assert_binary_flag "$CHECK_RPC_HEALTH" "CHECK_RPC_HEALTH"
  assert_binary_flag "$SEED_PREVIOUS_SNAPSHOT" "SEED_PREVIOUS_SNAPSHOT"
  assert_binary_flag "$INCLUDE_INVESTOR_PDF" "INCLUDE_INVESTOR_PDF"
  assert_binary_flag "$COMMIT_FORCE_ADD_SNAPSHOT" "COMMIT_FORCE_ADD_SNAPSHOT"

  [[ "$MODE" == "full" || "$MODE" == "monitoring" ]] || die "MODE must be full or monitoring"
  [[ "$START_STEP" =~ ^[0-9]+$ ]] || die "START_STEP must be numeric"
  [[ "$END_STEP" =~ ^[0-9]+$ ]] || die "END_STEP must be numeric"
  (( START_STEP <= END_STEP )) || die "START_STEP must be <= END_STEP"

  mkdir -p "$TRACKED_RUN_DIR" "$STEP_LOG_DIR"
  printf 'step_id\tstep_name\tstatus\tstarted_utc\tfinished_utc\tlog_path\tauto_commit\n' > "$STEP_TSV"

  ensure_git_identity
  ensure_clean_worktree

  if [[ "$DRY_RUN" != "1" ]]; then
    if should_run_step 4 && [[ -z "$BASE_RPC_URL_EFFECTIVE" ]]; then
      die "BASE_RPC_URL or REFRESH_RPC_URL must be set to run step 4"
    fi
  fi

  info "Execution run context"
  info "RUN_TAG=${RUN_TAG}"
  info "MODE=${MODE}"
  info "START_STEP=${START_STEP} END_STEP=${END_STEP}"
  info "SNAPSHOT_DIR=${SNAPSHOT_DIR}"
  info "EVIDENCE_DIR=${EVIDENCE_DIR}"
  info "TRACKED_RUN_DIR=${TRACKED_RUN_DIR}"
  info "LOG_ROOT=${LOG_ROOT}"
}

trap 'on_exit $?' EXIT

export RUN_DATE RUN_STAMP RUN_TAG MODE START_STEP END_STEP AUTO_COMMIT DRY_RUN
export SNAPSHOT_DIR EVIDENCE_DIR TABLES_DIR CHARTS_DIR TRACKED_RUN_DIR LOG_ROOT
export REFRESH_FROM_BLOCK REFRESH_CHUNK_SIZE REFRESH_RPC_URL BASE_RPC_URL_EFFECTIVE

preflight

run_step 0 "setup_context" step_0_setup
run_step 1 "refresh_defillama" step_1_refresh_defillama
run_step 2 "refresh_blockscout" step_2_refresh_blockscout
run_step 3 "refresh_forum_and_transactions" step_3_refresh_forum_tx
run_step 4 "refresh_supply_and_manifest" step_4_refresh_supply_and_manifest
run_step 5 "refresh_claims_and_nav" step_5_refresh_claims_nav
run_step 6 "build_evidence_and_v2" step_6_build_evidence_v2
run_step 7 "build_scenarios" step_7_build_scenarios
run_step 8 "freeze_and_monitor" step_8_freeze_and_monitor
run_step 9 "report_generation" step_9_report_outputs

if [[ "$RUN_IMPORTANT_GATES" == "1" ]]; then
  run_step 10 "quality_gates" step_10_quality_gates
else
  info "Skipping step 10 (quality gates) because RUN_IMPORTANT_GATES=0"
fi

OVERALL_STATUS="SUCCESS"
info "Update cycle execution completed successfully for RUN_TAG=${RUN_TAG}."
