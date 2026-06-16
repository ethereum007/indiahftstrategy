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
- Parity/box scan outputs now preserve executable leg sides and touch prices
  for downstream multi-leg order planning.
- Parity/box candidate promotion bridge converts passed scan, edge-audit, and
  sweep evidence into launch-compatible promotion reports and candidate configs
  while preserving selected leg prices and replay defaults.
- Parity/box order-plan bridge converts promoted candidates into grouped
  broker-neutral multi-leg paper/shadow templates for synthetic/future and box
  directions, with quantity, price, notional, and strike/expiry gates.
- Parity/box launch pipeline runs promoted candidates through order planning,
  staging, launch bundle creation, broker export, upload pack, and broker
  readiness review for Arrow.money/iRage-style paper or shadow handoff.
- CLI/report runners for parity/box scans and lead-lag measurement.
- Strategy evidence review supports a `parity` profile that requires parity
  edge audit, replay sweep, promotion, order-plan, and launch-pipeline artifacts
  with shared strategy and market identity before shadow scale-up review.
- Lead-lag research: lag-grid correlations, event lag profile, and latency
  viability curve.
- Lead-lag edge audit that gates measured relationships on events,
  correlation, laggard update rate, update latency, and latency-curve PnL
  before replay/sweep promotion.
- Lead-lag edge, replay, replay walk-forward, promotion, order-plan,
  launch-pipeline, and sweep artifacts retain `lead_lag_taker` plus
  market-profile identity for proof/catalog review, and non-India lead-lag
  replay can use explicit generic fee assumptions instead of NSE costs.
- Lead-lag replay walk-forward runner replays paired leader/laggard folds,
  aggregates proof gates, and writes a replay-ready candidate config with
  inherited market and generic fee assumptions.
- Lead-lag candidate promotion bridge converts passed replay walk-forward
  evidence into launch-compatible promotion reports and candidate configs for
  paper/shadow staging.
- Lead-lag order-plan bridge converts promoted candidates into broker-neutral
  paper/shadow trigger templates for both upward leader buy-laggard and
  downward leader sell-laggard paths, with quantity, notional, and price-band
  gates before staging.
- Lead-lag launch pipeline runs promoted candidates through order planning,
  staging, launch bundle creation, broker export, upload pack, and broker
  readiness review for Arrow.money/iRage-style paper or shadow handoff.
- Strategy evidence review supports a `leadlag` profile that requires measured
  lead-lag edge, replay walk-forward, stress, promotion, order-plan, and
  launch-pipeline artifacts with shared strategy and market identity before
  shadow scale-up review.
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
- Replay strategy instances reset run-local state at engine start for
  lead-lag taker, parity taker, and microprice imbalance, so repeated
  sweeps/replays cannot carry stale order, fill, signal, or legging state.
- Replay CLIs for parity taker and lead-lag taker, writing fills, equity,
  summary, signals/legging, and markout artifacts.
- Microprice/order-book imbalance replay strategy for single-instrument
  top-of-book pressure, including latency, depth, spread, hold-time, signal
  decay exits, signals, markouts, and proof-compatible outputs.
- Imbalance edge, replay, sweep, walk-forward, and pipeline commands now accept
  explicit market profiles, preserve market/tick-size and deployment defaults
  in candidate configs, and can run US regular-hours equity/options research
  without applying India session filters or costs.
- Non-India imbalance replay, replay sweeps, replay walk-forward, and pipeline
  runs accept explicit generic fee assumptions, preserve them in manifests and
  candidate configs, and apply them to US research PnL.
- Imbalance replay walk-forward runner that takes a selected candidate, replays
  it across multiple tick folds, runs proof gates, and emits aggregate
  paper/shadow readiness evidence.
- Imbalance candidate promotion bridge that converts passed replay
  walk-forward evidence into launch-compatible promotion reports and candidate
  configs for paper/shadow order staging.
- Imbalance order-plan bridge converts promoted microprice candidates into
  broker-neutral paper/shadow templates for bid-pressure buy and ask-pressure
  sell paths, with quantity, price, notional, and threshold checks.
- Imbalance launch pipeline runs promoted candidates through order planning,
  staging, launch bundle creation, broker export, upload pack, and broker
  readiness review for Arrow.money/iRage-style paper or shadow handoff.
