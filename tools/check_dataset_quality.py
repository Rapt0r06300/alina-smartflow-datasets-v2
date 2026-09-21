#!/usr/bin/env python3
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
reg = json.loads((root / "catalog/DATA_QUALITY_REGISTRY.json").read_text())
cat = json.loads((root / "catalog/DATA_CATALOG.json").read_text())

assert reg["validation_allowed_statuses"] == ["SAFE"]
assert reg["active_dataset"]["status"] == "NO_DATA"
assert reg["active_dataset"]["validation_allowed"] is False
assert reg["policy"]["legacy_import_allowed"] is False
assert reg["policy"]["secrets_forbidden"] is True
assert reg["policy"]["self_hosted_forbidden"] is True
assert reg["policy"]["user_pc_forbidden"] is True
assert cat["legacy_sources"]["enabled"] is False
assert cat["storage"]["replay_selection"] == "SAFE_MANIFEST_ONLY"
print("Alina dataset V2 policy: OK")
