import json
from pathlib import Path


def test_analysis_stage_gates_do_not_require_target_work_before_target_entry():
    gates = json.loads(Path("control/analysis-stage-gates.json").read_text(encoding="utf-8"))["stages"]

    # Entering REPLAY re-validates frozen data quality; replay work is created only
    # after the phase authority reaches REPLAY.
    assert "required_campaign_kinds" not in gates["REPLAY"]

    # Every later target is gated by completion of the stage immediately before it.
    assert gates["BACKTEST"]["required_campaign_kinds"] == ["replay"]
    assert gates["OOS"]["required_campaign_kinds"] == ["backtest"]
    assert gates["FORWARD_PAPER"]["required_campaign_kinds"] == ["oos"]
    assert gates["PNL_PROOF"]["required_campaign_kinds"] == ["forward_paper"]
    assert gates["SCOREBOARD"]["required_campaign_kinds"] == ["module_pnl_proof"]


def test_done_still_requires_all_economic_stage_campaigns():
    gates = json.loads(Path("control/analysis-stage-gates.json").read_text(encoding="utf-8"))["stages"]
    assert set(gates["DONE"]["required_campaign_kinds"]) == {
        "replay",
        "backtest",
        "oos",
        "forward_paper",
        "module_pnl_proof",
        "scoreboard",
    }
