#!/usr/bin/env python3
"""Validate cross-repository dispatch receipts against campaign manifests."""
from __future__ import annotations

import json
from pathlib import Path


def main():
    root = Path("catalog/dispatch-receipts")
    if not root.is_dir():
        return
    seen = set()
    for path in sorted(root.glob("*.json")):
        receipt = json.loads(path.read_text(encoding="utf-8"))
        required = {
            "schema", "request_id", "campaign_id", "main_code_sha",
            "dataset_repo_sha", "creation_phase", "phase_epoch",
        }
        missing = required - set(receipt)
        if missing:
            raise SystemExit(f"{path}: missing {sorted(missing)}")
        if receipt["schema"] != "alina.dispatch_receipt.v1":
            raise SystemExit(f"{path}: unsupported schema")
        if receipt["paper_only"] is not True or receipt["read_only"] is not True or receipt["real_execution"] is not False:
            raise SystemExit(f"{path}: unsafe receipt")
        if receipt["creation_phase"] not in {"COLLECT", "ANALYZE"} or int(receipt["phase_epoch"]) < 1:
            raise SystemExit(f"{path}: invalid phase identity")
        key = (receipt["request_id"], receipt["campaign_id"])
        if key in seen:
            raise SystemExit(f"{path}: duplicate dispatch identity")
        seen.add(key)
        campaign_path = Path("catalog/campaigns") / (str(receipt["campaign_id"]) + ".json")
        if not campaign_path.is_file():
            raise SystemExit(f"{path}: missing campaign manifest")
        campaign = json.loads(campaign_path.read_text(encoding="utf-8"))
        for field in ("code_sha", "creation_phase", "phase_epoch"):
            expected = receipt["main_code_sha"] if field == "code_sha" else receipt[field]
            actual = campaign.get(field)
            if actual != expected:
                raise SystemExit(f"{path}: campaign {field} mismatch")
    print(f"validated {len(seen)} dispatch receipts")


if __name__ == "__main__":
    main()
