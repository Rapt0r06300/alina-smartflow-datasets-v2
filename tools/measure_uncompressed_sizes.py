#!/usr/bin/env python3
"""Measure exact uncompressed byte sizes for immutable release assets."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import gzip
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any, Mapping

try:
    from tools.backfill_exact_trade_counts import _download
except ModuleNotFoundError:
    from backfill_exact_trade_counts import _download

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "catalog" / "DATA_INDEX.json"
PATCH = ROOT / "catalog" / "UNCOMPRESSED_SIZE_PATCH.json"


def _measure_candidate(row: Mapping[str, Any], temporary_root: str) -> tuple[str, dict[str, Any]]:
    dataset_id = str(row["dataset_id"])
    target = Path(temporary_root) / hashlib.sha256(dataset_id.encode("utf-8")).hexdigest()
    try:
        asset = _download(row, target)
        total = 0
        digest = hashlib.sha256()
        with asset.open("rb") as compressed:
            for chunk in iter(lambda: compressed.read(4 * 1024 * 1024), b""):
                digest.update(chunk)
        with gzip.open(asset, "rb") as handle:
            for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
                total += len(chunk)
        return dataset_id, {
            "uncompressed_bytes": total,
            "compressed_bytes": int(row.get("bytes") or 0),
            "asset_sha256": digest.hexdigest(),
        }
    except Exception as exc:
        reason = f"{type(exc).__name__}:{str(exc)[:240]}"
        return dataset_id, {"status": "UNAVAILABLE", "reason": reason, "retryable": True}
    finally:
        shutil.rmtree(target, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()
    worker_count = min(32, max(1, args.workers))

    index = json.loads(INDEX.read_text(encoding="utf-8"))
    rows = index.get("shards")
    prior = json.loads(PATCH.read_text(encoding="utf-8")) if PATCH.exists() else {"sizes": {}}
    sizes = prior.get("sizes") if isinstance(prior.get("sizes"), dict) else {}
    all_rows = [row for row in rows if isinstance(row, Mapping) and row.get("dataset_id")]

    for row in all_rows:
        dataset_id = str(row["dataset_id"])
        measured = sizes.get(dataset_id)
        if dataset_id in sizes and not (isinstance(measured, Mapping) and measured.get("retryable") is True):
            continue
        if not (row.get("release_repository") and row.get("release_tag") and row.get("release_asset")):
            sizes[dataset_id] = {
                "status": "UNAVAILABLE",
                "reason": "no_immutable_release_asset",
                "retryable": False,
            }

    candidates = sorted(
        [
            row
            for row in all_rows
            if str(row.get("dataset_id")) not in sizes
            or (
                isinstance(sizes.get(str(row.get("dataset_id"))), Mapping)
                and sizes[str(row.get("dataset_id"))].get("retryable") is True
            )
        ],
        key=lambda row: str(row.get("dataset_id")),
    )[: max(1, args.limit)]

    failed: list[dict[str, str]] = []
    with tempfile.TemporaryDirectory(prefix="alina-uncompressed-") as temporary_root:
        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            futures = [pool.submit(_measure_candidate, row, temporary_root) for row in candidates]
            for future in as_completed(futures):
                dataset_id, result = future.result()
                sizes[dataset_id] = result
                if result.get("status") == "UNAVAILABLE":
                    failed.append({"dataset_id": dataset_id, "reason": str(result.get("reason", ""))})

    remaining = sum(
        1
        for row in all_rows
        if str(row.get("dataset_id")) not in sizes
        or (
            isinstance(sizes.get(str(row.get("dataset_id"))), Mapping)
            and sizes[str(row.get("dataset_id"))].get("retryable") is True
        )
    )
    exact = sum(
        1
        for value in sizes.values()
        if isinstance(value, Mapping)
        and value.get("status") != "UNAVAILABLE"
        and isinstance(value.get("uncompressed_bytes"), int)
    )
    unavailable = sum(
        1
        for value in sizes.values()
        if isinstance(value, Mapping)
        and value.get("status") == "UNAVAILABLE"
        and value.get("retryable") is not True
    )
    body = {
        "schema": "alina.uncompressed_size_patch.v2",
        "method": "parallel_exact_gzip_decompression_byte_count_or_explicit_unavailable",
        "sizes": dict(sorted(sizes.items())),
        "attempted": len(candidates),
        "failed": sorted(failed, key=lambda item: item["dataset_id"]),
        "remaining_assets": remaining,
        "exact_assets": exact,
        "unavailable_assets": unavailable,
        "coverage_complete": remaining == 0,
    }
    PATCH.write_text(json.dumps(body, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "attempted": len(candidates),
                "remaining_assets": remaining,
                "exact_assets": exact,
                "unavailable_assets": unavailable,
                "coverage_complete": body["coverage_complete"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
