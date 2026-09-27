#!/usr/bin/env python3
"""Reconcile publication receipts with durable campaign manifests fail-closed."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--receipt-dir",default="catalog/receipts")
    p.add_argument("--campaign-dir",default="catalog/campaigns")
    a=p.parse_args()
    errors=[]; checked=0
    for receipt_path in sorted(Path(a.receipt_dir).glob("*.json")):
        row=json.loads(receipt_path.read_text(encoding="utf-8"))
        if row.get("schema")!="alina.publication_receipt.v2":
            continue
        checked+=1
        campaign_id=str(row.get("campaign_id") or "")
        manifest_path=Path(a.campaign_dir)/f"{campaign_id}.json"
        if not manifest_path.is_file():
            errors.append({"receipt":str(receipt_path),"code":"CAMPAIGN_MANIFEST_MISSING"}); continue
        manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
        units=manifest.get("completed_units") or {}
        unit=str(row.get("unit_id"))
        if unit not in units:
            errors.append({"receipt":str(receipt_path),"code":"PUBLISHED_UNIT_NOT_IN_MANIFEST","unit_id":unit})
        if manifest.get("code_sha") not in (None,row.get("alina_head")):
            errors.append({"receipt":str(receipt_path),"code":"ALINA_CODE_SHA_MISMATCH"})
        if row.get("publication_state") not in {"RELEASE_AND_RECEIPT_WRITTEN","RECONCILED"}:
            errors.append({"receipt":str(receipt_path),"code":"PUBLICATION_STATE_NOT_RECONCILABLE"})
    digest=hashlib.sha256(json.dumps({"checked":checked,"errors":errors},sort_keys=True,separators=(",",":")).encode()).hexdigest()
    print(json.dumps({"checked":checked,"errors":len(errors),"reconciliation_digest":digest},sort_keys=True))
    if errors:
        raise SystemExit("publication consistency reconciliation failed")
if __name__=="__main__": main()
