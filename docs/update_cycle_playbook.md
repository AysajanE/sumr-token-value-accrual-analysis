# SUMR Update Cycle Playbook

Last updated: 2026-03-04 (UTC)

Purpose: provide a repeatable, integrity-first process to refresh this repo with latest on-chain/off-chain data and regenerate all analysis outputs.

This playbook is designed for:
- the next update round, and
- all future rounds, with explicit controls for reproducibility and evidence integrity.

---

## 1) Non-Negotiable Integrity Rules

1. Never mix old and new snapshots in a single round without explicit disclosure.
2. Never hand-edit generated artifacts (`results/proofs`, `results/tables`, `results/charts`, `paper/*` outputs).
3. Preserve source-class separation in conclusions:
- `ONCHAIN_EXECUTED`
- `GOVERNANCE_FORUM`
- `API_DERIVED`
4. Store or preserve block numbers and UTC timestamps for every dynamic snapshot.
5. If a required source cannot be refreshed, mark the round `PARTIAL_REFRESH` and state exact gaps.
6. If strict gate is blocked, do not present strict-validated scenario outputs as validated.
7. Keep assumption pin provenance explicit (`scenario_assumptions_latest.json` must remain pinned or explicitly partial).
8. All commands run from repo root and paths are quoted.
9. For this repo path containing `$`, always single-quote full shell paths when needed.
10. No publication without passing the QA gates (Section 7) and completion checklist (Section 10).

---

## 2) Update Modes

Use one of two modes per round.

### A) Full Refresh (default and recommended)
- Refresh all dynamic on-chain/off-chain inputs.
- Rebuild all evidence/workflow/scenario/report outputs.
- Append monitoring row and freeze baseline.

### B) Monitoring Refresh (limited)
- Refresh claim logs + NAV + DeFiLlama + evidence + v2 + monitoring only.
- Use only for interim checks.
- Must not be used for “full latest report” claims.

---

## 3) Round Artifacts and Naming

Use date-tagged directories for snapshot/evidence round isolation.

```bash
export RUN_DATE="$(date -u +%F)"                 # e.g. 2026-03-04
export RUN_TAG="${RUN_DATE}-independent"         # naming convention used in repo
export SNAPSHOT_DIR="data/snapshots/external_review/${RUN_TAG}"
export EVIDENCE_DIR="results/proofs/evidence_${RUN_TAG}"
export TABLES_DIR="results/tables"
export CHARTS_DIR="results/charts"
```

If this is not the first round, use prior round as static seed:

```bash
export PREV_SNAPSHOT_DIR="data/snapshots/external_review/2026-02-09-independent"  # replace with latest prior
mkdir -p "$SNAPSHOT_DIR"
```

---

## 4) Prerequisites

1. Environment:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

2. Required `.env` values:
- `BASE_RPC_URL`
- `BASESCAN_API_KEY` (if ABI/source refresh needed via BaseScan paths)

3. Network/RPC health check:

```bash
python - <<'PY'
from web3 import Web3
from dotenv import load_dotenv
import os
load_dotenv(".env")
rpc = os.getenv("BASE_RPC_URL")
w3 = Web3(Web3.HTTPProvider(rpc))
print("RPC:", rpc)
print("connected:", w3.is_connected())
if w3.is_connected():
    print("latest_block:", w3.eth.block_number)
PY
```

---

## 5) Source Inventory for Full Refresh

### 5.1 Must-refresh every full round

1. DeFiLlama core (saved into `SNAPSHOT_DIR` with exact filenames expected by `evidence.py`):
- `defillama_protocol_lazy_summer.json`
- `defillama_protocol_summer_fi.json`
- `defillama_fees_dailyFees_lazy_summer.json`
- `defillama_fees_dailyRevenue_lazy_summer.json` (recommended; not strictly required by current evidence core)

2. Blockscout dynamic pages:
- `base_blockscout_treasury_token_transfers_all.json`
- `eth_blockscout_treasury_token_transfers_all.json`
- `base_blockscout_foundation_tipstream_token_transfers_all.json`
- `base_blockscout_tipjar_txs_all.json`
- `arb_blockscout_tipjar_txs_all.json`
- `eth_blockscout_tipjar_txs_all.json`
- `base_blockscout_grm_rewardAdded_all.json`

