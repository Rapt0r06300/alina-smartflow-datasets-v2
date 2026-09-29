#!/usr/bin/env python3
"""Compute reproducible cross-shard unique trade counts from immutable assets."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Mapping

try:
    from tools.backfill_exact_trade_counts import _download, _native_trade_keys
except ModuleNotFoundError:
    from backfill_exact_trade_counts import _download, _native_trade_keys

ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "catalog" / "DATA_INDEX.json"
PATCH_PATH = ROOT / "catalog" / "TRADE_UNIQUE_COUNT_PATCH.json"


def _persist_manifest_unique_counts(
    row: Mapping[str, Any],
    *,
    unique_count: int,
    exact: bool,
) -> None:
    manifest_path = ROOT / str(row.get("manifest_path") or "")
    if not manifest_path.is_file():
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(manifest, dict):
        return
    manifest["unique_trade_count"] = int(unique_count) if exact else None
    manifest["unique_trade_count_exact"] = bool(exact)
    temporary = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, manifest_path)


def _unique_candidate(row: Mapping[str, Any], covered: set[str]) -> bool:
    dataset_id = str(row.get("dataset_id") or "")
    if not dataset_id or dataset_id in covered:
        return False
    if row.get("trade_count_exact") is not True:
        return False
    return bool(
        row.get("release_repository")
        and row.get("release_tag")
        and row.get("release_asset")
        and row.get("sha256")
        and row.get("bytes")
    )


def _remaining(rows: list[object], covered: set[str]) -> list[Mapping[str, Any]]:
    return [
        row
        for row in rows
        if isinstance(row, Mapping) and _unique_candidate(row, covered)
    ]


def canonical_identity(value: str) -> str:
    """Store the full canonical identity: dedup counts must not rely on hashes."""
    if not isinstance(value, str) or not value:
        raise ValueError("empty trade identity")
    return value


def _scan_candidate(row: Mapping[str, Any], temporary_root: Path) -> dict[str, Any]:
    """Download and decode one immutable shard without touching global state."""
    dataset_id = str(row.get("dataset_id") or "")
    shard_root = temporary_root / dataset_id
    try:
        asset = _download(row, shard_root)
        total = 0
        exact = True
        shard_ids: set[str] = set()
        with gzip.open(asset, "rt", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                raw = json.loads(line)
                if not isinstance(raw, Mapping):
                    continue
                keys = _native_trade_keys(
                    raw,
                    venue=str(row.get("venue") or "unknown"),
                    family=str(row.get("family") or ""),
                    symbol=str(row.get("symbol") or ""),
                )
                if keys is None:
                    exact = False
                    continue
                total += len(keys)
                shard_ids.update(canonical_identity(key) for key in keys)
        return {
            "dataset_id": dataset_id,
            "trade_count_scanned": total,
            "identities": sorted(shard_ids),
            "exact": exact,
        }
    finally:
        shutil.rmtree(shard_root, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()
    if args.limit < 1:
        raise SystemExit("limit must be positive")
    if not 1 <= args.workers <= 32:
        raise SystemExit("workers must be between 1 and 32")

    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    rows = index.get("shards")
    if not isinstance(rows, list):
        raise SystemExit("invalid DATA_INDEX shards")
    prior: dict[str, Any] = {}
    if PATCH_PATH.exists():
        prior = json.loads(PATCH_PATH.read_text(encoding="utf-8"))
    if not isinstance(prior, dict) or prior.get("schema") != "alina.global_unique_trade_patch.v2":
        prior = {}

    counts = prior.get("counts") if isinstance(prior.get("counts"), dict) else {}
    failure_reasons = (
        prior.get("failure_reasons")
        if isinstance(prior.get("failure_reasons"), dict)
        else {}
    )
    covered = set(prior.get("covered_dataset_ids") or [])
    unavailable = prior.get("unavailable") if isinstance(prior.get("unavailable"), dict) else {}
    failure_attempts = prior.get("failure_attempts") if isinstance(prior.get("failure_attempts"), dict) else {}
    candidates = sorted(
        _remaining(rows, covered),
        key=lambda row: str(row.get("dataset_id") or ""),
    )[: args.limit]
    failed: list[dict[str, str]] = []

    with tempfile.TemporaryDirectory(prefix="alina-global-unique-") as temporary:
        root = Path(temporary)
        database = sqlite3.connect(root / "identities.sqlite")
        database.execute("CREATE TABLE ids (identity TEXT PRIMARY KEY)")
        database.executemany(
            "INSERT OR IGNORE INTO ids(identity) VALUES (?)",
            (
                (canonical_identity(str(identity)),)
                for identity in prior.get("identities") or []
            ),
        )
        database.commit()

        def scan(row: Mapping[str, Any]) -> tuple[Mapping[str, Any], dict[str, Any] | Exception]:
            try:
                return row, _scan_candidate(row, root)
            except Exception as exc:
                return row, exc

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            # executor.map preserves candidate order, so attribution of a duplicate
            # identity to its first shard remains deterministic across worker counts.
            for row, scanned in pool.map(scan, candidates):
                dataset_id = str(row.get("dataset_id") or "")
                if isinstance(scanned, Exception):
                    failure = {
                        "dataset_id": dataset_id,
                        "reason": type(scanned).__name__,
                        "detail": str(scanned)[-500:],
                    }
                elif scanned["exact"] is not True:
                    failure = {"dataset_id": dataset_id, "reason": "identity_missing"}
                else:
                    failure = None
                if failure is not None:
                    attempts = int(failure_attempts.get(dataset_id) or 0) + 1
                    failure_attempts[dataset_id] = attempts
                    failure["attempts"] = attempts
                    # A verified immutable coordinate that repeatedly cannot be
                    # decoded/downloaded is explicitly classified, never guessed.
                    if attempts >= 3:
                        unavailable[dataset_id] = {
                            **failure,
                            "status": "UNAVAILABLE",
                            "retryable": False,
                        }
                        covered.add(dataset_id)
                        failure_reasons.pop(dataset_id, None)
                    else:
                        failed.append(failure)
                        failure_reasons[dataset_id] = failure
                    continue

                identities = scanned["identities"]
                global_new = 0
                for identity in identities:
                    before = database.total_changes
                    database.execute(
                        "INSERT OR IGNORE INTO ids(identity) VALUES (?)",
                        (identity,),
                    )
                    global_new += int(database.total_changes > before)
                counts[dataset_id] = {
                    "trade_count_scanned": int(scanned["trade_count_scanned"]),
                    "unique_trade_count": len(identities),
                    "unique_trade_count_exact": True,
                    "global_new_identity_count": global_new,
                    "cross_shard_overlap_count": max(0, len(identities) - global_new),
                    "identity_version": "native-id-or-venue-family-symbol-time-side-price-size-v1",
                }
                _persist_manifest_unique_counts(
                    row,
                    unique_count=len(identities),
                    exact=True,
                )
                covered.add(dataset_id)
                failure_reasons.pop(dataset_id, None)
                database.commit()

        global_count = database.execute("SELECT COUNT(*) FROM ids").fetchone()[0]
        identity_rows = [
            row[0]
            for row in database.execute("SELECT identity FROM ids ORDER BY identity")
        ]

    for row in rows:
        if isinstance(row, dict):
            patch_row = counts.get(str(row.get("dataset_id") or ""))
            if isinstance(patch_row, Mapping):
                row.update(patch_row)
    INDEX_PATH.write_text(
        json.dumps(index, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    remaining = _remaining(rows, covered)
    result = {
        "schema": "alina.global_unique_trade_patch.v2",
        "method": "parallel_scan_then_deterministic_sqlite_full_identity_merge",
        "identity_version": "native-id-or-venue-family-symbol-time-side-price-size-v2-full-string",
        "collision_policy": "full canonical identity strings; native identifiers preferred; ambiguous missing identities fail closed",
        "counts": dict(sorted(counts.items())),
        "covered_dataset_ids": sorted(covered),
        "attempted": len(candidates),
        "failed": failed,
        "failure_reasons": dict(sorted(failure_reasons.items())),
        "failure_attempts": dict(sorted(failure_attempts.items())),
        "unavailable": dict(sorted(unavailable.items())),
        "unavailable_candidate_shards": len(unavailable),
        "remaining_candidate_shards": len(remaining),
        "global_unique_trade_count": global_count,
        "global_identity_digest": hashlib.sha256(
            json.dumps(identity_rows, separators=(",", ":")).encode()
        ).hexdigest(),
        "identities": identity_rows,
        "cross_shard_overlap_count": sum(
            int(value.get("cross_shard_overlap_count") or 0)
            for value in counts.values()
            if isinstance(value, Mapping)
        ),
        "coverage_complete": not remaining,
    }
    PATCH_PATH.write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "attempted",
                    "global_unique_trade_count",
                    "remaining_candidate_shards",
                    "coverage_complete",
                )
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
