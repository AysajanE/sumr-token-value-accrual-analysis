# Data Directory

## Structure

```
data/
├── contracts/          # Contract registry + ABIs (version-controlled)
│   ├── registry.csv    # Canonical address list
│   └── abis/           # ABI JSON files (named by address)
├── snapshots/          # Point-in-time API responses (timestamped)
│   ├── defillama/      # DeFiLlama protocol + fees JSON
│   └── explorer/       # BaseScan contract metadata
├── indexed/            # Decoded on-chain events (.parquet) — GITIGNORED
│   ├── transfers/      # ERC-20 Transfer events (fee mints, staking in/out)
│   ├── tip_events/     # TipAccrued / fee distribution events
│   ├── staking_events/ # Locked, Withdrawn, EarlyExit, PenaltyPaid
│   └── reward_events/  # RewardAdded, RewardPaid, claim events
└── prices/             # Price feeds (.parquet) — GITIGNORED
```

## What's Tracked vs Gitignored

| Directory | Git-tracked? | Regenerate with |
|-----------|-------------|-----------------|
| `contracts/` | Yes | `make registry` |
| `snapshots/` | Metadata only | `make snapshot` |
| `indexed/` | No | `make index` |
| `prices/` | No | `make index` (fetched during processing) |

## File Formats

- **registry.csv**: chain, address, label, abi_source, abi_hash, discovered_by, first_seen_block, notes
- **ABIs**: `{address}.json` — raw ABI array from BaseScan
- **Snapshots**: `{slug}_{kind}_{timestamp}.json` — raw API responses
- **Indexed events**: `.parquet` with columns: chain_id, block_number, block_time, tx_hash, log_index, event_name, decoded fields
- **Prices**: `.parquet` with columns: asset, chain, timestamp, price_usd, source
