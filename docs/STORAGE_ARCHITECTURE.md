# Storage architecture

## Event Intelligence V2

The scheduled `collect-event-intelligence-v2` workflow checks out an exact main
repository SHA, collects keyless public event sources on `ubuntu-latest`, publishes
immutable release assets, then serializes catalog indexing with every other control
plane writer. The manifest preserves the 120-idea coverage digest and its four
strategy-family bindings. `UNAVAILABLE` reconciliation remains `PARTIAL`; dataset
quality never promotes it to `SAFE` and never authorizes a PnL claim.

Alina SmartFlow V2 is designed to grow far beyond the practical size of a normal Git repository.

## Control plane
The Git tree stores only indexes, manifests, quality metadata, schemas, tests and compact reports.

## Data plane
Heavy collection data is stored as immutable GitHub Release assets, partitioned by family/venue/symbol/time window.

Each asset must have a manifest with SHA-256, provenance, exact time range, event count and quality state.

## Replay/backtest
A validation job:
1. resolves the requested time/symbol/venue window,
2. selects only manifests marked SAFE,
3. downloads only the necessary shards,
4. verifies SHA-256,
5. runs replay/backtest,
6. rejects any missing prerequisite instead of substituting zero.

This keeps the dataset large while keeping Git operations fast.
