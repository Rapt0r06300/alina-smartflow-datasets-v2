#!/usr/bin/env python3
"""Build the fail-closed cross-repository implementation closure receipt."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def load(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return default


def digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def git_sha(root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def validate_current_scoreboard_receipt(
    dataset: Path,
    phase: Mapping[str, Any],
) -> tuple[bool, dict[str, Any], str, dict[str, Any]]:
    receipt = load(dataset / "catalog/ANALYSIS_SCOREBOARD_RECEIPT.json", {})
    if not isinstance(receipt, dict) or receipt.get("schema") != "alina.analysis_scoreboard_receipt.v1":
        return False, {}, "CURRENT_SCOREBOARD_RECEIPT_MISSING", {}

    stored_receipt_digest = str(receipt.get("receipt_digest") or "")
    receipt_body = dict(receipt)
    receipt_body.pop("receipt_digest", None)
    if len(stored_receipt_digest) != 64 or digest(receipt_body) != stored_receipt_digest:
        return False, {}, "CURRENT_SCOREBOARD_RECEIPT_DIGEST_INVALID", receipt

    scoreboard = receipt.get("scoreboard")
    if not isinstance(scoreboard, dict):
        return False, {}, "CURRENT_SCOREBOARD_PAYLOAD_MISSING", receipt
    if scoreboard.get("schema_version") != "hypersmart.economic_family_scoreboards.v2":
        return False, {}, "CURRENT_SCOREBOARD_SCHEMA_INVALID", receipt
    if digest(scoreboard) != str(receipt.get("scoreboard_sha256") or ""):
        return False, {}, "CURRENT_SCOREBOARD_HASH_MISMATCH", receipt
    if scoreboard.get("paper_read_only") is not True or scoreboard.get("real_execution") is not False:
        return False, {}, "CURRENT_SCOREBOARD_NOT_PAPER_ONLY", receipt

    campaign_id = str(receipt.get("campaign_id") or "")
    if not campaign_id:
        return False, {}, "CURRENT_SCOREBOARD_CAMPAIGN_MISSING", receipt
    campaign = load(dataset / "catalog/campaigns" / f"{campaign_id}.json", {})
    if not isinstance(campaign, dict):
        return False, {}, "CURRENT_SCOREBOARD_CAMPAIGN_NOT_FOUND", receipt
    if (
        campaign.get("schema_version") != "alina.resumable_campaign.v2"
        or campaign.get("kind") != "scoreboard"
        or campaign.get("creation_phase") != "ANALYZE"
        or campaign.get("status") != "COMPLETE"
    ):
        return False, {}, "CURRENT_SCOREBOARD_CAMPAIGN_NOT_COMPLETE", receipt

    binding_pairs = (
        ("phase_epoch", phase.get("epoch")),
        ("source_collection_epoch", phase.get("source_collection_epoch")),
        ("dataset_selection_id", campaign.get("dataset_selection_id")),
        ("collection_cutoff_at_utc", campaign.get("collection_cutoff_at_utc")),
        ("code_sha", campaign.get("code_sha")),
    )
    for key, expected in binding_pairs:
        if receipt.get(key) != expected:
            return False, {}, f"CURRENT_SCOREBOARD_BINDING_MISMATCH:{key}", receipt

    if campaign.get("phase_epoch") != phase.get("epoch"):
        return False, {}, "CURRENT_SCOREBOARD_PHASE_EPOCH_STALE", receipt
    if campaign.get("source_collection_epoch") != phase.get("source_collection_epoch"):
        return False, {}, "CURRENT_SCOREBOARD_SOURCE_EPOCH_STALE", receipt
    if not receipt.get("evidence_tag") or not receipt.get("evidence_repository"):
        return False, {}, "CURRENT_SCOREBOARD_DURABLE_EVIDENCE_MISSING", receipt
    if receipt.get("paper_only") is not True or receipt.get("read_only") is not True or receipt.get("real_execution") is not False:
        return False, {}, "CURRENT_SCOREBOARD_RECEIPT_SAFETY_INVALID", receipt
    return True, scoreboard, "CURRENT_SCOREBOARD_RECEIPT_VALID", receipt


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
    resilience = load(dataset / "catalog/CAMPAIGN_RESILIENCE_RECEIPT.json", {})
    health = load(dataset / "catalog/DATASET_HEALTH_RECEIPT.json", {})
    scoreboard_valid, scoreboard, scoreboard_reason, scoreboard_receipt = (
        validate_current_scoreboard_receipt(dataset, phase if isinstance(phase, dict) else {})
    )
    event_status = load(alina / "docs/event-intelligence-120-status.json", {})
    event_summary = event_status.get("summary") if isinstance(event_status, dict) else {}

    families = {}
    scoreboard_families = scoreboard.get("families") if scoreboard_valid else {}
    if not isinstance(scoreboard_families, dict):
        scoreboard_families = {}
    source_names = {
        "copy_vault": "copy_vault",
        "lead_lag": "lead_lag",
        "cross_venue_dislocation": "cross_venue_dislocation_v2",
    }
    for family, source_name in source_names.items():
        source = scoreboard_families.get(source_name)
        if not isinstance(source, dict):
            state, reason = "UNMEASURABLE", scoreboard_reason
        elif source.get("verdict") == "KILL":
            state, reason = "KILL", "ECONOMIC_GATE_REJECTED"
        elif source.get("verdict") == "PROMOTE" and source.get("objective_status") == "ATTEINT":
            state, reason = "PROVEN", "NET_DAILY_OBJECTIVE_PROVEN"
        else:
            state, reason = "MORE_DATA", ",".join(
                source.get("verdict_reasons")
                or source.get("objective_reasons")
                or ["MORE_DATA"]
            )
        families[family] = {
            "state": state,
            "reason": reason,
            "net_pnl_usd": source.get("net_pnl_usd") if isinstance(source, dict) else None,
            "evidence_paths": source.get("evidence_paths", []) if isinstance(source, dict) else [],
            "paper_only": True,
            "read_only": True,
            "real_execution": False,
        }

    coverage = health.get("coverage") if isinstance(health, dict) else {}
    if not isinstance(coverage, dict):
        coverage = {}
    event_wiring_complete = bool(
        event_summary
        and not any(
            int(event_summary.get(key, 0))
            for key in ("MISSING", "BROKEN", "IMPLEMENTED_BUT_NOT_WIRED")
        )
    )
    exact_coverage_complete = all(
        coverage.get(key) is True
        for key in (
            "valid_record_count_exact",
            "unique_record_count_exact",
            "trade_count_exact",
            "unique_trade_count_exact",
            "uncompressed_bytes_exact",
        )
    )
    implementation_complete = bool(
        event_wiring_complete
        and exact_coverage_complete
        and watchdog.get("watchdog_status") == "HEALTHY"
        and resilience.get("status") == "READY"
        and phase.get("phase") == "ANALYZE"
        and phase.get("analysis_stage") in {"SCOREBOARD", "DONE"}
        and scoreboard_valid
    )
    final_validation_complete = bool(
        implementation_complete
        and scoreboard.get("schema_version") == "hypersmart.economic_family_scoreboards.v2"
        and all(
            row["state"] in {"PROVEN", "MORE_DATA", "UNMEASURABLE", "KILL"}
            for row in families.values()
        )
        and all(
            not str(row["reason"]).startswith("CURRENT_SCOREBOARD_")
            for row in families.values()
        )
    )
    body = {
        "schema": "alina.global_implementation_closure.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "alina_head": git_sha(alina),
        "dataset_v2_head": git_sha(dataset),
        "phase": phase,
        "event_intelligence": {
            "idea_count": len(event_status.get("items", [])) if isinstance(event_status, dict) else 0,
            "summary": event_summary or {},
            "wiring_complete": event_wiring_complete,
            "partial_proof_count": int((event_summary or {}).get("IMPLEMENTED_BUT_PARTIAL", 0)),
            "economic_proof_complete": event_wiring_complete
            and int((event_summary or {}).get("IMPLEMENTED_BUT_PARTIAL", 0)) == 0,
            "economic_proof_allowed": False,
        },
        "dataset": {
            "metrics_digest": metrics.get("metrics_digest"),
            "coverage": metrics.get("totals", {}),
            "watchdog_status": watchdog.get("watchdog_status"),
            "campaign_count": watchdog.get("campaign_count"),
        },
        "scoreboard_provenance": {
            "valid": scoreboard_valid,
            "reason": scoreboard_reason,
            "campaign_id": scoreboard_receipt.get("campaign_id") if isinstance(scoreboard_receipt, dict) else None,
            "phase_epoch": scoreboard_receipt.get("phase_epoch") if isinstance(scoreboard_receipt, dict) else None,
            "source_collection_epoch": scoreboard_receipt.get("source_collection_epoch") if isinstance(scoreboard_receipt, dict) else None,
            "dataset_selection_id": scoreboard_receipt.get("dataset_selection_id") if isinstance(scoreboard_receipt, dict) else None,
            "scoreboard_sha256": scoreboard_receipt.get("scoreboard_sha256") if isinstance(scoreboard_receipt, dict) else None,
            "evidence_tag": scoreboard_receipt.get("evidence_tag") if isinstance(scoreboard_receipt, dict) else None,
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
        "implementation_complete": implementation_complete,
        "final_validation_complete": final_validation_complete,
    }
    body["receipt_digest"] = digest(body)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(body, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output),
                "scoreboard_provenance_valid": scoreboard_valid,
                "receipt_digest": body["receipt_digest"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
