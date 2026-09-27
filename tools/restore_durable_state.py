#!/usr/bin/env python3
"""Reconstruct and validate Dataset V2 durable campaign state on a fresh runner."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

def canonical(v): return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False)
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--campaign-dir",default="catalog/campaigns")
    p.add_argument("--health",default="catalog/DATASET_HEALTH_RECEIPT.json")
    a=p.parse_args()
    manifests=[]
    for path in sorted(Path(a.campaign_dir).glob("*.json")):
        value=json.loads(path.read_text(encoding="utf-8"))
        required={"campaign_id","kind","status","code_sha","dataset_repo","dataset_generation","config_sha256","work_plan_sha256"}
        missing=required-set(value)
        if missing: raise SystemExit(f"{path}: missing {sorted(missing)}")
        if value.get("paper_only") is not True or value.get("read_only") is not True or value.get("real_execution") is not False:
            raise SystemExit(f"{path}: unsafe execution identity")
        manifests.append(value)
    health=json.loads(Path(a.health).read_text(encoding="utf-8"))
    if health.get("schema_version")!="alina.dataset_health_receipt.v1":
        raise SystemExit("unsupported health receipt schema")
    receipt_digest=health.get("receipt_digest")
    body=dict(health); body.pop("receipt_digest",None)
    if hashlib.sha256(canonical(body).encode()).hexdigest()!=receipt_digest:
        raise SystemExit("health receipt digest mismatch")
    print(json.dumps({"campaigns":len(manifests),"health_receipt_digest":receipt_digest,"restore_source":"repository durable state","cache_used":False},sort_keys=True))
if __name__=="__main__": main()
