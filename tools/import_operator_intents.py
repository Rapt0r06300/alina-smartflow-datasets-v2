#!/usr/bin/env python3
"""Import immutable operator intents from Alina main into Dataset V2 campaigns."""
from __future__ import annotations
import argparse, hashlib, json, subprocess
from pathlib import Path

COLLECT={"start_collection"}
ANALYZE={"analyze","replay","backtest","oos","forward_paper","module_pnl_proof","scoreboard","full_cycle"}
KIND={"replay":"replay","backtest":"backtest","oos":"backtest","forward_paper":"module_pnl_proof","module_pnl_proof":"module_pnl_proof","scoreboard":"module_pnl_proof"}

def digest(v): return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--alina-root",required=True)
    p.add_argument("--phase",required=True)
    p.add_argument("--phase-epoch",required=True,type=int)
    p.add_argument("--source-collection-epoch",default="")
    p.add_argument("--collection-cutoff-at-utc",default="")
    p.add_argument("--code-sha",required=True)
    a=p.parse_args()
    intent_root=Path(a.alina_root)/"control"/"operator-intents"
    if not intent_root.is_dir(): return
    for path in sorted(intent_root.glob("*.json")):
        row=json.loads(path.read_text(encoding="utf-8"))
        if row.get("paper_only") is not True or row.get("read_only") is not True or row.get("real_execution") is not False:
            raise SystemExit(f"unsafe operator intent: {path}")
        intent=str(row.get("intent") or "")
        if intent not in COLLECT|ANALYZE: continue
        expected_phase="COLLECT" if intent in COLLECT else "ANALYZE"
        if a.phase!=expected_phase: continue
        campaign_kind="market_collection" if intent in COLLECT else KIND.get(intent,"replay")
        request_id=str(row.get("request_id") or "")
        if not request_id: raise SystemExit(f"missing request id: {path}")
        campaign_id="operator-"+request_id[:32]+"-"+campaign_kind
        target=Path("catalog/campaigns")/(campaign_id+".json")
        if target.exists(): continue
        config=dict(row.get("config") or {})
        config["operator_intent"]=intent
        config["request_id"]=request_id
        cfg=digest(config)
        args=["python",str(Path(a.alina_root)/"tools/resumable_campaign.py"),"create",str(target),
              "--campaign-id",campaign_id,"--kind",campaign_kind,"--code-sha",a.code_sha,
              "--dataset-generation","V2_OPERATOR","--config-sha256",cfg,"--work-plan-sha256",digest({"intent":intent}),
              "--cursor-json",json.dumps(config,separators=(",",":")),"--creation-phase",a.phase,"--phase-epoch",str(a.phase_epoch)]
        if a.phase=="ANALYZE":
            args += ["--source-collection-epoch",a.source_collection_epoch,"--collection-cutoff-at-utc",a.collection_cutoff_at_utc,"--dataset-selection-id","operator-"+str(a.source_collection_epoch), "--operator-request-id",request_id]
        subprocess.run(args,check=True)
        print(json.dumps({"request_id":request_id,"campaign_id":campaign_id,"kind":campaign_kind},sort_keys=True))
if __name__=="__main__": main()
