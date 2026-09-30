from pathlib import Path


def _advance_analysis_block() -> str:
    text = Path(".github/workflows/resumable-campaign-controller.yml").read_text(
        encoding="utf-8"
    )
    marker = "  advance_analysis:\n"
    assert marker in text
    return text.split(marker, 1)[1]


def test_bounded_work_refreshes_closure_before_stage_advancement() -> None:
    block = _advance_analysis_block()
    assert "gh workflow run global-implementation-closure.yml" in block
    assert "gh workflow run analysis-stage-controller.yml" not in block


def test_global_closure_owns_followup_stage_dispatch() -> None:
    text = Path(".github/workflows/global-implementation-closure.yml").read_text(
        encoding="utf-8"
    )
    assert "gh workflow run analysis-stage-controller.yml" in text
