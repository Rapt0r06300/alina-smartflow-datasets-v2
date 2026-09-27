#!/usr/bin/env python3
"""Fail-closed phase/epoch gate for Dataset V2 campaign creation and workers."""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime
from pathlib import Path

PHASES={"IDLE","COLLECT","ANALYZE"}
COLLECT_KINDS={"market_collection","copy_vault_collection","official_archive_collection","event_intelligence_collection"}
ANALYZE_KINDS={"replay","backtest","module_pnl_proof"}

def load(path: Path) -> dict:
    try:
        value=json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"invalid phase state: {exc}")
    if not isinstance(value,dict):
        raise SystemExit("invalid phase state: expected object")
    required={"schema_version","phase","epoch","requested_at_utc","collection_started_at_utc",
              "collection_cutoff_at_utc","source_collection_epoch","analysis_stage"}
    missing=required-set(value)
    if missing:
        raise SystemExit(f"invalid phase state: missing {sorted(missing)}")
    if value["schema_version"] != 1 or value["phase"] not in PHASES:
        raise SystemExit("invalid phase schema or phase")
    if not isinstance(value["epoch"],int) or value["epoch"] < 1:
        raise SystemExit("invalid phase epoch")
    for key in ("requested_at_utc","collection_started_at_utc","collection_cutoff_at_utc"):
        if value[key] is not None:
            try: datetime.fromisoformat(str(value[key]).replace("Z","+00:00"))
            except ValueError: raise SystemExit(f"invalid timestamp: {key}")
    phase=value["phase"]
    if phase=="IDLE" and any(value[k] is not None for k in ("collection_started_at_utc","collection_cutoff_at_utc","source_collection_epoch","analysis_stage")):
        raise SystemExit("IDLE state contains active-phase fields")
    if phase=="COLLECT" and (value["collection_started_at_utc"] is None or value["collection_cutoff_at_utc"] is not None or value["source_collection_epoch"] is not None or value["analysis_stage"] is not None):
        raise SystemExit("invalid COLLECT state")
    if phase=="ANALYZE" and (value["collection_cutoff_at_utc"] is None or not isinstance(value["source_collection_epoch"],int) or value["analysis_stage"] is None):
        raise SystemExit("invalid ANALYZE state")
    return value

def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=["read","allow","manifest"])
    p.add_argument("--state",default="control/alina-phase.json")
    p.add_argument("--kind")
    p.add_argument("--manifest")
    args=p.parse_args()
    state=load(Path(args.state))
    if args.command=="read":
        print(json.dumps(state,sort_keys=True))
        return 0
    if args.command=="allow":
        if not args.kind: raise SystemExit("--kind required")
        allowed=(state["phase"]=="COLLECT" and args.kind in COLLECT_KINDS) or (state["phase"]=="ANALYZE" and args.kind in ANALYZE_KINDS)
        if not allowed: return 1
        print(json.dumps({"phase":state["phase"],"phase_epoch":state["epoch"],"source_collection_epoch":state["source_collection_epoch"],"collection_cutoff_at_utc":state["collection_cutoff_at_utc"]},sort_keys=True))
        return 0
    if not args.manifest: raise SystemExit("--manifest required")
    try: manifest=json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    except (OSError,ValueError) as exc: raise SystemExit(f"invalid manifest: {exc}")
    if manifest.get("schema_version")!="alina.resumable_campaign.v2":
        raise SystemExit("phase-aware worker refuses v1 manifest")
    if manifest.get("creation_phase")!=state["phase"] or manifest.get("phase_epoch")!=state["epoch"]:
        raise SystemExit("manifest phase/epoch mismatch")
    if state["phase"]=="ANALYZE":
        if manifest.get("source_collection_epoch")!=state["source_collection_epoch"] or manifest.get("collection_cutoff_at_utc")!=state["collection_cutoff_at_utc"]:
            raise SystemExit("manifest analysis freeze mismatch")
    print(json.dumps({"phase":state["phase"],"epoch":state["epoch"],"campaign_id":manifest.get("campaign_id")},sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
