#!/usr/bin/env python3
"""Persist the current ANALYZE scoreboard as an epoch-bound Dataset V2 receipt."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def build_receipt(
    manifest: Mapping[str, Any],
    scoreboard: Mapping[str, Any],
    *,
    evidence_tag: str,
    repository: str,
    unit_id: str,
) -> dict[str, Any]:
    if manifest.get("schema_version") != "alina.resumable_campaign.v2":
        raise ValueError("scoreboard campaign must use resumable campaign v2")
    if manifest.get("kind") != "scoreboard" or manifest.get("creation_phase") != "ANALYZE":
        raise ValueError("receipt requires an ANALYZE scoreboard campaign")
    phase_epoch = manifest.get("phase_epoch")
    source_epoch = manifest.get("source_collection_epoch")
    if isinstance(phase_epoch, bool) or not isinstance(phase_epoch, int) or phase_epoch < 1:
        raise ValueError("invalid phase_epoch")
    if isinstance(source_epoch, bool) or not isinstance(source_epoch, int) or source_epoch < 1:
        raise ValueError("invalid source_collection_epoch")
    selection_id = str(manifest.get("dataset_selection_id") or "")
    code_sha = str(manifest.get("code_sha") or "")
    campaign_id = str(manifest.get("campaign_id") or "")
    cutoff = str(manifest.get("collection_cutoff_at_utc") or "")
    if not campaign_id or not selection_id or not cutoff:
        raise ValueError("campaign identity/selection/cutoff is incomplete")
    if len(code_sha) != 40 or any(ch not in "0123456789abcdef" for ch in code_sha.lower()):
        raise ValueError("invalid pinned code_sha")
    if scoreboard.get("schema_version") != "hypersmart.economic_family_scoreboards.v2":
        raise ValueError("unexpected economic scoreboard schema")
    if scoreboard.get("paper_read_only") is not True or scoreboard.get("real_execution") is not False:
        raise ValueError("scoreboard is not paper/read-only")
    if not evidence_tag or not repository:
        raise ValueError("durable evidence coordinates are required")

    scoreboard_copy = json.loads(json.dumps(dict(scoreboard), sort_keys=True))
    body = {
        "schema": "alina.analysis_scoreboard_receipt.v1",
        "campaign_id": campaign_id,
        "unit_id": str(unit_id),
        "phase_epoch": phase_epoch,
        "source_collection_epoch": source_epoch,
        "collection_cutoff_at_utc": cutoff,
        "dataset_selection_id": selection_id,
        "code_sha": code_sha,
        "evidence_repository": str(repository),
        "evidence_tag": str(evidence_tag),
        "scoreboard_sha256": _digest(scoreboard_copy),
        "scoreboard": scoreboard_copy,
        "paper_only": True,
        "read_only": True,
        "real_execution": False,
    }
    body["receipt_digest"] = _digest(body)
    return body


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-manifest", required=True)
    parser.add_argument("--scoreboard", required=True)
    parser.add_argument("--evidence-tag", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--unit-id", required=True)
    parser.add_argument("--output", default="catalog/ANALYSIS_SCOREBOARD_RECEIPT.json")
    args = parser.parse_args(argv)

    receipt = build_receipt(
        _load(Path(args.campaign_manifest)),
        _load(Path(args.scoreboard)),
        evidence_tag=args.evidence_tag,
        repository=args.repository,
        unit_id=args.unit_id,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "campaign_id": receipt["campaign_id"],
        "phase_epoch": receipt["phase_epoch"],
        "scoreboard_sha256": receipt["scoreboard_sha256"],
        "receipt_digest": receipt["receipt_digest"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
