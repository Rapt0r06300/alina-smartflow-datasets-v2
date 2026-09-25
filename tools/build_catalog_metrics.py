#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
INDEX=ROOT/"catalog"/"DATA_INDEX.json"
METRICS=ROOT/"catalog"/"DATA_METRICS.json"

def build():
    idx=json.loads(INDEX.read_text(encoding="utf-8"))
    shards=idx.get("shards") or []
    totals={"TOTAL_SHARDS":len(shards),"SAFE_SHARDS":0,"PARTIAL_SHARDS":0,"REJECTED_SHARDS":0,"REPLAYABLE_SHARDS":0,
            "TOTAL_TRADES_COLLECTED":0,"TOTAL_TRADES_SAFE":0,"TOTAL_TRADES_PARTIAL":0,"TOTAL_TRADES_REJECTED":0,"TOTAL_TRADES_REPLAYABLE":0,
            "TOTAL_TRADE_RECORDS":0,"TRADE_SHARDS_WITH_EXACT_COUNT":0,"TRADE_SHARDS_MISSING_EXACT_COUNT":0,
            "TOTAL_RECORDS":0,"TOTAL_SAFE_RECORDS":0,"TOTAL_REPLAYABLE_RECORDS":0,"TOTAL_COMPRESSED_BYTES":0,"TOTAL_UNCOMPRESSED_BYTES":0}
    by_venue={}; by_symbol={}; by_family={}
    def bucket(table,key):
        if key not in table: table[key]={"shards":0,"records":0,"trades":0,"safe_trades":0,"replayable_trades":0,"bytes":0}
        return table[key]
    for row in shards:
        status=str(row.get("quality_status") or "")
        replay=bool(row.get("replay_compatible"))
        records=int(row.get("record_count") or row.get("event_count") or 0)
        trade_count_raw=row.get("trade_count")
        trades=int(trade_count_raw or 0)
        trade_family=str(row.get("family") or "").lower() in {"trades","agg_trades","fills","userfills","user_fills","copy_vault_fills"}
        if trade_family:
            totals["TOTAL_TRADE_RECORDS"]+=records
            if trade_count_raw is None:
                totals["TRADE_SHARDS_MISSING_EXACT_COUNT"]+=1
            else:
                totals["TRADE_SHARDS_WITH_EXACT_COUNT"]+=1
        b=int(row.get("bytes") or 0)
        totals["TOTAL_RECORDS"]+=records; totals["TOTAL_COMPRESSED_BYTES"]+=b
        if status=="SAFE": totals["SAFE_SHARDS"]+=1; totals["TOTAL_SAFE_RECORDS"]+=records; totals["TOTAL_TRADES_SAFE"]+=trades
        elif status=="PARTIAL": totals["PARTIAL_SHARDS"]+=1; totals["TOTAL_TRADES_PARTIAL"]+=trades
        elif status=="REJECT": totals["REJECTED_SHARDS"]+=1; totals["TOTAL_TRADES_REJECTED"]+=trades
        if replay: totals["REPLAYABLE_SHARDS"]+=1; totals["TOTAL_REPLAYABLE_RECORDS"]+=records; totals["TOTAL_TRADES_REPLAYABLE"]+=trades
        totals["TOTAL_TRADES_COLLECTED"]+=trades
        for table,key in ((by_venue,str(row.get("venue") or "unknown").lower()),(by_symbol,str(row.get("symbol") or "unknown").upper()),(by_family,str(row.get("family") or "unknown").lower())):
            d=bucket(table,key); d["shards"]+=1; d["records"]+=records; d["trades"]+=trades; d["bytes"]+=b
            if status=="SAFE": d["safe_trades"]+=trades
            if replay: d["replayable_trades"]+=trades
    payload={"schema_version":"alina.data_metrics.v2","method":"catalog_exact_manifest_counts_no_byte_estimation","totals":totals,
             "by_venue":dict(sorted(by_venue.items())),"by_symbol":dict(sorted(by_symbol.items())),"by_family":dict(sorted(by_family.items()))}
    METRICS.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return payload
if __name__=="__main__": print(json.dumps(build()["totals"],sort_keys=True))