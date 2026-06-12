# Build Status

## Current State

- Single-instrument event backtester with Indian costs, latency, queue fills,
  cancels, terminal flattening, OTR reporting, and tests.
- Multi-instrument shared-clock engine with venue latency, clock skew,
  per-instrument routing, portfolio limits, and shared equity.
- Data normalization for top-of-book ticks and option-chain snapshots,
  including IST session filtering, quarantine reports, and regime tags.
- Synthetic futures/options generator with planted lag relationships.
- Executable put-call parity and box scanner using touch prices, depth
  fractions, explicit as-of latency, and full leg costs.
- CLI/report runners for parity/box scans and lead-lag measurement.
- Lead-lag research: lag-grid correlations, event lag profile, and latency
  viability curve.
- Replay strategies: parity taker and lead-lag taker.
- Replay CLIs for parity taker and lead-lag taker, writing fills, equity,
  summary, signals/legging, and markout artifacts.
- Replay outputs automatically include fills-by-regime and equity-by-regime
  summaries to avoid cross-regime averaging.
- Markout tooling for fill quality/adverse selection analysis.
- Microstructure feature and label utilities, including forward-mid and
  triple-barrier labels.
- Purged walk-forward validation utility for overlapping labels.
- Expiry settlement running-average and convergence helpers.
- Compliance/risk utilities for OTR and cross-segment loss/profit guardrails.
- Black-76 pricing, implied-vol inversion, and quadratic smile fitting for
  options surface work.
- Surface-driven market-making quote generation with inventory skew and quote
  budget controls.
- Surface/theo markout analysis for option fills.
- PnL decomposition reports by source and instrument, including strategy fills
  versus terminal flattening.
- Shadow/live calibration comparison for broker/exchange fills versus simulated
  order expectations.
- Broker/vendor adapter scaffolding for normalized, Arrow.money-style, and
  iRage-style CSV exports.
- Unified `hft` command runner for scanners, replays, lead-lag measurement,
  and calibration reports.
- Spread-capture decomposition for paired round-trip fills, plus residual
  inventory reports in replay outputs.
- Data-quality diagnostics for tick and option-chain files, including spread,
  depth, timestamp, session, crossed quote, and strike coverage reports.
- Market profile layer for India NSE index derivatives and US regular-hours
  equities/options, with shared session filtering and configurable generic
  costs for non-India workflows.
- Proof-report gate for replay output folders, scoring PnL, fills, drawdown,
  OTR, regime robustness, spread capture, and markout quality against explicit
  thresholds.
- Lead-lag robustness sweep runner that replays trigger/latency grids, writes
  per-scenario artifacts, and aggregates proof pass rates plus robust scores.
- Parity robustness sweep runner that replays depth/as-of/latency grids,
  tracks signal and legging health, and aggregates proof pass rates plus robust
  scores.

## Test Gate

Run from repo root:

```powershell
pytest
```

Current passing suite: 74 tests.

## Next Build Targets

1. Add data adapters for the first real vendor export once files are available.
2. Replace placeholder Arrow.money/iRage column maps once real export schemas
   are available.
3. Add richer real-data diagnostics once the first vendor sample lands.
