#!/usr/bin/env python3
"""Build the fail-closed cross-repository implementation closure receipt."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def load(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return default


def git_sha(root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--alina-root", required=True)
    parser.add_argument("--dataset-root", default=".")
    parser.add_argument("--output", default="catalog/GLOBAL_IMPLEMENTATION_CLOSURE.json")
    args = parser.parse_args()
    alina = Path(args.alina_root)
    dataset = Path(args.dataset_root)
    phase = load(dataset / "control/alina-phase.json", {})
    metrics = load(dataset / "catalog/DATA_METRICS.json", {})
    watchdog = load(dataset / "catalog/CAMPAIGN_WATCHDOG_RECEIPT.json", {})
    event_status = load(alina / "docs/event-intelligence-120-status.json", {})
    event_summary = event_status.get("summary") if isinstance(event_status, dict) else {}
    families = {}
    for family in ("copy_vault", "lead_lag", "cross_venue_dislocation"):
        families[family] = {
            "state": "UNMEASURABLE",
            "reason": "FINAL_VALIDATION_REQUIRED",
            "paper_only": True,
            "read_only": True,
            "real_execution": False,
        }
    body = {
        "schema": "alina.global_implementation_closure.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "alina_head": git_sha(alina),
        "dataset_v2_head": git_sha(dataset),
        "phase": phase,
        "event_intelligence": {
            "idea_count": len(event_status.get("items", [])) if isinstance(event_status, dict) else 0,
            "summary": event_summary or {},
            "wiring_complete": bool(
                event_summary
                and not any(int(event_summary.get(key, 0)) for key in (
                    "MISSING", "BROKEN", "IMPLEMENTED_BUT_NOT_WIRED", "IMPLEMENTED_BUT_PARTIAL"
                ))
            ),
            "economic_proof_allowed": False,
        },
        "dataset": {
            "metrics_digest": metrics.get("metrics_digest"),
            "coverage": metrics.get("totals", {}),
            "watchdog_status": watchdog.get("watchdog_status"),
            "campaign_count": watchdog.get("campaign_count"),
        },
        "families": families,
        "security": {
            "paper_only": True,
            "read_only": True,
            "real_execution": False,
            "carry": "DISABLED_BY_SCOPE",
            "execution_keys_present": False,
        },
        "cloud_only": True,
        "implementation_complete": False,
        "final_validation_complete": False,
    }
    body["receipt_digest"] = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(body, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "receipt_digest": body["receipt_digest"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