3. On-chain claim/NAV refresh:
- `base_rpc_distributor_claimed_{usdc|lvusdc|abasusdc}_...json`
- `base_rpc_receipt_<tx_hash>.json` for configured SIP txs
- `base_rpc_lvusdc_convertToAssets_...json`
- `manifest_claim_refresh_latest.json`

4. Supply snapshot input required for full downstream reporting:
- `base_rpc_supply_and_receipts.json`

### 5.2 Refresh when changed / new governance cycle appears

1. Forum payloads:
- `summer_forum_sip3_13.json`
- `summer_forum_sip3_13_1.json`
- Add newer SIP forum JSONs when extending campaign coverage.

2. Governance execution tx payloads:
- `tx_<hash>.json` for each tracked campaign / sample proof tx.

3. Contract source snapshots:
- `base_blockscout_stsumr_contract.json`
- `base_blockscout_summerstaking_contract.json`

4. Campaign constants in code:
- `src/indexing/claims_refresh.py` (`SIP_TXS`)
- `src/analysis/evidence.py` (`SIP313_TX`, `SIP3131_TX`, related campaign handling)

If new payout campaigns are not added to code and snapshots, coverage must be disclosed as bounded/partial.

---

## 6) Full Refresh Procedure (Step-by-Step)

## Step 0: Create run directories and round log

```bash
mkdir -p "$SNAPSHOT_DIR" "$EVIDENCE_DIR" "$TABLES_DIR" "$CHARTS_DIR"
```

Optional: seed static files from prior snapshot to avoid missing static context.

```bash
rsync -a "$PREV_SNAPSHOT_DIR"/ "$SNAPSHOT_DIR"/
```

Then overwrite all dynamic files in subsequent steps.

## Step 1: Refresh DeFiLlama files expected by evidence

```bash
python - <<'PY'
import json, os, requests, pathlib
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
for file, url in targets.items():
    r = requests.get(url, timeout=90)
    r.raise_for_status()
    (snap / file).write_text(json.dumps(r.json(), indent=2), encoding="utf-8")
    print("wrote", snap / file)
PY
```

Also refresh timestamped notebook lane:

```bash
make snapshot
```

## Step 2: Refresh Blockscout snapshots (with pagination where required)

Use paginated fetch for endpoints returning `items` + `next_page_params`.

```bash
python - <<'PY'
import json, os, time, requests, pathlib
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

for file, url, mode in targets:
    payload = fetch_paginated(url) if mode == "paginated" else fetch_single(url)
    path = snap / file
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("wrote", path)
PY
```

## Step 3: Refresh forum and tx snapshots used by evidence

```bash
python - <<'PY'
import json, os, requests, pathlib
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
for file, url in targets.items():
    r = requests.get(url, timeout=90)
    r.raise_for_status()
    (snap / file).write_text(json.dumps(r.json(), indent=2), encoding="utf-8")
    print("wrote", snap / file)
PY
```

If new SIP payout cycles exist, add forum topic JSON and tx JSON here and extend code constants before analysis.

## Step 4: Refresh supply snapshot input (`base_rpc_supply_and_receipts.json`)

This file is required for supply-dependent evidence/report outputs.

```bash
python - <<'PY'
import json, os, requests, datetime, pathlib
from dotenv import load_dotenv
load_dotenv(".env")
rpc = os.getenv("BASE_RPC_URL")
if not rpc:
    raise SystemExit("BASE_RPC_URL missing")

snap_dir = os.getenv("SNAPSHOT_DIR")
if not snap_dir:
    raise SystemExit("SNAPSHOT_DIR is not set")
snap = pathlib.Path(snap_dir)
snap.mkdir(parents=True, exist_ok=True)

SUMR = "0x194f360d130f2393a5e9f3117a6a1b78abea1624"
decimals_sig = "0x313ce567"      # decimals()
total_sig = "0x18160ddd"         # totalSupply()
cap_sig = "0x355274ea"           # cap()

def rpc_call(method, params):
    payload = {"jsonrpc":"2.0","id":1,"method":method,"params":params}
    r = requests.post(rpc, json=payload, timeout=90)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError(data["error"])
    return data["result"]

latest_block = int(rpc_call("eth_blockNumber", []), 16)
def eth_call(data):
    return int(rpc_call("eth_call", [{"to": SUMR, "data": data}, hex(latest_block)]), 16)

payload = {
    "retrieved_utc": datetime.datetime.utcnow().isoformat() + "Z",
    "latest_block": latest_block,
    "sumr": {
        "address": SUMR,
        "decimals": eth_call(decimals_sig),
        "totalSupply_raw": str(eth_call(total_sig)),
        "cap_raw": str(eth_call(cap_sig)),
    },
}

out = snap / "base_rpc_supply_and_receipts.json"
out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
print("wrote", out)
PY
```

