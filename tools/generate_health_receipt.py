#!/usr/bin/env python3
"""Generate the lightweight, machine-readable Dataset V2 health receipt."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from typing import Any

def canonical(value: Any) -> str:
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False)

def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))

def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument("--metrics",default="catalog/DATA_METRICS.json")
    p.add_argument("--phase",default="control/alina-phase.json")
    p.add_argument("--campaign-dir",default="catalog/campaigns")
    p.add_argument("--output",default="catalog/DATASET_HEALTH_RECEIPT.json")
    p.add_argument("--dataset-commit",required=True)
    args=p.parse_args()
    metrics=load(Path(args.metrics))
    phase=load(Path(args.phase))
    totals=dict(metrics.get("totals") or {})
    campaigns=[]
    for path in sorted(Path(args.campaign_dir).glob("*.json")):
        try:
            row=load(path)
        except (OSError,ValueError):
            continue
        campaigns.append({
            "campaign_id":row.get("campaign_id"),
            "kind":row.get("kind"),
            "status":row.get("status"),
            "status_reason":row.get("status_reason"),
            "phase_epoch":row.get("phase_epoch"),
            "chunk_index":row.get("chunk_index"),
            "attempts":row.get("attempts"),
            "no_progress_count":row.get("no_progress_count"),
            "consecutive_failures":row.get("consecutive_failures"),
            "lease":row.get("lease"),
            "updated_at":row.get("updated_at"),
        })
    counts={}
    for row in campaigns:
        key=f'{row["kind"]}:{row["status"]}'
        counts[key]=counts.get(key,0)+1
    body={
        "schema_version":"alina.dataset_health_receipt.v1",
        "dataset_commit":args.dataset_commit,
        "metrics_schema_version":metrics.get("schema_version"),
        "metrics_method":metrics.get("method"),
        "phase":phase,
        "totals":totals,
        "by_venue":metrics.get("by_venue") or {},
        "by_family":metrics.get("by_family") or {},
        "campaign_counts":counts,
        "campaigns":campaigns,
        "coverage":{
            "trade_count_exact":bool(totals.get("TOTAL_TRADES_COUNT_COVERAGE_COMPLETE")),
            "unique_trade_count_exact":bool(totals.get("TOTAL_UNIQUE_TRADES_COVERAGE_COMPLETE")),
            "uncompressed_bytes_exact":totals.get("TOTAL_UNCOMPRESSED_BYTES") not in (None,0),
            "safe_shards":int(totals.get("SAFE_SHARDS") or 0),
            "replayable_shards":int(totals.get("REPLAYABLE_SHARDS") or 0),
        },
    }
    body["receipt_digest"]=hashlib.sha256(canonical(body).encode()).hexdigest()
    Path(args.output).write_text(json.dumps(body,sort_keys=True,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"output":args.output,"receipt_digest":body["receipt_digest"],"campaigns":len(campaigns)},sort_keys=True))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
