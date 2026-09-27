#!/usr/bin/env python3
"""Produce a durable, fail-closed campaign watchdog receipt."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def parse(value):
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--campaign-root", default="catalog/campaigns")
    p.add_argument("--output", default="catalog/CAMPAIGN_WATCHDOG_RECEIPT.json")
    a = p.parse_args()
    now = datetime.now(timezone.utc)
    active = {"PENDING", "RUNNING", "CONTINUATION_REQUIRED", "STUCK"}
    counts = {}
    stuck = []
    expired_leases = []
    unsafe = []
    manifests = sorted(Path(a.campaign_root).glob("*.json"))
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
        lease = row.get("lease")
        if isinstance(lease, dict) and lease.get("expires_at"):
            if parse(lease["expires_at"]) <= now and status in active:
                expired_leases.append(str(row.get("campaign_id") or path.stem))
    receipt = {
        "schema": "alina.campaign_watchdog_receipt.v1",
        "generated_at_utc": now.isoformat().replace("+00:00", "Z"),
        "campaign_count": len(manifests),
        "status_counts": dict(sorted(counts.items())),
        "stuck_campaigns": sorted(stuck),
        "expired_leases": sorted(expired_leases),
        "unsafe_campaigns": sorted(unsafe),
        "paper_only": True,
        "read_only": True,
        "real_execution": False,
        "watchdog_status": "BLOCKED" if unsafe else ("ATTENTION" if stuck or expired_leases else "HEALTHY"),
    }
    target = Path(a.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
