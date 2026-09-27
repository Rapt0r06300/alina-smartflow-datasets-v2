#!/usr/bin/env python3
"""Reconcile frozen Copy-Vault universe through campaign publication."""
from __future__ import annotations
import argparse, hashlib, json
from collections import Counter
from pathlib import Path
from typing import Any

def canonical(v:Any)->str:
    return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False)

def main()->int:
    p=argparse.ArgumentParser()
    p.add_argument("--campaign-dir",default="catalog/campaigns")
    p.add_argument("--output",default="catalog/COPY_VAULT_COVERAGE_RECEIPT.json")
    a=p.parse_args()
    rows=[]
    selected=set(); scheduled=set(); collected=set(); published=set(); qualified=0
    failures=[]
    for path in sorted(Path(a.campaign_dir).glob("copy-vault-*.json")):
        try: m=json.loads(path.read_text(encoding="utf-8"))
        except (OSError,ValueError): failures.append({"path":str(path),"reason":"INVALID_MANIFEST"}); continue
        units=m.get("completed_units") or {}
        campaign_selected=m.get("vault_universe_count")
        campaign_shards=m.get("vault_shard_count")
        if isinstance(campaign_selected,int): selected.add(campaign_selected)
        if isinstance(campaign_shards,int): scheduled.add(campaign_shards)
        for unit_id,u in units.items():
            if not isinstance(u,dict): continue
            result=u.get("result") if isinstance(u.get("result"),dict) else {}
            out=result.get("stdout") or ""
            try: parsed=json.loads(out) if out else {}
            except (TypeError,ValueError): parsed={}
            for key, target in (("vault_count",collected),("vault_shard_count",published)):
                value=parsed.get(key)
                if isinstance(value,int): target.add(value)
            bundle=parsed.get("bundle") if isinstance(parsed.get("bundle"),dict) else {}
            qualified += int(bundle.get("safe_count") or 0)
            if m.get("status") in {"STUCK","FAILED"}:
                failures.append({"campaign_id":m.get("campaign_id"),"status":m.get("status"),"reason":m.get("status_reason")})
        rows.append({
            "campaign_id":m.get("campaign_id"),
            "status":m.get("status"),
            "vault_universe_count":m.get("vault_universe_count"),
            "vault_shard_index":m.get("vault_shard_index"),
            "vault_shard_count":m.get("vault_shard_count"),
            "completed_units":len(units),
            "publication_receipts":sum(1 for unit_id in units if Path("catalog/receipts",f"{m.get('campaign_id')}-u{unit_id}.json").is_file()),
        })
    body={
        "schema":"alina.copy_vault_coverage_receipt.v1",
        "campaign_count":len(rows),
        "campaigns":rows,
        "selected_universe_counts":sorted(selected),
        "scheduled_shard_counts":sorted(scheduled),
        "observed_collected_counts":sorted(collected),
        "observed_published_shard_counts":sorted(published),
        "qualified_shard_count":qualified,
        "failed_or_stuck":failures,
        "reconciliation":{
            "selection_present":bool(selected),
            "sharding_present":bool(scheduled),
            "publication_receipts_present":all(r["publication_receipts"]>=r["completed_units"] for r in rows),
            "no_duplicate_shard_indices":len([r["vault_shard_index"] for r in rows if isinstance(r["vault_shard_index"],int)])==len(set(r["vault_shard_index"] for r in rows if isinstance(r["vault_shard_index"],int))),
            "silent_loss":bool(failures),
        },
        "paper_only":True,"read_only":True,"real_execution":False,
    }
    body["status"]="BLOCKED" if body["reconciliation"]["silent_loss"] or not body["reconciliation"]["selection_present"] else "OBSERVED"
    body["receipt_digest"]=hashlib.sha256(canonical(body).encode()).hexdigest()
    Path(a.output).write_text(json.dumps(body,sort_keys=True,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"campaign_count":len(rows),"status":body["status"],"receipt_digest":body["receipt_digest"]},sort_keys=True))
    return 0
if __name__=="__main__": raise SystemExit(main())
