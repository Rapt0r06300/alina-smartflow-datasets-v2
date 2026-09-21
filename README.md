# Alina SmartFlow Datasets V2

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
