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
        header=_workflow(name).split("permissions:",1)[0]
        assert "schedule:" not in header
        assert "workflow_dispatch" in header
        assert "self-hosted" not in _workflow(name)

def test_resumable_creator_is_scheduled_and_hosted():
    text=_workflow("create-resumable-campaigns.yml")
    assert "schedule:" in text
    assert "runs-on: ubuntu-latest" in text
    assert "self-hosted" not in text
    assert "market_collection" in text
    assert "copy_vault_collection" in text
    assert "official_archive_collection" in text
    assert "event_intelligence_collection" in text
    assert 'make_campaign replay' in text
    assert 'make_campaign backtest' in text
    assert 'make_campaign module_pnl_proof' in text
    assert "ref: main" in text
    assert "--cursor-json" in text
    assert "archives-binance-btc-" in text
    assert "archives-bybit-btc-" in text

def test_controller_worker_are_bounded_and_non_recursive():
    controller=_workflow("resumable-campaign-controller.yml")
    worker=_workflow("resumable-campaign-worker.yml")
    assert "timeout-minutes: 15" in controller
    assert "timeout-minutes: 345" in worker
    assert "cancel-in-progress: false" in controller
    assert "cancel-in-progress: false" in worker
    assert "self-hosted" not in controller+worker
    assert "gh workflow run resumable-campaign-worker.yml" in controller
    assert "gh workflow run" not in worker
    assert "Acquire hashed lease" in worker
    assert "publish_dataset_v2_release.py" in worker
    assert "index_run_manifest.py" in worker
    assert "worker_failed_before_result" in worker
    assert "ref: ${{ steps.pin.outputs.sha }}" in worker

def test_metrics_refresh_is_scheduled_and_serialized():
    text=_workflow("dataset-metrics-v2.yml")
    assert "schedule:" in text
    assert "group: dataset-v2-control-plane-index" in text
    assert "cancel-in-progress: false" in text
    assert "tools/build_catalog_metrics.py" in text