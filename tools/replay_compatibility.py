#!/usr/bin/env python3
from __future__ import annotations
import gzip,json
from pathlib import Path
from typing import Any,Mapping

TRADE_FAMILIES={"trades","agg_trades","fills","userfills","user_fills","copy_vault_fills"}
REPLAYABLE_FAMILIES={"trades","agg_trades","bbo","l2book","l2","book","funding","funding_settlement","open_interest","fills","userfills","user_fills","copy_vault_fills","copy_vault_l2","copy_vault_positions","copy_vault_selection","copy_vault_snapshot","external_events","activeassetctx","instrument_metadata","mark_price","ticker"}

def _open(path:Path):
    return gzip.open(path,"rt",encoding="utf-8") if path.name.endswith(".gz") else path.open(encoding="utf-8")

def inspect_asset(path:str|Path,manifest:Mapping[str,Any])->dict[str,Any]:
    p=Path(path); family=str(manifest.get("family") or "").lower()
    result={"record_count":0,"trade_count":0,"invalid_record_count":0,"out_of_order_count":0,"duplicate_count":0,"gap_count":int((manifest.get("integrity") or {}).get("gap_count") or 0),
            "replay_compatible":False,"replay_schema_version":"alina.replay.v1","replay_reason":"UNVERIFIED"}
    last=None; seen=set()
    try:
        with _open(p) as h:
            for line in h:
                if not line.strip(): continue
                try: row=json.loads(line)
                except Exception: result["invalid_record_count"]+=1; continue
                result["record_count"]+=1
                ts=row.get("exchange_ts_ms",row.get("timestamp_ms",row.get("ts_ms",row.get("timestamp"))))
                try: ts=float(ts)
                except Exception: ts=None
                if ts is None: result["invalid_record_count"]+=1
                elif last is not None and ts < last: result["out_of_order_count"]+=1
                if ts is not None: last=ts
                if family in TRADE_FAMILIES:
                    parsed=row.get("parsed_summary") if isinstance(row,dict) else None
                    count=(parsed or {}).get("event_count") if isinstance(parsed,dict) else None
                    try: count=int(count) if count is not None else 1
                    except Exception: count=1
                    result["trade_count"]+=max(1,count)
                native=row.get("trade_id") or row.get("id") or row.get("exec_id") or row.get("sequence")
                key=(manifest.get("venue"),manifest.get("symbol"),native if native is not None else (ts,row.get("side"),row.get("price"),row.get("size",row.get("qty"))))
                if key in seen: result["duplicate_count"]+=1
                else: seen.add(key)
    except (OSError,EOFError,UnicodeError):
        result["replay_reason"]="TRUNCATED_OR_UNREADABLE"; return result
    if result["record_count"]<=0: result["replay_reason"]="NO_RECORDS"
    elif result["invalid_record_count"]>0: result["replay_reason"]="INVALID_RECORD"
    elif result["out_of_order_count"]>0: result["replay_reason"]="OUT_OF_ORDER"
    elif result["gap_count"]>0: result["replay_reason"]="GAP"
    elif result["duplicate_count"]>0: result["replay_reason"]="DUPLICATES_PRESENT"
    elif family not in REPLAYABLE_FAMILIES: result["replay_reason"]="NO_REPLAY_ADAPTER"
    else: result["replay_compatible"]=True; result["replay_reason"]="SMOKE_OK"
    return result