## Step 4b: Regenerate snapshot manifest (`manifest.json`)

This keeps `as_of_utc` and checksum metadata current for evidence provenance.

```bash
python - <<'PY'
import os, json, hashlib, datetime
from pathlib import Path

snap_dir = os.getenv("SNAPSHOT_DIR")
if not snap_dir:
    raise SystemExit("SNAPSHOT_DIR is not set")
snap = Path(snap_dir)

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
for file, url in sorted(sources.items()):
    path = snap / file
    if not path.exists():
        continue
    data = path.read_bytes()
    entries.append({
        "file": file,
        "source_url": url,
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    })

manifest = {
    "as_of_utc": datetime.datetime.utcnow().isoformat() + "Z",
    "notes": [
        "Generated by update_cycle_playbook Step 4b.",
        "Includes static+dynamic round snapshot metadata and checksums.",
    ],
    "sources": entries,
}
(snap / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print("wrote", snap / "manifest.json", "entries:", len(entries))
PY
```

## Step 5: Refresh claims and LVUSDC NAV (automated scripts)

```bash
make refresh_claims \
  REFRESH_SNAPSHOT_DIR="$SNAPSHOT_DIR" \
  REFRESH_FROM_BLOCK=41932733

make refresh_lvusdc_nav \
  REFRESH_SNAPSHOT_DIR="$SNAPSHOT_DIR" \
  REFRESH_FROM_BLOCK=41932733
```

## Step 6: Build deterministic evidence and v2 workflow

```bash
make evidence \
  EVIDENCE_SNAPSHOT_DIR="$SNAPSHOT_DIR" \
  EVIDENCE_OUTPUT_DIR="$EVIDENCE_DIR"

make v2_workflow \
  V2_EVIDENCE_DIR="$EVIDENCE_DIR" \
  V2_TABLES_DIR="$TABLES_DIR" \
  V2_CHARTS_DIR="$CHARTS_DIR"
```

## Step 7: Build scenario artifacts with explicit pin provenance

Ensure pin file exists in the round snapshot:
- `"$SNAPSHOT_DIR/scenario_assumptions_pin.json"`

Then run:

```bash
python -m src.analysis.scenarios \
  --kpi-path "$EVIDENCE_DIR/kpi_summary.json" \
  --supply-snapshot-path "$SNAPSHOT_DIR/base_rpc_supply_and_receipts.json" \
  --assumptions-pin-path "$SNAPSHOT_DIR/scenario_assumptions_pin.json" \
  --output-dir "$TABLES_DIR"
```

## Step 8: Freeze baseline and append monitoring snapshot

```bash
make freeze_baseline

python -m src.analysis.monitor_cycle \
  --snapshot-dir "$SNAPSHOT_DIR" \
  --evidence-dir "$EVIDENCE_DIR" \
  --tables-dir "$TABLES_DIR"
```

## Step 9: Regenerate reports and investor outputs

```bash
make report
```

Optional PDF:

```bash
make investor_pdf
```

---

## 7) Quality Gates (Must Pass Before Publishing)

Run all checks after Step 9.

## Gate A: Freshness and path consistency

```bash
python - <<'PY'
import json
from pathlib import Path
m = json.loads(Path("results/tables/monitoring_latest.json").read_text())
print("snapshot_dir:", m["snapshot_dir"])
print("evidence_dir:", m["evidence_dir"])
print("observed_utc:", m["latest"]["observed_utc"])
PY
```

Expected:
- `snapshot_dir` ends with current `RUN_TAG`
- `evidence_dir` ends with current `RUN_TAG`

