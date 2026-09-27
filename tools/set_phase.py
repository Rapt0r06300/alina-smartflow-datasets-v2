#!/usr/bin/env python3
"""Apply one idempotent manual phase transition and persist its receipt."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def write_receipt(state, *, previous_phase, previous_epoch, request_id, path):
    receipt = {
        "schema": "alina.phase_transition_receipt.v1",
        "request_id": request_id,
        "previous_phase": previous_phase,
        "previous_epoch": previous_epoch,
        "new_phase": state["phase"],
        "new_epoch": state["epoch"],
        "state_digest": digest(state),
        "transitioned_at_utc": state["requested_at_utc"],
        "paper_only": True,
        "read_only": True,
        "real_execution": False,
    }
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        old = json.loads(target.read_text(encoding="utf-8"))
        stable = dict(receipt)
        stable.pop("transitioned_at_utc", None)
        old_stable = dict(old)
        old_stable.pop("transitioned_at_utc", None)
        if stable != old_stable:
            raise SystemExit("phase receipt identity conflict")
        return
    target.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--phase", choices=["IDLE", "COLLECT", "ANALYZE"], required=True)
    p.add_argument("--request-id", required=True)
    p.add_argument("--requested-by", default="operator")
    p.add_argument("--cutoff-at-utc")
    p.add_argument("--path", default="control/alina-phase.json")
    p.add_argument("--receipt-dir", default="control/phase-receipts")
    a = p.parse_args()
    path = Path(a.path)
    state = json.loads(path.read_text(encoding="utf-8"))
    receipt_path = Path(a.receipt_dir) / (a.request_id + ".json")
    if state.get("request_id") == a.request_id and state.get("phase") == a.phase:
        write_receipt(
            state,
            previous_phase=state.get("phase"),
            previous_epoch=state.get("epoch"),
            request_id=a.request_id,
            path=receipt_path,
        )
        print(json.dumps(state, sort_keys=True))
        return 0

    old_phase = state.get("phase")
    old_epoch = state.get("epoch")
    if old_phase not in {"IDLE", "COLLECT", "ANALYZE"} or not isinstance(old_epoch, int) or old_epoch < 1:
        raise SystemExit("invalid current phase state")
    if a.phase == "ANALYZE" and old_phase != "COLLECT":
        raise SystemExit("ANALYZE requires current COLLECT phase")
    stamp = a.cutoff_at_utc or now()
    if a.phase == "COLLECT":
        next_state = {
            **state,
            "phase": "COLLECT",
            "epoch": old_epoch + (old_phase != "COLLECT"),
            "requested_at_utc": stamp,
            "collection_started_at_utc": stamp,
            "collection_cutoff_at_utc": None,
            "source_collection_epoch": None,
            "analysis_stage": None,
            "requested_by": a.requested_by,
            "request_id": a.request_id,
        }
    elif a.phase == "ANALYZE":
        next_state = {
            **state,
            "phase": "ANALYZE",
            "epoch": old_epoch + 1,
            "requested_at_utc": stamp,
            "collection_cutoff_at_utc": stamp,
            "source_collection_epoch": old_epoch,
            "analysis_stage": "DRAIN",
            "requested_by": a.requested_by,
            "request_id": a.request_id,
        }
    else:
        next_state = {
            **state,
            "phase": "IDLE",
            "epoch": old_epoch + (old_phase != "IDLE"),
            "requested_at_utc": stamp,
            "collection_started_at_utc": None,
            "collection_cutoff_at_utc": None,
            "source_collection_epoch": None,
            "analysis_stage": None,
            "requested_by": a.requested_by,
            "request_id": a.request_id,
        }
    path.write_text(json.dumps(next_state, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    write_receipt(
        next_state,
        previous_phase=old_phase,
        previous_epoch=old_epoch,
        request_id=a.request_id,
        path=receipt_path,
    )
    print(json.dumps(next_state, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
