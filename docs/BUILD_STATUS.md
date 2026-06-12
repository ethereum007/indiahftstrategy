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
- Parity/box edge audit that gates scan outputs on opportunity count, net edge,
  persistence, direction coverage, and futures staleness before replay/sweep
  work.
- CLI/report runners for parity/box scans and lead-lag measurement.
- Lead-lag research: lag-grid correlations, event lag profile, and latency
  viability curve.
- Lead-lag edge audit that gates measured relationships on events,
  correlation, laggard update rate, update latency, and latency-curve PnL
  before replay/sweep promotion.
- Microprice/order-book imbalance edge audit that scans top-of-book ticks for
  imbalance/microprice signals and gates forward-mid response, direction
  coverage, and win rate before replay/sweep work.
- Microprice/order-book imbalance edge sweep that ranks entry thresholds,
  microprice-edge hurdles, and forward horizons before expensive replay grids,
  emitting replay defaults in a candidate config.
- Cross-day/fold imbalance edge selection that compares edge sweep outputs,
  requires stable pass rate, signal count, forward edge, and win rate, and
  emits a replay-ready candidate config.
- Imbalance edge walk-forward runner that sweeps multiple tick files, compares
  fold scenarios, emits aggregate evidence, and writes a replay-ready candidate
  config in one manifest-backed run.
- Microprice imbalance replay and replay-sweep CLIs can consume the edge
  sweep `candidate_config.json` directly, while explicit CLI parameters remain
  available for overrides.
- Replay strategies: parity taker and lead-lag taker.
- Replay CLIs for parity taker and lead-lag taker, writing fills, equity,
  summary, signals/legging, and markout artifacts.
- Microprice/order-book imbalance replay strategy for single-instrument
  top-of-book pressure, including latency, depth, spread, hold-time, signal
  decay exits, signals, markouts, and proof-compatible outputs.
- Imbalance replay walk-forward runner that takes a selected candidate, replays
  it across multiple tick folds, runs proof gates, and emits aggregate
  paper/shadow readiness evidence.
- Imbalance candidate promotion bridge that converts passed replay
  walk-forward evidence into launch-compatible promotion reports and candidate
  configs for paper/shadow order staging.
- End-to-end imbalance research pipeline that runs edge walk-forward,
  replay-proof walk-forward, and candidate promotion in one manifest-backed
  command with stage-level readiness evidence.
- Microprice/order-book imbalance robustness sweep across entry threshold,
  microprice edge, hold timer, feed latency, and order latency, with per-run
  replay artifacts, proof gate, pass rate, and robust score summary.
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
- Fill-model calibration report that converts broker/drop-copy reconciliation
  into replay-ready queue conservatism, order latency, slippage, and edge
  buffer recommendations.
- Fill-model drift gate that compares baseline and latest calibration configs
  to decide whether existing proof assumptions can be reused or calibrated
  proof must be rerun.
- Calibrated replay planning and replay CLI hooks that apply fill-model
  recommendations to lead-lag, parity, and surface-MM replay latency/depth/edge
  assumptions without loosening explicit conservative inputs.
- Calibration-aware proof refresh gate that consumes fill-model drift, baseline
  proof, latest proof, and calibrated replay evidence to decide whether proof
  can be reused or must be rerun before promotion/scale-up.
- Experiment catalog, strategy evidence review, and controlled scale-up planning
  can now require proof-refresh evidence before size increases.
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
- Market profile report command that exports India/US session, tick, lot-size,
  currency, and explicit generic fee assumptions as manifest-backed evidence
  before cross-market research runs.
- Proof-report gate for replay output folders, scoring PnL, fills, drawdown,
  OTR, regime robustness, spread capture, and markout quality against explicit
  thresholds.
- Lead-lag robustness sweep runner that replays trigger/latency grids, writes
  per-scenario artifacts, and aggregates proof pass rates plus robust scores.
- Parity robustness sweep runner that replays depth/as-of/latency grids,
  tracks signal and legging health, and aggregates proof pass rates plus robust
  scores.
- Cross-sweep scenario comparison for ranking parameter settings across days
  or folds by pass rate, median PnL, drawdown, regime losses, and robust score.
- Scenario promotion gate that converts cross-sweep selections into explicit
  paper/shadow readiness decisions, threshold checks, and machine-readable
  candidate configs.
- Paper/shadow launch bundle that joins a promoted scenario with staged
  broker-neutral orders, checks promotion and pre-trade cleanliness, and emits
  launch orders/configs for later Arrow.money/iRage-specific mapping.
