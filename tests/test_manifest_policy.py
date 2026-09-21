from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from manifest_policy import classify_manifest, verify_asset  # noqa: E402


def manifest() -> dict:
    return {
        "dataset_id": "bybit-btc-l2-1000-2000",
        "family": "l2",
        "venue": "bybit",
        "symbol": "BTCUSDT",
        "start_ts_ms": 1000,
        "end_ts_ms": 2000,
        "sha256": "a" * 64,
        "bytes": 123,
        "event_count": 50,
        "collector_version": "abc123",
        "source": "bybit_public_ws",
        "quality_status": "PARTIAL",
        "release_asset": "bybit-btc-l2-1000-2000.jsonl.gz",
        "asset_verified": True,
        "provenance": {
            "public_data_only": True,
            "authenticated": False,
            "real_execution": False,
        },
        "integrity": {
            "gap_count": 0,
            "duplicate_count": 0,
            "regression_count": 0,
            "missing_timestamp_count": 0,
            "missing_monotonic_count": 0,
            "desync_count": 0,
            "duplicates_deduped": True,
        },
        "reconciliation": {"status": "MATCHED"},
        "required_channels": ["l2Book"],
        "observed_channels": ["l2Book"],
        "cost_model": {"applicable": False, "ready": False},
    }


def test_complete_manifest_is_safe() -> None:
    status, reasons = classify_manifest(manifest())
    assert status == "SAFE"
    assert reasons == []


def test_gap_is_rejected() -> None:
    value = manifest()
    value["integrity"]["gap_count"] = 1
    status, reasons = classify_manifest(value)
    assert status == "REJECT"
    assert any(reason.startswith("FATAL_INTEGRITY:gap_count") for reason in reasons)


def test_unverified_reconciliation_is_never_safe() -> None:
    value = manifest()
    value["reconciliation"] = {"status": "UNVERIFIED"}
    status, reasons = classify_manifest(value)
    assert status == "PARTIAL"
    assert "RECONCILIATION_UNVERIFIED" in reasons


def test_unverified_asset_is_never_safe() -> None:
    value = manifest()
    value["asset_verified"] = False
    status, reasons = classify_manifest(value)
    assert status == "PARTIAL"
    assert "ASSET_NOT_VERIFIED" in reasons


def test_verify_asset_checks_size_and_sha256(tmp_path) -> None:
    path = tmp_path / "shard.jsonl.gz"
    path.write_bytes(b"real shard bytes")
    value = manifest()
    value["bytes"] = path.stat().st_size
    value["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert verify_asset(value, path) == (True, "MATCHED")

    path.write_bytes(b"tampered")
    assert verify_asset(value, path)[0] is False


def test_cost_model_blocks_safe_only_when_applicable() -> None:
    value = manifest()
    value["cost_model"] = {"applicable": True, "ready": False}
    assert classify_manifest(value)[0] == "PARTIAL"
    value["cost_model"]["ready"] = True
    assert classify_manifest(value)[0] == "SAFE"
