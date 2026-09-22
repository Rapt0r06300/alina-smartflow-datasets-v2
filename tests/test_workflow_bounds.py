from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _workflow(name: str) -> str:
    return (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")


def test_long_collectors_are_not_push_triggered() -> None:
    for name in ("collect-market-data-v2.yml", "collect-copy-vault-v2.yml"):
        header = _workflow(name).split("permissions:", 1)[0]
        assert "  push:" not in header


def test_market_schedule_has_runtime_headroom() -> None:
    text = _workflow("collect-market-data-v2.yml")
    assert 'cron: "17 */4 * * *"' in text
    assert 'default: "210"' in text
    assert "inputs.duration_minutes || '210'" in text


def test_copy_vault_sharding_respects_hyperliquid_user_cap() -> None:
    text = _workflow("collect-copy-vault-v2.yml")
    assert "cron: '47 1-23/4 * * *'" in text
    assert "max-parallel: 10" in text
    assert "shard: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]" in text
    assert "--vault-shard-count 10" in text
    assert "for shard in 0 1 2 3 4 5 6 7 8 9; do" in text
    assert 'default: \'100\'' in text
    assert "max_vaults must be in [1, 100]" in text


def test_copy_vault_schedule_has_runtime_headroom() -> None:
    text = _workflow("collect-copy-vault-v2.yml")
    assert "inputs.duration_s || '11400'" in text
    assert "duration_s must be in [60, 12000]" in text
    # 11,400 seconds = 190 minutes, comfortably below the 4-hour cadence.
    assert "timeout-minutes: 230" in text