- End-to-end imbalance research pipeline that runs edge walk-forward,
  replay-proof walk-forward, and candidate promotion in one manifest-backed
  command with stage-level readiness evidence plus optional required
  market-portability and multi-day data-readiness comparison preflights.
- Strategy evidence review supports an `imbalance` profile that requires
  imbalance edge walk-forward, replay walk-forward, promotion, research
  pipeline, order-plan, and launch-pipeline artifacts with shared strategy and
  market identity before shadow scale-up review.
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
- Strategy evidence review supports a `settlement` profile that requires
  settlement walk-forward, promotion, order-plan, and launch-pipeline artifacts
  with shared India market identity before shadow scale-up review.
- Compliance/risk utilities for OTR and cross-segment loss/profit guardrails.
- Black-76 pricing, implied-vol inversion, and quadratic smile fitting for
  options surface work.
- Surface-driven market-making quote generation with inventory skew and quote
  budget controls.
- Surface quality review that checks whether fitted theoretical values beat
  current option mids against future chain mids before replay, sweep, or paper
  routing work.
- Surface quote-risk review can require accepted multi-day vendor
  data-readiness comparison evidence before quotes move into replay or
  paper-routing workflows, and stamps strategy/market identity for catalog
  evidence review.
- Broker-neutral staging for surface quotes can require a passed quote-risk
  review, blocking all orders before Arrow.money/iRage preparation when quote
  hygiene evidence is missing or failed.
- Surface market-making robustness sweeps can require a passed quote-risk
  review and fail closed with manifest-backed proof artifacts before replay
  grids are run.
- Direct surface market-making replay can require the same quote-risk review
  and emits blocked replay artifacts instead of simulating unreviewed quotes.
- End-to-end surface market-making research pipeline that chains quote
  generation, optional surface-quality replay, quote-risk/data-readiness
  review, replay sweep proof, scenario selection, and promotion into one
  manifest-backed candidate run with an optional required market-portability
  preflight before quote generation while retaining surface-MM strategy and
  market identity across nested evidence artifacts.
- Strategy evidence review now supports a `surface_mm` profile that requires
  surface-quality, quote-risk, surface market-making research pipeline, and
  surface market-making launch pipeline artifacts with shared strategy and
  market identity before shadow scale-up review.
- Surface market-making launch pipeline that consumes a promoted surface
  research pipeline and first verifies upstream research readiness plus
  strategy/market identity before running quote-risk-enforced lifecycle
  planning, staging, launch bundling, broker export, upload-pack generation,
  and broker-readiness/runtime-session checks.
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
- Broker readiness now consumes dispatch round-trip route-readiness proof,
  requiring matching strategy/market identity and zero route gaps before
  Arrow.money/iRage live dry-run handoff, while retaining any final
  round-trip vendor market-data batch proof for broker-readiness handoff.
- Shadow session reports can now require and carry broker-readiness evidence,
  including broker route-readiness and dispatch round-trip proof, into
  session-level go/no-go records.
- Shadow session comparison now aggregates broker-readiness route proof across
  accepted sessions and blocks partial, mixed, or dirty broker route/dispatch
  proof before controlled scale-up.
- Unified `hft` command runner for scanners, replays, lead-lag measurement,
  and calibration reports.
- Spread-capture decomposition for paired round-trip fills, plus residual
  inventory reports in replay outputs.
- Data-quality diagnostics for tick and option-chain files, including spread,
  depth, timestamp, session, crossed quote, and strike coverage reports.
- Data readiness gate that combines vendor CSV intake, schema audit,
  mapped-data normalization, tick/chain diagnostics, market-profile fee
  assumptions, market-portability strategy/market pair approval, and
  instrument metadata before strategy research or promotion.
- Data readiness now carries vendor intake kind-selection state and emits a
  dedicated fail-closed check when auto-detected Arrow.money/iRage CSV kind is
  ambiguous, so proof catalogs can explain blocked vendor onboarding without
  reopening the intake folder.
- Data readiness can now require the vendor-intake kind to match the expected
  market-data kind, preventing an `orders` or `fills` sample from satisfying a
  `ticks` or `chain` research-data gate.
