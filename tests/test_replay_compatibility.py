from __future__ import annotations
from pathlib import Path
import json, tempfile, gzip
from tools.replay_compatibility import inspect_asset

def test_trade_asset_count_and_replay_gate():
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/"x.jsonl.gz"
        rows=[{"timestamp_ms":1,"trade_id":"a","price":"1","size":"2"},{"timestamp_ms":2,"trade_id":"b","price":"1","size":"3"}]
        with gzip.open(p,"wt",encoding="utf-8") as h:
            for r in rows: h.write(json.dumps(r)+"\n")
        m={"family":"trades","venue":"binance","symbol":"BTC"}
        out=inspect_asset(p,m)
        assert out["record_count"]==2
        assert out["trade_count"]==2
        assert out["replay_compatible"] is True

def test_out_of_order_is_not_replayable():
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/"x.jsonl"
        p.write_text(json.dumps({"timestamp_ms":2})+"\n"+json.dumps({"timestamp_ms":1})+"\n")
        out=inspect_asset(p,{"family":"trades","venue":"x","symbol":"Y"})
        assert out["out_of_order_count"]==1
        assert out["replay_compatible"] is False
