from __future__ import annotations

import hashlib
import json

import pytest

from tools.persist_analysis_scoreboard import build_improvement_ledger, build_receipt


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


def _full_scoreboard(copy_net, lead_net, cross_net):
    return {
        "schema_version": "hypersmart.economic_family_scoreboards.v2",
        "families": {
            "copy_vault": {"net_pnl_usd": copy_net, "verdict": "MORE_DATA"},
            "lead_lag": {"net_pnl_usd": lead_net, "verdict": "MORE_DATA"},
            "cross_venue_dislocation_v2": {"net_pnl_usd": cross_net, "verdict": "MORE_DATA"},
        },
        "paper_read_only": True,
        "real_execution": False,
    }


def test_ledger_etablit_reference_puis_ne_garde_que_les_ameliorations():
    first = build_improvement_ledger(
        _full_scoreboard(-4.0, 1.0, None),
        None,
        campaign_id="score-1",
        phase_epoch=3,
        source_collection_epoch=2,
        dataset_selection_id="sel-1",
        code_sha="a" * 40,
    )
    assert first["families"]["copy_vault"]["latest"]["status"] == "REFERENCE_ETABLIE"
    assert first["families"]["copy_vault"]["champion"]["net_pnl_usd"] == -4.0
    assert first["families"]["cross_venue_dislocation_v2"]["latest"]["status"] == "NON_MESURABLE"

    second = build_improvement_ledger(
        _full_scoreboard(-2.0, 0.5, -1.0),
        first,
        campaign_id="score-2",
        phase_epoch=4,
        source_collection_epoch=3,
        dataset_selection_id="sel-2",
        code_sha="b" * 40,
    )
    copy_row = second["families"]["copy_vault"]
    assert copy_row["latest"]["status"] == "AMELIORATION"
    assert copy_row["latest"]["delta_vs_previous_champion_usd"] == 2.0
    assert copy_row["champion"]["net_pnl_usd"] == -2.0

    lead_row = second["families"]["lead_lag"]
    assert lead_row["latest"]["status"] == "PAS_D_AMELIORATION"
    assert lead_row["champion"]["net_pnl_usd"] == 1.0
