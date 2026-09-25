from __future__ import annotations
import json
from pathlib import Path
from tools.build_catalog_metrics import build

def test_metrics_file_is_machine_readable_and_counts_shards():
    out=build()
    idx=json.loads((Path(__file__).resolve().parents[1]/"catalog"/"DATA_INDEX.json").read_text())
    assert out["totals"]["TOTAL_SHARDS"]==len(idx.get("shards") or [])
    assert "TOTAL_TRADES_COLLECTED" in out["totals"]
    assert "TOTAL_TRADES_REPLAYABLE" in out["totals"]