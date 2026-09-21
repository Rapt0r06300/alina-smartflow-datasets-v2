import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = json.loads((ROOT/"catalog/DATA_QUALITY_REGISTRY.json").read_text())
CAT = json.loads((ROOT/"catalog/DATA_CATALOG.json").read_text())

def test_safe_only_validation():
    assert REG["validation_allowed_statuses"] == ["SAFE"]

def test_starts_empty():
    assert REG["active_dataset"]["status"] == "NO_DATA"
    assert REG["active_dataset"]["validation_allowed"] is False

def test_no_legacy_import():
    assert REG["policy"]["legacy_import_allowed"] is False
    assert CAT["legacy_sources"]["enabled"] is False
    assert CAT["legacy_sources"]["automatic_import"] is False

def test_public_repo_safety():
    assert REG["policy"]["public_data_only"] is True
    assert REG["policy"]["secrets_forbidden"] is True

def test_no_pc_runner():
    assert REG["policy"]["self_hosted_forbidden"] is True
    assert REG["policy"]["user_pc_forbidden"] is True