- Launch-order export writer that validates launch bundles and emits
  adapter-labelled broker/paper order files, schema metadata, checks, and
  manifests, with Arrow.money/iRage marked as normalized placeholders until
  real vendor upload samples are mapped.
- Broker/drop-copy fill reconciliation for exported orders, including
  order-level fill status, unmatched fills, side/instrument mismatches,
  adverse slippage, latency, pass/fail checks, and manifests.
- Shadow-session acceptance report that combines launch, export, and
  reconciliation artifacts into one go/no-go record for paper/shadow promotion
  decisions.
- Multi-session shadow comparison gate for requiring repeated accepted
  paper/shadow sessions with consistent scenario keys, fill rates, slippage,
  mismatch, and reconciliation quality before scale-up.
- Experiment manifests for replay, sweep, proof, and selection outputs,
  capturing parameters, input hashes, artifact hashes, git state, and runtime
  package versions.
- Experiment catalog command that scans manifest-bearing run folders into a
  searchable evidence ledger with inferred pass/ready status and summary
  metrics.
- Strategy evidence review gate that consumes the experiment catalog and
  requires successful proof, stress, promotion, shadow, or user-selected run
  types before scale-up decisions.
- Controlled scale-up plan report that combines strategy evidence, shadow
  comparison, launch, and optional exposure summaries into explicit order,
  notional, adapter, and kill-switch limits.
- Runtime telemetry snapshot builder that converts scale-up, export,
  reconciliation, PnL, open-order, and position artifacts into guard-ready
  `runtime_telemetry.csv` inputs with source/check summaries.
- Runtime scale-up guard that evaluates live or paper telemetry snapshots
  against `scaleup_config.json` limits and kill switches, returning explicit
  continue/halt decisions.
- Halt response planner that converts runtime guard halts into broker-neutral
  cancel-order and flatten-position action files with fail-closed price checks
  and manifests.
- Halt response export mapper that turns emergency cancel and flatten actions
  into reviewed broker/vendor CSV shapes, with normalized passthrough until
  Arrow.money/iRage emergency schemas are finalized.
- Halt execution reconciliation gate that verifies emergency cancel
  acknowledgements, flatten fills, and final flat positions after a guard halt.
- Halt incident review that combines guard, response, export, and execution
  evidence into one incident-closure timeline, check set, and summary.
- Post-halt resume gate that requires a closed incident, ready scale-up plan,
  scenario/adapter continuity, optional operator approval, and emits
  resume authorization/config artifacts.
- Replay stress reports for extra fee multipliers, tick slippage, and adverse
  bps shocks, including stressed PnL, cost bps, drawdown, and pass/fail gates.
- Surface quote runner that fits per-snapshot option smiles from chain/futures
  data and emits budgeted market-making quotes with marketability checks and
  manifests.
- Surface quote risk review for market-making quote sets, gating marketable
  quotes, quote edge, side balance, market spread, instrument coverage, and
  concentration before replay or live routing.
- Option order exposure review for staged, launch, or exported order batches,
  including Black-76 delta/vega, gross notional, side imbalance, and
  instrument concentration checks.
- Passive surface market-making replay that tests generated quotes against
  later option-chain snapshots, writes fills/unfilled quotes/equity/markout
  artifacts, and produces proof-report-compatible `summary.csv` runs.
- Surface market-making robustness sweep across TTL, routing latency,
  fill-depth, and markout horizons, with per-scenario replays, proof gates,
  robust scores, and manifests.
- Broker-neutral order staging for generated quotes or generic order
  candidates, including pre-trade quantity/notional/marketability/price-band
  checks, accepted/rejected order artifacts, and manifests for later
  Arrow.money/iRage routing adapters.
- Adapter schema audit for vendor sample CSV headers, including required,
  missing, and extra source columns plus a mapping template and manifest before
  real Arrow.money/iRage column maps are finalized.
- Configurable mapped broker-order export that converts broker-neutral launch
  orders into a vendor CSV shape from a reviewed mapping file, with required
  field checks, simple transforms, and manifests.

## Test Gate

Run from repo root:

```powershell
pytest
```

Current passing suite: 229 tests.

## Next Build Targets

1. Add data adapters for the first real vendor export once files are available.
2. Replace placeholder Arrow.money/iRage column maps once real export schemas
   are available.
3. Add broker-specific order-file/export mappings once Arrow.money/iRage sample
   order schemas are available.
