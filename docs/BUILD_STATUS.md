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
- Imbalance edge, replay, sweep, walk-forward, and pipeline commands now accept
  explicit market profiles, preserve market/tick-size defaults in candidate
  configs, and can run US regular-hours equity/options research without
  applying India session filters or costs.
- Non-India imbalance replay, replay sweeps, replay walk-forward, and pipeline
  runs accept explicit generic fee assumptions, preserve them in manifests and
  candidate configs, and apply them to US research PnL.
- Imbalance replay walk-forward runner that takes a selected candidate, replays
  it across multiple tick folds, runs proof gates, and emits aggregate
  paper/shadow readiness evidence.
- Imbalance candidate promotion bridge that converts passed replay
  walk-forward evidence into launch-compatible promotion reports and candidate
  configs for paper/shadow order staging.
- End-to-end imbalance research pipeline that runs edge walk-forward,
  replay-proof walk-forward, and candidate promotion in one manifest-backed
  command with stage-level readiness evidence and an optional required
  multi-day data-readiness comparison preflight.
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
- Settlement convergence audit command that compares expiring option touch
  prices with projected settlement intrinsic value, applies explicit
  edge/cost gates, and emits candidate configs for later replay work.
- Settlement convergence walk-forward runner that can require accepted
  multi-day vendor data-readiness comparison evidence before repeating the
  expiry-window audit across folds, then requires stable pass rate and edge and
  emits aggregate evidence plus a replay-candidate config.
- Settlement candidate promotion bridge that converts passed settlement
  walk-forward evidence into launch-compatible promotion reports and
  candidate configs for paper/shadow staging.
- Settlement order planner that turns promoted settlement candidates into
  broker-neutral limit-order candidates for the standard staging, launch,
  export, and reconciliation path.
- Settlement launch pipeline that chains a promoted settlement candidate
  through order planning, staging, launch bundling, broker export,
  Arrow.money/iRage upload-pack generation, and broker-readiness/runtime-session
  gating with component-level readiness.
- Compliance/risk utilities for OTR and cross-segment loss/profit guardrails.
- Black-76 pricing, implied-vol inversion, and quadratic smile fitting for
  options surface work.
- Surface-driven market-making quote generation with inventory skew and quote
  budget controls.
- Surface quote-risk review can require accepted multi-day vendor
  data-readiness comparison evidence before quotes move into replay or
  paper-routing workflows.
- Broker-neutral staging for surface quotes can require a passed quote-risk
  review, blocking all orders before Arrow.money/iRage preparation when quote
  hygiene evidence is missing or failed.
- Surface market-making robustness sweeps can require a passed quote-risk
  review and fail closed with manifest-backed proof artifacts before replay
  grids are run.
- Direct surface market-making replay can require the same quote-risk review
  and emits blocked replay artifacts instead of simulating unreviewed quotes.
- End-to-end surface market-making research pipeline that chains quote
  generation, quote-risk/data-readiness review, replay sweep proof, scenario
  selection, and promotion into one manifest-backed candidate run.
- Surface market-making launch pipeline that consumes a promoted surface
  research pipeline and runs quote-risk-enforced lifecycle planning, staging,
  launch bundling, broker export, upload-pack generation, and
  broker-readiness/runtime-session checks.
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
  can be reused or must be rerun before promotion/scale-up, while failing
  closed on mixed strategy/market proof identities.
- Experiment catalog, strategy evidence review, and controlled scale-up planning
  can now require proof-refresh evidence before size increases, and scale-up
  validates proof-refresh strategy/market identity against the promotion target.
- Broker/vendor adapter scaffolding for normalized, Arrow.money-style, and
  iRage-style CSV exports.
- Unified `hft` command runner for scanners, replays, lead-lag measurement,
  and calibration reports.
- Spread-capture decomposition for paired round-trip fills, plus residual
  inventory reports in replay outputs.
- Data-quality diagnostics for tick and option-chain files, including spread,
  depth, timestamp, session, crossed quote, and strike coverage reports.
- Data readiness gate that combines vendor CSV intake, schema audit,
  mapped-data normalization, tick/chain diagnostics, market-profile fee
  assumptions, and instrument metadata before strategy research or promotion.
- Vendor market-data onboarding pipelines that run Arrow.money/iRage CSV
  intake, normalized mapping, tick/chain diagnostics, data-readiness gates, and
  multi-day readiness comparison before walk-forward research.
- Multi-dataset data-readiness comparison gate that requires repeated clean
  market-data days before walk-forward research or strategy evidence review.
- Market profile layer for India NSE index derivatives and US regular-hours
  equities/options, with shared session filtering and configurable generic
  costs for non-India workflows.
- Market profile report command that exports India/US session, tick, lot-size,
  currency, and explicit generic fee assumptions as manifest-backed evidence
  before cross-market research runs.
