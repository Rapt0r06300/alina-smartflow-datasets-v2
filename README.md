# Alina SmartFlow Datasets V2

Event Intelligence is collected by `collect-event-intelligence-v2` from bounded
public, read-only sources on GitHub Hosted. Every `external_events` manifest must
carry the complete 120-idea integration contract linking Copy-Vault, Lead-Lag,
Cross-Venue Dislocation and arbitrage. Because no exact independent reference
exists for heterogeneous external events, these shards remain `PARTIAL` and are
never accepted as PnL proof.

Fresh public dataset repository for NEW Alina SmartFlow collection data only.

## Lifecycle

```
incoming -> quarantine -> safe
                       -> rejected
```

Only exact windows qualified as `SAFE` may feed validation replays/backtests.

## Storage model

- Git `main`: manifests, indexes, quality state, schemas, tests and small reports.
- GitHub Releases: immutable heavy data shards.
- Heavy data is partitioned; replay/backtest jobs download only the required SAFE shards.
- No automatic import from any legacy dataset.
- No secrets, API keys, private wallet data or credentials may be stored here.
- GitHub-hosted only. No self-hosted runner and no user-PC workflow.

Initial state: `NO_DATA`.

## Official archive fallback

- Binance USD-M and Bybit public historical trade archives are ingested through bounded GitHub-hosted jobs when live endpoints are unavailable from the hosted region.
- Archive records are tagged as historical exchange-time-only evidence. They do **not** fabricate collector receive timestamps or monotonic clocks.
- Archive shards remain `PARTIAL` unless a separate qualification path proves the missing timing/reconciliation requirements; they are never automatically promoted to live-quality `SAFE`.
- Heavy archive data is stored only in immutable GitHub Releases and indexed through the same V2 control plane.
