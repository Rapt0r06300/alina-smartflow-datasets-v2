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
    resilience = load(dataset / "catalog/CAMPAIGN_RESILIENCE_RECEIPT.json", {})
    health = load(dataset / "catalog/DATASET_HEALTH_RECEIPT.json", {})
    scoreboard = load(alina / "runtime/reports/economic_family_scoreboards.json", {})
    event_status = load(alina / "docs/event-intelligence-120-status.json", {})
    event_summary = event_status.get("summary") if isinstance(event_status, dict) else {}
    families = {}
    scoreboard_families = scoreboard.get("families") if isinstance(scoreboard, dict) else {}
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
            state, reason = "UNMEASURABLE", "SCOREBOARD_RECEIPT_MISSING"
        elif source.get("verdict") == "KILL":
            state, reason = "KILL", "ECONOMIC_GATE_REJECTED"
        elif source.get("verdict") == "PROMOTE" and source.get("objective_status") == "ATTEINT":
            state, reason = "PROVEN", "NET_DAILY_OBJECTIVE_PROVEN"
        else:
            state, reason = "MORE_DATA", ",".join(source.get("verdict_reasons") or source.get("objective_reasons") or ["MORE_DATA"])
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
        and not any(int(event_summary.get(key, 0)) for key in (
            "MISSING", "BROKEN", "IMPLEMENTED_BUT_NOT_WIRED"
        ))
    )
    exact_coverage_complete = all(coverage.get(key) is True for key in (
        "valid_record_count_exact", "unique_record_count_exact", "trade_count_exact",
        "unique_trade_count_exact", "uncompressed_bytes_exact",
    ))
    implementation_complete = bool(
        event_wiring_complete
        and exact_coverage_complete
        and watchdog.get("watchdog_status") == "HEALTHY"
        and resilience.get("status") == "READY"
        and phase.get("phase") == "ANALYZE"
        and phase.get("analysis_stage") in {"SCOREBOARD", "DONE"}
    )
    final_validation_complete = bool(
        implementation_complete
        and scoreboard.get("schema_version") == "hypersmart.economic_family_scoreboards.v2"
        and all(row["state"] in {"PROVEN", "MORE_DATA", "UNMEASURABLE", "KILL"} for row in families.values())
        and all(row["reason"] != "SCOREBOARD_RECEIPT_MISSING" for row in families.values())
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
            "economic_proof_complete": event_wiring_complete and int((event_summary or {}).get("IMPLEMENTED_BUT_PARTIAL", 0)) == 0,
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
        "implementation_complete": implementation_complete,
        "final_validation_complete": final_validation_complete,
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