- Market portability report that maps each strategy workflow across India and
  US market profiles, flags explicit fee-model requirements, and keeps
  India-specific settlement mechanics blocked until a separate US model exists.
- Instrument metadata coverage report that parses option symbols across
  internal, settlement, NSE compact, and OCC formats, emits unparsed gaps, and
  can fail closed before exposure, upload, or US portability work.
- Proof-report gate for replay output folders, scoring PnL, fills, drawdown,
  OTR, regime robustness, spread capture, and markout quality against explicit
  thresholds while carrying strategy/market identity and blocking mixed
  identity proof bundles.
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
- Launch bundles can require passed quote-risk review evidence for staged
  surface market-making orders before paper/shadow packaging.
- Launch-order export writer that validates launch bundles and emits
  adapter-labelled broker/paper order files, schema metadata, checks, and
  manifests, with Arrow.money/iRage marked as normalized placeholders until
  real vendor upload samples are mapped.
- Broker upload pack command that applies built-in Arrow.money/iRage review
  templates to broker-neutral exports, emits the upload-shaped CSV plus the
  mapping used, carries quote lifecycle metadata for submit/replace review,
  and fails closed unless placeholder schemas are explicitly allowed for
  dry-run review.
- Broker/drop-copy fill reconciliation for exported orders, including
  order-level fill status, unmatched fills, side/instrument mismatches,
  adverse slippage, latency, pass/fail checks, and manifests.
- Shadow-session acceptance report that combines launch, export,
  reconciliation, and optional runtime-session monitor artifacts into one
  go/no-go record for paper/shadow promotion decisions, carrying runtime
  strategy/market, proof-refresh identity, and broker resume-gate proof
  identity, blocking supplied or required sessions when the runtime guard
  halted, and failing closed on bad runtime proof-refresh or resume-gate proof
  state.
- Multi-session shadow comparison gate for requiring repeated accepted
  paper/shadow sessions with consistent scenario keys, fill rates, slippage,
  runtime strategy/market, proof-refresh identity, broker resume proof
  identity, mismatch, reconciliation quality, and zero halted runtime monitors
  before scale-up.
- Experiment manifests for replay, sweep, proof, and selection outputs,
  capturing parameters, input hashes, artifact hashes, git state, and runtime
  package versions.
- Experiment catalog command that scans manifest-bearing run folders into a
  searchable evidence ledger with inferred pass/ready status and summary
  metrics for research, market portability, calibration, data operations,
  launch, broker upload, broker readiness, shadow-session, scale-up, quote
  lifecycle, runtime guard, halt-response, and resume artifacts.
- Strategy evidence review gate that consumes the experiment catalog and
  requires successful proof, stress, promotion, broker-readiness, shadow, or
  user-selected run types before scale-up decisions, with optional fail-closed
  checks that all passing required artifacts share the expected strategy and
  market identity, including runtime identity aliases from broker and shadow
  evidence.
- Controlled scale-up plan report that combines strategy evidence, shadow
  comparison, launch, optional exposure summaries, proof freshness, and
  instrument metadata coverage, single-day and multi-day data-readiness
  evidence, and broker-readiness evidence into explicit order, open-order
  notional and age, position notional, adapter, telemetry-freshness,
  lifecycle-order, replace-order, delta, and vega kill-switch limits, carries
  strategy/market identity, direct and shadow proof-refresh state, and broker
  runtime-session guard and resume-gate evidence into scale-up configs,
  automatically requires broker/runtime guard evidence for live-dry-run
  targets, fails closed on broker runtime-session, broker resume-gate
  proof-refresh, or shadow proof-refresh strategy/market mismatches, and can
  consume a settlement or surface-MM launch pipeline root directly.
- Runtime telemetry snapshot builder that converts scale-up, export,
  broker-upload, reconciliation, optional instrument metadata, PnL, open-order,
  and position artifacts into guard-ready `runtime_telemetry.csv` inputs with
  source/check summaries, derives active open-order notional from remaining
  quantity/price or broker notional fields, derives stale open-order age from
  broker age fields or active order timestamps, derives live gross/net position
  notional from marks or total notional columns, derives net delta/vega from
  total or unit Greek position columns, carries scale-up strategy/market and
  proof-refresh freshness identity plus broker resume-gate proof identity, and
  can consume settlement or surface-MM launch pipeline roots for broker export
  and upload-pack evidence.
- Runtime scale-up guard that evaluates live or paper telemetry snapshots
  against `scaleup_config.json` limits, kill switches, telemetry freshness,
  lifecycle/replace message controls, open-order quantity/notional/age,
  position-inventory notional/delta/vega limits, and required instrument
  metadata plus strategy/market continuity, accepts telemetry output folders
  directly, validates required proof-refresh readiness and strategy/market
  identity plus broker resume-gate proof identity, and returns explicit
  continue/halt decisions with failed check names and first halt reasons.