- Data readiness now checks adapter consistency across vendor intake, schema
  audit, and mapped-data summaries, and can enforce an expected Arrow.money or
  iRage adapter before research data is accepted.
- Data readiness now also checks data-kind consistency across vendor intake,
  schema audit, and mapped-data summaries, and applies expected tick/chain
  kind checks to mapped-data and schema evidence, not only intake evidence.
- Data readiness artifacts now carry vendor intake source-file, source-header,
  mapping-draft, file-size, and mapping-coverage fingerprints into both
  component rows and the top-level summary for catalog and broker handoff
  traceability.
- Vendor market-data onboarding pipelines that run Arrow.money/iRage CSV
  intake, normalized mapping, tick/chain diagnostics, data-readiness gates, and
  multi-day readiness comparison before walk-forward research, carrying raw
  source, header, mapping, component-manifest, and comparison fingerprints for
  repeatable vendor data proof, plus JSON handoff configs for strategy research
  and future vendor adapters.
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
  India-specific settlement mechanics blocked until a separate US model
  exists, while emitting a machine-readable ready/gap config with matching
  strategy-evidence and ops-launch evidence commands for downstream US research
  planning.
- Route readiness review that combines market-portability pairs, matching
  strategy evidence, and file-provenance-gated `ops_launch` evidence into a
  route-level live-dry-run go/no-go matrix.
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
- Broker readiness gate that fingerprints supplied dispatch round-trip config
  files so carried route-enable dispatch failed-check counters stay auditable
  when round-trip evidence is passed as either a folder or sibling files.
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
  lifecycle, runtime guard, halt-response, and resume artifacts, plus input
  provenance counters that separate exact file fingerprints, directory-tree
  fingerprints, hashed inputs, and unresolved raw inputs.
- Strategy evidence review gate that consumes the experiment catalog and
  requires successful proof, stress, promotion, broker-readiness, shadow, or
  user-selected run types before scale-up decisions, with optional fail-closed
  checks that all passing required artifacts share the expected strategy and
  market identity, including runtime identity aliases from broker and shadow
  evidence.
- Strategy evidence review supports an `ops_launch` profile, with
  `broker_dryrun`, `launch_ops`, and `live_dryrun` aliases, that requires
  scale-up, runtime telemetry, runtime guard, runtime-session, broker
  readiness, cutover, route-enable, dispatch plan, non-submitting send packet,
  dispatch acknowledgement, and broker dispatch round-trip artifacts before a
  launch route is treated as operationally proven, and emits an operational
  live-dry-run route-review recommendation instead of the strategy scale-up
  recommendation; ops-launch reviews now fail closed by default on directory or
  unfingerprinted catalog inputs unless explicitly allowed.
- Controlled scale-up plan report that combines strategy evidence, shadow
  comparison, launch, optional exposure summaries, proof freshness, and
  instrument metadata coverage, single-day and multi-day data-readiness
  evidence, route-readiness evidence, and broker-readiness evidence into
  explicit order, open-order notional and age, position notional, adapter,
  telemetry-freshness,
  lifecycle-order, replace-order, delta, and vega kill-switch limits, carries
  strategy/market identity, direct and shadow proof-refresh state, and broker
  runtime-session guard, resume-gate, and dispatch round-trip evidence into
  scale-up configs, automatically requires broker/runtime guard and clean
  dispatch round-trip evidence plus route-readiness proof and nested route
  proof for live-dry-run targets, consumes lead-lag, imbalance, parity-box,
  settlement, and surface-MM launch pipeline root summaries for strategy/market
  readiness continuity when a launch-pipeline folder is supplied directly,
  fingerprints the resolved input summary CSVs plus route-readiness and nested
  broker-readiness proof in the manifest, consumes multi-day shadow-comparison
  broker-readiness route/dispatch proof and broker-readiness-carried shadow
  broker proof plus broker-readiness vendor market-data batch proof when present,
  hydrates broker vendor-data proof from nested broker-readiness config sidecars
  when launch-pipeline summaries are thin, fails closed
  on broker runtime-session, broker resume-gate proof-refresh, dispatch
  round-trip failed checks, route-enable dispatch round-trip failed checks,
  dispatch route proof, launch-pipeline identity mismatches, dirty
  broker-carried shadow broker/vendor data proof, or shadow proof-refresh or shadow
  broker-readiness strategy/market mismatches, carries vendor market-data batch
  config provenance from onboarding comparisons through cutover authorization,
  and can consume these launch pipeline roots directly.
