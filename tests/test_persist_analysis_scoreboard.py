from __future__ import annotations

import hashlib
import json

import pytest

from tools.persist_analysis_scoreboard import build_receipt


def _manifest():
    return {
        "schema_version": "alina.resumable_campaign.v2",
        "campaign_id": "analysis-e3-scoreboard-v2",
        "kind": "scoreboard",
        "creation_phase": "ANALYZE",
        "phase_epoch": 3,
        "source_collection_epoch": 2,
        "collection_cutoff_at_utc": "2026-09-29T10:56:59Z",
        "dataset_selection_id": "phase-2-cutoff",
        "code_sha": "a" * 40,
    }


def _scoreboard():
    return {
        "schema_version": "hypersmart.economic_family_scoreboards.v2",
        "families": {"copy_vault": {"verdict": "MORE_DATA"}},
        "paper_read_only": True,
        "real_execution": False,
    }


def test_receipt_binds_current_epoch_selection_and_scoreboard_hash():
    receipt = build_receipt(
        _manifest(),
        _scoreboard(),
        evidence_tag="campaign-evidence-analysis-e3-scoreboard-v2-u0",
        repository="Rapt0r06300/alina-smartflow-datasets-v2",
        unit_id="0",
    )
    expected = hashlib.sha256(
        json.dumps(_scoreboard(), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert receipt["phase_epoch"] == 3
    assert receipt["source_collection_epoch"] == 2
    assert receipt["dataset_selection_id"] == "phase-2-cutoff"
    assert receipt["scoreboard_sha256"] == expected
    assert len(receipt["receipt_digest"]) == 64
    assert receipt["real_execution"] is False


def test_receipt_rejects_non_scoreboard_or_unpinned_selection():
    manifest = _manifest()
    manifest["kind"] = "backtest"
    with pytest.raises(ValueError):
        build_receipt(manifest, _scoreboard(), evidence_tag="tag", repository="repo", unit_id="0")

    manifest = _manifest()
    manifest["dataset_selection_id"] = ""
    with pytest.raises(ValueError):
        build_receipt(manifest, _scoreboard(), evidence_tag="tag", repository="repo", unit_id="0")


def test_receipt_rejects_non_paper_scoreboard():
    scoreboard = _scoreboard()
    scoreboard["real_execution"] = True
    with pytest.raises(ValueError):
        build_receipt(_manifest(), scoreboard, evidence_tag="tag", repository="repo", unit_id="0")
