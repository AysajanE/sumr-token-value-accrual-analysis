"""
Project-wide constants: chain config, known addresses, fee parameters.

Load secrets from .env; everything else is hardcoded from on-chain / docs.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ── Paths ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RESULTS_DIR = PROJECT_ROOT / "results"

load_dotenv(PROJECT_ROOT / ".env")

# ── RPC / API ────────────────────────────────────────────────────────────────
BASE_RPC_URL = os.getenv("BASE_RPC_URL", "")
BASESCAN_API_KEY = os.getenv("BASESCAN_API_KEY", "")
DEFILLAMA_BASE_URL = os.getenv("DEFILLAMA_BASE_URL", "https://api.llama.fi")

# ── Chain ─────────────────────────────────────────────────────────────────────
BASE_CHAIN_ID = 8453

# ── Known Addresses (Base) ────────────────────────────────────────────────────
SUMR_TOKEN = "0x194f360d130f2393a5e9f3117a6a1b78abea1624"
ST_SUMR = "0x7cc488f2681cfc2a5e8a00184bfa94ea6d520d1c"

# ── Fee Parameters (from docs — treat as hypotheses, verify on-chain) ────────
STABLECOIN_VAULT_FEE_BPS = 100   # 1.00%
ETH_VAULT_FEE_BPS = 30           # 0.30%
CLAIMED_AVG_FEE_BPS = 66         # 0.66% (article claim)

# ── Tip Split (from DeFiLlama methodology — verify on-chain) ─────────────────
STAKER_SHARE = 0.20   # 20% of tips → stakers
TREASURY_SHARE = 0.10  # 10% of tips → DAO treasury
DEPOSITOR_SHARE = 0.70  # 70% of tips → vault depositors

# ── Token Supply ──────────────────────────────────────────────────────────────
MAX_SUPPLY = 1_000_000_000       # 1B tokens
MAX_SUPPLY_RAW = 10**27          # 1B * 10^18 decimals
TOKEN_DECIMALS = 18

# ── DeFiLlama Slugs ──────────────────────────────────────────────────────────
LAZY_SUMMER_SLUG = "lazy-summer-protocol"
SUMMERFI_SLUG = "summer.fi"
