"""Shared utilities for interactive due-diligence notebooks.

These helpers keep notebook code concise, consistent, and reproducible.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


def project_root() -> Path:
    """Return repository root by walking up from this file."""
    return Path(__file__).resolve().parents[1]


def setup_notebook_context() -> Path:
    """Ensure repo root is on sys.path and return it."""
    root = project_root()
    root_str = root.as_posix()
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    return root


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def latest_file(pattern: str, base_dir: Path | None = None) -> Path | None:
    """Return latest file matching a glob pattern by mtime."""
    root = base_dir or project_root()
    files = list(root.glob(pattern))
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def latest_evidence_dir() -> Path | None:
    """Pick latest evidence dir under results/proofs/evidence_*."""
    proofs_dir = project_root() / "results" / "proofs"
    dirs = [p for p in proofs_dir.glob("evidence_*") if p.is_dir()]
    if not dirs:
        return None
    return max(dirs, key=lambda p: p.stat().st_mtime)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


def run_make_targets(targets: list[str], cwd: Path | None = None) -> None:
    """Run make targets sequentially and stream output in notebook."""
    workdir = cwd or project_root()
    for target in targets:
        print(f"[make] {target}")
        subprocess.run(["make", target], cwd=workdir, check=True)


def refresh_defillama_snapshots() -> None:
    """Pull latest DeFiLlama snapshots via existing indexer module."""
    setup_notebook_context()
    from src.indexing.defillama import pull_all_snapshots

    pull_all_snapshots()


def latest_defillama_snapshot(slug: str, kind: str) -> Path | None:
    pattern = f"data/snapshots/defillama/{slug}_{kind}_*.json"
    return latest_file(pattern)


def protocol_tvl_df(protocol_payload: dict[str, Any]) -> pd.DataFrame:
    """Normalize protocol tvl payload to DataFrame."""
    tvl = pd.DataFrame(protocol_payload.get("tvl") or [])
    if tvl.empty:
        return tvl
    tvl["date"] = pd.to_datetime(tvl["date"], unit="s", utc=True)
    tvl["totalLiquidityUSD"] = pd.to_numeric(tvl["totalLiquidityUSD"], errors="coerce")
    tvl = tvl.dropna(subset=["totalLiquidityUSD"]).sort_values("date").reset_index(drop=True)
    return tvl


def fee_series_df(fees_payload: dict[str, Any]) -> pd.DataFrame:
    """Normalize defillama fee payload to DataFrame."""
    data = pd.DataFrame(fees_payload.get("totalDataChart") or [], columns=["date", "dailyFeesUSD"])
    if data.empty:
        return data
    data["date"] = pd.to_datetime(data["date"], unit="s", utc=True)
    data["dailyFeesUSD"] = pd.to_numeric(data["dailyFeesUSD"], errors="coerce")
    data = data.dropna(subset=["dailyFeesUSD"]).sort_values("date").reset_index(drop=True)
    return data


def rolling_annualized_fees(fees_df: pd.DataFrame, window_days: int = 30) -> pd.DataFrame:
    """Compute rolling annualized fee run-rate from daily fee series."""
    if fees_df.empty:
        return fees_df.copy()
    out = fees_df.copy()
    out[f"fees_{window_days}d_sum"] = out["dailyFeesUSD"].rolling(window_days, min_periods=window_days).sum()
    out[f"fees_{window_days}d_annualized"] = out[f"fees_{window_days}d_sum"] * (365.0 / window_days)
    return out


def summarize_fee_productivity(
    tvl_df: pd.DataFrame,
    fees_df: pd.DataFrame,
    fee_window_days: int = 90,
) -> dict[str, Any]:
    """Compute fee productivity summary with explicit window assumptions."""
    if tvl_df.empty or fees_df.empty:
        return {
            "status": "NO_DATA",
            "message": "TVL or fee series is empty.",
        }

    fee_tail = fees_df.tail(fee_window_days)
    if fee_tail.empty:
        return {
            "status": "NO_FEE_WINDOW",
            "message": "Fee window could not be constructed.",
        }

    start = fee_tail["date"].iloc[0]
    end = fee_tail["date"].iloc[-1]
    tvl_window = tvl_df[(tvl_df["date"] >= start) & (tvl_df["date"] <= end)]
    if tvl_window.empty:
        tvl_window = tvl_df.tail(len(fee_tail))

    fees_window = float(fee_tail["dailyFeesUSD"].sum())
    annualized = fees_window * (365.0 / len(fee_tail))
    avg_tvl = float(tvl_window["totalLiquidityUSD"].mean()) if not tvl_window.empty else 0.0
    implied_rate = annualized / avg_tvl if avg_tvl > 0 else 0.0

    return {
        "status": "OK",
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "window_days": int(len(fee_tail)),
        "fees_window_usd": fees_window,
        "fees_annualized_usd": annualized,
        "avg_tvl_usd": avg_tvl,
        "implied_fee_rate": implied_rate,
    }


def fmt_usd(value: float | int | None, decimals: int = 2) -> str:
    if value is None:
        return "n/a"
    return f"${value:,.{decimals}f}"


def fmt_pct(value: float | int | None, decimals: int = 2) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.{decimals}f}%"
