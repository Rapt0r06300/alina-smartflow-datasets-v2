#!/usr/bin/env python3
"""Explicit, fail-closed migration of resumable campaign manifests to V2."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--manifest-dir", default="catalog/campaigns")
    p.add_argument("--phase", choices=["COLLECT", "ANALYZE"], required=True)
    p.add_argument("--phase-epoch", type=int, required=True)
    p.add_argument("--source-collection-epoch", type=int)
    p.add_argument("--collection-cutoff-at-utc")
    p.add_argument("--dataset-selection-id")
    p.add_argument("--analysis-stage")
    p.add_argument("--apply", action="store_true")
    a = p.parse_args()
    if a.phase == "ANALYZE" and (
        a.source_collection_epoch is None
        or not a.collection_cutoff_at_utc
        or not a.dataset_selection_id
    ):
        raise SystemExit("ANALYZE migration requires source epoch, cutoff and selection id")

    changed = 0
    for path in sorted(Path(a.manifest_dir).glob("*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        schema = row.get("schema_version")
        if schema == "alina.resumable_campaign.v2":
            continue
        if schema != "alina.resumable_campaign.v1":
            raise SystemExit(f"{path}: unsupported schema {schema!r}")
        if row.get("real_execution") is not False or row.get("paper_only") is not True or row.get("read_only") is not True:
            raise SystemExit(f"{path}: unsafe manifest cannot migrate")
        migrated = {
            **row,
            "schema_version": "alina.resumable_campaign.v2",
            "creation_phase": a.phase,
            "phase_epoch": a.phase_epoch,
            "source_collection_epoch": a.source_collection_epoch,
            "collection_cutoff_at_utc": a.collection_cutoff_at_utc,
            "dataset_selection_id": a.dataset_selection_id,
            "analysis_stage": a.analysis_stage or ({
                "replay": "REPLAY",
                "backtest": "BACKTEST",
                "oos": "OOS",
                "forward_paper": "FORWARD_PAPER",
                "module_pnl_proof": "PNL_PROOF",
                "scoreboard": "SCOREBOARD",
            }.get(str(row.get("kind") or "")) if a.phase == "ANALYZE" else None),
            "checkpoint_lineage": list(row.get("checkpoint_lineage") or []),
            "terminal_evidence_digest": row.get("terminal_evidence_digest") or (
                next(iter(reversed(list((row.get("completed_units") or {}).values()))), {}).get("sha256")
                if row.get("status") == "COMPLETE" else None
            ),
        }
        if a.apply:
            path.write_text(json.dumps(migrated, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        changed += 1
    print(json.dumps({"migrated": changed, "applied": a.apply}, sort_keys=True))


if __name__ == "__main__":
    main()
