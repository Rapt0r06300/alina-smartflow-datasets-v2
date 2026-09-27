#!/usr/bin/env python3
"""Measure exact uncompressed byte sizes for immutable release assets."""
from __future__ import annotations
import argparse, gzip, hashlib, json, shutil, tempfile
from pathlib import Path
from typing import Mapping
from backfill_exact_trade_counts import _download

ROOT=Path(__file__).resolve().parents[1]
INDEX=ROOT/"catalog"/"DATA_INDEX.json"
PATCH=ROOT/"catalog"/"UNCOMPRESSED_SIZE_PATCH.json"

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--limit",type=int,default=200)
    a=p.parse_args()
    index=json.loads(INDEX.read_text(encoding="utf-8"))
    rows=index.get("shards")
    prior=json.loads(PATCH.read_text(encoding="utf-8")) if PATCH.exists() else {"sizes":{}}
    sizes=prior.get("sizes") if isinstance(prior.get("sizes"),dict) else {}
    all_rows=[r for r in rows if isinstance(r,Mapping) and r.get("dataset_id")]
    for row in all_rows:
        dataset_id=str(row["dataset_id"])
        if dataset_id in sizes:
            continue
        if not (row.get("release_repository") and row.get("release_tag") and row.get("release_asset")):
            sizes[dataset_id]={"status":"UNAVAILABLE","reason":"no_immutable_release_asset"}
    candidates=sorted([r for r in all_rows if str(r.get("dataset_id")) not in sizes],key=lambda r:str(r.get("dataset_id")))[:max(1,a.limit)]
    failed=[]; attempted=0
    with tempfile.TemporaryDirectory(prefix="alina-uncompressed-") as tmp:
        for row in candidates:
            attempted+=1; dataset_id=str(row["dataset_id"])
            try:
                asset=_download(row,Path(tmp)/dataset_id)
                total=0
                with gzip.open(asset,"rb") as handle:
                    for chunk in iter(lambda:handle.read(4*1024*1024),b""): total+=len(chunk)
                sizes[dataset_id]={"uncompressed_bytes":total,"compressed_bytes":int(row.get("bytes") or 0),"asset_sha256":hashlib.sha256(asset.read_bytes()).hexdigest()}
            except Exception as exc:
                reason=f"{type(exc).__name__}:{str(exc)[:240]}"
                failed.append({"dataset_id":dataset_id,"reason":reason})
                sizes[dataset_id]={"status":"UNAVAILABLE","reason":reason}
            shutil.rmtree(Path(tmp)/dataset_id,ignore_errors=True)
    remaining=len([r for r in rows if isinstance(r,Mapping) and str(r.get("dataset_id")) not in sizes and r.get("release_repository") and r.get("release_tag") and r.get("release_asset")])
    body={"schema":"alina.uncompressed_size_patch.v1","method":"exact_gzip_decompression_byte_count","sizes":dict(sorted(sizes.items())),"attempted":attempted,"failed":failed,"remaining_assets":remaining,"coverage_complete":remaining==0 and not failed}
    PATCH.write_text(json.dumps(body,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"attempted":attempted,"remaining_assets":remaining,"coverage_complete":body["coverage_complete"]},sort_keys=True))
if __name__=="__main__": main()
