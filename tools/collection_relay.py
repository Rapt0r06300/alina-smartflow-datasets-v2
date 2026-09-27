#!/usr/bin/env python3
"""Select explicit collection successor dispatches from durable Dataset V2 state."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def parse(value):
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", default="control/alina-phase.json")
    parser.add_argument("--campaign-dir", default="catalog/campaigns")
    parser.add_argument("--max-dispatches", type=int, default=32)
    args = parser.parse_args()

    phase = json.loads(Path(args.phase).read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)
    if phase.get("phase") != "COLLECT":
        print(json.dumps({
            "schema": "alina.collection_relay_plan.v1",
            "phase": phase.get("phase"),
            "dispatches": [],
            "reason": "collection_phase_inactive",
        }, sort_keys=True))
        return 0

    dispatches = []
    for path in sorted(Path(args.campaign_dir).glob("*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        if row.get("schema_version") != "alina.resumable_campaign.v2":
            continue
        if row.get("creation_phase") != "COLLECT" or row.get("phase_epoch") != phase.get("epoch"):
            continue
        if row.get("kind") not in {
            "market_collection", "copy_vault_collection",
            "official_archive_collection", "event_intelligence_collection",
        }:
            continue
        if row.get("status") not in {"PENDING", "CONTINUATION_REQUIRED", "STUCK"}:
            continue
        if row.get("lease") and parse(row["lease"]["expires_at"]) > now:
            continue
        if row.get("next_due_at") and parse(row["next_due_at"]) > now:
            continue
        cursor = row.get("cursor") or {}
        generation = int(cursor.get("generation") or row.get("chunk_index") or 0)
        dispatches.append({
            "campaign_id": row.get("campaign_id"),
            "phase_epoch": phase.get("epoch"),
            "generation": generation + 1,
            "predecessor_run_id": cursor.get("last_run_id"),
            "requested_handoff_at_utc": now.isoformat().replace("+00:00", "Z"),
        })
    dispatches = dispatches[:max(0, args.max_dispatches)]
    print(json.dumps({
        "schema": "alina.collection_relay_plan.v1",
        "phase": phase.get("phase"),
        "phase_epoch": phase.get("epoch"),
        "dispatches": dispatches,
        "paper_only": True,
        "read_only": True,
        "real_execution": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