- Runtime telemetry snapshot builder that converts scale-up, export,
  broker-upload, reconciliation, optional instrument metadata, PnL, open-order,
  and position artifacts into guard-ready `runtime_telemetry.csv` inputs with
  source/check summaries, derives active open-order notional from remaining
  quantity/price or broker notional fields, derives stale open-order age from
  broker age fields or active order timestamps, derives live gross/net position
  notional from marks or total notional columns, derives net delta/vega from
  total or unit Greek position columns, carries scale-up strategy/market and
  proof-refresh freshness identity plus broker resume-gate proof identity, and
  can consume launch pipeline roots for broker export and upload-pack evidence
  while recording resolved source CSV paths and manifest fingerprints.
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
  top-level session summary while fingerprinting resolved source snapshots,
  telemetry/guard child artifacts, child manifests, and optional halt-response
  artifacts in the session manifest.
- Halt response planner that converts runtime guard halts into broker-neutral
  cancel-order and flatten-position action files with fail-closed price checks
  and manifests, stamping guard failed check names and first halt reasons onto
  the summary and action CSVs for operator review while carrying strategy and
  market identity into the emergency action packet, and fingerprinting resolved
  guard summary/check files plus open-order and position snapshots.
- Halt response export mapper that turns emergency cancel and flatten actions
  into reviewed broker/vendor CSV shapes, with normalized passthrough until
  Arrow.money/iRage emergency schemas are finalized, and fingerprints the
  exact halt-response action files plus optional mapping files.
- Halt execution reconciliation gate that verifies emergency cancel
  acknowledgements, flatten fills, and final flat positions after a guard halt,
  while fingerprinting the halt-response action files and supplied execution
  evidence snapshots.
- Halt incident review that combines guard, response, export, and execution
  evidence into one incident-closure timeline, check set, and summary with
  guard trigger plus strategy/market context carried through the review and
  fingerprints each component summary/check file.
- Post-halt resume gate that requires a closed incident, ready scale-up plan,
  scenario/adapter, strategy/market, and proof-refresh continuity, optional
  operator approval, and emits resume authorization/config artifacts carrying
  the incident guard trigger and proof context from the prior halt, with
  automatic operator approval and guard-trigger acknowledgement required for
  `live_dryrun` resumes while fingerprinting resolved incident, scale-up, and
  operator-review inputs.
- Cutover gate that authorizes the final paper/shadow/live-dryrun route only
  after scale-up, route-readiness proof, broker readiness, runtime-session
  guard, proof freshness, required dispatch round-trip proof plus nested route
  proof for live-dry-run, nested broker-readiness summaries from launch
  pipeline roots, scale-up shadow broker-readiness aggregates, dispatch
  round-trip and route-enable failed-check counters, optional broker
  resume-gate proof, broker-readiness-carried shadow broker proof,
  broker-readiness-carried vendor market-data batch proof, and operator
  strategy/market/limit acknowledgement agree in one manifest-backed
  authorization artifact that fingerprints resolved scale-up, broker-readiness,
  runtime-session, and operator-review inputs.
- Route-enable packet that consumes ready cutover and broker upload evidence,
  bounds order counts and optional export notional by cutover limits, rechecks
  cutover route-readiness proof, live-dry-run dispatch round-trip proof,
  carried route-enable failed-check counters, nested route proof, and
  cutover-carried shadow broker-readiness aggregates plus
  broker-readiness-carried shadow broker proof, carries cutover-retained vendor
  market-data batch dataset/header/mapping provenance plus
  cutover-retained broker-readiness vendor market-data batch proof, resolves
  broker upload/export summaries from launch pipeline roots, fingerprints resolved
  cutover/upload/export inputs, and emits the final machine-readable broker
  route-enable config without submitting orders.