- Runtime session monitor that chains telemetry building, scale-up guard
  evaluation, and automatic halt-response planning into one manifest-backed
  paper/shadow go/no-go artifact, preserving the guard halt trigger and
  strategy/market plus proof-refresh and broker resume-gate identity in the
  top-level session summary.
- Halt response planner that converts runtime guard halts into broker-neutral
  cancel-order and flatten-position action files with fail-closed price checks
  and manifests, stamping guard failed check names and first halt reasons onto
  the summary and action CSVs for operator review while carrying strategy and
  market identity into the emergency action packet.
- Halt response export mapper that turns emergency cancel and flatten actions
  into reviewed broker/vendor CSV shapes, with normalized passthrough until
  Arrow.money/iRage emergency schemas are finalized.
- Halt execution reconciliation gate that verifies emergency cancel
  acknowledgements, flatten fills, and final flat positions after a guard halt.
- Halt incident review that combines guard, response, export, and execution
  evidence into one incident-closure timeline, check set, and summary with
  guard trigger plus strategy/market context carried through the review.
- Post-halt resume gate that requires a closed incident, ready scale-up plan,
  scenario/adapter, strategy/market, and proof-refresh continuity, optional
  operator approval, and emits resume authorization/config artifacts carrying
  the incident guard trigger and proof context from the prior halt, with
  automatic operator approval and guard-trigger acknowledgement required for
  `live_dryrun` resumes.
- Cutover gate that authorizes the final paper/shadow/live-dryrun route only
  after scale-up, broker readiness, runtime-session guard, proof freshness,
  optional broker resume-gate proof, and operator strategy/market/limit
  acknowledgement agree in one manifest-backed authorization artifact.
- Route-enable packet that consumes ready cutover and broker upload evidence,
  bounds order counts and optional export notional by cutover limits, and emits
  the final machine-readable broker route-enable config without submitting
  orders.
- Replay stress reports for extra fee multipliers, tick slippage, and adverse
  bps shocks, including stressed PnL, cost bps, drawdown, strategy/market
  identity consistency, and pass/fail gates.
- Surface quote runner that fits per-snapshot option smiles from chain/futures
  data and emits budgeted market-making quotes with marketability checks and
  manifests.
- Surface quote risk review for market-making quote sets, gating marketable
  quotes, quote edge, side balance, market spread, instrument coverage, and
  concentration before replay or live routing.
- Surface quote lifecycle planner that converts reviewed quote snapshots into
  submit/replace/cancel actions plus routeable submit/replace order files with
  TTL, OTR, message-budget, and active-quote controls before Arrow.money/iRage
  paper-routing preparation, preserving replace lineage through staging,
  launch, and broker-neutral export artifacts.
- Option order exposure review for staged, launch, or exported order batches,
  including Black-76 delta/vega, gross notional, side imbalance, and
  instrument concentration checks, with cross-market option metadata inference
  for internal, settlement, NSE compact, and OCC symbols.
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
- Mapped vendor-data normalization command that applies reviewed header
  mappings to real tick, chain, order, or fill CSVs and emits normalized data,
  mapping checks, summary, and manifest artifacts.
- Configurable mapped broker-order export that converts broker-neutral launch
  orders into a vendor CSV shape from a reviewed mapping file, with required
  field checks, simple transforms, and manifests.
- Vendor order-mapping draft command that reads a broker-neutral export plus
  an Arrow.money/iRage sample upload header, suggests reviewable mappings, and
  fails closed on unmapped required vendor fields.
- Vendor CSV intake report that profiles unknown Arrow.money/iRage samples,
  infers tick/chain/order/fill shape, scores normalized mapping coverage, and
  emits a reviewed-mapping draft for market-data normalization.
- Broker integration readiness report that combines schema audit, broker order
  export, mapping draft, mapped orders, upload pack, optional halt export, and
  optional reconciliation/runtime-session/resume-gate evidence into one
  fail-closed Arrow.money/iRage go/no-go artifact, blocking supplied or
  required runtime sessions when the scale-up guard halted and retaining
  resume proof-refresh identity for post-halt restart review.
- Halt response and halt incident evidence now preserve runtime proof-refresh
  fields from the guard through cancel/flatten packets, response summaries,
  response config, incident timelines, and incident closure summaries.

## Test Gate

Run from repo root:

```powershell
pytest
```

Current passing suite: 444 tests.

## Next Build Targets

1. Add data adapters for the first real vendor export once files are available.
2. Replace placeholder Arrow.money/iRage column maps once real export schemas
   are available.
3. Replace the built-in upload review templates with broker-signed
   Arrow.money/iRage order schemas once sample files are available.
