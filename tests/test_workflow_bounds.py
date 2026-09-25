from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _workflow(name: str) -> str:
    return (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")


def test_legacy_long_collectors_are_manual_only():
    for name in (
        "collect-market-data-v2.yml",
        "collect-copy-vault-v2.yml",
        "collect-official-archives-v2.yml",
        "collect-event-intelligence-v2.yml",
    ):
        text = _workflow(name)
        header = text.split("permissions:", 1)[0]
        assert "schedule:" not in header
        assert "workflow_dispatch" in header
        assert "self-hosted" not in text


def test_resumable_creator_is_continuous_hosted_and_frozen():
    text = _workflow("create-resumable-campaigns.yml")
    assert "schedule:" in text
    assert "cron: \'2 * * * *\'" in text
    assert "group: resumable-campaign-creation-hourly" in text
    assert "cancel-in-progress: false" in text
    assert "runs-on: ubuntu-latest" in text
    assert "self-hosted" not in text
    assert '"duration_s":3500' in text
    assert '"coins":"BTC,ETH,SOL,XRP,DOGE,BNB,AVAX,LINK,SUI,ADA,TRX,TON,WIF,ARB,OP,APT"' in text
    assert "market_collection" in text
    assert "copy_vault_collection" in text
    assert "freeze_copy_vault_selection.py" in text
    assert "COPY_COUNT" in text
    assert "COPY_LANES" in text
    assert "ACTIVE_COPY_CAMPAIGNS" in text
    assert "active Copy-Vault sweep already exists" in text
    assert "CONTINUATION_REQUIRED" in text
    assert "(COPY_COUNT + 9) / 10" in text
    assert "COPY_LANE<COPY_LANES" in text
    assert "copy-vault-$COPY_LANE-$BUCKET-v6" in text
    assert "selection_file" in text
    assert "selection_sha256" in text
    assert "catalog/copy_vault_selections" in text
    assert "official_archive_collection" in text
    assert "event_intelligence_collection" in text
    assert "make_campaign             replay" in text
    assert "make_campaign               backtest" in text
    assert "make_campaign               module_pnl_proof" in text
    assert "ref: main" in text
    assert "--cursor-json" in text
    assert "archives-binance-btc-" in text
    assert "archives-bybit-btc-" in text
    assert "REPLAY_START_MS" in text
    assert "ECON_START_MS" in text
    assert "max_shards" in text
    assert "64" in text
    assert "128" in text
    assert "gh workflow run resumable-campaign-controller.yml" in text
    assert "uses: ./.github/workflows/resumable-campaign-controller.yml" not in text
    assert "actions: write" in text


def test_resumable_creator_encodes_copy_vault_cursor_as_valid_json():
    text = _workflow("create-resumable-campaigns.yml")
    assert "COPY_CURSOR=" in text
    assert "json.dumps" in text
    assert '"$COPY_CURSOR"' in text
    assert '"{"duration_s":3500' not in text


def test_controller_worker_are_bounded_hosted_and_non_recursive():
    controller = _workflow("resumable-campaign-controller.yml")
    worker = _workflow("resumable-campaign-worker.yml")
    assert "cron: '*/5 * * * *'" in controller
    assert "push:" in controller
    assert "resumable-campaign-controller.yml" in controller
    assert "timeout-minutes: 10" in controller
    assert "timeout-minutes: 345" in worker
    assert "cancel-in-progress: false" in controller
    assert "cancel-in-progress: false" in worker
    assert "self-hosted" not in controller + worker
    assert "uses: ./.github/workflows/resumable-campaign-worker.yml" in controller
    assert "copy_work:" in controller
    assert "other_work:" in controller
    assert "max-parallel: 1" in controller
    assert "max-parallel: 12" in controller
    assert "head -n 128" in controller
    assert "copy_matrix" in controller
    assert "other_matrix" in controller
    assert "fromJSON(needs.select.outputs.copy_matrix)" in controller
    assert "fromJSON(needs.select.outputs.other_matrix)" in controller
    assert "gh workflow run resumable-campaign-worker.yml" not in worker
    assert "ref: ${{ steps.pin.outputs.sha }}" in worker
    assert "Claim durable campaign lease" in worker
    assert "Persist collection data or analysis evidence" in worker
    assert "Publish final campaign checkpoint" in worker
    assert "publish_dataset_v2_release.py" in worker
    assert "verify_lease" in worker
    assert "workflow_call:" in worker
    assert "Refresh Dataset V2 main" in controller
    assert "Refresh Dataset V2 main before pin" in worker
    assert 'os.path.abspath(str(part["selection_file"]))' in worker
    assert "COPY_VAULT_SWEEP_DURATION_CAP_S=300" in worker
    assert 'part["duration_s"] = min' in worker
    assert "actions: write" not in worker


def test_metrics_refresh_is_scheduled_and_serialized():
    text = _workflow("dataset-metrics-v2.yml")
    assert "schedule:" in text
    assert "group: dataset-v2-control-plane-index" in text
    assert "cancel-in-progress: false" in text
    assert "tools/build_catalog_metrics.py" in text


def test_reconcile_covers_all_production_release_families_and_pins_actions():
    text = _workflow("reconcile-v2-catalog.yml")
    assert "event-intelligence-v2-" in text
    assert "data-v2-" in text
    assert "actions/checkout@v4" not in text
    assert "actions/setup-python@v5" not in text
    assert "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683" in text
    assert "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065" in text
    assert "Download only new production V2 run manifests" in text
    assert "known={" in text


def test_resumable_worker_preserves_frozen_cursor_and_retry_policy():
    worker = _workflow("resumable-campaign-worker.yml")
    assert 'part=dict(m.get("cursor") or {})' in worker
    assert 'part.setdefault("duration_s",3500)' in worker
    assert 'part.setdefault("max_vaults",10)' in worker
    assert "TEMPORARY_EXTERNAL" in worker
    assert "failure=True" in worker


def test_resumable_creator_and_controller_track_current_main_for_new_work():
    creator = _workflow("create-resumable-campaigns.yml")
    controller = _workflow("resumable-campaign-controller.yml")
    assert "ref: main" in creator
    assert "ref: main" in controller
    assert "777d329176ded9e9262c33a9411adc99c55caa02" not in creator + controller


def test_bridge_and_exact_count_backfill_are_scheduled_hosted():
    bridge = _workflow("main-dataset-v2-bridge-smoke.yml")
    backfill = _workflow("backfill-exact-trade-counts.yml")
    assert "schedule:" in bridge
    assert "schedule:" in backfill
    assert "push:" in backfill
    assert "backfill-exact-trade-counts.yml" in backfill
    assert "backfill_exact_trade_counts.py" in backfill
    assert 'default: "500"' in backfill
    assert 'inputs.limit || \'500\'' in backfill
    assert "runs-on: ubuntu-latest" in bridge
    assert "runs-on: ubuntu-latest" in backfill
    assert "self-hosted" not in bridge + backfill
    assert "hl_observer.ops.v2_dataset_bridge" in bridge
    assert "backfill_exact_trade_counts.py" in backfill
