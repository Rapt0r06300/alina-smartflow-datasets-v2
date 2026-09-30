from __future__ import annotations

import gzip
import json

from tools import backfill_global_unique_trade_counts as global_counts


def test_scan_candidate_extracts_exact_identities_without_global_state(tmp_path, monkeypatch):
    asset = tmp_path / "asset.jsonl.gz"
    raw = {
        "topic": "publicTrade.BTCUSDT",
        "data": [
            {"i": "a", "T": 1, "p": "10", "v": "1", "S": "Buy", "s": "BTCUSDT"},
            {"i": "b", "T": 2, "p": "11", "v": "2", "S": "Sell", "s": "BTCUSDT"},
            {"i": "a", "T": 1, "p": "10", "v": "1", "S": "Buy", "s": "BTCUSDT"},
        ],
    }
    with gzip.open(asset, "wt", encoding="utf-8") as handle:
        handle.write(json.dumps({"raw_payload": json.dumps(raw)}) + "\n")
    monkeypatch.setattr(global_counts, "_download", lambda row, destination: asset)
    row = {
        "dataset_id": "sample",
        "venue": "bybit",
        "family": "trades",
        "symbol": "BTCUSDT",
    }

    result = global_counts._scan_candidate(row, tmp_path)

    assert result["dataset_id"] == "sample"
    assert result["trade_count_scanned"] == 3
    assert result["unique_trade_count"] == 2
    assert result["exact"] is True
    identities = result["identity_path"]
    with open(identities, encoding="utf-8") as handle:
        rows = [line.strip() for line in handle if line.strip()]
    assert rows == sorted(set(rows))
    assert len(rows) == 2


def test_unique_candidate_excludes_non_trade_zero_count_assets():
    base = {
        "dataset_id": "x",
        "trade_count_exact": True,
        "release_repository": "owner/repo",
        "release_tag": "tag",
        "release_asset": "asset.jsonl.gz",
        "sha256": "a" * 64,
        "bytes": 1,
    }
    assert global_counts._unique_candidate({**base, "family": "bbo", "trade_count": 0}) is False
    assert global_counts._unique_candidate({**base, "family": "l2Book", "trade_count": 100}) is False
    assert global_counts._unique_candidate({**base, "family": "trades", "trade_count": 0}) is False
    assert global_counts._unique_candidate({**base, "family": "trades", "trade_count": 1}) is True
