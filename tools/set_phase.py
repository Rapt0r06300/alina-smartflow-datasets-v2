#!/usr/bin/env python3
"""Apply one idempotent manual phase transition to control/alina-phase.json."""
from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
from pathlib import Path

def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--phase",choices=["IDLE","COLLECT","ANALYZE"],required=True)
    p.add_argument("--request-id",required=True)
    p.add_argument("--requested-by",default="operator")
    p.add_argument("--cutoff-at-utc")
    p.add_argument("--path",default="control/alina-phase.json")
    a=p.parse_args()
    path=Path(a.path)
    state=json.loads(path.read_text(encoding="utf-8"))
    if state.get("request_id")==a.request_id and state.get("phase")==a.phase:
        print(json.dumps(state,sort_keys=True))
        return 0
    old_phase=state.get("phase")
    old_epoch=state.get("epoch")
    if old_phase not in {"IDLE","COLLECT","ANALYZE"} or not isinstance(old_epoch,int) or old_epoch<1:
        raise SystemExit("invalid current phase state")
    if a.phase=="ANALYZE" and old_phase!="COLLECT":
        raise SystemExit("ANALYZE requires current COLLECT phase")
    stamp=a.cutoff_at_utc or now()
    if a.phase=="COLLECT":
        next_state={**state,"phase":"COLLECT","epoch":old_epoch+(old_phase!="COLLECT"),
          "requested_at_utc":stamp,"collection_started_at_utc":stamp,"collection_cutoff_at_utc":None,
          "source_collection_epoch":None,"analysis_stage":None,"requested_by":a.requested_by,"request_id":a.request_id}
    elif a.phase=="ANALYZE":
        next_state={**state,"phase":"ANALYZE","epoch":old_epoch+1,"requested_at_utc":stamp,
          "collection_cutoff_at_utc":stamp,"source_collection_epoch":old_epoch,
          "analysis_stage":"DRAIN","requested_by":a.requested_by,"request_id":a.request_id}
    else:
        next_state={**state,"phase":"IDLE","epoch":old_epoch+(old_phase!="IDLE"),
          "requested_at_utc":stamp,"collection_started_at_utc":None,"collection_cutoff_at_utc":None,
          "source_collection_epoch":None,"analysis_stage":None,"requested_by":a.requested_by,"request_id":a.request_id}
    path.write_text(json.dumps(next_state,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(next_state,sort_keys=True))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
