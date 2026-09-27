#!/usr/bin/env python3
"""Compute reproducible cross-shard unique trade counts from immutable assets."""
from __future__ import annotations
import argparse, hashlib, json, sqlite3, shutil, tempfile
from pathlib import Path
from typing import Any, Mapping
from backfill_exact_trade_counts import _candidate, _download, _native_trade_keys, _load_patch

ROOT=Path(__file__).resolve().parents[1]
INDEX_PATH=ROOT/"catalog"/"DATA_INDEX.json"
PATCH_PATH=ROOT/"catalog"/"TRADE_UNIQUE_COUNT_PATCH.json"

def digest_identity(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--limit",type=int,default=200)
    args=p.parse_args()
    index=json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    rows=index.get("shards")
    if not isinstance(rows,list): raise SystemExit("invalid DATA_INDEX shards")
    exact_patch=_load_patch()
    prior={}
    if PATCH_PATH.exists():
        prior=json.loads(PATCH_PATH.read_text(encoding="utf-8"))
    counts=prior.get("counts") if isinstance(prior.get("counts"),dict) else {}
    covered=set(prior.get("covered_dataset_ids") or [])
    candidates=sorted(
        [r for r in rows if isinstance(r,Mapping) and _candidate(r,exact_patch.get("counts",{})) and str(r.get("dataset_id")) not in covered],
        key=lambda r:str(r.get("dataset_id") or ""),
    )[:max(1,args.limit)]
    attempted=0; failed=[]
    with tempfile.TemporaryDirectory(prefix="alina-global-unique-") as tmp:
        db=sqlite3.connect(Path(tmp)/"identities.sqlite")
        db.execute("CREATE TABLE ids (identity TEXT PRIMARY KEY)")
        for old in prior.get("identity_digests") or []:
            db.execute("INSERT OR IGNORE INTO ids(identity) VALUES (?)",(str(old),))
        for row in candidates:
            attempted+=1; dataset_id=str(row.get("dataset_id") or "")
            try:
                asset=_download(row,Path(tmp)/dataset_id)
                total=0; unique=0; exact=True
                import gzip
                with gzip.open(asset,"rt",encoding="utf-8") as handle:
                    for line in handle:
                        if not line.strip(): continue
                        raw=json.loads(line)
                        if not isinstance(raw,Mapping): continue
                        keys=_native_trade_keys(raw,venue=str(row.get("venue") or "unknown"),family=str(row.get("family") or ""),symbol=str(row.get("symbol") or ""))
                        if keys is None:
                            exact=False; continue
                        total+=len(keys)
                        for key in keys:
                            d=digest_identity(key)
                            before=db.total_changes
                            db.execute("INSERT OR IGNORE INTO ids(identity) VALUES (?)",(d,))
                            unique += int(db.total_changes>before)
                if not exact:
                    failed.append({"dataset_id":dataset_id,"reason":"identity_missing"})
                    continue
                counts[dataset_id]={"trade_count_scanned":total,"unique_trade_count_exact":True}
                covered.add(dataset_id)
                db.commit()
                shutil.rmtree(Path(tmp)/dataset_id,ignore_errors=True)
            except Exception as exc:
                failed.append({"dataset_id":dataset_id,"reason":type(exc).__name__})
        global_count=db.execute("SELECT COUNT(*) FROM ids").fetchone()[0]
        identity_rows=[row[0] for row in db.execute("SELECT identity FROM ids ORDER BY identity")]
    result={
        "schema":"alina.global_unique_trade_patch.v1",
        "method":"sqlite_sha256_identity_dedup_across_immutable_release_assets",
        "counts":dict(sorted(counts.items())),
        "covered_dataset_ids":sorted(covered),
        "attempted":attempted,
        "failed":failed,
        "remaining_candidate_shards":len([r for r in rows if isinstance(r,Mapping) and _candidate(r,exact_patch.get("counts",{})) and str(r.get("dataset_id")) not in covered]),
        "global_unique_trade_count":global_count,
        "global_identity_digest":hashlib.sha256(json.dumps(identity_rows,separators=(",",":")).encode()).hexdigest(),
        "coverage_complete":len(failed)==0 and not [r for r in rows if isinstance(r,Mapping) and _candidate(r,exact_patch.get("counts",{})) and str(r.get("dataset_id")) not in covered],
    }
    PATCH_PATH.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:result[k] for k in ("attempted","global_unique_trade_count","remaining_candidate_shards","coverage_complete")},sort_keys=True))
if __name__=="__main__": main()
