from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "create-resumable-campaigns.yml"


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_campaign_creation_workflow_has_single_canonical_structure() -> None:
    text = _text()
    assert text.count("\njobs:\n") == 1
    assert text.count("\n  launch:\n") == 1
    assert text.count("make_campaign() {") == 1
    assert text.count("PHASE_ARGS+=(--operator-request-id") == 1


def test_analysis_selection_identity_is_exact_sha256_binding() -> None:
    text = _text()
    assert 'DATA_INDEX_SHA="$(sha256sum catalog/DATA_INDEX.json' in text
    assert 'DATASET_SELECTION_ID="$(printf' in text
    assert 'grep -Eq \'^[0-9a-f]{64}$\'' in text
    assert '--dataset-selection-id "$DATASET_SELECTION_ID"' in text
    assert '--dataset-selection-id "phase-' not in text


def test_workflow_has_no_post_launch_duplicated_campaign_body() -> None:
    text = _text()
    launch = text.index("\n  launch:\n")
    tail = text[launch:]
    assert "make_campaign() {" not in tail
    assert "PHASE_ARGS+=(--source-collection-epoch" not in tail
