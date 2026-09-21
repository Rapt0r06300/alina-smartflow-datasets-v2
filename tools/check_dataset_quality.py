#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
reg = json.loads((root / "catalog/DATA_QUALITY_REGISTRY.json").read_text())
cat = json.loads((root / "catalog/DATA_CATALOG.json").read_text())
index = json.loads((root / "catalog/DATA_INDEX.json").read_text())

statuses = set(reg["status_vocabulary"])
assert statuses == {"SAFE", "PARTIAL", "STALE", "REJECT", "NO_DATA"}
assert reg["validation_allowed_statuses"] == ["SAFE"]
assert reg["policy"]["legacy_import_allowed"] is False
assert reg["policy"]["secrets_forbidden"] is True
assert reg["policy"]["self_hosted_forbidden"] is True
assert reg["policy"]["user_pc_forbidden"] is True
assert cat["legacy_sources"]["enabled"] is False
assert cat["storage"]["replay_selection"] == "SAFE_MANIFEST_ONLY"

shards = index.get("shards") or []
assert isinstance(shards, list)
for row in shards:
    assert row["quality_status"] in statuses
    manifest_path = root / row["manifest_path"]
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text())
    assert manifest["dataset_id"] == row["dataset_id"]
    assert manifest["quality_status"] == row["quality_status"]
    assert manifest["validation_allowed"] is (row["quality_status"] == "SAFE")

expected_active = (
    "SAFE"
    if any(row["quality_status"] == "SAFE" for row in shards)
    else ("PARTIAL" if shards else "NO_DATA")
)
assert index["active_data_status"] == expected_active
assert reg["active_dataset"]["status"] == expected_active
assert reg["active_dataset"]["validation_allowed"] is (expected_active == "SAFE")
assert reg["active_dataset"]["proof_of_pnl_allowed"] is (expected_active == "SAFE")
print("Alina dataset V2 policy: OK")
