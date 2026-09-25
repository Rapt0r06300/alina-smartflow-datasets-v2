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
        header = _workflow(name).split("permissions:", 1)[0]
        assert "schedule:" not in header
        assert "workflow_dispatch" in header
        assert "self-hosted" not in _workflow(name)


def test_resumable_creator_is_continuous_hosted_and_frozen():
    text = _workflow("create-resumable-campaigns.yml")
    assert "schedule:" in text
    assert "runs-on: ubuntu-latest" in text
    assert "self-hosted" not in text
    assert '"duration_s":3600' in text
    assert "BTC,ETH,SOL,XRP,DOGE,BNB,AVAX,LINK,SUI,ADA,TRX,TON,WIF,ARB,OP,APT" in text
    assert "market_collection" in text
    assert "copy_vault_collection" in text
    assert "official_archive_collection" in text
    assert "event_intelligence_collection" in text
    assert "make_campaign replay" in text
    assert "make_campaign backtest" in text
    assert "make_campaign module_pnl_proof" in text
    assert "ref: main" in text
    assert "--cursor-json" in text
    assert "archives-binance-btc-" in text
    assert "archives-bybit-btc-" in text
    assert "REPLAY_START_MS" in text
    assert "BACKTEST_START_MS" in text
    assert "PNL_START_MS" in text


def test_controller_worker_are_bounded_hosted_and_non_recursive():
    controller = _workflow("resumable-campaign-controller.yml")
    worker = _workflow("resumable-campaign-worker.yml")
    assert "cron: '*/5 * * * *'" in controller
    assert "timeout-minutes: 15" in controller
    assert "timeout-minutes: 345" in worker
    assert "cancel-in-progress: false" in controller
    assert "cancel-in-progress: false" in worker
    assert "self-hosted" not in controller + worker
    assert "gh workflow run resumable-campaign-worker.yml" in controller
    assert "gh workflow run" not in worker
    assert "ref: ${{ steps.pin.outputs.sha }}" in worker
    assert "Acquire durable campaign lease" in worker
    assert "Publish collection bundle and index immediately" in worker
    assert "Publish replay/backtest/PnL evidence" in worker
    assert "publish_dataset_v2_release.py" in worker
    assert "tools/index_run_manifest.py" in worker
    assert "tools/build_catalog_metrics.py" in worker
    assert "verify_lease" in worker


def test_metrics_refresh_is_scheduled_and_serialized():
    text = _workflow("dataset-metrics-v2.yml")
    assert "schedule:" in text
    assert "group: dataset-v2-control-plane-index" in text
    assert "cancel-in-progress: false" in text
    assert "tools/build_catalog_metrics.py" in text


def test_reconcile_covers_all_production_release_families_and_pins_actions():
    text = _workflow("reconcile-v2-catalog.yml")
    assert "event-intelligence-v2-" in text
    assert "actions/checkout@v4" not in text
    assert "actions/setup-python@v5" not in text
    assert "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683" in text
    assert "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065" in text


def test_resumable_worker_preserves_frozen_cursor_and_retry_policy():
    worker = _workflow("resumable-campaign-worker.yml")
    assert 'part=dict(m.get("cursor") or {})' in worker
    assert 'part.setdefault("duration_s",3600)' in worker
    assert 'part.setdefault("max_vaults",20)' in worker
    assert 'required=("venue","coin","symbol","start_date")' in worker
    assert "TEMPORARY_EXTERNAL" in worker
    assert "failure=True" in worker


def test_resumable_creator_and_controller_track_current_main_for_new_work():
    creator = _workflow("create-resumable-campaigns.yml")
    controller = _workflow("resumable-campaign-controller.yml")
    assert "ref: main" in creator
    assert "ref: main" in controller
    assert "777d329176ded9e9262c33a9411adc99c55caa02" not in creator + controller