## Gate B: Scenario assumptions pinned

```bash
python - <<'PY'
import json
from pathlib import Path
s = json.loads(Path("results/tables/scenario_assumptions_latest.json").read_text())
print("status:", s.get("status"))
print("token_price_pinned:", s["assumptions"]["token_price_usd"]["pinned"])
print("supply_pinned:", s["assumptions"]["circulating_supply_tokens"]["pinned"])
PY
```

Expected:
- status `READY_PINNED` preferred (or explicit documented exception).

## Gate C: Evidence core files exist

```bash
python - <<'PY'
from pathlib import Path
import json
m = json.loads(Path("results/tables/monitoring_latest.json").read_text())
e = Path(m["evidence_dir"])
required = [
  "kpi_summary.json",
  "payout_attribution_summary.json",
  "staker_revenue_canonical_summary.json",
  "source_of_funds_summary.json",
  "emissions_vs_revenue_decomposition.json",
  "discrepancy_tickets.json",
]
missing = [f for f in required if not (e / f).exists()]
print("missing:", missing)
if missing:
    raise SystemExit(1)
PY
```

## Gate D: Report sync integrity

```bash
python - <<'PY'
from pathlib import Path
t = Path("paper/report.md").read_text(encoding="utf-8")
assert "<!-- BEGIN AUTO_FACTS -->" in t
assert "<!-- END AUTO_FACTS -->" in t
print("report markers: OK")
PY
```

## Gate E: Ticket severity visibility

```bash
python - <<'PY'
import json
from pathlib import Path
m = json.loads(Path("results/tables/monitoring_latest.json").read_text())
e = Path(m["evidence_dir"])
t = json.loads((e / "discrepancy_tickets.json").read_text())
print("ticket_summary:", t.get("summary"))
print("open_high_ticket_count:", m["latest"].get("open_high_ticket_count"))
PY
```

Expected:
- High-severity open tickets should be zero for publication; otherwise publish with explicit risk callout.

---

## 8) Publication and Version Control Checklist

1. Ensure `git status` only includes intended files.
2. Validate docs/report as-of timestamps align to monitoring/evidence.
3. Commit using one round-scoped message, e.g.:
- `data: refresh <RUN_TAG> snapshots and rebuild evidence/workflow/reports`
4. Tag round in commit body with:
- refresh block range
- evidence dir
- monitoring observed UTC
- strict gate status
- top open tickets

---

## 9) Known Structural Limits (Must Be Disclosed)

1. Campaign attribution confidence remains bounded/partial when claim events omit campaign IDs.
2. Current campaign logic is still keyed to tracked SIP tx constants; new campaigns require code/config updates.
3. Some support artifacts in investor memo are optional and may come from legacy generators not in active `make report`.
4. `make index` / `src.indexing.events` and `make reconcile` are not currently full artifact-producing production lanes.

---

## 10) Round Completion Checklist (Copy/Paste Template)

Use this checklist in PR description or round log.

- [ ] Created `RUN_TAG` snapshot/evidence directories.
- [ ] Refreshed DeFiLlama core files into `SNAPSHOT_DIR`.
- [ ] Refreshed Blockscout dynamic snapshots with pagination.
- [ ] Refreshed forum + tx snapshots for all tracked campaigns.
- [ ] Refreshed `base_rpc_supply_and_receipts.json`.
- [ ] Ran `refresh_claims` and `refresh_lvusdc_nav`.
- [ ] Rebuilt evidence and v2 workflow.
- [ ] Rebuilt scenario assumptions/matrix with pinned provenance.
- [ ] Ran baseline freeze and monitoring snapshot append.
- [ ] Rebuilt reports (`make report`).
- [ ] Passed gates A-E.
- [ ] Captured residual risks and open tickets in release notes.

---

## 11) Recommended Future Hardening (Backlog)

1. Add a single `src/indexing/external_review_refresh.py` collector to remove ad hoc snippets.
2. Move campaign tx/topic registry out of code constants into versioned config.
3. Add pytest smoke tests for:
- required artifact existence
- schema keys
- monitoring/report consistency checks.
4. Add one command target:
- `make full_refresh RUN_TAG=...`
5. Add machine-readable round manifest in `results/tables/update_round_manifest_latest.json`.
