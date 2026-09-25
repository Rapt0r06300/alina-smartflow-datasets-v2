#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "catalog" / "DATA_INDEX.json"
METRICS = ROOT / "catalog" / "DATA_METRICS.json"
TRADE_FAMILIES = {
    "trades",
    "agg_trades",
    "fills",
    "userfills",
    "user_fills",
    "copy_vault_fills",
}


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError, OverflowError):
        return 0


def _bucket(table: dict[str, dict[str, int]], key: str) -> dict[str, int]:
    if key not in table:
        table[key] = {
            "shards": 0,
            "records": 0,
            "trades": 0,
            "unique_trades_within_shards": 0,
            "safe_trades": 0,
            "replayable_trades": 0,
            "bytes": 0,
            "trade_shards_exact": 0,
            "trade_shards_missing_exact": 0,
        }
    return table[key]


def build() -> dict[str, Any]:
    idx = json.loads(INDEX.read_text(encoding="utf-8"))
    shards = idx.get("shards") or []
    totals: dict[str, Any] = {
        "TOTAL_SHARDS": len(shards),
        "SAFE_SHARDS": 0,
        "PARTIAL_SHARDS": 0,
        "REJECTED_SHARDS": 0,
        "REPLAYABLE_SHARDS": 0,
        "TOTAL_TRADES_COLLECTED": 0,
        "TOTAL_TRADES_SAFE": 0,
        "TOTAL_TRADES_PARTIAL": 0,
        "TOTAL_TRADES_REJECTED": 0,
        "TOTAL_TRADES_REPLAYABLE": 0,
        "TOTAL_UNIQUE_TRADES_WITHIN_SHARDS": 0,
        "TOTAL_RECORDS": 0,
        "TOTAL_SAFE_RECORDS": 0,
        "TOTAL_REPLAYABLE_RECORDS": 0,
        "TOTAL_COMPRESSED_BYTES": 0,
        "TOTAL_UNCOMPRESSED_BYTES": 0,
        "TRADE_SHARDS_WITH_EXACT_COUNT": 0,
        "TRADE_SHARDS_MISSING_EXACT_COUNT": 0,
        "TRADE_SHARDS_WITH_EXACT_UNIQUE_COUNT": 0,
        "TRADE_SHARDS_MISSING_EXACT_UNIQUE_COUNT": 0,
    }
    by_venue: dict[str, dict[str, int]] = {}
    by_symbol: dict[str, dict[str, int]] = {}
    by_family: dict[str, dict[str, int]] = {}

    for row in shards:
        if not isinstance(row, dict):
            continue
        status = str(row.get("quality_status") or "")
        replay = row.get("replay_compatible") is True
        records = _int(row.get("record_count") or row.get("event_count"))
        compressed = _int(row.get("bytes"))
        uncompressed = _int(row.get("uncompressed_bytes"))
        family = str(row.get("family") or "").lower()
        trade_family = family in TRADE_FAMILIES
        trade_exact = trade_family and row.get("trade_count_exact") is True
        unique_exact = trade_family and row.get("unique_trade_count_exact") is True
        trades = _int(row.get("trade_count")) if trade_exact else 0
        unique_trades = _int(row.get("unique_trade_count")) if unique_exact else 0

        totals["TOTAL_RECORDS"] += records
        totals["TOTAL_COMPRESSED_BYTES"] += compressed
        totals["TOTAL_UNCOMPRESSED_BYTES"] += uncompressed

        if status == "SAFE":
            totals["SAFE_SHARDS"] += 1
            totals["TOTAL_SAFE_RECORDS"] += records
            totals["TOTAL_TRADES_SAFE"] += trades
        elif status == "PARTIAL":
            totals["PARTIAL_SHARDS"] += 1
            totals["TOTAL_TRADES_PARTIAL"] += trades
        elif status in {"REJECT", "REJECTED"}:
            totals["REJECTED_SHARDS"] += 1
            totals["TOTAL_TRADES_REJECTED"] += trades

        if replay:
            totals["REPLAYABLE_SHARDS"] += 1
            totals["TOTAL_REPLAYABLE_RECORDS"] += records
            totals["TOTAL_TRADES_REPLAYABLE"] += trades

        if trade_family:
            if trade_exact:
                totals["TRADE_SHARDS_WITH_EXACT_COUNT"] += 1
                totals["TOTAL_TRADES_COLLECTED"] += trades
            else:
                totals["TRADE_SHARDS_MISSING_EXACT_COUNT"] += 1
            if unique_exact:
                totals["TRADE_SHARDS_WITH_EXACT_UNIQUE_COUNT"] += 1
                totals["TOTAL_UNIQUE_TRADES_WITHIN_SHARDS"] += unique_trades
            else:
                totals["TRADE_SHARDS_MISSING_EXACT_UNIQUE_COUNT"] += 1

        for table, key in (
            (by_venue, str(row.get("venue") or "unknown").lower()),
            (by_symbol, str(row.get("symbol") or "unknown").upper()),
            (by_family, family or "unknown"),
        ):
            bucket = _bucket(table, key)
            bucket["shards"] += 1
            bucket["records"] += records
            bucket["bytes"] += compressed
            if trade_family:
                if trade_exact:
                    bucket["trades"] += trades
                    bucket["trade_shards_exact"] += 1
                else:
                    bucket["trade_shards_missing_exact"] += 1
                if unique_exact:
                    bucket["unique_trades_within_shards"] += unique_trades
                if status == "SAFE":
                    bucket["safe_trades"] += trades
                if replay:
                    bucket["replayable_trades"] += trades

    totals["TOTAL_TRADES_COUNT_COVERAGE_COMPLETE"] = (
        totals["TRADE_SHARDS_MISSING_EXACT_COUNT"] == 0
    )
    totals["TOTAL_UNIQUE_TRADES_COVERAGE_COMPLETE"] = (
        totals["TRADE_SHARDS_MISSING_EXACT_UNIQUE_COUNT"] == 0
    )

    payload = {
        "schema_version": "alina.data_metrics.v3",
        "method": "verified_manifest_or_asset_scan_counts_no_byte_estimation",
        "totals": totals,
        "by_venue": dict(sorted(by_venue.items())),
        "by_symbol": dict(sorted(by_symbol.items())),
        "by_family": dict(sorted(by_family.items())),
        "notes": {
            "TOTAL_TRADES_COLLECTED": (
                "sum of shards whose trade_count_exact=true only; unknown legacy "
                "trade shards are excluded, never zero-filled"
            ),
            "TOTAL_UNIQUE_TRADES_WITHIN_SHARDS": (
                "deduplicated within each verified shard only; this is not a claim "
                "of global cross-shard uniqueness"
            ),
        },
    }
    METRICS.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


if __name__ == "__main__":
    print(json.dumps(build()["totals"], sort_keys=True))
