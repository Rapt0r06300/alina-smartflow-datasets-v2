#!/usr/bin/env python3
"""Backfill exact trade counts from immutable GitHub Release assets.

This tool never estimates from bytes. It verifies the indexed asset size and SHA-256,
then scans gzip JSONL TickEnvelope records. Counts are persisted in a separate patch
catalog so future reconciliation can re-apply them without mutating historical release
manifests.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "catalog" / "DATA_INDEX.json"
PATCH_PATH = ROOT / "catalog" / "TRADE_COUNT_PATCH.json"
TRADE_FAMILIES = {
    "trades",
    "agg_trades",
    "fills",
    "userfills",
    "user_fills",
    "copy_vault_fills",
}


class BackfillError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _trade_increment(record: Mapping[str, Any]) -> int:
    parsed = record.get("parsed_summary")
    if isinstance(parsed, Mapping):
        for key in ("event_count", "fill_count"):
            value = parsed.get(key)
            if value is not None and not isinstance(value, bool):
                try:
                    return max(0, int(value))
                except (TypeError, ValueError, OverflowError):
                    pass
    return 1


def _raw_payload(record: Mapping[str, Any]) -> Any:
    raw = record.get("raw_payload")
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    return raw


def _native_trade_keys(
    record: Mapping[str, Any],
    *,
    venue: str,
    family: str,
    symbol: str,
) -> list[str] | None:
    raw = _raw_payload(record)
    venue = venue.lower()
    family = family.lower()
    keys: list[str] = []

    def add(prefix: str, value: Any) -> None:
        if value is not None and str(value) != "":
            keys.append(f"{venue}|{family}|{symbol}|{prefix}|{value}")

    if venue == "binance" and isinstance(raw, Mapping):
        if family == "agg_trades":
            add("a", raw.get("a"))
        else:
            add("t", raw.get("t"))
        return keys or None

    if venue == "hyperliquid" and isinstance(raw, Mapping):
        data = raw.get("data")
        rows = data if isinstance(data, list) else []
        if rows:
            for row in rows:
                if not isinstance(row, Mapping):
                    continue
                if row.get("tid") is not None:
                    add("tid", row.get("tid"))
                else:
                    fallback = (
                        row.get("time"),
                        row.get("px"),
                        row.get("sz"),
                        row.get("side"),
                        row.get("coin"),
                        row.get("hash"),
                    )
                    add("fallback", "|".join("" if v is None else str(v) for v in fallback))
            return keys or None

    if venue == "bybit" and isinstance(raw, Mapping):
        rows = raw.get("data")
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, Mapping):
                    if row.get("i") is not None:
                        add("i", row.get("i"))
                    else:
                        fallback = (
                            row.get("T"),
                            row.get("p"),
                            row.get("v"),
                            row.get("S"),
                            row.get("s"),
                        )
                        add("fallback", "|".join("" if v is None else str(v) for v in fallback))
            return keys or None

    if venue == "okx" and isinstance(raw, Mapping):
        rows = raw.get("data")
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, Mapping):
                    if row.get("tradeId") is not None:
                        add("tradeId", row.get("tradeId"))
                    else:
                        fallback = (
                            row.get("ts"),
                            row.get("px"),
                            row.get("sz"),
                            row.get("side"),
                            row.get("instId"),
                        )
                        add("fallback", "|".join("" if v is None else str(v) for v in fallback))
            return keys or None

    if venue == "bitget" and isinstance(raw, Mapping):
        rows = raw.get("data")
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, Mapping):
                    native = row.get("tradeId") or row.get("trade_id")
                    if native is not None:
                        add("tradeId", native)
                    else:
                        fallback = (
                            row.get("ts"),
                            row.get("price"),
                            row.get("size"),
                            row.get("side"),
                        )
                        add("fallback", "|".join("" if v is None else str(v) for v in fallback))
            return keys or None

    # Copy-Vault and any other trade-like family: use explicit native IDs when
    # present. If a record cannot be decomposed reliably, unique_count remains
    # unproven instead of being guessed.
    if isinstance(raw, Mapping):
        rows = raw.get("data")
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, Mapping):
                    native = (
                        row.get("tid")
                        or row.get("tradeId")
                        or row.get("trade_id")
                        or row.get("hash")
                    )
                    if native is None:
                        return None
                    add("native", native)
            return keys or None

    return None


def inspect_asset(path: Path, row: Mapping[str, Any]) -> dict[str, Any]:
    expected_size = int(row.get("bytes") or 0)
    expected_sha = str(row.get("sha256") or "").lower()
    if expected_size <= 0 or path.stat().st_size != expected_size:
        raise BackfillError("asset size mismatch")
    actual_sha = _sha256(path)
    if len(expected_sha) != 64 or actual_sha != expected_sha:
        raise BackfillError("asset sha256 mismatch")

    trade_count = 0
    unique_hashes: set[int] = set()
    unique_proven = True
    records = 0
    venue = str(row.get("venue") or "unknown")
    family = str(row.get("family") or "")
    symbol = str(row.get("symbol") or "")

    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            raw = json.loads(line)
            if not isinstance(raw, Mapping):
                continue
            records += 1
            trade_count += _trade_increment(raw)
            keys = _native_trade_keys(
                raw,
                venue=venue,
                family=family,
                symbol=symbol,
            )
            if keys is None:
                unique_proven = False
            else:
                for key in keys:
                    digest = hashlib.blake2b(
                        key.encode("utf-8"),
                        digest_size=8,
                    ).digest()
                    unique_hashes.add(int.from_bytes(digest, "big"))

    return {
        "trade_count": trade_count,
        "trade_count_exact": True,
        "unique_trade_count": len(unique_hashes) if unique_proven else None,
        "unique_trade_count_exact": unique_proven,
        "record_count_scanned": records,
        "asset_sha256": actual_sha,
    }


def _download(row: Mapping[str, Any], destination: Path) -> Path:
    repository = str(row.get("release_repository") or "")
    tag = str(row.get("release_tag") or "")
    asset = str(row.get("release_asset") or "")
    if not repository or not tag or not asset:
        raise BackfillError("release coordinates missing")
    destination.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "gh",
            "release",
            "download",
            tag,
            "--repo",
            repository,
            "--pattern",
            asset,
            "--dir",
            os.fspath(destination),
            "--clobber",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise BackfillError((result.stderr or result.stdout or "download failed").strip())
    path = destination / asset
    if not path.is_file():
        raise BackfillError("downloaded asset missing")
    return path


def _load_patch() -> dict[str, Any]:
    if not PATCH_PATH.is_file():
        return {
            "schema": "alina.trade_count_patch.v1",
            "method": "verified_release_asset_scan_no_estimation",
            "counts": {},
        }
    value = json.loads(PATCH_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise BackfillError("invalid patch catalog")
    value.setdefault("schema", "alina.trade_count_patch.v1")
    value.setdefault("method", "verified_release_asset_scan_no_estimation")
    value.setdefault("counts", {})
    return value


def _candidate(row: Mapping[str, Any], patch: Mapping[str, Any]) -> bool:
    family = str(row.get("family") or "").lower()
    if family not in TRADE_FAMILIES:
        return False
    dataset_id = str(row.get("dataset_id") or "")
    if not dataset_id or dataset_id in patch:
        return False
    if row.get("trade_count_exact") is True and int(row.get("trade_count") or 0) > 0:
        return False
    return bool(
        row.get("release_repository")
        and row.get("release_tag")
        and row.get("release_asset")
        and row.get("sha256")
        and row.get("bytes")
    )


def backfill(limit: int) -> dict[str, Any]:
    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    rows = index.get("shards")
    if not isinstance(rows, list):
        raise BackfillError("invalid data index")
    patch_doc = _load_patch()
    counts = patch_doc.get("counts")
    if not isinstance(counts, dict):
        raise BackfillError("invalid trade count patch counts")

    candidates = [
        row for row in rows
        if isinstance(row, Mapping) and _candidate(row, counts)
    ][: max(1, int(limit))]
    updated = 0
    failed: list[dict[str, str]] = []

    with tempfile.TemporaryDirectory(prefix="alina-trade-count-") as tmp:
        tmp_root = Path(tmp)
        for row in candidates:
            dataset_id = str(row["dataset_id"])
            try:
                path = _download(row, tmp_root / dataset_id)
                result = inspect_asset(path, row)
            except Exception as exc:
                failed.append(
                    {
                        "dataset_id": dataset_id,
                        "error": type(exc).__name__,
                    }
                )
                continue
            counts[dataset_id] = result
            row.update(result)
            updated += 1
            shutil.rmtree(tmp_root / dataset_id, ignore_errors=True)

    patch_doc["counts"] = dict(sorted(counts.items()))
    patch_doc["processed_exact_shards"] = len(counts)
    patch_doc["remaining_candidate_shards"] = max(0, len([
        row for row in rows
        if isinstance(row, Mapping) and _candidate(row, counts)
    ]))
    PATCH_PATH.write_text(
        json.dumps(patch_doc, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    INDEX_PATH.write_text(
        json.dumps(index, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "updated": updated,
        "attempted": len(candidates),
        "failed": failed,
        "remaining_candidate_shards": patch_doc["remaining_candidate_shards"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    try:
        result = backfill(args.limit)
    except (BackfillError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"TRADE_COUNT_BACKFILL_NO_GO:{type(exc).__name__}:{exc}")
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