- Broker dispatch planner that binds a route-enable authorization to the exact
  broker upload rows, hashes the route/upload payloads, creates deterministic
  dry-run dispatch IDs, carries broker schema review status/mode plus
  route-readiness proof, live-dry-run nested route proof, and route-carried
  shadow broker-readiness aggregates plus broker-readiness-carried shadow
  broker proof from route-enable as `route_broker_shadow_broker_*`, preserves
  route-enable-carried vendor market-data batch provenance as
  `route_vendor_market_data_batch_*`, preserves route-enable-carried
  broker-readiness vendor market-data batch proof as
  `route_broker_dispatch_roundtrip_vendor_market_data_batch_*`, and fails
  closed on disabled routes,
  nested route-enable dispatch round-trip failed checks, dirty route proof,
  duplicate source order IDs, dirty carried shadow broker proof, or unresolved
  upload-order files while resolving launch pipeline upload roots and
  fingerprinting the route-enable summary/config, route-enable manifest, and
  upload CSV without sending orders.
- Broker dispatch send packet builder that turns an armed dry-run dispatch
  plan into non-submitting adapter request envelopes, idempotency keys, payload
  hashes, route-readiness proof, route round-trip proof tags, and
  acknowledgement templates while carrying broker schema review status/mode
  route-enable dispatch round-trip failed-check counters, dispatch-carried
  shadow broker-readiness aggregates plus broker-readiness-carried shadow
  broker proof from the dispatch config as `route_broker_shadow_broker_*`, and
  vendor market-data batch provenance as `dispatch_vendor_market_data_batch_*`,
  plus broker-readiness vendor market-data batch proof as
  `dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_*`, validating route-readiness identity,
  carried shadow proof quality, and route proof batch continuity, forcing live
  submission off, and fingerprinting exact dispatch input files plus the
  dispatch manifest when present.
- Broker dispatch acknowledgement reconciliation that matches dry-run dispatch
  rows to broker ack logs, accepts only explicit success statuses, carries
  broker schema review status/mode, route-readiness proof, route round-trip
  proof, and route-enable failed-check counters from the dispatch config,
  validates route-readiness identity, send-stage shadow broker-readiness
  aggregates, broker-readiness-carried shadow broker proof,
  dispatch-carried vendor market-data batch provenance as
  `ack_vendor_market_data_batch_*`, broker-readiness final dispatch
  round-trip vendor market-data proof as
  `ack_broker_dispatch_roundtrip_vendor_market_data_batch_*`, and
  acknowledgement-log proof batch continuity, hydrating missing broker
  vendor-data proof through dispatch/route-enable/cutover manifests when
  needed, and
  fails closed on missing, rejected, duplicate, dirty-proof, stale-proof, or
  unmatched acknowledgement rows while fingerprinting exact dispatch, dispatch
  manifest, and ack log inputs.
- Broker dispatch round-trip review that joins dispatch rows, non-submitting
  sender requests, and broker acknowledgements into one dry-run proof gate with
  identity, route-readiness consistency, raw ack-log route proof consistency,
  route-enable failed-check counters and broker schema review status/mode from
  upstream configs, shadow broker-readiness consistency across dispatch, send,
  and acknowledgement configs, broker-readiness shadow broker consistency,
  vendor market-data batch provenance consistency, broker-readiness final
  dispatch round-trip vendor market-data consistency, hydrating missing broker
  vendor-data proof through dispatch/route-enable/cutover manifests when
  component configs are thin,
  request-count, submission-disabled, and
  accepted-ack checks while fingerprinting exact component proof files and
  manifests.
- Replay stress reports for extra fee multipliers, tick slippage, and adverse
  bps shocks, including stressed PnL, cost bps, drawdown, strategy/market
  identity consistency, and pass/fail gates.
- Surface quote runner that fits per-snapshot option smiles from chain/futures
  data using explicit market session profiles and emits budgeted market-making
  quotes with marketability checks and manifests.
- Surface quote risk review for market-making quote sets, gating marketable
  quotes, quote edge, side balance, market spread, instrument coverage, and
  concentration before replay or live routing.
- Surface quote lifecycle planner that converts reviewed quote snapshots into
  submit/replace/cancel actions plus routeable submit/replace order files with
  optional surface-quality evidence, TTL, OTR, message-budget, and
  active-quote controls before Arrow.money/iRage paper-routing preparation,
  preserving replace lineage through staging, launch, and broker-neutral
  export artifacts.
