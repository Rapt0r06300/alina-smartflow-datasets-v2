#!/usr/bin/env python3
"""Import immutable operator intents from Alina main into Dataset V2 campaigns."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

COLLECT = {"start_collection"}
ANALYZE = {
    "analyze",
    "replay",
    "backtest",
    "oos",
    "forward_paper",
    "module_pnl_proof",
    "scoreboard",
    "full_cycle",
}
KIND = {
    "replay": "replay",
    "backtest": "backtest",
    "oos": "oos",
    "forward_paper": "forward_paper",
    "module_pnl_proof": "module_pnl_proof",
    "scoreboard": "scoreboard",
}


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def write_dispatch_receipt(*, campaign_id, request_id, code_sha, dataset_sha, phase, phase_epoch, source_epoch):
    receipt = {
        "schema": "alina.dispatch_receipt.v1",
        "request_id": request_id,
        "campaign_id": campaign_id,
        "main_code_sha": code_sha,
        "dataset_repo_sha": dataset_sha,
        "creation_phase": phase,
        "phase_epoch": phase_epoch,
        "source_collection_epoch": source_epoch,
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID"),
        "dispatched_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "paper_only": True,
        "read_only": True,
        "real_execution": False,
    }
    target = Path("catalog/dispatch-receipts") / (campaign_id + ".json")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        old = json.loads(target.read_text(encoding="utf-8"))
        stable = dict(receipt)
        stable.pop("dispatched_at_utc", None)
        old_stable = dict(old)
        old_stable.pop("dispatched_at_utc", None)
        if stable != old_stable:
            raise SystemExit("dispatch receipt identity conflict")
        return
    target.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def campaign_kinds(intent):
    if intent == "full_cycle":
        return ("replay", "backtest", "oos", "forward_paper", "module_pnl_proof", "scoreboard")
    return (KIND.get(intent, "replay"),)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--alina-root", required=True)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--phase-epoch", required=True, type=int)
    parser.add_argument("--source-collection-epoch", default="")
    parser.add_argument("--collection-cutoff-at-utc", default="")
    parser.add_argument("--code-sha", required=True)
    parser.add_argument("--dataset-repo-sha", required=True)
    args = parser.parse_args()

    intent_root = Path(args.alina_root) / "control" / "operator-intents"
    if not intent_root.is_dir():
        return

    for path in sorted(intent_root.glob("*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        if (
            row.get("paper_only") is not True
            or row.get("read_only") is not True
            or row.get("real_execution") is not False
        ):
            raise SystemExit(f"unsafe operator intent: {path}")

        intent = str(row.get("intent") or "")
        if intent not in COLLECT | ANALYZE:
            continue
        expected_phase = "COLLECT" if intent in COLLECT else "ANALYZE"
        if args.phase != expected_phase:
            continue

        request_id = str(row.get("request_id") or "")
        if not request_id:
            raise SystemExit(f"missing request id: {path}")

        for campaign_kind in campaign_kinds(intent):
            campaign_id = "operator-" + request_id[:32] + "-" + campaign_kind
            target = Path("catalog/campaigns") / (campaign_id + ".json")
            receipt_target = Path("catalog/dispatch-receipts") / (campaign_id + ".json")
            if target.exists():
                if not receipt_target.exists():
                    existing = json.loads(target.read_text(encoding="utf-8"))
                    write_dispatch_receipt(
                        campaign_id=campaign_id,
                        request_id=request_id,
                        code_sha=str(existing.get("code_sha") or args.code_sha),
                        dataset_sha=args.dataset_repo_sha,
                        phase=str(existing.get("creation_phase") or args.phase),
                        phase_epoch=int(existing.get("phase_epoch") or args.phase_epoch),
                        source_epoch=existing.get("source_collection_epoch"),
                    )
                continue

            config = dict(row.get("config") or {})
            config["operator_intent"] = intent
            config["request_id"] = request_id
            config["operator_stage"] = campaign_kind
            config_sha = digest(config)
            plan = {"intent": intent, "stage": campaign_kind}
            command = [
                "python",
                str(Path(args.alina_root) / "tools/resumable_campaign.py"),
                "create",
                str(target),
                "--campaign-id",
                campaign_id,
                "--kind",
                campaign_kind,
                "--code-sha",
                args.code_sha,
                "--dataset-generation",
                "V2_OPERATOR",
                "--config-sha256",
                config_sha,
                "--work-plan-sha256",
                digest(plan),
                "--cursor-json",
                json.dumps(config, separators=(",", ":")),
                "--creation-phase",
                args.phase,
                "--phase-epoch",
                str(args.phase_epoch),
            ]
            if args.phase == "ANALYZE":
                command += [
                    "--source-collection-epoch",
                    args.source_collection_epoch,
                    "--collection-cutoff-at-utc",
                    args.collection_cutoff_at_utc,
                    "--dataset-selection-id",
                    "operator-" + str(args.source_collection_epoch),
                    "--operator-request-id",
                    request_id,
                ]

            env = os.environ.copy()
            env["PYTHONPATH"] = (
                str(Path(args.alina_root) / "src")
                + os.pathsep
                + env.get("PYTHONPATH", "")
            )
            subprocess.run(command, check=True, env=env)
            write_dispatch_receipt(
                campaign_id=campaign_id,
                request_id=request_id,
                code_sha=args.code_sha,
                dataset_sha=args.dataset_repo_sha,
                phase=args.phase,
                phase_epoch=args.phase_epoch,
                source_epoch=args.source_collection_epoch if args.phase == "ANALYZE" else None,
            )
            print(
                json.dumps(
                    {
                        "request_id": request_id,
                        "campaign_id": campaign_id,
                        "kind": campaign_kind,
                    },
                    sort_keys=True,
                )
            )


if __name__ == "__main__":
    main()
