#!/usr/bin/env python3
"""Monotonically advance ANALYZE stage in the durable Dataset V2 phase state."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


ORDER = ("DRAIN", "QUALITY", "REPLAY", "BACKTEST", "OOS", "FORWARD_PAPER", "PNL_PROOF", "SCOREBOARD", "DONE")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--stage", choices=ORDER, required=True)
    p.add_argument("--request-id", required=True)
    p.add_argument("--expected-epoch", type=int, required=True)
    p.add_argument("--path", default="control/alina-phase.json")
    a = p.parse_args()
    path = Path(a.path)
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("phase") != "ANALYZE":
        raise SystemExit("analysis stage requires ANALYZE phase")
    if int(state.get("epoch", 0)) != a.expected_epoch:
        raise SystemExit("stale phase epoch")
    current = str(state.get("analysis_stage") or "")
    if current not in ORDER:
        raise SystemExit("invalid current analysis stage")
    if ORDER.index(a.stage) < ORDER.index(current):
        raise SystemExit(f"analysis stage regression: {current}->{a.stage}")
    if state.get("request_id") != a.request_id and a.stage == current:
        raise SystemExit("stage identity conflict")
    if a.stage != current:
        state = {**state, "analysis_stage": a.stage, "request_id": a.request_id}
        path.write_text(json.dumps(state, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(state, sort_keys=True))


if __name__ == "__main__":
    main()