- Option order exposure review for staged, launch, or exported order batches,
  including Black-76 delta/vega, gross notional, side imbalance, and
  instrument concentration checks, with cross-market option metadata inference
  for internal, settlement, NSE compact, and OCC symbols.
- Passive surface market-making replay that tests generated quotes against
  later option-chain snapshots, writes fills/unfilled quotes/equity/markout
  artifacts, and produces proof-report-compatible `summary.csv` runs.
- Surface market-making robustness sweep across TTL, routing latency,
  fill-depth, and markout horizons, with market identity carried through
  per-scenario replays, proof gates, robust scores, and manifests.
- Broker-neutral order staging for generated quotes or generic order
  candidates, including optional surface-quality evidence, pre-trade
  quantity/notional/marketability/price-band checks, accepted/rejected order
  artifacts, and manifests for later Arrow.money/iRage routing adapters.
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
  emits a reviewed-mapping draft plus source/header/mapping fingerprints for
  market-data normalization.
- Vendor CSV intake now fails closed when automatic kind detection is
  ambiguous, for example when a broker file can be interpreted equally well as
  orders or fills, and requires an explicit `--kind` before normalization.
- Broker integration readiness report that combines schema audit, broker order
  export, mapping draft, mapped orders, upload pack, optional halt export, and
  optional reconciliation/runtime-session/resume-gate/dispatch-roundtrip
  evidence into one fail-closed Arrow.money/iRage go/no-go artifact, blocking
  unreviewed placeholder schemas unless a passed schema audit, reviewable
  order-mapping draft, and mapped-order export prove a reviewed vendor mapping
  path for the same adapter, blocking supplied or required runtime sessions
  when the scale-up guard halted, retaining resume proof-refresh identity for
  post-halt restart review, and resolving launch pipeline export/upload roots
  while carrying proved dry-run dispatch round-trip identity, route proof
  quality, failed-check count, route-enable dispatch round-trip failed-check
  count from the round-trip config, round-trip manifest provenance, shadow
  broker-readiness aggregate, broker-readiness-carried shadow broker aggregate,
  round-trip vendor market-data batch provenance, broker-readiness final
  dispatch round-trip vendor market-data provenance,
  acknowledgement quality, schema review mode, and a structured
  `broker_readiness_config.json` handoff into broker readiness,
  scale-up, cutover, and route-enable handoff artifacts, with scale-up now
  fingerprinting the broker-readiness JSON sidecar when present,
  cutover fingerprinting the same sidecar from direct or nested
  broker-readiness inputs, preserving broker-readiness-carried shadow proof
  separately as `broker_shadow_broker_*` fields and cutover preserving them as
  `scaleup_broker_shadow_broker_*` authorization/config fields, with
  route-enable fingerprinting the cutover manifest, carrying the same proof as
  `cutover_broker_shadow_broker_*`, preserving cutover-retained vendor
  market-data batch provenance as `cutover_vendor_market_data_batch_*`, and
  dispatch preserving that provenance as `route_vendor_market_data_batch_*`
  before the sender packet carries it as `dispatch_vendor_market_data_batch_*`
  and the ack gate carries it as `ack_vendor_market_data_batch_*`, with the
  final round-trip proof preserving it as `roundtrip_vendor_market_data_batch_*`
  before broker readiness revalidates and carries it directly or as
  `dispatch_roundtrip_vendor_market_data_batch_*`, and scale-up revalidates and
  carries the broker-readiness broker-specific copy as
  `broker_dispatch_roundtrip_vendor_market_data_batch_*` before cutover
  prefers the broker-specific config block, hydrates missing scale-up broker
  vendor-data proof from direct or launch-root broker-readiness sidecars,
  revalidates it, and preserves it as
  `scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_*`, and
  route-enable prefers its cutover-specific config block, hydrates missing proof
  from broker-readiness sidecars referenced by the cutover manifest, revalidates it, and
  preserves it as
  `cutover_broker_dispatch_roundtrip_vendor_market_data_batch_*`, before
  broker dispatch prefers its route-native config block, hydrates missing proof
  through the route-enable/cutover manifest chain, revalidates it, and
  preserves it as
  `route_broker_dispatch_roundtrip_vendor_market_data_batch_*`, before the
  non-submitting sender packet prefers its dispatch-native config block, hydrates missing proof
  through the dispatch/route-enable/cutover manifest chain, and
  preserves it as
  `dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_*`, before the
  acknowledgement reconciliation prefers its ack-stage config block, hydrates
  missing proof through the dispatch/route-enable/cutover manifest chain, and
  preserves it as
  `ack_broker_dispatch_roundtrip_vendor_market_data_batch_*`, and the final
  round-trip proof prefers its roundtrip-stage config block, hydrates missing
  component proof through the dispatch/route-enable/cutover manifest chain, and reconciles it as
  `roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_*`, before
  broker readiness prefers its readiness-native broker vendor-data config block
  when present, otherwise revalidates the roundtrip-stage block directly or
  through normalized handoff fields, scale-up, cutover, route-enable, broker
  dispatch, broker dispatch send, broker dispatch ack, and the final
  round-trip gate accept those direct final proof prefixes and carry them into
  their stage-native broker vendor-data fields, and broker readiness can
  promote the generic final round-trip vendor proof into broker-specific
  readiness proof when no broker-prefixed proof is present.
  Broker vendor-data
  proof selection now uses one shared active-proof selector across cutover,
  route-enable, dispatch, send, ack, round-trip, and broker-readiness stages,
  and broker readiness can now consume a generated
  `vendor_market_data_batch_config.json` directly for Arrow.money/iRage
  end-to-end intake proof runs. A top-level
  `pipeline-broker-vendor-readiness` command now chains vendor batch generation
  into broker readiness and emits root summary/config/manifest artifacts, and
  all launch-family pipelines can forward that proof root into broker readiness
  through `--broker-vendor-data-readiness` with regression coverage for
  lead-lag, imbalance, parity, settlement, and surface-MM across direct API and
  CLI operator paths. The generated `pipeline-broker-vendor-readiness` root now
  has end-to-end CLI coverage feeding a launch pipeline before scale-up
  preserves the broker-readiness config sidecar proof in its operator-visible
  summary/config. Broker readiness now evaluates standalone vendor-batch proof
  roots even when no dispatch round-trip proof is supplied, compares them
  against the launch/broker expected market when available, and fails closed
  across all five launch CLIs when an iRage proof root is supplied to an
  Arrow.money/normalized launch adapter or when an otherwise matching proof
  root carries a non-India market. The standalone `review-broker-readiness`
  CLI now also accepts `--expected-market` so operator-supplied vendor-batch
  artifacts can be market-checked outside a launch pipeline, including
  vendor-only proof roots with no dispatch round-trip supplied. Broker
  readiness now also checks expected vendor data kind, so chain proof roots
  cannot satisfy tick-data launch/broker-readiness gates, and it validates the
  vendor-batch manifest run type so a random or mislabeled proof directory
  cannot satisfy broker/vendor market-data readiness. Scale-up now carries the
  same manifest identity field from generic or broker-prefixed broker-readiness
  vendor proofs and rejects non-`vendor_market_data_batch_pipeline` proofs
  before controlled capital increases. Cutover now preserves and revalidates
  the same manifest identity on scale-up-carried broker/vendor proofs before
  route enable can inherit them. Route enable now carries and revalidates that
  manifest identity before broker dispatch planning can inherit cutover-carried
  broker/vendor data proof. Broker dispatch planning now carries and revalidates
  that identity before send packets can inherit route-enable-carried proof.
  Broker dispatch send, acknowledgement, and final round-trip gates now carry
  and revalidate the same identity before scale-up can inherit it, including
  both generic and broker-readiness-prefixed vendor proof paths.
- Halt response and halt incident evidence now preserve runtime proof-refresh
  fields from the guard through cancel/flatten packets, response summaries,
  response config, incident timelines, and incident closure summaries.

## Test Gate

Run from repo root:

```powershell
pytest
```

Current passing suite: 819 tests.

## Next Build Targets

1. Add data adapters for the first real vendor export once files are available.
2. Replace placeholder Arrow.money/iRage column maps once real export schemas
   are available.
3. Replace the built-in upload review templates with broker-signed
   Arrow.money/iRage order schemas once sample files are available.
