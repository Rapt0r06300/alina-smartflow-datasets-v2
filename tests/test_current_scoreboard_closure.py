from __future__ import annotations

import hashlib
import json

from tools.build_global_implementation_closure import (
    digest,
    validate_current_scoreboard_receipt,
)


def _phase():
    return {
        "phase": "ANALYZE",
        "epoch": 3,
        "source_collection_epoch": 2,
        "analysis_stage": "SCOREBOARD",
    }


def _campaign():
    return {
        "schema_version": "alina.resumable_campaign.v2",
        "campaign_id": "analysis-e3-scoreboard-v2",
        "kind": "scoreboard",
        "creation_phase": "ANALYZE",
        "status": "COMPLETE",
        "phase_epoch": 3,
        "source_collection_epoch": 2,
        "dataset_selection_id": "phase-2-cutoff",
        "collection_cutoff_at_utc": "2026-09-29T10:56:59Z",
        "code_sha": "a" * 40,
    }


def _scoreboard():
    return {
        "schema_version": "hypersmart.economic_family_scoreboards.v2",
        "families": {
            "copy_vault": {"verdict": "MORE_DATA"},
            "lead_lag": {"verdict": "MORE_DATA"},
            "cross_venue_dislocation_v2": {"verdict": "KILL"},
        },
        "paper_read_only": True,
        "real_execution": False,
    }


def _write_receipt(root):
    campaign = _campaign()
    scoreboard = _scoreboard()
    (root / "catalog/campaigns").mkdir(parents=True)
    (root / "catalog/campaigns" / f"{campaign['campaign_id']}.json").write_text(
        json.dumps(campaign), encoding="utf-8"
    )
    body = {
        "schema": "alina.analysis_scoreboard_receipt.v1",
        "campaign_id": campaign["campaign_id"],
        "unit_id": "0",
        "phase_epoch": campaign["phase_epoch"],
        "source_collection_epoch": campaign["source_collection_epoch"],
        "collection_cutoff_at_utc": campaign["collection_cutoff_at_utc"],
        "dataset_selection_id": campaign["dataset_selection_id"],
        "code_sha": campaign["code_sha"],
        "evidence_repository": "Rapt0r06300/alina-smartflow-datasets-v2",
        "evidence_tag": "campaign-evidence-analysis-e3-scoreboard-v2-u0",
        "scoreboard_sha256": digest(scoreboard),
        "scoreboard": scoreboard,
        "paper_only": True,
        "read_only": True,
        "real_execution": False,
    }
    body["receipt_digest"] = digest(body)
    (root / "catalog/ANALYSIS_SCOREBOARD_RECEIPT.json").write_text(
        json.dumps(body), encoding="utf-8"
    )
    return body


def test_current_scoreboard_receipt_validates_exact_epoch_binding(tmp_path):
    receipt = _write_receipt(tmp_path)
    valid, scoreboard, reason, loaded = validate_current_scoreboard_receipt(
        tmp_path, _phase()
    )
    assert valid is True
    assert reason == "CURRENT_SCOREBOARD_RECEIPT_VALID"
    assert scoreboard == receipt["scoreboard"]
    assert loaded["dataset_selection_id"] == "phase-2-cutoff"


def test_stale_phase_epoch_is_rejected(tmp_path):
    _write_receipt(tmp_path)
    phase = _phase()
    phase["epoch"] = 4
    valid, _, reason, _ = validate_current_scoreboard_receipt(tmp_path, phase)
    assert valid is False
    assert reason in {
        "CURRENT_SCOREBOARD_BINDING_MISMATCH:phase_epoch",
        "CURRENT_SCOREBOARD_PHASE_EPOCH_STALE",
    }


def test_tampered_scoreboard_is_rejected(tmp_path):
    receipt = _write_receipt(tmp_path)
    receipt["scoreboard"]["families"]["copy_vault"]["verdict"] = "PROMOTE"
    (tmp_path / "catalog/ANALYSIS_SCOREBOARD_RECEIPT.json").write_text(
        json.dumps(receipt), encoding="utf-8"
    )
    valid, _, reason, _ = validate_current_scoreboard_receipt(tmp_path, _phase())
    assert valid is False
    assert reason in {
        "CURRENT_SCOREBOARD_RECEIPT_DIGEST_INVALID",
        "CURRENT_SCOREBOARD_HASH_MISMATCH",
    }
