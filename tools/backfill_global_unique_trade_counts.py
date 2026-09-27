#!/usr/bin/env python3
"""Compute reproducible cross-shard unique trade counts from immutable assets."""
from __future__ import annotations
import argparse, hashlib, json, os, sqlite3, shutil, tempfile
from pathlib import Path
from typing import Any, Mapping
from backfill_exact_trade_counts import _download, _native_trade_keys

ROOT=Path(__file__).resolve().parents[1]


def _persist_manifest_unique_counts(
    row: Mapping[str, Any],
    *,
    unique_count: int,
    exact: bool,
) -> None:
    manifest_path = ROOT / str(row.get("manifest_path") or "")
    if not manifest_path.is_file():
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(manifest, dict):
        return
    manifest["unique_trade_count"] = int(unique_count) if exact else None
    manifest["unique_trade_count_exact"] = bool(exact)
    temporary = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, manifest_path)


def _unique_candidate(row: Mapping[str, Any], covered: set[str]) -> bool:
    dataset_id = str(row.get("dataset_id") or "")
    if not dataset_id or dataset_id in covered:
        return False
    if row.get("trade_count_exact") is not True:
        return False
    return bool(
        row.get("release_repository")
        and row.get("release_tag")
        and row.get("release_asset")
        and row.get("sha256")
        and row.get("bytes")
    )


def _remaining(rows: list[object], covered: set[str]) -> list[Mapping[str, Any]]:
    return [
        row for row in rows
        if isinstance(row, Mapping) and _unique_candidate(row, covered)
    ]
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
    prior={}
    if PATCH_PATH.exists():
        prior=json.loads(PATCH_PATH.read_text(encoding="utf-8"))
    counts=prior.get("counts") if isinstance(prior.get("counts"),dict) else {}
    covered=set(prior.get("covered_dataset_ids") or [])
    candidates=sorted(
        _remaining(rows, covered),
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
                total=0; unique=0; global_new=0; exact=True; shard_ids=set()
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
                            inserted = int(db.total_changes > before)
                            global_new += inserted
                            shard_ids.add(d)
                if not exact:
                    failed.append({"dataset_id":dataset_id,"reason":"identity_missing"})
                    continue
                unique=len(shard_ids)
                counts[dataset_id]={
                    "trade_count_scanned": total,
                    "unique_trade_count": unique,
                    "unique_trade_count_exact": True,
                    "global_new_identity_count": global_new,
                    "cross_shard_overlap_count": max(0, unique - global_new),
                    "identity_version": "native-id-or-venue-family-symbol-time-side-price-size-v1",
                }
                _persist_manifest_unique_counts(
                    row,
                    unique_count=len(shard_ids),
                    exact=True,
                )
                covered.add(dataset_id)
                db.commit()
                shutil.rmtree(Path(tmp)/dataset_id,ignore_errors=True)
            except Exception as exc:
                failed.append({"dataset_id":dataset_id,"reason":type(exc).__name__})
        global_count=db.execute("SELECT COUNT(*) FROM ids").fetchone()[0]
        identity_rows=[row[0] for row in db.execute("SELECT identity FROM ids ORDER BY identity")]
    for row in rows:
        if isinstance(row, dict):
            patch_row = counts.get(str(row.get("dataset_id") or ""))
            if isinstance(patch_row, Mapping):
                row.update(patch_row)
    INDEX_PATH.write_text(
        json.dumps(index, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    result={
        "schema":"alina.global_unique_trade_patch.v1",
        "method":"sqlite_sha256_identity_dedup_across_immutable_release_assets",
        "identity_version":"native-id-or-venue-family-symbol-time-side-price-size-v1",
        "collision_policy":"native identifiers preferred; deterministic composite fallback is retained and ambiguous missing identities fail closed",
        "counts":dict(sorted(counts.items())),
        "covered_dataset_ids":sorted(covered),
        "attempted":attempted,
        "failed":failed,
        "remaining_candidate_shards":len(_remaining(rows, covered)),
        "global_unique_trade_count":global_count,
        "global_identity_digest":hashlib.sha256(json.dumps(identity_rows,separators=(",",":")).encode()).hexdigest(),
        "cross_shard_overlap_count":sum(int(v.get("cross_shard_overlap_count") or 0) for v in counts.values() if isinstance(v,Mapping)),
        "coverage_complete":len(failed)==0 and not _remaining(rows, covered),
    }
    PATCH_PATH.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:result[k] for k in ("attempted","global_unique_trade_count","remaining_candidate_shards","coverage_complete")},sort_keys=True))
if __name__=="__main__": main()
