#!/usr/bin/env python3
"""Build a fail-closed resilience receipt from Dataset V2 campaign lineage."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-dir", default="catalog/campaigns")
    parser.add_argument("--output", default="catalog/CAMPAIGN_RESILIENCE_RECEIPT.json")
    args = parser.parse_args()

    rows = []
    violations = []
    for path in sorted(Path(args.campaign_dir).glob("*.json")):
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            violations.append({"path": str(path), "code": "INVALID_MANIFEST", "detail": str(exc)})
            continue
        campaign_id = str(manifest.get("campaign_id") or path.stem)
        required = {
            "schema_version", "status", "history", "completed_units",
            "checkpoint_lineage", "limits", "attempts", "chunk_index",
            "no_progress_count", "consecutive_failures",
        }
        missing = sorted(required - set(manifest))
        if missing:
            violations.append({"campaign_id": campaign_id, "code": "RECOVERY_FIELDS_MISSING", "fields": missing})
            continue
        if manifest.get("schema_version") != "alina.resumable_campaign.v2":
            violations.append({"campaign_id": campaign_id, "code": "V2_LINEAGE_REQUIRED"})
        for field in ("history", "completed_units", "checkpoint_lineage"):
            if not isinstance(manifest.get(field), (list, dict)):
                violations.append({"campaign_id": campaign_id, "code": f"{field.upper()}_TYPE_INVALID"})
        if any(
            manifest.get(flag) is not expected
            for flag, expected in (
                ("paper_only", True),
                ("read_only", True),
                ("real_execution", False),
            )
        ):
            violations.append({"campaign_id": campaign_id, "code": "UNSAFE_EXECUTION_IDENTITY"})
        units = manifest.get("completed_units") or {}
        for unit_id, unit in units.items():
            if not isinstance(unit, dict) or len(str(unit.get("sha256") or "")) != 64:
                violations.append({
                    "campaign_id": campaign_id,
                    "code": "CHECKPOINT_DIGEST_INVALID",
                    "unit_id": str(unit_id),
                })
        lease = manifest.get("lease")
        if lease is not None:
            required_lease = {"owner_run_id", "lease_token_sha256", "acquired_at", "expires_at"}
            if not isinstance(lease, dict) or required_lease - set(lease):
                violations.append({"campaign_id": campaign_id, "code": "LEASE_LINEAGE_INVALID"})
        rows.append({
            "campaign_id": campaign_id,
            "status": manifest.get("status"),
            "schema_version": manifest.get("schema_version"),
            "checkpoint_count": len(manifest.get("checkpoint_lineage") or []),
            "completed_unit_count": len(units),
            "history_count": len(manifest.get("history") or []),
            "has_lease": lease is not None,
        })

    receipt = {
        "schema": "alina.campaign_resilience_receipt.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "campaign_count": len(rows),
        "campaigns": rows,
        "violations": violations,
        "failure_matrix": {
            "before_checkpoint_write": "DURABLE_STATE_REQUIRED",
            "after_checkpoint_before_lease_release": "CHECKPOINT_LINEAGE_REQUIRED",
            "during_publish": "PUBLICATION_RECEIPT_REQUIRED",
            "after_publish_before_terminal_manifest": "TERMINAL_EVIDENCE_REQUIRED",
            "lease_expiry": "STALE_LEASE_REFUSED",
            "duplicate_worker_wakeup": "UNIT_DIGEST_IDEMPOTENT",
        },
        "status": "BLOCKED" if violations else "READY",
        "paper_only": True,
        "read_only": True,
        "real_execution": False,
    }
    receipt["receipt_digest"] = hashlib.sha256(canonical(receipt).encode()).hexdigest()
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "campaigns": len(rows),
        "violations": len(violations),
        "status": receipt["status"],
        "receipt_digest": receipt["receipt_digest"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
