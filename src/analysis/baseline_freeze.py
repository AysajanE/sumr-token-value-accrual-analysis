"""
Freeze a reproducible checksum baseline for current results artifacts.

Outputs:
- results/tables/baseline_manifest_<timestamp>.json
- results/tables/baseline_manifest_latest.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import PROJECT_ROOT, RESULTS_DIR

SCHEMA_VERSION = "baseline_manifest_v1"
EXCLUDED_PREFIXES = (
    "results/tables/baseline_manifest_",
)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def relpath_from_root(path: Path, project_root: Path) -> str:
    return path.resolve().relative_to(project_root.resolve()).as_posix()


def resolve_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return (PROJECT_ROOT / path).resolve()


def is_excluded(rel_path: str) -> bool:
    return any(rel_path.startswith(prefix) for prefix in EXCLUDED_PREFIXES)


def collect_result_files(results_dir: Path, project_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(results_dir.rglob("*")):
        if not path.is_file():
            continue
        rel_path = relpath_from_root(path, project_root)
        if is_excluded(rel_path):
            continue
        rows.append(
            {
                "path": rel_path,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return rows


def compute_tree_sha256(rows: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        line = f"{row['path']}\t{row['size_bytes']}\t{row['sha256']}\n"
        digest.update(line.encode("utf-8"))
    return digest.hexdigest()


def load_monitoring_context(monitoring_path: Path) -> dict[str, Any]:
    if not monitoring_path.exists():
        return {
            "source_file": None,
            "observed_utc": None,
            "refresh_from_block": None,
            "refresh_to_block": None,
        }

    payload = load_json(monitoring_path)
    latest = payload.get("latest") or {}
    return {
        "source_file": monitoring_path.as_posix(),
        "observed_utc": latest.get("observed_utc"),
        "refresh_from_block": latest.get("refresh_from_block"),
        "refresh_to_block": latest.get("refresh_to_block"),
    }


def freeze_baseline(results_dir: Path, tables_dir: Path, monitoring_path: Path) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")

    files = collect_result_files(results_dir=results_dir, project_root=PROJECT_ROOT)
    file_count = len(files)
    total_size_bytes = int(sum(int(row["size_bytes"]) for row in files))
    tree_sha = compute_tree_sha256(files)
    monitoring = load_monitoring_context(monitoring_path)

    manifest = {
        "schema": SCHEMA_VERSION,
        "generated_utc": now.isoformat(),
        "project_root": PROJECT_ROOT.as_posix(),
        "scope": {
            "results_dir": results_dir.as_posix(),
            "file_count": file_count,
            "total_size_bytes": total_size_bytes,
            "excluded_prefixes": list(EXCLUDED_PREFIXES),
        },
        "monitoring_context": monitoring,
        "fingerprints": {
            "tree_sha256": tree_sha,
        },
        "files": files,
    }

    dated_path = tables_dir / f"baseline_manifest_{stamp}.json"
    latest_path = tables_dir / "baseline_manifest_latest.json"
    save_json(dated_path, manifest)
    save_json(latest_path, manifest)

    print("Baseline checksum manifest refreshed")
    print(f"Generated UTC: {manifest['generated_utc']}")
    print(f"Files hashed: {file_count}")
    print(f"Tree SHA256: {tree_sha}")
    print(
        "Refresh block range: "
        f"{monitoring.get('refresh_from_block')} -> {monitoring.get('refresh_to_block')}"
    )
    print(f"Files written: {dated_path.name}, {latest_path.name}")
    return manifest


def show_latest_manifest(tables_dir: Path) -> None:
    latest_path = tables_dir / "baseline_manifest_latest.json"
    if not latest_path.exists():
        raise FileNotFoundError(
            f"Latest baseline manifest not found: {latest_path}. Run freeze command first."
        )

    payload = load_json(latest_path)
    scope = payload.get("scope") or {}
    monitoring = payload.get("monitoring_context") or {}
    fingerprints = payload.get("fingerprints") or {}

    print("Baseline status")
    print(f"Manifest UTC: {payload.get('generated_utc')}")
    print(f"Files hashed: {scope.get('file_count')}")
    print(f"Tree SHA256: {fingerprints.get('tree_sha256')}")
    print(
        "Refresh block range: "
        f"{monitoring.get('refresh_from_block')} -> {monitoring.get('refresh_to_block')}"
    )
    print(f"Monitoring observed UTC: {monitoring.get('observed_utc')}")
    print(f"Manifest source: {latest_path.as_posix()}")


def main() -> None:
    default_results_dir = RESULTS_DIR
    default_tables_dir = RESULTS_DIR / "tables"
    default_monitoring_path = default_tables_dir / "monitoring_latest.json"

    parser = argparse.ArgumentParser(description="Freeze or inspect checksum baseline for current results artifacts.")
    parser.add_argument("--results-dir", type=Path, default=default_results_dir)
    parser.add_argument("--tables-dir", type=Path, default=default_tables_dir)
    parser.add_argument("--monitoring-path", type=Path, default=default_monitoring_path)
    parser.add_argument("--show-latest", action="store_true", help="Print summary from baseline_manifest_latest.json.")
    args = parser.parse_args()

    resolved_results_dir = resolve_path(args.results_dir)
    resolved_tables_dir = resolve_path(args.tables_dir)
    resolved_monitoring_path = resolve_path(args.monitoring_path)

    if args.show_latest:
        show_latest_manifest(tables_dir=resolved_tables_dir)
        return

    freeze_baseline(
        results_dir=resolved_results_dir,
        tables_dir=resolved_tables_dir,
        monitoring_path=resolved_monitoring_path,
    )


if __name__ == "__main__":
    main()
