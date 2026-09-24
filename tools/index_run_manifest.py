#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping

from manifest_policy import classify_manifest

ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "catalog" / "DATA_INDEX.json"
REGISTRY_PATH = ROOT / "catalog" / "DATA_QUALITY_REGISTRY.json"
CATALOG_PATH = ROOT / "catalog" / "DATA_CATALOG.json"

_STAGE_BY_STATUS = {
    "SAFE": "safe",
    "PARTIAL": "quarantine",
    "STALE": "quarantine",
    "REJECT": "rejected",
    "NO_DATA": "incoming",
}


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _normalize_manifest(raw: Mapping[str, Any]) -> dict[str, Any]:
    manifest = dict(raw)
    release = manifest.get("release")
    if isinstance(release, Mapping):
        manifest.setdefault("release_repository", release.get("repository"))
        manifest.setdefault("release_tag", release.get("tag"))
        manifest.setdefault("release_asset", release.get("asset_name"))
        manifest.setdefault("release_id", release.get("release_id"))
        manifest.setdefault("release_asset_id", release.get("asset_id"))
        manifest.setdefault("release_remote_size", release.get("remote_size"))
        manifest.setdefault("release_remote_digest", release.get("remote_digest"))
    return manifest


def _index_row(manifest: Mapping[str, Any], manifest_path: Path, root: Path) -> dict[str, Any]:
    row = {
        "dataset_id": manifest.get("dataset_id"),
        "family": manifest.get("family"),
        "venue": manifest.get("venue"),
        "symbol": manifest.get("symbol"),
        "start_ts_ms": manifest.get("start_ts_ms"),
        "end_ts_ms": manifest.get("end_ts_ms"),
        "quality_status": manifest.get("quality_status"),
        "collection_run_id": manifest.get("collection_run_id"),
        "manifest_path": str(manifest_path.relative_to(root)).replace("\\", "/"),
        "release_repository": manifest.get("release_repository"),
        "release_tag": manifest.get("release_tag"),
        "release_asset": manifest.get("release_asset"),
        "sha256": manifest.get("sha256"),
        "bytes": manifest.get("bytes"),
        "event_count": manifest.get("event_count"),
    }
    integration = manifest.get("event_intelligence")
    if isinstance(integration, Mapping):
        row.update(
            {
                "event_intelligence_idea_count": integration.get("idea_count"),
                "event_intelligence_coverage_sha256": integration.get(
                    "coverage_sha256"
                ),
                "linked_strategy_families": integration.get(
                    "linked_strategy_families"
                ),
            }
        )
    return row


def index_run_manifests(
    run_manifest_paths: Iterable[str | Path],
    *,
    root: str | Path = ROOT,
) -> dict[str, Any]:
    base = Path(root)
    index_path = base / "catalog" / "DATA_INDEX.json"
    registry_path = base / "catalog" / "DATA_QUALITY_REGISTRY.json"
    catalog_path = base / "catalog" / "DATA_CATALOG.json"

    index = json.loads(index_path.read_text(encoding="utf-8"))
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    rows_by_id = {
        str(row.get("dataset_id")): dict(row)
        for row in (index.get("shards") or [])
        if isinstance(row, Mapping) and row.get("dataset_id")
    }

    imported = 0
    statuses: dict[str, int] = {}
    for run_path in run_manifest_paths:
        payload = json.loads(Path(run_path).read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError(f"invalid run manifest: {run_path}")
        if payload.get("schema") != "alina.dataset_run_manifest.v2":
            raise ValueError(f"unexpected run manifest schema: {run_path}")
        repository = str(payload.get("repository") or "")
        if repository != "Rapt0r06300/alina-smartflow-datasets-v2":
            raise ValueError(f"foreign dataset repository refused: {repository}")

        manifests = payload.get("manifests")
        if not isinstance(manifests, list):
            raise ValueError(f"run manifest has no manifests array: {run_path}")

        for raw in manifests:
            if not isinstance(raw, Mapping):
                continue
            manifest = _normalize_manifest(raw)
            dataset_id = str(manifest.get("dataset_id") or "").strip()
            if not dataset_id:
                raise ValueError("dataset_id required")
            status, reasons = classify_manifest(manifest)
            manifest["quality_status"] = status
            manifest["quality_reasons"] = reasons
            manifest["validation_allowed"] = status == "SAFE"
            # A SAFE shard may be used by validation, but dataset quality alone
            # never proves that any strategy has positive PnL.
            manifest["proof_of_pnl_allowed"] = False

            for stage in set(_STAGE_BY_STATUS.values()):
                stale = base / "datasets" / stage / f"{dataset_id}.manifest.json"
                if stale.exists():
                    stale.unlink()
            destination = (
                base
                / "datasets"
                / _STAGE_BY_STATUS[status]
                / f"{dataset_id}.manifest.json"
            )
            _atomic_json(destination, manifest)
            rows_by_id[dataset_id] = _index_row(manifest, destination, base)
            statuses[status] = statuses.get(status, 0) + 1
            imported += 1

    shards = sorted(
        rows_by_id.values(),
        key=lambda row: (
            int(row.get("start_ts_ms") or 0),
            str(row.get("venue") or ""),
            str(row.get("family") or ""),
            str(row.get("symbol") or ""),
            str(row.get("dataset_id") or ""),
        ),
    )
    active = (
        "SAFE"
        if any(row.get("quality_status") == "SAFE" for row in shards)
        else ("PARTIAL" if shards else "NO_DATA")
    )
    index["shards"] = shards
    index["active_data_status"] = active
    _atomic_json(index_path, index)

    safe_count = sum(1 for row in shards if row.get("quality_status") == "SAFE")
    partial_count = sum(1 for row in shards if row.get("quality_status") == "PARTIAL")
    stale_count = sum(1 for row in shards if row.get("quality_status") == "STALE")
    reject_count = sum(1 for row in shards if row.get("quality_status") == "REJECT")

    registry["active_dataset"] = {
        "status": active,
        "validation_allowed": active == "SAFE",
        # Dataset quality can authorize validation, never prove strategy PnL.
        "proof_of_pnl_allowed": False,
        "indexed_shards": len(shards),
        "safe_count": safe_count,
        "partial_count": partial_count,
        "stale_count": stale_count,
        "reject_count": reject_count,
    }
    _atomic_json(registry_path, registry)

    catalog["active_data_status"] = active
    catalog["indexed_shard_count"] = len(shards)
    catalog["safe_shard_count"] = safe_count
    catalog["partial_shard_count"] = partial_count
    catalog["stale_shard_count"] = stale_count
    catalog["reject_shard_count"] = reject_count
    _atomic_json(catalog_path, catalog)
    return {
        "imported_manifests": imported,
        "indexed_shards": len(shards),
        "active_data_status": active,
        "statuses": statuses,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Index verified dataset V2 RUN_MANIFEST release evidence."
    )
    parser.add_argument("run_manifests", nargs="+")
    args = parser.parse_args()
    result = index_run_manifests(args.run_manifests)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
