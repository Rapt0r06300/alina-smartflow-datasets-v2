#!/usr/bin/env python3
"""Produce a durable, fail-closed campaign watchdog receipt."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path


def parse(value):
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _run_state(run_id: str) -> tuple[str, str]:
    if not run_id:
        return "missing", ""
    try:
        cp = subprocess.run(
            ["gh", "run", "view", run_id, "--json", "status,conclusion"],
            text=True,
            capture_output=True,
            check=False,
        )
        if cp.returncode != 0:
            return "unknown", (cp.stderr or "").strip()[-300:]
        payload = json.loads(cp.stdout or "{}")
        return str(payload.get("status") or "unknown"), str(payload.get("conclusion") or "")
    except (OSError, ValueError):
        return "unknown", "gh_unavailable"


def _dispatch_successor(row: dict, repository: str, now: datetime) -> tuple[bool, str]:
    campaign_id = str(row.get("campaign_id") or "")
    cursor = row.get("cursor") if isinstance(row.get("cursor"), dict) else {}
    marker = cursor.get("successor_dispatch_at_utc")
    if marker:
        try:
            if parse(marker) + timedelta(minutes=20) > now:
                return False, "dispatch_recent"
        except (TypeError, ValueError):
            pass
    predecessor = str(cursor.get("last_run_id") or "")
    status, detail = _run_state(predecessor)
    if predecessor and status != "completed":
        return False, "predecessor_active"
    command = [
        "gh", "workflow", "run", "resumable-campaign-worker.yml",
        "--repo", repository,
        "--ref", "main",
        "-f", f"campaign_id={campaign_id}",
        "-f", f"phase_epoch={row.get('phase_epoch')}",
        "-f", f"generation={int(row.get('chunk_index') or 0)}",
        "-f", f"predecessor_run_id={predecessor or 'unknown'}",
        "-f", f"requested_handoff_at_utc={now.isoformat().replace('+00:00', 'Z')}",
    ]
    cp = subprocess.run(command, text=True, capture_output=True, check=False)
    if cp.returncode != 0:
        return False, (cp.stderr or cp.stdout or "dispatch_failed").strip()[-500:]
    cursor["successor_dispatch_at_utc"] = now.isoformat().replace("+00:00", "Z")
    row["cursor"] = cursor
    row["updated_at"] = now.isoformat().replace("+00:00", "Z")
    return True, "dispatched"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--campaign-root", default="catalog/campaigns")
    p.add_argument("--phase-state", default="control/alina-phase.json")
    p.add_argument("--output", default="catalog/CAMPAIGN_WATCHDOG_RECEIPT.json")
    p.add_argument("--dispatch", action="store_true")
    a = p.parse_args()
    now = datetime.now(timezone.utc)
    active = {"PENDING", "RUNNING", "CONTINUATION_REQUIRED", "STUCK"}
    counts = {}
    stuck = []
    expired_leases = []
    unsafe = []
    manifests = sorted(Path(a.campaign_root).glob("*.json"))
    dispatched = []
    dispatch_failures = []
    lease_repairs = []
    phase = {}
    phase_error = None
    try:
        phase = json.loads(Path(a.phase_state).read_text(encoding="utf-8"))
        if (
            not isinstance(phase, dict)
            or phase.get("phase") not in {"IDLE", "COLLECT", "ANALYZE"}
            or not isinstance(phase.get("epoch"), int)
        ):
            raise ValueError("invalid phase state")
    except (OSError, ValueError):
        phase = {}
        phase_error = "invalid_phase_state"
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    for path in manifests:
        row = json.loads(path.read_text(encoding="utf-8"))
        status = str(row.get("status") or "")
        counts[status] = counts.get(status, 0) + 1
        if status in active and (
            row.get("paper_only") is not True
            or row.get("read_only") is not True
            or row.get("real_execution") is not False
        ):
            unsafe.append(path.name)
        if status == "STUCK":
            stuck.append(str(row.get("campaign_id") or path.stem))
        if (
            a.dispatch
            and phase.get("phase") == "COLLECT"
            and row.get("creation_phase") == "COLLECT"
            and row.get("phase_epoch") == phase.get("epoch")
            and status == "CONTINUATION_REQUIRED"
            and repository
        ):
            ok, detail = _dispatch_successor(row, repository, now)
            if ok:
                dispatched.append(str(row.get("campaign_id") or path.stem))
                path.write_text(
                    json.dumps(row, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8",
                )
            else:
                dispatch_failures.append({
                    "campaign_id": str(row.get("campaign_id") or path.stem),
                    "reason": detail,
                })
        lease = row.get("lease")
        if isinstance(lease, dict) and lease.get("expires_at"):
            try:
                lease_expired = parse(lease["expires_at"]) <= now
            except (TypeError, ValueError):
                lease_expired = True
            if lease_expired and status in active:
                campaign_id = str(row.get("campaign_id") or path.stem)
                expired_leases.append(campaign_id)
                # Expired ownership must not remain resumable or appear alive to
                # the operator surface. Preserve the evidence, revoke the lease,
                # and force the next worker to reconcile from the last checkpoint.
                history = row.setdefault("history", [])
                history.append({
                    "at_utc": now.isoformat().replace("+00:00", "Z"),
                    "event": "WATCHDOG_LEASE_EXPIRED",
                    "previous_status": status,
                    "previous_lease": dict(lease),
                })
                row["lease"] = None
                row["status"] = "STUCK"
                row["stuck_reason"] = "LEASE_EXPIRED_REQUIRES_RECONCILIATION"
                row["updated_at"] = now.isoformat().replace("+00:00", "Z")
                lease_repairs.append(campaign_id)
                path.write_text(
                    json.dumps(row, sort_keys=True, indent=2) + "\\n",
                    encoding="utf-8",
                )
    receipt = {
        "schema": "alina.campaign_watchdog_receipt.v1",
        "generated_at_utc": now.isoformat().replace("+00:00", "Z"),
        "campaign_count": len(manifests),
        "status_counts": dict(sorted(counts.items())),
        "stuck_campaigns": sorted(stuck),
        "expired_leases": sorted(expired_leases),
        "lease_repairs": sorted(lease_repairs),
        "unsafe_campaigns": sorted(unsafe),
        "successors_dispatched": sorted(dispatched),
        "successor_dispatch_failures": sorted(
            dispatch_failures, key=lambda item: item["campaign_id"]
        ),
        "phase_checked": phase,
        "phase_error": phase_error,
        "paper_only": True,
        "read_only": True,
        "real_execution": False,
        "watchdog_status": (
            "BLOCKED"
            if unsafe or phase_error
            else ("ATTENTION" if stuck or expired_leases or dispatch_failures else "HEALTHY")
        ),
    }
    target = Path(a.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
