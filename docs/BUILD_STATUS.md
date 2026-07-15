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
- Strategy evidence and scorecards now include a
  `provider_imbalance_ops_launch` profile that requires the provider-data
  imbalance scorecard, route-readiness, runtime, broker-readiness, cutover,
  route-enable, dispatch/send/ack, final round-trip wrappers, and the
  non-authorizing broker rehearsal certificate before live-dry-run review. The
  scorecard now also propagates provider final
  broker round-trip synthetic sidecar proof counts and blocks the provider
  launch profile when expected sidecars are missing or unreadable. It also
  propagates broker rehearsal certificate passed/live-dry-run/authorizing/hash
  counts into scorecard actions.
- Generic sweep selections now have a CSCV-style backtest-overfit audit.
  `audit-backtest-overfit` forms deterministic chronological partitions,
  evaluates symmetric in-sample/OOS combinations, reports Probability of
  Backtest Overfitting, rank stability, selected-scenario degradation and OOS
  positive rate, fails incomplete scenario grids, and separately gates the
  rank-1 candidate's selection rate, conditional overfit rate, and conditional
  OOS positive rate. `promote-scenario` can
  require this proof and always blocks a supplied audit that failed, came from
  a different selection-manifest SHA, or drifted from its own manifest.
- Selected candidates now have a multiple-testing-aware significance gate.
  `audit-backtest-significance` consumes current CSCV partition scores, runs an
  exact one-sided sign test with scenario-count Bonferroni correction, and
  records a deterministic bootstrap mean interval and positive-mean
  probability. It fails closed on weak or underpowered evidence, a failed CSCV
  audit, candidate mismatch, or any overfit artifact/input drift. Generic
  promotion can require and manifest-bind this proof from the same selection.
- Selected candidates now have a selection-isolated chronological holdout
  gate. `audit-backtest-holdout` evaluates only the frozen development winner,
  rejects development/holdout path overlap, verifies each holdout sweep and
  source fingerprint, and gates full candidate coverage, proof pass rate,
  mean/median/worst score, net PnL, fills, and optional drawdown. Promotion
  binds the candidate identity, selection-manifest SHA, and current holdout
  manifest. The audit explicitly distinguishes recorded selection isolation
  from any unverifiable claim that a human never inspected the data.
- Multi-period parameter research now has a single strict orchestration gate.
  `pipeline-robust-selection` reserves the final three ordered sweeps as
  holdouts by default, requires full coverage across the earlier development
  periods, and verifies every sweep against its generating manifest. It then
  runs CSCV, corrected significance, frozen-candidate holdout, and promotion,
  binding all proofs and the exact selection manifest into root evidence. The
  default ready study therefore needs nine periods: six development plus three
  holdouts. Missing or drifted provenance, development/holdout overlap,
  underpowered studies, incomplete grids, memorized parameters, instability,
  weak corrected significance, losing holdouts, downstream drift, or promotion
  breaches fail closed. Sweep integrity is bound into nested promotion so a
  leaf cannot appear ready when root provenance failed. Ready output advances
  only to broker-neutral order staging with `authorizes_submission=false`.
  A supplied prospective research-family registration is now a first-class
  preflight stage: the exact registered study row must match the result root,
  strategy, market, primary metric, scenario ceiling, and development/holdout
  counts. Its registration ID and manifest SHA are preserved in the root
  summary, candidate config, and manifest. Registration proof and sweep
  provenance jointly gate nested promotion; exploratory unregistered runs stay
  compatible unless registration is explicitly required.
  Registered executions now add a launch-contract preflight that verifies the
  current matrix artifact, contract-core hash, exact study/output identity,
  ordered sweeps and labels, grouping columns, holdout count, and registration
  fingerprint. The robust root fingerprints the immutable contract file and
  records the matrix-manifest SHA observed at launch, so refreshing mutable
  closure coverage does not invalidate the completed result.
  The official executor now creates a unique launch-execution receipt before
  dispatch. That receipt binds the immutable contract, exact stored argv,
  launch-matrix manifest observed at dispatch, and a canonical digest of the
  resolved robust-selection semantics. The completed root fingerprints the
  receipt and must reproduce the same semantic digest, so manual argv edits,
  changed defaults, threshold overrides, or reconstructed launches fail the
  promotion preflight.
  Dispatches now also append an immutable receipt-linked record to a
  lock-protected, hash-chained attempt ledger. Duplicate calls fail closed.
  A retry must name the latest attempt ID, include a non-empty reason, and carry
  explicit operator attestation; a contract with any completed robust summary
  cannot be replayed. Robust roots fingerprint their immutable attempt record,
  while launch coverage revalidates the complete live chain.
  The executor now finalizes each returned or exceptional dispatch into a
  second immutable, hash-chained outcome record. Outcomes distinguish
  completed-ready, completed-blocked, completed-inconsistent, and interrupted
  attempts while binding exit status plus exact result summary/manifest hashes.
  Completed coverage requires the outcome's stored manifest hash to match the
  current robust root. Missing finalization is reported as completed-unfinalized
  rather than inferred away or made replayable.
  `recover-research-family-study-outcome` closes that narrow crash window
  without dispatching research again. Recovery requires the latest attempt ID,
  a current result bound to the same receipt/contract, an exit status consistent
  with root readiness, a non-empty reason, and explicit operator attestation.
  The recovered claim is preserved inside the ordinary immutable outcome chain.
- Research families can now be registered prospectively before outcomes exist.
  `register-research-family` normalizes and validates a CSV plan containing
  strategy, market, hypothesis, metric, maximum search breadth, at least six
  development periods, at least three holdouts, and a future result root for
  each study. It emits a deterministic registration ID, lock file, runbook, and
  manifest bound to the original plan. Shared manifest timestamps now retain
  microsecond UTC precision so post-hoc registrations can fail time ordering.
- Registered research families now have an immutable launch and closure-
  coverage matrix. `plan-research-family-launches` consumes prospective JSON
  sweep/group specifications, verifies every sweep manifest, emits a
  deterministic argv contract per registered row, and classifies results as
  completed-ready, completed-blocked, completed-unfinalized,
  attempt-incomplete/interrupted/inconsistent, explicitly abandoned, or never
  launched.
  Existing roots count only when they bind the exact registration ID, label,
  manifest SHA, launch-contract ID, contract-file SHA, execution-receipt ID,
  and hash-chained attempt record. The
  `run-research-family-study` executor runs only a current launch-ready row's
  exact stored argv and injects the receipt path as dispatch evidence.
  Abandonments require a unique reason ledger row and an explicit operator
  attestation; all artifacts remain non-authorizing.
- Cross-strategy research now has a declared-family multiple-testing ledger.
  `audit-research-family` verifies each robust-selection root, includes failed
  and non-ready attempts in the family size, and applies Holm-Bonferroni to the
  already scenario-adjusted candidate p-values. Only source-ready candidates
  with passed holdout proof can survive. Duplicate roots, drift, missing
  p-values, authorizing source claims, and an incomplete-family attestation all
  fail closed. Optional prospective closure additionally requires a current
  matching registration/lock, exact family labels and result paths, and a
  registration timestamp earlier than every result manifest. Closure also
  matches strategy, market, primary metric, maximum scenario breadth, and exact
  development/holdout counts against each registered row. It now additionally
  requires every robust source root to carry a passed binding to its exact
  registered study label and to fingerprint the same registration-manifest SHA
  used for closure. Retrospective path and contract matching alone cannot close
  a family. A current launch matrix can now add attested abandoned studies to
  Holm's denominator at conservative adjusted p-value 1.0 while keeping them
  ineligible for candidacy. Never-launched rows, omitted completed roots, launch
  drift, and incomplete coverage block closure. The audit still
  records the operator's completeness attestation because omitted experiments
  cannot be detected by software and invalidate the error-control claim.
  Family closure now also emits a launch-attempt/outcome census sourced from
  the strict immutable ledgers. Every dispatch, interruption, finalized or
  recovered outcome, and attested exact retry remains visible in
  `research_family_launch_attempt_census.csv` and as per-study aggregate
  fields. Census closure cross-checks current
  contract IDs, per-contract and aggregate attempt/outcome counts, latest
  record pointers, retry evidence, and non-authorizing status against the
  launch matrix. Operational retries remain bound to the same registered
  contract and explicitly contribute zero additional hypotheses to Holm's
  denominator.
- Lead-lag, imbalance, parity/box, settlement, and surface-MM launch pipeline
  root summaries now retain broker-readiness route-control proof from
  broker-vendor data readiness roots as `broker_readiness_route_readiness_*`
  and `broker_readiness_route_broker_route_readiness_*` fields.
- Runtime telemetry, runtime guard, and runtime-session summaries now carry
  scale-up `broker_readiness.route_readiness` proof into live-dry-run
  monitoring, including route-ready/gap pairs plus launch-control,
  portfolio-safe, and concentration-safe broker route runs; the guard fails
  closed when required route proof is missing, mismatched, or stale.
- Controlled scale-up now also carries route-readiness resume-route proof:
  direct route-readiness summaries preserve
  `ops_broker_roundtrip_resume_route_*_pairs`, broker-carried route proof
  preserves `ops_broker_roundtrip_resume_route_*_runs`, and scale-up blocks
  stale broker route proof when the resume-route ready run is missing or any
  resume-route breach subtype is non-zero.
- Market-data source planning is now a first-class backend integration gate:
  `plan-market-data-source` validates file replay, Arrow.money, and iRage
  source contracts, records sanitized REST/websocket/file URIs, stores only
  credential environment variable names, and hands ready file sources to
  `pipeline-vendor-market-data` while live sources point to the provider
  fetcher implementation. Source plans now also write a blank
  `market_data_source_env_template.env` sidecar and a manifest-backed
  `live_fetch_contract` command template so Arrow.money/iRage credential
  staging and dry-run fetch planning are traceable from the first backend gate.
  Arrow.money and iRage live plans now default missing credential env-var names
  into blank provider-specific template entries, preserving the no-secret
  artifact contract while letting adapter setup proceed before real credentials
  arrive.
  Source, fetch, fetcher, and client handoffs now also preserve the provider
  exchange/segment plus the market-session timezone/open/close window, giving
  iRage/Arrow adapter wiring an explicit NSE/NFO session contract instead of
  relying on implicit defaults.
  Source plans now also write a hashable `provider_profile` contract covering
  the built-in provider adapter, supported transports, capabilities, default
  credential env-var names, auth requirement, and `values_stored=false`; fetch
  plans, provider request templates, client packets, adapter execution
  contracts, and manifests preserve the same profile SHA and block stale
  artifacts that lose it before real iRage/Arrow backend adapters are wired.
- Market-data fetch planning now consumes those source contracts:
  `plan-market-data-fetch` validates provider/file handoff, symbols, REST
  backfill windows, latency budgets, credential env-var references, and output
  filenames without calling external APIs or storing secrets; file plans route
  to `pipeline-vendor-market-data` and REST/websocket plans route to the
  provider fetcher with a manifest-backed config. Fetch plans now fail closed
  when a live source plan is missing its blank credential env-template sidecar,
  fingerprint that template in the manifest, and carry the upstream
  `live_fetch_contract` into `market_data_fetch_config.json` for Arrow.money
  and iRage adapter handoff.
- Provider market-data fetcher preparation now turns ready REST/websocket fetch
  plans into credential-safe request/subscription templates:
  `plan-provider-market-data-fetcher` validates live transport, symbols,
  runtime budgets, carried source-plan env-template proof, carried
  `live_fetch_contract`, and optional env-var presence while writing only
  env-var names, blank env-template path/hash references, and presence booleans,
  not secret values. Request templates now also carry a credential-safe
  `adapter_execution_contract` with provider/adapter/transport/mode, endpoint,
  output filename, blank env-template proof, env-var names, dry-run status, and
  explicit API-contract approval requirements for the future Arrow.money/iRage
  backend adapter. The adapter contract also carries the provider-profile SHA
  and capabilities expected by the future backend runner.
- Provider market-data client dry-run packets now close the backend data-source
  handoff before live credentials: `prepare-provider-market-data-client`
  validates ready request templates, env-var contracts, normalized CSV output
  schema, runtime budgets, carried blank env-template proof, and carried
  `live_fetch_contract`, then emits a manifest-backed execution packet for the
  eventual Arrow.money/iRage client without making external API calls. Client
  packets now preserve that `adapter_execution_contract` plus session label,
  output schema columns, clock-skew budget, and local buffer budget so a backend
  runner can bind the exact dry-run contract without reading secrets. Client
  packets and manifests now also preserve the provider-profile contract and SHA.
- Provider market-data live session planning now creates credential-safe capture
  packets before the market opens: `plan-provider-market-data-live-session`
  validates the dry-run client packet, NSE session windows, weekday, optional
  runtime env-var presence, carried blank env-template proof, carried
  `live_fetch_contract`, carried exchange/segment plus source-session metadata
  matching the market profile, per-window capture paths, and emits the exact
  post-capture `pipeline-provider-market-data-batch` command. Live-session
  packets now also carry the upstream `adapter_execution_contract` plus the
  provider-profile contract/SHA, live-session readiness, trade date,
  capture-window count, capture-command count, and post-capture batch command,
  along with structured, non-secret provider capture command handoffs for each
  window: provider, transport, endpoint, env-var names, start/end, output path,
  and command template.
- Provider market-data live preflight now checks the planned provider capture
  just before the market run: `preflight-provider-market-data-live-session`
  validates the session packet, runtime credential env-var presence, carried
  blank env-template proof, carried `live_fetch_contract`, carried
  provider-profile contract/SHA, exchange/session metadata consistency,
  writable capture and batch paths, capture/batch collision risk, per-window
  provider capture command templates, and local clock timing without persisting
  credential values. The preflight config and manifest surface the provider
  capture command list and carried `adapter_execution_contract` with
  live-preflight readiness, timing status, capture counts, provider-profile
  SHA/capabilities, and credential env-var names for Arrow.money/iRage adapter
  execution, and fail closed if any capture window is missing it.
- Provider market-data live capture bundling now turns a ready preflight into
  a backend adapter handoff: `bundle-provider-market-data-live-capture` writes
  per-window capture commands, a credential-safe JSON bundle, a blank env-var
  template for provider credentials, a dedicated
  `provider_market_data_adapter_handoff.json` contract with schema columns and
  rendered commands, preflight-carried source env-template proof,
  `live_fetch_contract` provenance, provider-profile contract/SHA, inherited
  exchange/session metadata for the approved source, and the exact post-capture
  ingest command while blocking missing preflight evidence, metadata drift, and
  capture overwrite risk.
  Capture bundling now also requires the structured provider capture command
  handoff from both the live-session packet and preflight config to match,
  then carries that command list, provider profile, and
  `adapter_execution_contract` into the bundle, adapter handoff, and manifest
  for Arrow.money/iRage adapter execution audit.
  Default adapter commands now explicitly pass the handoff JSON and blank
  capture env-template file, so Arrow.money/iRage adapter processes receive
  the same contract artifacts the bundle manifests. Bundle summary/JSON,
  adapter handoff, and manifest extras now include capture env-template and
  adapter handoff SHA-256 values for direct provider handoff audit.
- The default provider capture command is now executable through the
  credential-safe `provider-adapter` runner. It loads only an explicit trusted
  Python `module:function` backend from the provider-specific backend env var
  (or the generic fallback), validates the ready handoff and blank credential
  template, requires runtime credentials without persisting their values,
  enforces exact provider/window/output identity, and verifies CSV schema,
  timestamps, quotes, and quantities before writing a hash-backed
  `<capture>.adapter.json` receipt. Capture bundles now publish the backend
  entrypoint env-var and callable contract in both the adapter handoff and
  `adapter_execution_contract`. Arrow.money/iRage network backends remain
  intentionally external until their approved API contracts are available.
- Provider market-data live rehearsal now proves the backend handoff without
  provider credentials: `rehearse-provider-market-data-live-capture` writes
  explicitly marked synthetic normalized captures from the bundle, optionally
  runs live-session ingest, fingerprints the bundle credential env-template and
  adapter handoff contract when present, carries the source env-template proof,
  `live_fetch_contract`, and `adapter_execution_contract`, and reports that the
  result is smoke-test evidence only until replaced by real Arrow.money/iRage
  captures. Synthetic capture sidecars now also retain the rendered adapter
  command hash, capture env-template hash, adapter handoff hash, source
  env-template proof, live-fetch contract summary, and credential-safe adapter
  execution summary, with manifest fingerprints for those sidecars before real
  provider credentials are used.
- Provider market-data live session ingest now closes the post-market loop:
  `ingest-provider-market-data-live-session` reads the session packet, verifies
  all expected capture files exist and are non-empty, then runs the structured
  provider batch ingestion and manifests the resulting proof chain. When an
  approved capture bundle is supplied, ingest also fingerprints the bundle and
  its blank credential env-template plus adapter handoff contract artifacts,
  source env-template proof, exchange/session metadata matching the live packet,
  `live_fetch_contract`, and `adapter_execution_contract` for backend handoff
  provenance. Ingest and evidence summaries/configs now also carry the capture
  env-template and adapter handoff SHA-256 values directly, so provider
  credential-template and adapter-contract provenance are visible without
  parsing the manifest input block. Bundle-linked ingest now also verifies that
  provider capture command handoffs, the provider-profile contract/SHA, and the
  adapter execution contract match the live-session packet, then carries the
  structured command list, provider profile, and adapter contract into the
  ingest summary/config/manifest for downstream live-data audit. Bundle-linked
  real captures must now also carry adjacent `provider-adapter` receipts. Ingest
  recomputes and validates capture, handoff, environment-template, and receipt
  hashes plus provider/window/schema/credential-presence contracts, fingerprints
  every receipt in the manifest, and routes missing, stale, or mismatched proof
  back to `provider-adapter`. Rehearsal-sidecar captures remain exempt at ingest
  only as explicitly synthetic smoke evidence and are still blocked from real
  research handoff by evidence review.
- Provider market-data live evidence review now protects research handoff from
  rehearsal artifacts: `review-provider-market-data-live-evidence` verifies
  live ingest, batch readiness, capture row counts, manifest proof,
  capture-bundle/env-template/adapter-handoff provenance, source env-template
  proof, exchange/session metadata, `live_fetch_contract`, and
  `adapter_execution_contract` when supplied, and credential-safe session
  packets while blocking `*.csv.rehearsal.json` synthetic captures from being
  marked research-ready. Synthetic smoke evidence now has to prove each
  rehearsal sidecar still matches the ingest lineage: adapter command hash,
  capture env-template hash, adapter handoff hash, source env-template proof,
  provider-fetcher handoff, credential-safe adapter contract, and rehearsal-only
  invariants are all validated against ingest provenance when present or the
  referenced files when rehearsal ingest did not carry the bundle block before
  `--allow-synthetic-rehearsal` can pass as smoke. Bundle-linked evidence review
  also carries provider capture command
  counts/lists, provider-profile proof, and the adapter execution contract from
  ingest into summary/config/manifest artifacts and blocks research handoff if
  the capture-bundle command list, provider profile, adapter contract, or
  rehearsal sidecar proof is missing or no longer matches the live-session
  packet. Bundle-linked real evidence now reruns adapter receipt validation
  against current captures and contracts, matches receipt records and hashes
  across ingest config plus manifest inputs/extras, fingerprints the receipts
  again, and blocks any capture or receipt mutation after ingest.
- Provider market-data research handoff now turns research-ready live evidence
  into executable strategy-research command plans:
  `handoff-provider-market-data-research` maps provider top-of-book tick folds
  to imbalance edge/replay walk-forward runs, carries capture
  bundle/env-template/adapter-handoff provenance, source env-template proof, and
  `live_fetch_contract` plus exchange/session metadata into summary/config/runbook
  artifacts plus the manifest, and keeps synthetic smoke evidence, missing
  upstream live-data contracts, metadata drift, or unsupported strategy lanes
  blocked until the needed real inputs exist. Research handoff summary/config and
  manifest extras now also expose the capture env-template and adapter handoff
  SHA-256 values directly for downstream strategy audit. The handoff now carries
  provider capture command counts/lists from live evidence and blocks strategy
  research if the capture-bundle command handoff is missing or mismatched. It
  also carries provider-profile proof and the credential-safe
  `adapter_execution_contract` into summary/config/runbook and manifest
  artifacts, and blocks research when either contract is missing, stores
  credential values, or no longer matches live evidence. Synthetic smoke
  handoff now also carries `synthetic_sidecar_proof` from live evidence into
  summary/config/runbook and manifest artifacts, and even explicit smoke mode
  blocks if the proof is missing, stale, or no longer covers every synthetic
  fold. The same handoff now carries `adapter_receipt_proof`, requires it to
  match between evidence config and manifest, and recomputes every capture and
  required receipt hash before strategy commands can become ready.
- Provider market-data imbalance research now runs the first strategy pipeline
  directly from provider live evidence: `run-provider-market-data-imbalance-research`
  nests the research handoff, executes imbalance edge/replay/promotion on real
  provider tick folds, preserves live capture bundle/env-template/adapter
  handoff provenance, source env-template proof, exchange/session metadata, and
  `live_fetch_contract` through the strategy wrapper artifacts and manifest, and
  blocks before strategy math when evidence is synthetic smoke or not
  research-ready. The wrapper summary/config and manifest extras also expose
  capture env-template and adapter handoff SHA-256 values directly for
  strategy-layer audit, and now carry provider capture command counts/lists plus
  capture-bundle command match proof into the imbalance research layer. The
  wrapper now also carries provider-profile proof and the credential-safe
  `adapter_execution_contract` from the nested research handoff into
  summary/config/runbook and manifest artifacts, and blocks strategy research
  when either contract is missing, unsafe, or no longer matched to live
  evidence. It now also carries nested `synthetic_sidecar_proof` and blocks
  explicit synthetic-smoke research when the rehearsal sidecar proof is missing,
  stale, or does not cover every synthetic fold. The wrapper now requires the
  handoff's sealed `adapter_receipt_proof`, verifies every required receipt and
  capture fingerprint against live evidence, fingerprints those source files in
  its own manifest, and blocks before strategy math when that proof is missing,
  incomplete, or mismatched.
- Provider market-data imbalance evidence review now packages live-data research
  into a research-only evidence profile:
  `review-provider-market-data-imbalance-evidence` catalogs the provider
  research run, reviews the `provider_imbalance_research` profile, carries
  capture bundle/env-template/adapter handoff provenance, source env-template
  proof, exchange/session metadata, capture-bundle session match proof, and
  `live_fetch_contract` into evidence summary/config/runbook artifacts plus the
  manifest, and points ready candidates to
  `pipeline-imbalance-launch` without weakening the full launch-ready
  `imbalance` profile. Evidence summary/config and manifest extras now also
  expose capture env-template and adapter handoff SHA-256 values directly, and
  carry provider capture command counts/lists plus capture-bundle command match
  proof into the research-evidence package. The evidence review now also carries
  provider-profile proof and the credential-safe `adapter_execution_contract`
  from provider imbalance research into summary/config/runbook and manifest
  artifacts, and blocks launch packaging when either contract is missing,
  unsafe, or no longer matched to live evidence. It now also carries nested
  `synthetic_sidecar_proof` plus flattened sidecar counts from provider
  imbalance research, and blocks launch packaging when synthetic provider folds
  are missing ready rehearsal sidecar proof. The review now reads the provider
  research manifest, requires its sealed `adapter_receipt_proof` to exactly
  match research config, rechecks all receipt/capture fingerprint counts, and
  preserves the proof in summary/config/runbook and manifest artifacts before
  launch packaging can become ready.
- Provider market-data imbalance launch packaging now bridges ready provider
  research evidence into broker handoff artifacts:
  `pipeline-provider-market-data-imbalance-launch` infers the promoted candidate,
  runs the standard imbalance launch pipeline, preserves capture
  bundle/env-template/adapter handoff provenance, source env-template proof, and
  exchange/session metadata, capture-bundle session match proof, and
  `live_fetch_contract` in the launch wrapper summary/config/runbook artifacts
  plus manifest, and points ready packets to the full
  `review-strategy-evidence --profile imbalance` gate. Launch summary/config
  and manifest extras now also expose capture env-template and adapter handoff
  SHA-256 values directly for broker handoff audit, and carry provider capture
  command counts/lists plus capture-bundle command match proof into the launch
  packet. Launch packaging now also carries provider-profile proof plus the
  credential-safe `adapter_execution_contract` from provider imbalance evidence
  and blocks the downstream launch pipeline from running when either contract
  is missing, unsafe, or no longer matched to live evidence. It now also carries
  nested `synthetic_sidecar_proof` plus flattened sidecar counts from provider
  imbalance evidence, and blocks the downstream launch pipeline when synthetic
  provider folds are missing ready rehearsal sidecar proof. The launch wrapper
  now reads the provider evidence manifest, requires exact
  `adapter_receipt_proof` agreement with evidence config, re-hashes every
  required receipt and provider capture before broker launch math can run, and
  fingerprints those files again in its own manifest.
- Provider market-data imbalance launch evidence review now closes that proof
  loop: `review-provider-market-data-imbalance-launch-evidence` catalogs both
  provider research and provider launch roots, carries capture
  bundle/env-template/adapter handoff provenance, source env-template proof, and
  exchange/session metadata, capture-bundle session match proof, and
  `live_fetch_contract` into launch-evidence summary/config/runbook artifacts
  plus manifest, verifies the full launch-ready `imbalance` profile, and hands
  ready packets to `score-strategy-readiness`. Launch-evidence summary/config
  and manifest extras now also expose capture env-template and adapter handoff
  SHA-256 values directly, and carry provider capture command counts/lists plus
  capture-bundle command match proof into the full launch-evidence package.
  The same gate now carries provider-profile proof plus the credential-safe
  `adapter_execution_contract` from the provider launch packet and blocks
  scorecard readiness when either contract is missing, unsafe, or no longer
  matched to live evidence. It now also carries nested `synthetic_sidecar_proof`
  plus flattened sidecar counts from the provider launch packet, and blocks
  scorecard readiness when synthetic provider folds are missing ready rehearsal
  sidecar proof. The review now reads the launch manifest, requires exact
  `adapter_receipt_proof` agreement with launch config, re-hashes every required
  receipt and provider capture, and fingerprints those files in its own manifest
  before strategy scorecard readiness can pass.
- Provider market-data imbalance scorecard now makes the final readiness gate
  provider-specific: `score-provider-market-data-imbalance-readiness` consumes
  the launch-evidence review, scores only the full `imbalance` profile, carries
  capture bundle/env-template/adapter handoff provenance, source env-template
  proof, exchange/session metadata, capture-bundle session match proof, and
  `live_fetch_contract` into its summary/config/runbook artifacts plus manifest,
  and hands ready evidence to
  `plan-provider-market-data-imbalance-scaleup`. Scorecard summary/config and
  manifest extras now also expose capture env-template and adapter handoff
  SHA-256 values directly, and carry provider capture command counts/lists plus
  capture-bundle command match proof into the provider readiness scorecard.
  The scorecard also carries provider-profile proof plus the credential-safe
  `adapter_execution_contract` from launch evidence and blocks scale-up
  readiness when either contract is missing, unsafe, or no longer matched to
  live evidence. It also carries nested `synthetic_sidecar_proof` plus
  flattened sidecar counts from launch evidence and blocks scale-up readiness
  when synthetic provider folds are missing ready rehearsal sidecar proof. The
  scorecard now reads the launch-evidence manifest, requires exact
  `adapter_receipt_proof` agreement with launch-evidence config, re-hashes every
  required receipt and provider capture, fingerprints those files in its own
  manifest, and refuses to run the nested readiness scorer when that proof has
  drifted.
- Provider market-data imbalance scale-up planning now preserves the same live
  adapter audit trail from the provider scorecard: the scale-up summary/config
  and manifest extras carry capture env-template and adapter handoff SHA-256
  values directly, carry provider capture command counts/lists plus
  capture-bundle command match proof from scorecard into scale-up planning, and
  manifest inputs fingerprint those files for iRage/live provider handoff
  review. Scale-up planning also carries provider-profile proof plus the
  credential-safe `adapter_execution_contract` from the provider scorecard and
  blocks runtime telemetry readiness when either contract is missing, unsafe,
  or no longer matched to live evidence. It also carries nested
  `synthetic_sidecar_proof` plus flattened sidecar counts from the provider
  scorecard and blocks runtime telemetry readiness when synthetic provider
  folds are missing ready rehearsal sidecar proof. Scale-up now reads the
  provider scorecard manifest, requires exact `adapter_receipt_proof` agreement
  with scorecard config, re-hashes every required receipt and provider capture,
  fingerprints those files in its own manifest, and refuses to run the generic
  planner when that proof has drifted.
- Provider market-data imbalance runtime telemetry now keeps that live adapter
  audit trail intact after scale-up: runtime telemetry summary/config and
  manifest extras expose capture env-template and adapter handoff SHA-256
  values directly, carry provider capture command counts/lists plus
  capture-bundle command match proof from scale-up into runtime telemetry, and
  the manifest fingerprints the same files before runtime guard monitoring.
  Runtime telemetry also carries provider-profile proof plus the
  credential-safe `adapter_execution_contract` from scale-up and blocks guard
  monitoring when either contract is missing, unsafe, or no longer matched to
  live evidence. It also carries nested `synthetic_sidecar_proof` plus
  flattened sidecar counts from scale-up and blocks guard monitoring when
  synthetic provider folds are missing ready rehearsal sidecar proof. Runtime
  telemetry now reads the scale-up manifest, requires exact
  `adapter_receipt_proof` agreement with scale-up config, re-hashes every
  required receipt and provider capture, fingerprints accepted files in its
  own manifest, and refuses to invoke the generic telemetry builder when that
  proof has drifted. Runtime telemetry now also carries the scale-up
  route-readiness provider broker
  round-trip synthetic sidecar breach counter and routes stale nonzero breach
  packets back to provider route readiness.
- Provider market-data imbalance runtime guard now preserves those adapter
  fingerprints through halt/continue monitoring: guard summary/config and
  manifest extras expose capture env-template and adapter handoff SHA-256
  values directly, carry provider capture command counts/lists plus
  capture-bundle command match proof from runtime telemetry into guard
  monitoring, and keep that proof visible before runtime session review.
  Runtime guard also carries provider-profile proof plus the credential-safe
  `adapter_execution_contract` from runtime telemetry and blocks
  runtime-session monitoring when either contract is missing, unsafe, or no
  longer matched to live evidence. It also carries nested
  `synthetic_sidecar_proof` plus flattened sidecar counts from runtime
  telemetry and blocks runtime-session monitoring when synthetic provider
  folds are missing ready rehearsal sidecar proof. Runtime guard now reads the
  runtime-telemetry manifest, requires exact `adapter_receipt_proof` agreement
  with telemetry config, re-hashes every required receipt and provider capture,
  fingerprints accepted files in its own manifest, and refuses to invoke the
  generic guard when that proof has drifted. Runtime guard now also carries the
  runtime-telemetry route-readiness provider broker round-trip synthetic
  sidecar breach counter and routes stale nonzero breach packets back to
  provider route readiness.
- Provider market-data imbalance runtime session now carries the same adapter
  fingerprints into broker-readiness handoff: session summary/config and
  manifest extras expose capture env-template and adapter handoff SHA-256
  values directly. Runtime session also carries provider-profile proof plus
  the credential-safe `adapter_execution_contract` from runtime guard and
  blocks broker-readiness review when either contract is missing, unsafe, or no
  longer matched to live evidence. It also carries nested
  `synthetic_sidecar_proof` plus flattened sidecar counts from runtime guard
  and blocks broker-readiness review when synthetic provider folds are missing
  ready rehearsal sidecar proof. Runtime session now reads the runtime-guard
  manifest, requires exact `adapter_receipt_proof` agreement with guard config,
  re-hashes every required receipt and provider capture, fingerprints accepted
  files in its own manifest, and refuses to invoke the generic session monitor
  when that proof has drifted. Runtime session now also carries the runtime
  guard route-readiness provider broker round-trip synthetic sidecar breach
  counter and routes stale nonzero breach packets back to provider route
  readiness before broker review.
- Provider market-data imbalance broker readiness now preserves those adapter
  fingerprints into broker handoff review: broker-readiness summary/config and
  manifest extras expose capture env-template and adapter handoff SHA-256
  values directly. Broker readiness also carries provider-profile proof plus
  the credential-safe `adapter_execution_contract` from runtime session and
  blocks cutover review when either contract is missing, unsafe, or no longer
  matched to live evidence. It also carries nested `synthetic_sidecar_proof`
  plus flattened sidecar counts from runtime session and blocks cutover review
  when synthetic provider folds are missing ready rehearsal sidecar proof.
  Broker readiness now reads the runtime-session manifest, requires exact
  `adapter_receipt_proof` agreement with session config, re-hashes every
  required receipt and provider capture, fingerprints accepted files in its
  own manifest, and refuses to invoke the generic broker-readiness scorer when
  that proof has drifted. Broker readiness now also preserves the
  runtime-session route-readiness provider broker round-trip synthetic sidecar
  breach counter and routes stale nonzero breach packets back to provider route
  readiness.
- Provider market-data imbalance cutover now keeps the same adapter
  fingerprints in the final pre-dispatch gate: cutover summary/config and
  manifest extras expose capture env-template and adapter handoff SHA-256
  values directly. Cutover also carries provider-profile proof plus the
  credential-safe `adapter_execution_contract` from broker readiness and
  blocks route-enable review when either contract is missing, unsafe, or no
  longer matched to live evidence. It also carries nested
  `synthetic_sidecar_proof` plus flattened sidecar counts from broker
  readiness and blocks route-enable review when synthetic provider folds are
  missing ready rehearsal sidecar proof. Cutover now reads the
  broker-readiness manifest, requires exact `adapter_receipt_proof` agreement
  with broker-readiness config, re-hashes every required receipt and provider
  capture, fingerprints accepted files in its own manifest, and refuses to
  invoke the generic cutover gate when that proof has drifted. Cutover now also
  preserves the
  broker-readiness route-readiness provider broker round-trip synthetic
  sidecar breach counter and routes stale nonzero breach packets back to
  provider route readiness.
- Provider market-data imbalance route enable now preserves those adapter
  fingerprints into broker-dispatch authorization: route-enable summary/config
  and manifest extras expose capture env-template and adapter handoff SHA-256
  values directly. Route enable also carries provider-profile proof plus the
  credential-safe `adapter_execution_contract` from cutover and blocks
  broker-dispatch planning when either contract is missing, unsafe, or no
  longer matched to live evidence. It also carries nested
  `synthetic_sidecar_proof` plus flattened sidecar counts from cutover and
  blocks broker-dispatch planning when synthetic provider folds are missing
  ready rehearsal sidecar proof. Route enable now reads the cutover manifest,
  requires exact `adapter_receipt_proof` agreement with cutover config,
  re-hashes every required receipt and provider capture, fingerprints accepted
  files in its own manifest, and refuses to invoke the generic route-enable
  gate when that proof has drifted. Route enable now also preserves the
  cutover-carried route-readiness provider broker round-trip synthetic sidecar
  breach counter and routes stale nonzero breach packets back to provider
  route readiness.
- Provider market-data imbalance broker dispatch now keeps those adapter
  fingerprints in the dry-run dispatch planner: broker-dispatch summary/config
  and manifest extras expose capture env-template and adapter handoff SHA-256
  values directly. Broker dispatch also carries provider-profile proof plus the
  credential-safe `adapter_execution_contract` from route enable and blocks
  broker-dispatch-send preparation when either contract is missing, unsafe, or
  no longer matched to live evidence. It also carries nested
  `synthetic_sidecar_proof` plus flattened sidecar counts from route enable and
  blocks broker-dispatch-send preparation when synthetic provider folds are
  missing ready rehearsal sidecar proof. Broker dispatch now reads the
  route-enable manifest, requires exact `adapter_receipt_proof` agreement with
  route-enable config, re-hashes every required receipt and provider capture,
  fingerprints accepted files in its own manifest, and refuses to invoke the
  generic broker-dispatch planner when that proof has drifted. Broker dispatch
  now also preserves the
  route-enable-carried route-readiness provider broker round-trip synthetic
  sidecar breach counter and routes stale nonzero breach packets back to
  provider route readiness.
- Provider market-data imbalance broker dispatch send now preserves those
  adapter fingerprints into the non-submitting sender packet: send
  summary/config and manifest extras expose capture env-template and adapter
  handoff SHA-256 values directly. Broker dispatch send also carries
  provider-profile proof plus the credential-safe `adapter_execution_contract`
  from broker dispatch and blocks acknowledgement reconciliation when either
  contract is missing, unsafe, or no longer matched to live evidence. It also
  carries nested `synthetic_sidecar_proof` plus flattened sidecar counts from
  broker dispatch and blocks acknowledgement reconciliation when synthetic
  provider folds are missing ready rehearsal sidecar proof. Broker dispatch
  send now reads the broker-dispatch manifest, requires exact
  `adapter_receipt_proof` agreement with broker-dispatch config, re-hashes every
  required receipt and provider capture, fingerprints accepted files in its own
  manifest, and refuses to invoke the generic non-submitting send-packet builder
  when that proof has drifted. Broker dispatch send now also preserves the
  broker-dispatch-carried route-readiness provider
  broker round-trip synthetic sidecar breach counter and routes stale nonzero
  breach packets back to provider route readiness.
- Provider market-data imbalance broker dispatch acknowledgement now carries
  those adapter fingerprints into ack reconciliation: acknowledgement
  summary/config and manifest extras expose capture env-template and adapter
  handoff SHA-256 values directly. Acknowledgement reconciliation also carries
  provider-profile proof plus the credential-safe `adapter_execution_contract`
  from broker dispatch send and blocks broker-dispatch round-trip review when
  either contract is missing, unsafe, or no longer matched to live evidence.
  It also carries nested `synthetic_sidecar_proof` plus flattened sidecar
  counts from broker dispatch send and blocks broker-dispatch round-trip review
  when synthetic provider folds are missing ready rehearsal sidecar proof.
  Acknowledgement reconciliation now reads the send-packet manifest, requires
  exact `adapter_receipt_proof` agreement with send-packet config, re-hashes
  every required receipt and provider capture, fingerprints accepted files in
  its own manifest, and refuses to invoke generic acknowledgement reconciliation
  when that proof has drifted. Acknowledgement reconciliation now also
  preserves the send-carried
  route-readiness provider broker round-trip synthetic sidecar breach counter
  and routes stale nonzero breach packets back to provider route readiness.
- Provider market-data imbalance broker dispatch round-trip now preserves those
  adapter fingerprints into the final dry-run bridge proof: round-trip
  summary/config and manifest extras expose capture env-template and adapter
  handoff SHA-256 values directly. Round-trip proof also carries
  provider-profile proof plus the credential-safe `adapter_execution_contract`
  from acknowledgement reconciliation and blocks the broker-readiness feed when
  either contract is missing, unsafe, or no longer matched to live evidence.
  It also carries nested `synthetic_sidecar_proof` plus flattened sidecar
  counts from acknowledgement reconciliation and blocks the broker-readiness
  feed when synthetic provider folds are missing ready rehearsal sidecar proof.
  Round-trip proof now also preserves the acknowledgement-carried
  route-readiness provider broker round-trip synthetic sidecar breach counter
  and routes stale nonzero breach packets back to provider route readiness.
- Provider market-data imbalance broker readiness now also keeps those final
  dry-run bridge fingerprints when dispatch round-trip proof is supplied:
  broker-readiness summary/config and manifest extras expose the
  dispatch-roundtrip capture env-template and adapter handoff SHA-256 values
  directly. Broker readiness also carries the round-trip provider-profile
  proof plus the credential-safe `adapter_execution_contract` and fails closed
  back to `review-provider-market-data-imbalance-broker-dispatch-roundtrip`
  when either final dry-run contract is missing, unsafe, stale, or mismatched
  against runtime-session evidence. It also carries the round-trip
  `synthetic_sidecar_proof` plus flattened sidecar counts and routes back to
  broker-dispatch round-trip review when synthetic provider folds are present
  but the final dry-run proof no longer has ready rehearsal sidecars attached.
- Provider market-data imbalance cutover now carries those dispatch-roundtrip
  fingerprints forward from broker readiness: cutover summary/config and
  manifest extras expose the dispatch-roundtrip capture env-template and
  adapter handoff SHA-256 values directly. Cutover also preserves the final
  round-trip provider-profile proof plus the credential-safe
  `adapter_execution_contract` and blocks route-enable review when either
  broker-readiness handoff is missing, unsafe, stale, or no longer matched to
  runtime-session evidence. It also carries the broker-readiness
  `dispatch_roundtrip_synthetic_*` sidecar proof and routes back to broker
  readiness when synthetic final dry-run folds are present without ready
  rehearsal sidecars.
- Provider market-data imbalance route enable now carries those
  dispatch-roundtrip fingerprints forward from cutover: route-enable
  summary/config and manifest extras expose the dispatch-roundtrip capture
  env-template and adapter handoff SHA-256 values directly. Route enable also
  preserves the final round-trip provider-profile proof plus the
  credential-safe `adapter_execution_contract` and blocks broker-dispatch
  planning when either cutover handoff is missing, unsafe, stale, or no longer
  matched to runtime-session evidence. It also carries the cutover-retained
  `dispatch_roundtrip_synthetic_*` sidecar proof and routes back to cutover
  when synthetic final dry-run folds are present without ready rehearsal
  sidecars.
- Provider market-data imbalance broker dispatch now carries those
  dispatch-roundtrip fingerprints forward from route enable: broker-dispatch
  summary/config and manifest extras expose the dispatch-roundtrip capture
  env-template and adapter handoff SHA-256 values directly. Broker dispatch also
  preserves the final round-trip provider-profile proof plus the
  credential-safe `adapter_execution_contract` and blocks send preparation when
  either route-enable handoff is missing, unsafe, stale, or no longer matched
  to runtime-session evidence. It also carries the route-enable-retained
  `dispatch_roundtrip_synthetic_*` sidecar proof and routes back to
  route-enable when synthetic final dry-run folds are present without ready
  rehearsal sidecars.
- Provider market-data imbalance broker dispatch send now carries those
  dispatch-roundtrip fingerprints forward from broker dispatch:
  broker-dispatch-send summary/config and manifest extras expose the
  dispatch-roundtrip capture env-template and adapter handoff SHA-256 values
  directly. Broker dispatch send also preserves the final round-trip provider
  profile plus credential-safe `adapter_execution_contract` and blocks
  acknowledgement reconciliation when the broker-dispatch handoff is missing,
  unsafe, stale, or no longer matched to the runtime-session provider profile
  or adapter contract. It also carries the broker-dispatch-retained
  `dispatch_roundtrip_synthetic_*` sidecar proof and routes back to broker
  dispatch when synthetic final dry-run folds are present without ready
  rehearsal sidecars.
- Provider market-data imbalance broker dispatch ack now carries those
  dispatch-roundtrip fingerprints forward from broker dispatch send:
  broker-dispatch-ack summary/config and manifest extras expose the
  dispatch-roundtrip capture env-template and adapter handoff SHA-256 values
  directly. Broker dispatch ack also preserves the final round-trip provider
  profile plus credential-safe `adapter_execution_contract` and blocks
  round-trip review when the broker-dispatch-send handoff is missing, unsafe,
  stale, or no longer matched to the runtime-session provider profile or
  adapter contract. It also carries the send-retained
  `dispatch_roundtrip_synthetic_*` sidecar proof and routes back to broker
  dispatch send when synthetic final dry-run folds are present without ready
  rehearsal sidecars.
- Provider market-data imbalance broker dispatch round-trip now carries those
  dispatch-roundtrip fingerprints forward from broker dispatch ack:
  broker-dispatch-roundtrip summary/config and manifest extras expose the
  dispatch-roundtrip capture env-template and adapter handoff SHA-256 values
  directly. Broker dispatch round-trip also preserves the final round-trip
  `adapter_execution_contract` and blocks the broker-readiness feed when the
  acknowledgement handoff is missing, unsafe, stale, or no longer matched to
  the runtime-session adapter contract.
- Provider market-data capture review now validates a credentialed provider
  client CSV against the dry-run packet before research ingestion:
  `review-provider-market-data-capture` checks normalized schema, row counts,
  timestamp parsing/monotonicity, capture fingerprints, and emits the exact
  `pipeline-vendor-market-data --adapter normalized` handoff.
- Provider market-data root ingestion now combines capture review and the
  normalized vendor/data-readiness pipeline:
  `pipeline-provider-market-data` creates one manifest-backed folder with
  component proof for the provider capture, nested normalized pipeline, action
  queue, and research-ready `review-data-readiness` handoff.
- Provider market-data batch ingestion now validates multiple live capture
  sessions from one dry-run client packet: `pipeline-provider-market-data-batch`
  runs per-capture roots, compares nested data-readiness evidence, rejects
  duplicate capture fingerprints, and writes a batch-level manifest for
  walk-forward research handoff.
- CLI/report runners for parity/box scans and lead-lag measurement.
- Strategy evidence review supports a `parity` profile that requires parity
  edge audit, replay sweep, promotion, order-plan, and launch-pipeline artifacts
  with shared strategy and market identity before shadow scale-up review.
- Strategy readiness scorecard ranks lead-lag, imbalance, parity/box,
  settlement, and surface market-making evidence profiles from one experiment
  catalog while filtering shared run types by strategy/market identity and
  emitting explicit missing-evidence gaps.
- Strategy readiness can now bind a current registered research-family audit
  with `--research-family` and enforce it with
  `--require-research-family`. Research profiles automatically require this
  proof when their catalog contains a passed prospectively registered robust
  selection, so the requirement cannot be bypassed by omitting the flag. The
  scorecard verifies the complete family artifact/input manifest, prospective
  registration closure, family-wise error-control claim, selected-candidate
  ledger, and non-authorizing status, then requires the exact normalized
  candidate scenario plus strategy and market to match one family survivor.
  Missing proof routes to `audit-research-family`; stale, blocked, ambiguous,
  or candidate-mismatched proof blocks readiness and remains visible in the
  scorecard, gaps, action queue, JSON handoff, runbook, and manifest. The
  provider-imbalance scorecard wrapper exposes the same family path/requirement
  controls, carries family status into its summary, and fingerprints the family
  root directly so this proof remains usable in the India-first provider lane.
- Strategy readiness scorecard can also score the file-provenance-gated
  `ops_launch` live-dry-run evidence lane for a named strategy, and fails
  closed on mixed strategy identities when no explicit ops strategy is supplied.
- Strategy readiness scorecard now applies the same `ops_launch` broker gates
  as strategy evidence review, including blocked placeholder schemas, final
  broker round-trip allocation breaches, and final broker portfolio
  concentration OK/breach proof, with failed evidence-check names preserved in
  scorecard rows and scheduler action outputs.
- Strategy readiness scorecard rows, gap rows, and summary now name the next
  required run type and CLI gate so blocked research or broker dry-run lanes
  can move directly to the missing proof step.
- Strategy readiness scorecard writes `strategy_scorecard_next_actions.json`,
  a machine-readable ranked next-action and open-gap sidecar for automated
  research/ops follow-up.
- Strategy readiness next-actions JSON now includes a versioned schema plus
  `primary_action_status`, `primary_action`, `ready_actions`/
  `blocked_actions` queues, and counts for scheduler handoff.
- Strategy readiness scorecard summaries and JSON handoffs now expose
  `failed_check_count`, blocked-profile `failed_check_names`,
  `first_failed_reason`, and structured `primary_blocker` fields for the first
  blocked strategy profile, so schedulers can distinguish a ready scale-up lane
  from the next missing research or broker-proof artifact.
- Strategy readiness scorecard now emits `strategy_scorecard_action_queue.csv`,
  a priority-ordered ready/blocked queue with next CLI gate/help fields for
  simple scheduler handoff.
- `score-strategy-readiness` can now fail closed with
  `--fail-on-blocked-actions` or `--fail-on-actions`, matching the strategy
  portfolio and broker handoff gates.
- Strategy readiness scorecard CSV/JSON outputs include `next_gate_help_command`
  hints so every blocked research or ops lane exposes the exact CLI entry point
  to inspect before scheduling the next run.
- Strategy readiness next-actions JSON now exposes root `next_gate` and
  `next_gate_help_command` aliases for the best ranked action, matching the
  downstream data, route, and broker handoff configs.
- Strategy readiness scorecard now writes a manifest-tracked
  `strategy_scorecard_runbook.md` handoff with ready actions, blocked actions,
  open gaps, and the next CLI gate/help command for review.
- Experiment catalog now recognizes strategy scorecard summaries, preserving
  best-profile and next-gate readiness signals for downstream evidence ledgers.
- Strategy portfolio allocation now converts ready scorecard profiles into a
  conservative paper/shadow capital plan with reserve, per-profile caps,
  checks, config JSON, runbook, manifest, and fail-closed primary blocker
  fields when no strategy lane is eligible.
- Strategy portfolio allocation now emits
  `strategy_portfolio_action_queue.csv`, mirrors scheduler action counts and
  primary action fields in summary/config, and `allocate-strategy-portfolio`
  can fail closed with `--fail-on-blocked-actions` or `--fail-on-actions`.
- Strategy portfolio allocation can now require minimum distinct strategies or
  markets and cap aggregate allocation to a single strategy or market before a
  paper/shadow portfolio is treated as ready for scale-up.
- Controlled scale-up can now require that strategy portfolio allocation,
  select the matching strategy/market allocation row, cap per-session notional
  at the allocated notional, and retain the selected portfolio context in
  `scaleup_summary.csv`, `scaleup_config.json`, and manifest inputs.
- Controlled scale-up now also carries strategy portfolio concentration
  context, including distinct strategy/market counts and maximum aggregate
  strategy/market allocation weights, into summary/config handoffs.
- Runtime telemetry and guard reports now carry the selected strategy portfolio
  allocation context from `scaleup_config.json` and explicitly halt if session
  notional breaches the selected paper/shadow allocation notional.
- Runtime telemetry, guard, and session handoffs now also preserve strategy
  portfolio concentration context from scale-up, including distinct
  strategy/market counts and maximum aggregate strategy/market allocation
  weights.
- Runtime session summaries and step ledgers now retain strategy portfolio
  allocation context from telemetry/guard, including selected strategy/market,
  eligibility, allocation weight/notional, pre-cap notional, and cap-applied
  state for paper/shadow operator handoff.
- Cutover and route-enable gates now carry strategy portfolio allocation
  evidence downstream from runtime-session proof, fail closed on bad allocation
  readiness/identity, and block route enablement when exported order notional
  exceeds the selected paper/shadow allocation.
- Cutover and route-enable handoffs now also preserve runtime strategy
  portfolio concentration context, including minimum distinct counts, observed
  allocated strategy/market counts, top concentration names, and maximum
  strategy/market allocation weights.
- Broker dispatch planning now carries route-enable strategy portfolio
  allocation evidence, computes notional from the resolved upload-order file,
  and blocks dry-run dispatch when that actual upload notional exceeds the
  selected allocation.
- Broker dispatch planning now also carries route-enable strategy portfolio
  concentration context into dispatch summary/config artifacts, keeping
  distinct count, top concentration, and maximum allocation-weight evidence
  available before dry-run send packets.
- Broker dispatch planning now emits manifest-tracked
  `broker_dispatch_action_queue.csv` and `broker_dispatch_runbook.md`
  scheduler handoffs, routing route-enable, allocation, route-readiness,
  dispatch round-trip, vendor-data, resume, and malformed dispatch-order
  blockers to their next CLI gate before send packets are prepared.
- Broker dispatch config JSON and summary rows now mirror dispatch action
  counts, primary action status, next gate/help command, and action arrays, and
  `plan-broker-dispatch` can fail closed with `--fail-on-blocked-actions` or
  `--fail-on-actions`.
- Broker dispatch send now carries dispatch-retained strategy portfolio
  allocation evidence into the non-submitting sender packet and blocks packet
  readiness when dispatch notional exceeds the selected allocation.
- Broker dispatch send now also preserves dispatch-retained strategy portfolio
  concentration context in sender summary/config artifacts before expected
  acknowledgements are generated.
- Broker dispatch send now revalidates dispatch-retained route-readiness ops
  broker controls before non-submitting sender packets advance, preserving
  direct route breach counters and broker-carried route proof in send
  summary/config artifacts.
- Broker dispatch send now also carries dispatch-retained broker resume-route
  proof into the non-submitting sender packet, revalidating primary and
  closed-incident branches before dry-run request envelopes can inherit
  post-halt authorization.
- Broker dispatch send now emits manifest-tracked
  `broker_dispatch_send_action_queue.csv` and
  `broker_dispatch_send_runbook.md` scheduler handoffs, routing dispatch-plan,
  sender-envelope, route-readiness, round-trip, broker-readiness, and
  vendor-data blockers before acknowledgement reconciliation is trusted.
- Broker dispatch send config JSON and summary rows now mirror send action
  counts, primary action status, next gate/help command, and action arrays, and
  `prepare-broker-dispatch-send` can fail closed with
  `--fail-on-blocked-actions` or `--fail-on-actions`.
- Broker dispatch acknowledgement reconciliation now carries dispatch-retained
  strategy portfolio allocation evidence and blocks acknowledgement pass status
  when dispatch notional exceeds the selected allocation.
- Broker dispatch acknowledgement reconciliation now also preserves
  dispatch-retained strategy portfolio concentration context in ack
  summary/config artifacts before round-trip proof review.
- Broker dispatch acknowledgement reconciliation now revalidates
  dispatch-retained route-readiness ops broker controls before accepted ack
  evidence advances, preserving direct breach counters and broker-carried
  route proof in ack summary/config artifacts.
- Broker dispatch acknowledgement reconciliation now also carries
  dispatch-retained broker resume-route proof, revalidating primary and
  closed-incident branches before accepted ack evidence can inherit post-halt
  authorization.
- Broker dispatch acknowledgement reconciliation now emits manifest-tracked
  `broker_dispatch_ack_action_queue.csv` and
  `broker_dispatch_ack_runbook.md` scheduler handoffs, routing missing,
  rejected, duplicate, unmatched, stale-route, readiness, vendor-data, and
  allocation blockers to their next CLI gate before round-trip proof is trusted.
- Broker dispatch acknowledgement config JSON and summary rows now mirror ack
  action counts, primary action status, next gate/help command, and action
  arrays, and `reconcile-broker-dispatch` can fail closed with
  `--fail-on-blocked-actions` or `--fail-on-actions`.
- Broker dispatch round-trip review now reconciles strategy portfolio
  allocation evidence across dispatch/send/ack artifacts and blocks the final
  proof on identity, allocation, or dispatch-notional inconsistencies.
- Broker dispatch round-trip review now also preserves the component-carried
  strategy portfolio concentration context in final proof summary/config
  artifacts.
- Broker dispatch round-trip review now revalidates route-readiness ops broker
  controls across dispatch, send, and ack artifacts before final dry-run bridge
  proof can pass, preserving direct breach counters and broker-carried route
  proof in round-trip summary/config artifacts.
- Broker dispatch round-trip review now also reconciles broker resume-route
  proof across dispatch/send/ack artifacts, revalidating primary and
  closed-incident branches before final dry-run bridge proof can inherit
  post-halt authorization.
- Experiment catalog summaries, action plans, runbooks, and CLI exit gates now
  track final broker round-trip resume-route proof, including primary/incident
  branch readiness plus route-gap, launch-control, portfolio, and concentration
  breach counters.
- Broker dispatch round-trip review now emits manifest-tracked
  `broker_dispatch_roundtrip_action_queue.csv` and
  `broker_dispatch_roundtrip_runbook.md` scheduler handoffs, routing failed
  dispatch, send, ack, route-readiness, broker-readiness, vendor-data,
  allocation, and cross-component proof checks to their next CLI gate.
- Broker dispatch round-trip config JSON and summary rows now mirror final
  proof action counts, primary action status, next gate/help command, and
  action arrays, and `review-broker-dispatch-roundtrip` can fail closed with
  `--fail-on-blocked-actions` or `--fail-on-actions`.
- Experiment catalog now recognizes strategy portfolio allocation summaries,
  preserving paper/shadow allocation readiness, top-profile, and allocated
  weight signals for downstream research ledgers.
- Adapter schema audits now emit `adapter_schema_review_checklist.csv` so
  Arrow.money/iRage onboarding separates missing-column blockers from
  placeholder-schema and extra-field review tasks.
- Adapter schema audits now also emit manifest-tracked
  `adapter_schema_action_queue.csv`, `adapter_schema_config.json`, and
  `adapter_schema_runbook.md`, making missing vendor fields, placeholder schema
  review debt, and extra-column classification visible to catalog schedulers.
- Broker readiness now carries adapter schema review checklist evidence into
  its summary/config and manifest inputs, preserving Arrow.money/iRage schema
  blockers and review tasks through the broker gate.
- Broker readiness now emits `broker_readiness_action_queue.csv`, a
  manifest-tracked failed-check queue with inferred next CLI gates and help
  commands for Arrow.money/iRage operator or scheduler handoff.
- Broker readiness now fails closed on stale route-readiness proof that does
  not preserve launch-grade ops broker controls and allocation/concentration
  proof counts.
- Broker readiness now revalidates final dispatch round-trip direct
  route-readiness launch-control and breach-pair evidence, plus
  broker-carried `route_broker_route_readiness` allocation-safe and
  concentration-OK run counts, before Arrow.money/iRage handoff.
- Broker readiness now also revalidates post-halt resume-gate carried broker
  route-readiness proof from both the new scale-up plan and the closed halt
  incident, preserving `resume_broker_route_readiness_*` summary/config fields
  and routing dirty resume-route evidence back to `review-route-readiness`.
- Broker readiness now writes a manifest-tracked `broker_readiness_runbook.md`
  with component status and blocked-action next gates for operator review.
- Broker readiness config JSON now mirrors the readiness action queue as
  counts, primary next gate/help, and `next_actions`/`ready_actions`/
  `blocked_actions`, plus root-level `primary_action_status` and
  `primary_action`, giving schedulers one JSON handoff for broker blockers.
- `review-broker-readiness` can now fail closed with
  `--fail-on-blocked-actions` or `--fail-on-actions`, matching the broker
  dispatch gate family exit-code contract.
- Broker-vendor data readiness now writes manifest-tracked action queue and
  runbook handoffs so Arrow.money/iRage vendor-batch, broker-readiness, and
  wrapper failures expose next CLI gates at the proof root.
- Broker-vendor data readiness config JSON now mirrors the root action queue
  as counts, primary next gate/help, and `next_actions`/`ready_actions`/
  `blocked_actions`, plus root-level `primary_action_status` and
  `primary_action`, so schedulers can consume wrapper blockers without parsing
  CSV files.
- Broker-vendor data readiness now preserves accepted broker-readiness
  route-control proof in wrapper summary/config artifacts, including direct
  route launch-control/breach-pair evidence and broker-carried allocation-safe
  plus concentration-OK route-run counts.
- Broker-vendor data readiness now also preserves broker-readiness
  resume-gate route proof from both the new scale-up route readiness and the
  incident-carried route readiness, keeping post-halt route authorization
  visible at the wrapper proof root.
- `pipeline-broker-vendor-readiness` now exposes the same
  `--fail-on-blocked-actions` and `--fail-on-actions` scheduler gates for
  Arrow.money/iRage vendor-data proof runs.
- Data readiness and comparison config JSONs now expose root-level
  `primary_action_status` and `primary_action` fields next to the existing
  next-gate aliases, giving Arrow.money/iRage data schedulers the selected
  failed check or dataset context without parsing every queue row.
- Vendor market-data pipeline and batch roots now also write manifest-tracked
  action queues and runbooks that promote nested data-readiness/comparison
  blockers into catalog-visible next gates for Arrow.money/iRage onboarding.
- Vendor market-data pipeline and batch summaries now expose explicit market
  identity, so catalog queues and future US-market expansion can filter vendor
  onboarding evidence without opening config sidecars.
- Vendor market-data pipeline and batch config JSON now mirrors root action
  queues as `next_actions`, `ready_actions`, and `blocked_actions`, so
  schedulers can consume vendor onboarding blockers without parsing CSV files.
- Vendor market-data pipeline and batch config JSON now also exposes
  root-level `primary_action_status` and `primary_action`, carrying the
  selected failed check, dataset, and next-gate context for Arrow.money/iRage
  onboarding schedulers.
- Vendor CSV intake now emits manifest-tracked `vendor_intake_action_queue.csv`,
  `vendor_intake_config.json`, and `vendor_intake_runbook.md`, so ambiguous
  kind selection or unmapped Arrow.money/iRage sample columns become catalog
  schedulable actions before the broader market-data batch pipeline runs.
- `intake-vendor-csv` can now fail closed with `--fail-on-blocked-actions` or
  `--fail-on-actions`, matching the stricter scheduler gates used by downstream
  mapped-data and vendor market-data onboarding commands.
- Experiment catalog now recognizes broker-vendor data readiness summaries,
  preserving wrapper proof readiness and Arrow.money/iRage data-proof signals
  for downstream evidence ledgers.
- The `ops_launch` strategy evidence and scorecard profile now requires
  `broker_vendor_data_readiness_pipeline` proof and points missing wrapper
  evidence to `pipeline-broker-vendor-readiness --help`, so broker-vendor data
  readiness is a launch prerequisite rather than a passive catalog signal.
- Route readiness now emits manifest-tracked `route_readiness_action_queue.csv`
  and `route_readiness_runbook.md` handoffs, carrying next gates, help commands,
  and strategy/ops evidence status into the final live-dry-run route review.
- Route readiness now independently verifies `ops_launch` evidence summaries
  carry launch-grade broker controls, including blocked placeholder schema
  gates, final broker round-trip portfolio-safe proof, and final broker
  portfolio concentration OK/breach proof, while surfacing
  `ops_launch_control_failures` in route pairs, JSON config, action queue, and
  runbook outputs.
- Route readiness now also verifies `ops_launch` final broker round-trip
  resume-route proof, blocking live-dryrun route review when primary/incident
  resume branches are missing, gapped, launch-control-failed, portfolio-unsafe,
  or concentration-unsafe.
- Route readiness now also carries provider-data imbalance final broker
  round-trip synthetic sidecar proof from `provider_imbalance_ops_launch`
  evidence into route pairs, action queues, and config JSON, and blocks live
  dry-run route review when the provider sidecar proof is missing or breached.
- Provider-data imbalance scale-up now revalidates the route-readiness provider
  broker round-trip synthetic sidecar breach counter in the nested generic
  scale-up gate, surfaces that count in wrapper summaries/config, and routes
  breached Arrow.money/iRage-ready packets back to provider route readiness.
- Provider-data imbalance runtime telemetry now preserves the same
  route-readiness sidecar breach counter from scale-up, blocks guard monitoring
  when a stale packet exposes nonzero provider sidecar breaches, and routes the
  repair action back to provider route readiness.
- Provider-data imbalance runtime guard now preserves the route-readiness
  sidecar breach counter from runtime telemetry, blocks runtime-session
  monitoring on nonzero provider sidecar breaches, and routes repair back to
  provider route readiness.
- Provider-data imbalance runtime session now preserves the route-readiness
  sidecar breach counter from runtime guard, blocks broker-readiness review on
  nonzero provider sidecar breaches, and routes repair back to provider route
  readiness.
- Provider-data imbalance broker readiness now preserves the route-readiness
  sidecar breach counter from runtime session, blocks cutover review on nonzero
  provider sidecar breaches, and routes repair back to provider route readiness.
- Provider-data imbalance cutover now preserves the route-readiness sidecar
  breach counter from broker readiness, blocks route-enable review on nonzero
  provider sidecar breaches, and routes repair back to provider route readiness.
- Provider-data imbalance route enable now preserves the route-readiness
  sidecar breach counter from cutover, blocks broker-dispatch planning on
  nonzero provider sidecar breaches, and routes repair back to provider route
  readiness.
- Provider-data imbalance route enable now also carries cutover's final
  broker-dispatch round-trip route-readiness sidecar breach counter, blocks
  broker-dispatch planning on nonzero final dry-run provider sidecar breaches,
  and routes repair back to provider route readiness.
- Provider-data imbalance broker dispatch now preserves the route-readiness
  sidecar breach counter from route enable, blocks broker-dispatch-send
  preparation on nonzero provider sidecar breaches, and routes repair back to
  provider route readiness.
- Provider-data imbalance broker dispatch send now preserves the
  route-readiness sidecar breach counter from broker dispatch, blocks
  acknowledgement reconciliation on nonzero provider sidecar breaches, and
  routes repair back to provider route readiness.
- Provider-data imbalance broker dispatch acknowledgement now preserves the
  route-readiness sidecar breach counter from broker dispatch send, blocks
  broker-dispatch round-trip review on nonzero provider sidecar breaches, and
  routes repair back to provider route readiness.
- Provider-data imbalance broker dispatch round-trip now preserves the
  route-readiness sidecar breach counter from broker dispatch acknowledgement,
  blocks broker-readiness review on nonzero provider sidecar breaches, and
  routes repair back to provider route readiness.
- Provider-data imbalance broker readiness now also revalidates the final
  broker-dispatch round-trip's route-readiness sidecar breach counter, blocks
  cutover review on nonzero final dry-run provider sidecar breaches, and routes
  repair back to provider route readiness.
- Provider-data imbalance cutover now also carries broker-readiness's final
  broker-dispatch round-trip route-readiness sidecar breach counter, blocks
  route-enable review on nonzero final dry-run provider sidecar breaches, and
  routes repair back to provider route readiness.
- Route readiness summaries now carry primary next-gate/help fields and
  ready/blocked action counts, making the final route scheduler signal visible
  directly in experiment catalogs.
- Route readiness config JSON now mirrors the route action queue as
  `next_actions`, `ready_actions`, and `blocked_actions`, plus root-level
  `primary_action_status` and `primary_action`, giving schedulers the final
  live-dry-run route handoff without parsing CSV files.
- `review-route-readiness` can now fail closed with
  `--fail-on-blocked-actions` or `--fail-on-actions`, matching the scorecard,
  portfolio, and broker scheduler gates.
- Scale-up, cutover, and route-enable config JSONs now retain their legacy
  failed-check name lists while adding `failed_check_count` and a structured
  `primary_blocker` record, so launch schedulers can surface the first failed
  gate without opening every checks CSV.
- Scale-up now fails closed on stale route-readiness ops broker controls from
  either direct route-readiness summaries or broker-readiness-carried route
  proof, preserving allocation/concentration blocked/breach counts in the
  scale-up summary/config.
- Cutover now revalidates those scale-up route-readiness ops broker controls,
  blocking live-dryrun authorization on missing launch controls, blocked route
  pairs, or broker round-trip allocation/concentration breaches, and preserving
  direct plus broker-carried route proof in cutover summary/config handoffs.
- Route-enable now revalidates cutover-retained route-readiness ops broker
  controls before broker routing can be enabled, preserving direct
  launch-control/breach counters and broker-carried allocation/concentration
  run counts in route-enable summary/config handoffs.
- Route-enable now also carries cutover-retained scale-up broker resume-route
  proof, revalidating both the primary and incident branches before broker
  dispatch planning can inherit post-halt route authorization.
- Broker dispatch now revalidates those route-enable-retained route-readiness
  ops broker controls before dry-run dispatch planning, carrying direct
  breach counters and broker-carried route proof into dispatch summary/config
  handoffs.
- Broker dispatch now also carries route-enable-retained broker resume-route
  proof, revalidating primary and incident branches before dry-run send packet
  preparation can inherit post-halt dispatch authorization.
- Cutover gate now emits manifest-tracked `cutover_action_queue.csv` and
  `cutover_runbook.md` handoffs, routing failed scale-up, route-readiness,
  broker-readiness, runtime-session, dispatch-roundtrip, vendor-data,
  resume-gate, and operator-review checks to their next CLI gate before
  route-enable automation can proceed.
- Route-enable now emits manifest-tracked `route_enable_action_queue.csv` and
  `route_enable_runbook.md` handoffs, routing failed cutover, upload-pack,
  order-export, route-readiness, dispatch-roundtrip, vendor-data, resume-gate,
  and identity checks before broker dispatch planning can proceed.
- Broker dispatch, send, acknowledgement, and round-trip config JSONs now
  expose the same `failed_check_count` plus structured `primary_blocker`
  contract, so broker-stage automation can route the first failed dry-run gate
  without parsing every component checks CSV.
- Resume gate config JSON now exposes `failed_check_count` and structured
  `primary_blocker` while keeping the legacy failed-check name list, so
  post-halt automation can route the first failed resume condition directly
  from `resume_config.json`.
- Resume gate now emits manifest-tracked `resume_action_queue.csv` and
  `resume_runbook.md` handoffs, routing open incidents, stale scale-up plans,
  identity mismatches, proof-refresh blockers, and operator-review gaps to the
  next CLI gate before broker/runtime resume automation can continue.
- Resume gate now carries broker route-readiness proof from the closed halt
  incident and the new scale-up config, failing closed on missing readiness,
  strategy/market drift, route gaps, launch-control failures, or broker
  portfolio/concentration round-trip breaches before post-halt runtime resume.
- Halt response config JSON now exposes response-plan `failed_check_count`,
  `failed_checks`, and structured `primary_blocker` next to the guard trigger
  context, so emergency automation can route packet-construction blockers
  without confusing them with the original guard halt reason.
- Halt response planning now emits manifest-tracked
  `halt_response_action_queue.csv` and `halt_response_runbook.md` handoffs,
  routing non-halt guard states and missing flatten-price blockers back to
  `plan-halt-response` or runtime guard review before cancel/flatten packets
  are trusted.
- Halt response export now emits manifest-tracked
  `halt_response_export_action_queue.csv`,
  `halt_response_export_config.json`, and
  `halt_response_export_runbook.md` handoffs, routing unready halt-response
  packets, adapter mismatches, and cancel/flatten mapping blockers back to
  `plan-halt-response` or `export-halt-response` before broker emergency files
  are trusted.
- Halt response plans now carry runtime guard `broker_route_readiness_*`
  proof into `halt_cancel_orders.csv`, `halt_flatten_orders.csv`,
  `halt_response_summary.csv`, and `halt_response_config.json`, keeping
  emergency cancel/flatten packets tied to the broker route controls that were
  active at halt time.
- Runtime session monitoring now emits manifest-tracked
  `runtime_session_action_queue.csv`, `runtime_session_config.json`, and
  `runtime_session_runbook.md` handoffs, routing blocked telemetry repairs,
  skipped or failed halt-response packets, and ready halt packets to the next
  runtime or halt-response CLI gate from the top-level session folder.
- Runtime scale-up guard now emits manifest-tracked
  `runtime_guard_action_queue.csv`, `runtime_guard_config.json`, and
  `runtime_guard_runbook.md` handoffs, turning guard halts into scheduler-ready
  `plan-halt-response` actions while routing scale-up, proof-refresh, and
  resume-gate blockers to their repair gates.
- Halt incident review now emits manifest-tracked
  `halt_incident_action_queue.csv` and `halt_incident_runbook.md` handoffs,
  routing guard, response, export, and execution blockers to the next recovery
  CLI before resume-gate automation trusts a closed incident.
- Halt incident timeline and summary rows now retain carried
  `broker_route_readiness_*` route-ready/gap-pair and ops-control proof from
  the guard or halt-response record, preserving the route-control trail through
  incident closure.
- Halt execution reconciliation now emits manifest-tracked
  `halt_execution_action_queue.csv` and `halt_execution_runbook.md` handoffs,
  routing missing cancel acknowledgements, incomplete flatten fills, and
  residual final positions back to recovery reconciliation before incident
  closure can pass.
- Market portability now emits manifest-tracked `market_portability_action_queue.csv`
  and `market_portability_runbook.md` handoffs, carrying ready/blocked
  India-to-US strategy/market actions, evidence gates, fee-model blockers, and
  next-gate help into catalog-level scheduler plans.
- Market portability config JSON now exposes primary `next_gate` and
  `next_gate_help_command` alongside `primary_action_status`,
  `primary_action`, action counts, and action arrays, matching downstream
  route/broker scheduler handoffs.
- `market-portability-report` can now fail closed with `--fail-on-breach`,
  `--fail-on-gaps`, `--fail-on-blocked-actions`, or `--fail-on-actions`,
  giving CI/schedulers a direct gate before non-India research or
  route-readiness runs are scheduled.
- Experiment catalogs now write `experiment_catalog_action_queue.csv`, a
  consolidated scheduler queue of cataloged next-gate/help signals across
  scorecards, route reviews, and future summary-bearing handoffs.
- `experiment_catalog_action_plan.json` now exposes root-level `next_gate`,
  `next_gate_help_command`, `primary_action_status`, and `primary_action`
  fields so automation can schedule the highest-priority ready or blocked
  catalog handoff without parsing every action array.
- Experiment catalogs now write a manifest-tracked
  `experiment_catalog_runbook.md` with readiness, input-provenance totals, and
  the consolidated next-action queue for operator review.
- Experiment catalog action queues now promote run-local `*_action_queue.csv`
  sidecars, so broker readiness, broker-vendor data readiness, route, and
  scorecard blockers remain visible in the top-level scheduler queue.
- Experiment catalog action queues now preserve promoted sidecar source,
  dataset, component, check, and pipeline-dir context, so vendor market-data
  pipeline/batch blockers remain explainable after catalog consolidation.
- Experiment catalog action queues and action-plan JSON now preserve
  `failed_check_count`, `failed_check_names`, `first_failed_reason`, and
  `primary_blocker_*` fields from source summaries or sidecar queues, and the
  action plan exposes the first blocked catalog action as a structured
  `primary_blocker`.
- Experiment catalog summaries now expose ready, blocked, unknown, and total
  action-queue counts for scheduler gating without opening the queue CSV.
- Experiment catalog summaries, action plans, and runbooks now expose broker
  dispatch round-trip portfolio proof counts, including portfolio-provided,
  portfolio-ready, portfolio-safe, and portfolio-breach runs for Arrow.money or
  iRage dry-run launch review.
- Experiment catalog summaries, action plans, runbooks, and `catalog-runs`
  gates now expose provider imbalance broker round-trip synthetic sidecar proof
  counts, ready runs, and breach runs, so scheduler automation can reject final
  Arrow.money/iRage provider broker dry-run evidence when rehearsal sidecars
  were expected but not retained/readable.
- Strategy evidence review now consumes those provider broker round-trip
  synthetic sidecar proof counts: provider imbalance ops-launch evidence
  automatically requires a ready final sidecar proof and fails on missing or
  unreadable provider broker round-trip sidecars before live-dryrun route
  review.
- Experiment catalog summaries, action plans, and runbooks now aggregate final
  broker round-trip portfolio concentration proof counts, including
  concentration-present, concentration-ok, and concentration-breach runs when
  dry-run summaries carry strategy/market allocation-count and max-weight
  limits.
- Experiment catalog summaries, action plans, and runbooks now aggregate
  placeholder broker schema state, counting active, allowed, reviewed,
  unreviewed, and blocked placeholder-schema runs so Arrow.money/iRage dry-run
  catalogs expose remaining vendor-schema review debt at the top level.
- Experiment catalogs now write manifest-tracked
  `experiment_catalog_action_plan.json`, a typed ready/blocked/unknown action
  plan with top actions and scheduler recommendation for automation handoff.
- `catalog-runs` can now fail closed with `--fail-on-blocked-actions` or
  `--fail-on-actions`, giving CI/schedulers a direct exit-code gate on the
  catalog action queue.
- `catalog-runs` can now fail closed with
  `--fail-on-blocked-placeholder-schema` or strict
  `--fail-on-placeholder-schema`, giving schedulers separate dry-run and
  promotion/live-readiness gates for Arrow.money/iRage schema review debt.
- `catalog-runs` can now fail closed with
  `--fail-on-broker-roundtrip-portfolio-breach` or
  `--require-broker-roundtrip-portfolio-safe`, so Arrow.money/iRage dry-run
  catalogs can enforce final dispatch notional stayed inside the selected
  strategy portfolio allocation.
- `catalog-runs` can now fail closed with
  `--fail-on-broker-roundtrip-portfolio-concentration-breach` or
  `--require-broker-roundtrip-portfolio-concentration-ok`, so dry-run catalogs
  can enforce final broker portfolio concentration stayed inside selected
  strategy/market count and max-weight limits.
- `review-strategy-evidence --profile ops_launch` now automatically applies
  the same launch-grade checks for blocked placeholder schemas, portfolio-safe
  final broker dispatch round-trip proof, portfolio concentration-OK proof,
  broker round-trip allocation breaches, and broker round-trip concentration
  breaches, while custom evidence reviews can opt into those gates explicitly.
- `review-strategy-evidence --profile ops_launch` and the ops-launch strategy
  scorecard now also require clean final broker round-trip resume-route proof,
  blocking stale post-halt route authorization before live-dryrun route review.
- `catalog-runs --fail-on-catalog-gaps` now fails on failed summaries,
  missing summaries, dirty runs, or unfingerprinted inputs before a catalog is
  reused as proof for strategy, broker, or route gates.
- Experiment catalogs now write manifest-tracked
  `experiment_catalog_hygiene_gaps.csv` plus runbook/action-plan hygiene
  entries, naming each failed summary, missing summary, dirty run, and
  unfingerprinted input with a recommended fix.
- Catalog hygiene gaps now carry source-summary `next_gate` and
  `next_gate_help_command` repair hints when available, keeping failed
  summary remediation schedulable from the hygiene sidecar.
- Experiment catalog action plans now expose `catalog_hygiene_ready` and
  prioritize hygiene repair recommendations before any queued strategy,
  broker, or route action scheduling.
- Broker vendor-data readiness summaries and JSON configs now surface
  `failed_check_count`, `failed_check_names`, `first_failed_reason`, and
  structured primary-blocker fields for the first failed wrapper root check,
  so Arrow.money/iRage proof blockers route to vendor batch, broker-readiness,
  or wrapper reruns without opening nested artifacts.
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
- Fill-model calibration now emits manifest-tracked
  `fill_model_action_queue.csv` and `fill_model_runbook.md` handoffs, with
  matching action metadata inside `fill_model_config.json`, making sample-size,
  fill-rate, mismatch, overfill, unmatched-fill, and slippage blockers
  catalog-visible before calibrated replay assumptions are trusted.
- Fill-model drift gate that compares baseline and latest calibration configs
  to decide whether existing proof assumptions can be reused or calibrated
  proof must be rerun.
- Fill-model drift now emits manifest-tracked
  `fill_model_drift_action_queue.csv`, `fill_model_drift_config.json`, and
  `fill_model_drift_runbook.md` handoffs, making unready calibration configs,
  instrument-set changes, and queue/latency/slippage/edge drift
  catalog-visible before proof refresh reuses old evidence.
- Calibrated replay planning and replay CLI hooks that apply fill-model
  recommendations to lead-lag, parity, and surface-MM replay latency/depth/edge
  assumptions without loosening explicit conservative inputs.
- Calibration-aware proof refresh gate that consumes fill-model drift, baseline
  proof, latest proof, and calibrated replay evidence to decide whether proof
  can be reused or must be rerun before promotion/scale-up, while failing
  closed on mixed strategy/market proof identities.
- Proof refresh now emits manifest-tracked `proof_refresh_action_queue.csv`,
  `proof_refresh_config.json`, and `proof_refresh_runbook.md` handoffs, making
  missing proof, failed latest proof, calibrated replay, and strategy/market
  identity blockers catalog-visible before promotion or scale-up trusts reused
  evidence.
- Experiment catalog, strategy evidence review, and controlled scale-up planning
  can now require proof-refresh evidence before size increases, and scale-up
  validates proof-refresh strategy/market identity against the promotion target.
- Broker/vendor adapter scaffolding for normalized, Arrow.money-style, and
  iRage-style CSV exports.
- Broker readiness now consumes dispatch round-trip route-readiness proof,
  requiring matching strategy/market identity and zero route gaps before
  Arrow.money/iRage live dry-run handoff, while retaining any final
  round-trip vendor market-data batch proof for broker-readiness handoff,
  including source-fingerprint coverage, minimum mapping coverage, and mapping
  draft uniqueness metrics.
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
- Data readiness now emits manifest-tracked `data_readiness_action_queue.csv`
  and `data_readiness_runbook.md` handoffs, mapping failed vendor intake,
  schema, normalization, diagnostics, market-profile, market-portability, and
  metadata checks to the next CLI gate for catalog-level scheduler plans.
- Data readiness summaries and JSON handoffs now expose
  `failed_check_count`, `failed_check_names`, `first_failed_reason`, and
  structured primary-blocker fields so raw vendor-data blockers can be routed
  to the exact first failed intake, schema, normalization, diagnostics,
  market-profile, portability, or metadata check.
- Data readiness now writes manifest-tracked `data_readiness_config.json`,
  mirroring summary, component, failed-check, and action-queue state as a
  scheduler-readable JSON handoff for raw vendor data blockers.
- `review-data-readiness` can now fail closed with
  `--fail-on-blocked-actions` or `--fail-on-actions`, giving schedulers a
  direct exit-code gate on raw vendor-data repair work.
- Vendor market-data onboarding pipelines that run Arrow.money/iRage CSV
  intake, normalized mapping, tick/chain diagnostics, data-readiness gates, and
  multi-day readiness comparison before walk-forward research, carrying raw
  source, header, mapping, component-manifest, and comparison fingerprints for
  repeatable vendor data proof, plus JSON handoff configs for strategy research
  and future vendor adapters.
- `pipeline-vendor-market-data` and `pipeline-vendor-market-data-batch` can now
  fail closed with `--fail-on-blocked-actions` or `--fail-on-actions`, giving
  schedulers a direct exit-code gate on promoted Arrow.money/iRage repair work.
- Multi-dataset data-readiness comparison gate that requires repeated clean
  market-data days before walk-forward research or strategy evidence review,
  and can fail closed when vendor-data folds do not come from distinct raw
  source-file fingerprints, when source-fingerprint coverage is incomplete, or
  when any fold falls below the required mapping coverage.
- Multi-dataset data-readiness comparisons now emit manifest-tracked
  `data_readiness_comparison_action_queue.csv` and
  `data_readiness_comparison_runbook.md` handoffs, mapping failed repeatability
  checks to `review-data-readiness` or `pipeline-vendor-market-data-batch`.
- Multi-dataset data-readiness comparisons now also write manifest-tracked
  `data_readiness_comparison_config.json`, preserving dataset rows,
  failed-check names, and ready/blocked action queues for batch schedulers.
- `compare-data-readiness` can now fail closed with
  `--fail-on-blocked-actions` or `--fail-on-actions`, matching the single-run
  data-readiness gate before walk-forward research is scheduled.
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
  surfaces the first schema or built-in mapping blocker in the summary, and
  fails closed unless placeholder schemas are explicitly allowed for dry-run
  review.
- Broker upload packs now also emit manifest-tracked
  `broker_upload_action_queue.csv`, `broker_upload_config.json`, and
  `broker_upload_runbook.md` handoffs, making placeholder schema, built-in
  mapping, and empty broker-order blockers catalog-visible before broker
  readiness trusts upload evidence.
- Broker/drop-copy fill reconciliation for exported orders, including
  order-level fill status, unmatched fills, side/instrument mismatches,
  adverse slippage, latency, pass/fail checks, and manifests.
- Broker/drop-copy fill reconciliation now also emits manifest-tracked
  `reconciliation_action_queue.csv`, `reconciliation_config.json`, and
  `reconciliation_runbook.md` handoffs, making fill-rate, overfill, mismatch,
  unmatched-fill, and slippage blockers catalog-visible before broker readiness
  trusts paper/shadow execution evidence.
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
  hydrates broker route-readiness ops proof from launch pipeline root summaries
  when the nested broker-readiness folder is not available,
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
  continue/halt decisions with failed check names, first halt reasons, config
  JSON, action queue, and runbook handoffs.
- Runtime session monitor that chains telemetry building, scale-up guard
  evaluation, and automatic halt-response planning into one manifest-backed
  paper/shadow go/no-go artifact, preserving the guard halt trigger and
  strategy/market plus proof-refresh and broker resume-gate identity in the
  top-level session summary and scheduler action queue while fingerprinting
  resolved source snapshots, telemetry/guard child artifacts, child manifests,
  and optional halt-response artifacts in the session manifest.
- Halt response planner that converts runtime guard halts into broker-neutral
  cancel-order and flatten-position action files with fail-closed price checks
  and manifests, stamping guard failed check names and first halt reasons onto
  the summary and action CSVs for operator review while carrying strategy and
  market identity into the emergency action packet, exposing the first failed
  response-plan check in config, emitting scheduler action queue/runbook
  handoffs, and fingerprinting resolved guard summary/check files plus
  open-order and position snapshots.
- Halt response export mapper that turns emergency cancel and flatten actions
  into reviewed broker/vendor CSV shapes, with normalized passthrough until
  Arrow.money/iRage emergency schemas are finalized, fingerprints the exact
  halt-response action files plus optional mapping files, and surfaces the
  first failed export mapping/readiness blocker in the one-row summary,
  config JSON, action queue, and runbook.
- Halt execution reconciliation gate that verifies emergency cancel
  acknowledgements, flatten fills, and final flat positions after a guard halt,
  while fingerprinting the halt-response action files and supplied execution
  evidence snapshots and surfacing the first failed acknowledgement, fill, or
  residual-position blocker in the summary.
- Halt incident review that combines guard, response, export, and execution
  evidence into one incident-closure timeline, check set, and summary with
  guard trigger plus strategy/market context carried through the review and
  fingerprints each component summary/check file while exposing the first
  failed closure gate as primary blocker fields in the summary.
- Post-halt resume gate that requires a closed incident, ready scale-up plan,
  scenario/adapter, strategy/market, and proof-refresh continuity, optional
  operator approval, and emits resume authorization/config artifacts carrying
  the incident guard trigger and proof context from the prior halt, with
  automatic operator approval and guard-trigger acknowledgement required for
  `live_dryrun` resumes while fingerprinting resolved incident, scale-up, and
  operator-review inputs and exposing the first failed resume check in config.
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
  runtime-session, and operator-review inputs, carries runtime-session strategy
  portfolio allocation context, and exposes the first failed check as a
  structured config blocker plus scheduler action queue/runbook handoff.
- Route-enable packet that consumes ready cutover and broker upload evidence,
  bounds order counts and optional export notional by cutover limits plus any
  selected strategy portfolio allocation, rechecks cutover route-readiness
  proof, live-dry-run dispatch round-trip proof,
  carried route-enable failed-check counters, nested route proof, and
  cutover-carried shadow broker-readiness aggregates plus
  broker-readiness-carried shadow broker proof, carries cutover-retained vendor
  market-data batch dataset/header/mapping provenance plus
  cutover-retained broker-readiness vendor market-data batch proof, resolves
  broker upload/export summaries from launch pipeline roots, fingerprints resolved
  cutover/upload/export inputs, and emits the final machine-readable broker
  route-enable config with a primary blocker record plus scheduler action
  queue/runbook handoff without submitting orders.
- Broker dispatch planner that binds a route-enable authorization to the exact
  broker upload rows, hashes the route/upload payloads, creates deterministic
  dry-run dispatch IDs, computes upload-row notional, carries broker schema review status/mode plus
  route-readiness proof, live-dry-run nested route proof, and route-carried
  shadow broker-readiness aggregates plus broker-readiness-carried shadow
  broker proof from route-enable as `route_broker_shadow_broker_*`, preserves
  route-enable-carried vendor market-data batch provenance as
  `route_vendor_market_data_batch_*`, preserves route-enable-carried
  broker-readiness vendor market-data batch proof as
  `route_broker_dispatch_roundtrip_vendor_market_data_batch_*`, and fails
  closed on disabled routes, portfolio allocation breaches,
  nested route-enable dispatch round-trip failed checks, dirty route proof,
  duplicate source order IDs, dirty carried shadow broker proof, or unresolved
  upload-order files while resolving launch pipeline upload roots and
  fingerprinting the route-enable summary/config, route-enable manifest, and
  upload CSV without sending orders while exposing the first failed dispatch
  check as a structured config blocker plus scheduler action queue/runbook
  handoff.
- Broker dispatch send packet builder that turns an armed dry-run dispatch
  plan into non-submitting adapter request envelopes, idempotency keys, payload
  hashes, route-readiness proof, route round-trip proof tags, and
  acknowledgement templates while carrying broker schema review status/mode
  route-enable dispatch round-trip failed-check counters, dispatch-carried
  strategy portfolio allocation evidence and dispatch notional guards,
  shadow broker-readiness aggregates plus broker-readiness-carried shadow
  broker proof from the dispatch config as `route_broker_shadow_broker_*`, and
  vendor market-data batch provenance as `dispatch_vendor_market_data_batch_*`,
  plus broker-readiness vendor market-data batch proof as
  `dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_*`, validating route-readiness identity,
  carried shadow proof quality, and route proof batch continuity, forcing live
  submission off, and fingerprinting exact dispatch input files plus the
  dispatch manifest when present while carrying the first failed sender check
  in config plus scheduler action queue/runbook handoff.
- Broker dispatch acknowledgement reconciliation that matches dry-run dispatch
  rows to broker ack logs, accepts only explicit success statuses, carries
  broker schema review status/mode, route-readiness proof, route round-trip
  proof, and route-enable failed-check counters from the dispatch config,
  validates route-readiness identity, strategy portfolio allocation continuity,
  send-stage shadow broker-readiness aggregates, broker-readiness-carried
  shadow broker proof,
  dispatch-carried vendor market-data batch provenance as
  `ack_vendor_market_data_batch_*`, broker-readiness final dispatch
  round-trip vendor market-data proof as
  `ack_broker_dispatch_roundtrip_vendor_market_data_batch_*`, and
  acknowledgement-log proof batch continuity, hydrating missing broker
  vendor-data proof through dispatch/route-enable/cutover manifests when
  needed, and
  fails closed on missing, rejected, duplicate, dirty-proof, stale-proof, or
  unmatched acknowledgement rows while fingerprinting exact dispatch, dispatch
  manifest, and ack log inputs plus the first failed ack check in config and
  a scheduler action queue/runbook handoff.
- Broker dispatch round-trip review that joins dispatch rows, non-submitting
  sender requests, and broker acknowledgements into one dry-run proof gate with
  identity, route-readiness consistency, raw ack-log route proof consistency,
  route-enable failed-check counters and broker schema review status/mode from
  upstream configs, shadow broker-readiness consistency across dispatch, send,
  and acknowledgement configs, broker-readiness shadow broker consistency,
  strategy portfolio allocation consistency across dispatch, send, and ack,
  vendor market-data batch provenance consistency, broker-readiness final
  dispatch round-trip vendor market-data consistency, hydrating missing broker
  vendor-data proof through dispatch/route-enable/cutover manifests when
  component configs are thin,
  request-count, submission-disabled, and
  accepted-ack checks while fingerprinting exact component proof files and
  manifests and exposing the first failed cross-component check in config plus
  a scheduler action queue/runbook handoff.
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
  real Arrow.money/iRage column maps are finalized, with the first missing
  required source column surfaced in the summary.
- Mapped vendor-data normalization command that applies reviewed header
  mappings to real tick, chain, order, or fill CSVs and emits normalized data,
  mapping checks, summary, and manifest artifacts with the first failed
  required normalized column surfaced in the summary.
- Mapped vendor-data normalization now also emits manifest-tracked
  `mapped_data_action_queue.csv`, `mapped_data_config.json`, and
  `mapped_data_runbook.md` handoffs, routing unmapped required fields or
  zero-row normalization output back to `normalize-mapped-data` before vendor
  files are trusted as research inputs.
- Configurable mapped broker-order export that converts broker-neutral launch
  orders into a vendor CSV shape from a reviewed mapping file, with required
  field checks, simple transforms, manifests, and summary-level primary blocker
  fields for the first failed vendor target column.
- Mapped broker-order export now also emits manifest-tracked
  `mapped_order_action_queue.csv`, `mapped_order_config.json`, and
  `mapped_order_runbook.md` handoffs, making missing or blank final vendor
  upload fields catalog-visible before broker readiness trusts mapped orders.
- Vendor order-mapping draft command that reads a broker-neutral export plus
  an Arrow.money/iRage sample upload header, suggests reviewable mappings, and
  fails closed on unmapped required vendor fields while surfacing the first
  unmapped required vendor column in the summary.
- Vendor order-mapping drafts now also emit manifest-tracked
  `order_mapping_draft_action_queue.csv`, `order_mapping_draft_config.json`,
  and `order_mapping_draft_runbook.md` handoffs, making unmapped required
  broker-upload sample columns catalog-visible before mapped order exports are
  trusted.
- Vendor CSV intake report that profiles unknown Arrow.money/iRage samples,
  infers tick/chain/order/fill shape, scores normalized mapping coverage, and
  emits a reviewed-mapping draft plus source/header/mapping fingerprints for
  market-data normalization while surfacing ambiguous kind selection or the
  first unmapped normalized column in the summary.
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
  `scaleup_broker_shadow_broker_*` authorization/config fields. Scale-up now
  also revalidates broker-readiness-carried shadow broker vendor-data wrapper
  counters as `broker_shadow_broker_vendor_data_readiness_*` before promotion,
  and cutover now revalidates the same counters as
  `scaleup_broker_shadow_broker_vendor_data_readiness_*`, with route-enable
  regression coverage for partial cutover-carried broker-shadow wrapper
  coverage before dispatch routing can be enabled, broker dispatch regression
  coverage for the same partial route-carried wrapper before dry-run packets
  can be armed, broker dispatch send coverage before non-submitting sender
  packets can advance, acknowledgement coverage before accepted ack evidence
  can advance, and final round-trip coverage before dry-run bridge proof can
  feed broker readiness, plus broker readiness coverage before integration
  readiness can pass, and
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
  `scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_*` plus the
  `scaleup_broker_vendor_data_readiness_*` wrapper gate, and
  route-enable prefers its cutover-specific config block, hydrates missing proof
  from broker-readiness sidecars referenced by the cutover manifest, revalidates
  the wrapper and nested batch, and preserves them as
  `cutover_broker_vendor_data_readiness_*` and
  `cutover_broker_dispatch_roundtrip_vendor_market_data_batch_*`, before
  broker dispatch prefers its route-native config block, hydrates missing proof
  through the route-enable/cutover manifest chain, revalidates the wrapper and
  nested batch, and preserves them as
  `route_broker_vendor_data_readiness_*` and
  `route_broker_dispatch_roundtrip_vendor_market_data_batch_*`, before the
  non-submitting sender packet prefers its dispatch-native config block,
  hydrates missing proof through the dispatch/route-enable/cutover manifest
  chain, revalidates the wrapper and nested batch, and preserves them as
  `dispatch_broker_vendor_data_readiness_*` and
  `dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_*`, before the
  acknowledgement reconciliation prefers its ack-stage config block, hydrates
  missing proof through the dispatch/route-enable/cutover manifest chain,
  revalidates the wrapper and nested batch, and preserves them as
  `ack_broker_vendor_data_readiness_*` and
  `ack_broker_dispatch_roundtrip_vendor_market_data_batch_*`, and the final
  round-trip proof prefers its roundtrip-stage config block, hydrates missing
  component proof through the dispatch/route-enable/cutover manifest chain,
  revalidates the wrapper and nested batch, and reconciles them as
  `roundtrip_broker_vendor_data_readiness_*` and
  `roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_*`, before
  broker readiness prefers its readiness-native broker vendor-data config
  blocks when present, otherwise revalidates the roundtrip-stage wrapper and
  nested batch directly or through normalized handoff fields, scale-up, cutover, route-enable, broker
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
  summary/config, and its own summary/config now surfaces source-file
  fingerprint coverage, mapping coverage, and mapping-draft provenance from
  the generated vendor batch. It now also writes root-level pass/fail checks
  for wrapper readiness, vendor-batch distinct-source proof, coverage, mapping
  provenance, and broker-readiness acceptance, and broker readiness now blocks
  supplied wrapper roots whose own readiness config is not ready even if their
  nested vendor batch is internally valid. Scale-up now also hydrates the
  broker-vendor wrapper readiness state from `broker_readiness_config.json`, so
  a failed Arrow.money/iRage wrapper sidecar cannot be masked by a valid nested
  vendor batch during controlled capital increases. Scale-up now also carries
  and revalidates resume-gate broker route-readiness proof from broker
  summaries, launch-pipeline fallbacks, or the same sidecar as
  `broker_resume_broker_route_readiness_*` and
  `broker_resume_incident_broker_route_readiness_*` fields before promotion.
  Cutover now preserves and revalidates those same scale-up-carried
  resume-route branches as `scaleup_broker_resume_broker_route_readiness_*`,
  `scaleup_broker_resume_incident_broker_route_readiness_*`, and nested
  `scaleup_broker_resume_gate` config blocks before route-enable can inherit
  post-halt authorization.
  Broker readiness now evaluates standalone vendor-batch proof
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
  the same manifest identity, coverage, mapping-draft provenance, and
  broker-vendor wrapper readiness state on scale-up-carried broker/vendor
  proofs before route enable can inherit them.
  Route enable now carries and revalidates that wrapper readiness state,
  manifest identity, coverage, and mapping-draft provenance before broker
  dispatch planning can inherit cutover-carried broker/vendor data proof. Broker
  dispatch planning now carries and revalidates that wrapper readiness state,
  identity, source-file fingerprint coverage, mapping coverage, and
  mapping-draft provenance before send packets can inherit route-enable-carried
  proof.
  Broker dispatch send now carries that wrapper readiness state plus
  coverage/provenance fields and revalidates broker-readiness-prefixed vendor
  proof before non-submitting send packets can inherit it. Acknowledgement now
  carries that wrapper readiness state plus coverage/provenance fields and
  revalidates broker-readiness-prefixed vendor proof before accepted ack
  evidence can advance. Final round-trip gates now carry that wrapper readiness
  state and reconcile the same identity, coverage, and mapping-draft provenance
  across dispatch/send/ack
  before scale-up can inherit it, including both generic and
  broker-readiness-prefixed vendor proof paths. Broker readiness now consumes
  the final round-trip wrapper block directly, so a failed wrapper cannot be
  masked when the final dry-run proof is reviewed for integration readiness.
  Shadow-session acceptance now carries the broker-readiness
  `broker_vendor_data_readiness_*` fields and fails closed when the
  Arrow.money/iRage wrapper proof is unready or has failed checks. Shadow
  comparison now aggregates the same wrapper fields and blocks promotion when
  accepted broker-readiness sessions lose or fail that proof. Scale-up now
  retains and enforces that shadow-comparison wrapper aggregate before
  promotion, cutover now carries and revalidates the same aggregate before
  live-dryrun route authorization, and route-enable now revalidates the
  cutover-carried aggregate before a broker route can be enabled. Broker
  dispatch now revalidates the route-enable-carried aggregate before broker
  dry-run dispatch packets can be armed, and broker dispatch send now
  revalidates the dispatch-carried aggregate before non-submitting sender
  packets can be reviewed. Broker dispatch ack now revalidates the
  sender-carried aggregate before accepted ack evidence can advance. Broker
  dispatch round-trip now revalidates the ack-carried aggregate before final
  dry-run proof can advance. Broker readiness now revalidates the
  roundtrip-carried aggregate before broker integration readiness can pass.
  Scale-up now carries the same
  coverage/provenance fields into its plan, summary, config, and broker-readiness
  sidecar hydration, and blocks scale-up when that broker/vendor proof is
  incomplete.
- Provider-data imbalance now has a dedicated scale-up wrapper after the
  readiness scorecard. `plan-provider-market-data-imbalance-scaleup` infers the
  launch-evidence, full imbalance `strategy_evidence`, and nested launch
  pipeline paths from the provider scorecard, requires a real shadow comparison,
  carries capture bundle/env-template/adapter handoff provenance, source
  env-template proof, exchange/session metadata, capture-bundle session match
  proof, and `live_fetch_contract` into the provider wrapper
  summary/config/runbook artifacts plus manifest, writes nested generic
  `scaleup` outputs, and points ready runs to
  `build-provider-market-data-imbalance-runtime-telemetry`.
- Provider-data imbalance now has a dedicated runtime telemetry wrapper after
  provider scale-up. `build-provider-market-data-imbalance-runtime-telemetry`
  infers nested `scaleup_config.json` plus broker export/upload inputs from the
  provider launch pipeline, accepts optional live PnL/open-order/position CSVs,
  carries capture bundle/env-template/adapter handoff provenance, source
  env-template proof, exchange/session metadata, capture-bundle session match
  proof, and `live_fetch_contract` into provider wrapper
  summary/config/runbook artifacts plus manifest, writes nested generic
  `runtime_telemetry` outputs, and points ready runs to
  `monitor-provider-market-data-imbalance-runtime-guard`.
- Provider-data imbalance now has a provider runtime guard wrapper after runtime
  telemetry. `monitor-provider-market-data-imbalance-runtime-guard` resolves the
  nested `scaleup_config.json` and `runtime_telemetry.csv`, carries capture
  bundle/env-template/adapter handoff provenance, source env-template proof,
  exchange/session metadata, capture-bundle session match proof, and
  `live_fetch_contract` into provider wrapper summary/config/runbook artifacts
  plus manifest, writes nested generic `runtime_guard` outputs,
  converts guard halts into ready
  `plan-halt-response` actions, and routes clean guards to
  `monitor-provider-market-data-imbalance-runtime-session`.
- Provider-data imbalance now has a provider runtime session wrapper after the
  provider guard. `monitor-provider-market-data-imbalance-runtime-session`
  infers the provider runtime telemetry inputs, reruns the nested generic
  `runtime_session`, carries capture bundle/env-template/adapter handoff
  provenance, source env-template proof, exchange/session metadata,
  capture-bundle session match proof, provider capture-command proof, and
  `live_fetch_contract` into provider
  summary/config/runbook artifacts plus manifest, routes clean sessions to
  `review-provider-market-data-imbalance-broker-readiness`, and exposes ready
  `export-halt-response` actions when a guarded session halts with a ready halt
  packet.
- Provider-data imbalance now has a provider broker-readiness wrapper after the
  provider runtime session.
  `review-provider-market-data-imbalance-broker-readiness` infers the nested
  generic runtime session plus provider launch order export/upload pack,
  reruns `review-broker-readiness` under a nested folder with dry-run friendly
  defaults, carries capture bundle/env-template/adapter handoff provenance,
  source env-template proof, exchange/session metadata, capture-bundle session
  match proof, provider capture-command proof, round-trip provider
  capture-command arrays from `dispatch_roundtrip_provenance`, and
  `live_fetch_contract` into provider summary/config/runbook artifacts plus
  manifest, writes provider
  checks/summary/action/config/runbook artifacts, and routes ready runs to
  `review-provider-market-data-imbalance-cutover`.
- Provider-data imbalance now has a provider cutover wrapper after provider
  broker-readiness. `review-provider-market-data-imbalance-cutover` infers
  nested generic scale-up, broker-readiness, and runtime-session evidence,
  reruns `review-cutover-gate` under a nested folder, carries capture
  bundle/env-template/adapter handoff provenance, source env-template proof,
  exchange/session metadata, capture-bundle session match proof, provider
  capture-command proof, round-trip provider command arrays from either
  `dispatch_roundtrip_provenance` or older root/capture-bundle config fields,
  and `live_fetch_contract` into provider summary/config/runbook artifacts
  plus manifest, preserves cutover safety
  blockers such as missing route-readiness proof, and routes fully clean runs to
  `review-route-enable`.
- Provider-data imbalance now has a provider route-enable wrapper after cutover.
  `review-provider-market-data-imbalance-route-enable` infers the nested generic
  cutover and broker upload/order-export inputs, reruns `review-route-enable`
  under a nested folder, carries capture bundle/env-template/adapter handoff
  provenance, source env-template proof, exchange/session metadata,
  capture-bundle session match proof, provider capture-command proof,
  round-trip provider command arrays from either
  `dispatch_roundtrip_provenance` or older root/capture-bundle config fields,
  final `dispatch_roundtrip_route_readiness_*` sidecar breach proof, plus
  `live_fetch_contract` into provider summary/config/runbook artifacts plus
  manifest, blocks broker-dispatch planning on nonzero final dry-run sidecar
  breach pairs, writes provider
  checks/summary/action/config/runbook artifacts, routes
  blockers back to the exact repair gate, and sends clean Arrow.money/iRage
  dry-run routes to `plan-broker-dispatch`.
- Provider-data imbalance now has a provider broker-dispatch wrapper after
  provider route-enable. `plan-provider-market-data-imbalance-broker-dispatch`
  infers the nested generic `route_enable` and broker upload pack, reruns
  `plan-broker-dispatch` under a nested folder, carries capture
  bundle/env-template/adapter handoff provenance, source env-template proof,
  exchange/session metadata, capture-bundle session match proof, provider
  capture-command proof, and `live_fetch_contract` into provider
  summary/config/runbook artifacts plus manifest, carries route-enable's final
  `dispatch_roundtrip_route_readiness_*` sidecar breach proof, blocks send
  preparation on nonzero final dry-run provider sidecar breaches, writes provider
  checks/summary/action/config/runbook artifacts, indexes the run for
  catalog/scorecard discovery, and routes clean non-submitting dry-run
  dispatch plans to `prepare-broker-dispatch-send`.
- Provider-data imbalance now has a provider broker-dispatch-send wrapper after
  provider broker dispatch. `prepare-provider-market-data-imbalance-broker-dispatch-send`
  infers the nested generic `broker_dispatch` plan, reruns
  `prepare-broker-dispatch-send` under a nested folder, carries capture
  bundle/env-template/adapter handoff provenance, source env-template proof,
  exchange/session metadata, capture-bundle session match proof, provider
  capture-command proof, and `live_fetch_contract` into provider
  summary/config/runbook artifacts plus manifest, carries broker-dispatch's
  final `dispatch_roundtrip_route_readiness_*` sidecar breach proof, blocks
  acknowledgement reconciliation on nonzero final dry-run provider sidecar
  breaches, writes provider
  checks/summary/action/config/runbook artifacts, indexes the run for
  catalog/scorecard discovery, and routes clean non-submitting send packets to
  dry-run acknowledgement capture via `reconcile-broker-dispatch`.
- Provider-data imbalance now has a provider broker-dispatch acknowledgement
  wrapper after provider send packets. `reconcile-provider-market-data-imbalance-broker-dispatch`
  requires an explicit dry-run ack CSV, infers the nested generic
  `broker_dispatch` plan, reruns `reconcile-broker-dispatch` under a nested
  folder, carries capture bundle/env-template/adapter handoff provenance,
  source env-template proof, exchange/session metadata, capture-bundle session
  match proof, provider capture-command proof, and `live_fetch_contract` into
  provider summary/config/runbook artifacts plus manifest, carries the
  send-retained final `dispatch_roundtrip_route_readiness_*` sidecar breach
  proof, blocks acknowledgement reconciliation on nonzero final dry-run
  provider sidecar breaches, writes provider
  checks/summary/action/config/runbook artifacts, indexes the run for
  catalog/scorecard discovery, and routes clean ack proof to
  `review-provider-market-data-imbalance-broker-dispatch-roundtrip`.
- Provider-data imbalance now has a provider broker-dispatch round-trip wrapper
  after provider acknowledgement proof. `review-provider-market-data-imbalance-broker-dispatch-roundtrip`
  infers the nested generic dispatch, send, and ack folders, reruns
  `review-broker-dispatch-roundtrip` under a nested folder, carries the
  acknowledgement-inherited capture bundle/source credential proof,
  exchange/session metadata, capture-bundle session match proof, provider
  capture-command proof, and `live_fetch_contract` into provider
  summary/config/runbook artifacts plus manifest metadata, carries the
  ack-retained final `dispatch_roundtrip_route_readiness_*` sidecar breach
  proof, reads the acknowledgement manifest, requires exact config/manifest
  `adapter_receipt_proof` agreement, re-hashes every required adapter receipt
  and provider capture, and fingerprints the accepted files in its own
  manifest. Receipt-proof or file drift prevents the nested generic round-trip
  from running and routes repair back to provider broker-dispatch
  acknowledgement reconciliation. It blocks broker-readiness feed on nonzero
  final dry-run provider sidecar breaches, writes provider
  checks/summary/action/config/runbook artifacts, indexes the run for
  catalog/scorecard discovery, and routes clean
  dry-run round-trip evidence to
  `review-provider-market-data-imbalance-broker-readiness --dispatch-roundtrip`
  before cutover promotion.
- Provider-data imbalance broker readiness now accepts that provider
  broker-dispatch round-trip wrapper root directly. The wrapper resolves the
  nested generic `broker_dispatch_roundtrip` proof, passes it into
  `review-broker-readiness`, exposes provider and nested round-trip paths plus
  ready/failed-check fields in the provider summary/config/runbook, promotes
  any nested dispatch and broker-dispatch vendor-market-data batch proof into
  provider summary/config/runbook/manifest metadata, preserves any upstream
  proof and upstream vendor-market-data batch lineage from the provider
  wrapper, now prefers explicit provider-roundtrip `dispatch_roundtrip_*`
  proof fields before falling back to older top-level wrapper fields, carries
  the round-trip capture bundle/env-template/adapter handoff lineage plus
  round-trip source credential env-template, exchange/session metadata,
  capture-bundle session match proof, provider capture-command proof, and
  `live_fetch_contract` proof beside runtime-session provenance, fails closed
  if both sides provide conflicting file provenance, exchange/session/live-fetch
  identity, or provider capture-command proof, and keeps all proof roots,
  including the round-trip source credential env-template, in the manifest for
  audit. For provider wrapper roots it now also reads the final round-trip
  summary/config/manifest before generic broker review, requires the expected
  manifest run type plus exact round-trip config/manifest/runtime-session
  `adapter_receipt_proof` agreement, re-hashes every required receipt and
  capture, and fingerprints both accepted file sets in the broker-readiness
  manifest. Proof or byte drift prevents generic broker-readiness from running
  and routes the final-proof repair back to provider broker-dispatch round-trip
  review. Direct nested generic round-trip folders remain supported without
  imposing provider-wrapper-only metadata.
- Provider-data imbalance cutover now carries that broker-dispatch round-trip
  audit trail forward from provider broker-readiness. The provider cutover
  summary/config/manifest preserve both the provider wrapper root and nested
  generic `broker_dispatch_roundtrip` path, broker-dispatch
  vendor-market-data batch proof, any upstream proof lineage, and upstream
  vendor-market-data batch lineage. It now also keeps the broker-readiness
  validated round-trip capture bundle/env-template/adapter handoff paths,
  source credential env-template proof, round-trip exchange/session metadata,
  capture-bundle session match proof, round-trip provider capture-command
  counts/match flags, provider command arrays from either
  `dispatch_roundtrip_provenance` or older root/capture-bundle config fields,
  live-fetch exchange/session identity,
  `live_fetch_contract`, and
  provenance-consistency flags in summary/config/runbook/manifest artifacts so
  route-enable and later broker dispatch stages can trace the same proof chain
  before live-data dry-runs. Cutover also carries the final round-trip
  `dispatch_roundtrip_route_readiness_*` sidecar breach proof from
  broker-readiness and blocks route-enable review back to provider route
  readiness when nonzero final dry-run sidecar breach pairs remain. Cutover now
  also revalidates broker-readiness's final provider-wrapper receipt proof:
  when required receipts are present it requires exact
  `dispatch_roundtrip_provenance` agreement with both the broker-readiness
  manifest and root runtime receipt proof, re-hashes every receipt and capture,
  and fingerprints both final file sets in its own manifest before generic
  cutover can run. Proof or byte drift routes repair back to provider broker
  readiness; provider wrappers without required receipts and packets without a
  provider-wrapper proof remain compatible and are marked not applicable in the
  runbook. Cutover also hydrates missing or blank
  `dispatch_roundtrip_*` summary fields from broker-readiness
  `dispatch_roundtrip_provenance` config sidecars, while keeping explicit CSV
  `False`/`0` values authoritative, so mixed-version broker-readiness outputs still
  preserve the validated iRage/Arrow live-data handoff trail, including the
  command bundle proof needed before provider route-enable.
- Provider-data imbalance route-enable now preserves the cutover-carried
  provider broker-dispatch round-trip wrapper and nested generic
  `broker_dispatch_roundtrip` paths, broker-dispatch vendor-market-data batch
  proof, upstream proof lineage, and upstream vendor-market-data batch lineage
  in route-enable summary/config/manifest artifacts. It also carries the
  cutover-retained validated round-trip capture bundle/env-template/adapter
  handoff paths, source credential env-template proof, round-trip
  exchange/session metadata, capture-bundle session match proof, round-trip
  provider capture-command counts/arrays/match flags, live-fetch
  exchange/session identity, `live_fetch_contract`, and provenance-consistency
  flags into summary/config/runbook artifacts plus manifest inputs/metadata,
  keeping dry-run broker proof visible through the handoff to provider
  broker-dispatch planning. Route-enable now also hydrates missing or blank
  cutover `dispatch_roundtrip_*` summary fields from the cutover
  `dispatch_roundtrip_provenance` config block before falling back to the
  broker-readiness config block, while preserving explicit summary `False`
  and `0` values, so sparse cutover CSVs do not lose the validated live-data handoff or
  command bundle proof. Route-enable also carries the cutover-retained final
  round-trip `synthetic_sidecar_proof` plus flattened
  `dispatch_roundtrip_synthetic_*` counters and blocks broker-dispatch planning
  back to cutover when synthetic final dry-run folds are present without ready
  rehearsal sidecars. It now also revalidates cutover's final provider-wrapper
  receipt proof: when required receipts exist it requires exact
  `dispatch_roundtrip_provenance` agreement with the cutover manifest and root
  runtime receipt proof, re-hashes every receipt and capture, and fingerprints
  both final file sets before generic route authorization. Proof or byte drift
  routes repair back to provider cutover; no-provider-wrapper packets and
  wrappers without required receipts remain compatible and are marked not
  applicable in the runbook.
- Provider-data imbalance broker-dispatch now preserves the route-enable-carried
  provider broker-dispatch round-trip wrapper and nested generic
  `broker_dispatch_roundtrip` paths, broker-dispatch vendor-market-data batch
  proof, upstream proof lineage, and upstream vendor-market-data batch lineage
  in broker-dispatch summary/config/manifest artifacts. It also carries the
  route-enable-retained validated round-trip capture bundle/env-template/adapter
  handoff paths, source credential env-template proof, round-trip
  exchange/session metadata, capture-bundle session match proof, round-trip
  provider capture-command counts/match flags, provider command arrays from
  either `dispatch_roundtrip_provenance` or older root/capture-bundle config
  fields, live-fetch
  exchange/session identity, `live_fetch_contract`, and source/capture
  provenance-consistency flags through summary/config/runbook artifacts plus
  manifest inputs/metadata before the non-submitting send packet is prepared.
  It also carries nested `synthetic_sidecar_proof` plus flattened sidecar counts
  from route enable and blocks send packet preparation when synthetic provider
  folds are missing ready rehearsal sidecar proof. Broker-dispatch now also
  revalidates route-enable's final provider-wrapper receipt proof: when
  required receipts exist it requires exact `dispatch_roundtrip_provenance`
  agreement with the route-enable manifest and root runtime receipt proof,
  re-hashes every receipt and capture, and fingerprints both final file sets
  before generic non-submitting dispatch planning. Proof or byte drift routes
  repair back to provider route-enable; no-provider-wrapper packets and
  wrappers without required receipts remain compatible and are marked not
  applicable in the runbook.
  Broker-dispatch now also hydrates missing or blank route-enable
  `dispatch_roundtrip_*` summary fields from the route-enable
  `dispatch_roundtrip_provenance` config sidecar, while preserving explicit
  summary `False` and `0` values, so sparse route-enable CSVs do not lose the
  validated live-data handoff or command bundle proof before send packet
  preparation. Broker-dispatch also carries the route-enable-retained final
  round-trip `synthetic_sidecar_proof` plus flattened
  `dispatch_roundtrip_synthetic_*` counters and blocks send packet preparation
  back to route-enable when synthetic final dry-run folds are present without
  ready rehearsal sidecars. Broker-dispatch also carries the route-enable
  route-readiness provider broker round-trip synthetic sidecar breach counter
  and blocks send packet preparation back to provider route readiness when stale
  route-readiness packets expose nonzero sidecar breaches.
- Provider-data imbalance broker-dispatch-send now preserves the same
  provider/nested broker-dispatch round-trip paths, broker-dispatch
  vendor-market-data batch proof, upstream proof lineage, and upstream
  vendor-market-data batch lineage in send summary/config/runbook artifacts
  and manifests. It now also carries the broker-dispatch-retained validated
  round-trip capture bundle/env-template/adapter handoff paths, source
  credential env-template proof, round-trip exchange/session metadata,
  capture-bundle session match proof, round-trip provider capture-command
  counts/match flags, provider command arrays from either
  `dispatch_roundtrip_provenance` or older root/capture-bundle config fields,
  round-trip provider profile proof, live-fetch exchange/session identity,
  `live_fetch_contract`, and source/capture provenance-consistency flags
  through send summary/config/runbook artifacts plus manifest inputs/metadata
  while still keeping `submission_enabled=false`. It blocks acknowledgement
  reconciliation when the broker-dispatch-retained round-trip provider profile
  or adapter contract is missing, unsafe, stale, or no longer matched to
  runtime-session evidence. It also carries nested `synthetic_sidecar_proof`
  plus flattened sidecar counts from broker dispatch and blocks acknowledgement
  reconciliation when synthetic provider folds are missing ready rehearsal
  sidecar proof. Broker-dispatch-send now also carries the
  broker-dispatch-retained final round-trip `synthetic_sidecar_proof` plus
  flattened `dispatch_roundtrip_synthetic_*` counters and blocks
  acknowledgement reconciliation back to broker dispatch when synthetic final
  dry-run folds are present without ready rehearsal sidecars.
  Broker-dispatch-send now also revalidates broker-dispatch's final
  provider-wrapper receipt proof: when required receipts exist it requires
  exact `dispatch_roundtrip_provenance` agreement with the broker-dispatch
  manifest and root runtime receipt proof, re-hashes every receipt and capture,
  and fingerprints both final file sets before producing non-submitting request
  envelopes. Proof or byte drift routes repair back to provider broker
  dispatch; no-provider-wrapper packets and wrappers without required receipts
  remain compatible and are marked not applicable in the runbook.
  It also carries the broker-dispatch-retained route-readiness provider
  broker round-trip synthetic sidecar breach counter and blocks acknowledgement
  reconciliation
  back to provider route readiness when stale packets expose nonzero sidecar
  breaches.
  Broker-dispatch-send now also
  hydrates missing or blank broker-dispatch `dispatch_roundtrip_*` summary
  fields from the broker-dispatch `dispatch_roundtrip_provenance` config
  sidecar, while preserving explicit summary `False` and `0` values, so sparse
  broker-dispatch CSVs do not lose validated live-data provenance, provider
  profile proof, command bundle proof, or sidecar counters before dry-run
  request envelopes are produced.
- Provider-data imbalance broker-dispatch acknowledgement now preserves those
  provider/nested broker-dispatch round-trip paths, broker-dispatch
  vendor-market-data batch proof, upstream proof lineage, and upstream
  vendor-market-data batch lineage in acknowledgement summary/config/runbook
  artifacts and manifests. It now also carries the send-retained validated
  round-trip capture bundle/env-template/adapter handoff paths, source
  credential env-template proof, round-trip exchange/session metadata,
  capture-bundle session match proof, round-trip provider capture-command
  counts/match flags, provider command arrays from either
  `dispatch_roundtrip_provenance` or older root/capture-bundle config fields,
  round-trip provider profile proof, live-fetch exchange/session identity,
  `live_fetch_contract`, and source/capture provenance-consistency flags
  through acknowledgement summary/config/runbook artifacts plus manifest
  inputs/metadata before the final provider round-trip wrapper is trusted.
  Acknowledgement blocks round-trip review when the send-retained round-trip
  provider profile or adapter contract is missing, unsafe, stale, or no longer
  matched to runtime-session evidence. It also carries nested
  `synthetic_sidecar_proof` plus flattened sidecar counts from broker dispatch
  send and blocks round-trip review when synthetic provider folds are missing
  ready rehearsal sidecar proof. It also carries the send-retained final
  round-trip `synthetic_sidecar_proof` plus flattened
  `dispatch_roundtrip_synthetic_*` counters and blocks round-trip review back
  to broker-dispatch-send when synthetic final dry-run folds are present
  without ready rehearsal sidecars. Acknowledgement now also revalidates the
  send-retained final provider-wrapper receipt proof: when required receipts
  exist it requires exact `dispatch_roundtrip_provenance` agreement with the
  send manifest and root runtime receipt proof, re-hashes every receipt and
  capture, and fingerprints both final file sets before accepting dry-run
  acknowledgements. Proof or byte drift routes repair back to provider send
  preparation; no-provider-wrapper packets and wrappers without required
  receipts remain compatible and are marked not applicable in the runbook. It
  also carries the send-retained
  route-readiness provider broker round-trip synthetic sidecar breach counter
  and blocks round-trip review back to provider route readiness when stale
  packets expose nonzero sidecar breaches. It also carries the send-retained
  final `dispatch_roundtrip_route_readiness_*` sidecar breach proof and blocks
  acknowledgement reconciliation before final round-trip review when nonzero
  final dry-run sidecar breaches remain.
  Acknowledgement now also hydrates
  missing or blank send-packet
  `dispatch_roundtrip_*` summary fields from the send
  `dispatch_roundtrip_provenance` config sidecar, while preserving explicit
  summary `False` and `0` values, so sparse send CSVs do not lose validated live-data
  provenance, provider profile proof, command bundle proof, or sidecar counters
  before final round-trip review.
- Provider-data imbalance broker-dispatch round-trip now keeps the
  acknowledgement-carried provider/nested proof and vendor-market-data batch
  proof as upstream lineage while also generating a fresh nested
  `broker_dispatch_roundtrip` proof, so the final readiness handoff can
  distinguish inherited dry-run evidence from the newly reviewed round-trip
  artifact. It also preserves the acknowledgement-carried capture bundle,
  blank credential env-template, adapter handoff paths, source credential
  env-template proof, and `live_fetch_contract`, plus the ack-retained
  validated round-trip capture bundle/env-template/adapter handoff paths,
  source credential env-template proof, round-trip exchange/session metadata,
  capture-bundle session match proof, round-trip provider capture-command
  counts/match flags, provider command arrays from either
  `dispatch_roundtrip_provenance` or older root/capture-bundle config fields,
  live-fetch exchange/session identity,
  `live_fetch_contract`, and source/capture provenance-consistency flags, in
  provider summary/config/runbook artifacts plus manifest inputs/extra
  metadata. It also hydrates sparse acknowledgement round-trip summary rows
  from the acknowledgement `dispatch_roundtrip_provenance` sidecar without
  dropping validated command bundle proof. It also carries the ack-retained
  final round-trip `synthetic_sidecar_proof` plus flattened
  `dispatch_roundtrip_synthetic_*` counters and blocks the broker-readiness
  feed back to acknowledgement reconciliation when synthetic final dry-run
  folds are present without ready rehearsal sidecars. Round-trip review now
  also revalidates the acknowledgement-carried final provider-wrapper receipt
  proof: when required receipts exist it requires exact
  `dispatch_roundtrip_provenance` agreement with the acknowledgement manifest
  and root runtime receipt proof, re-hashes every receipt and capture, and
  fingerprints both final file sets before creating a fresh nested round-trip
  artifact. Proof or byte drift routes repair back to provider acknowledgement
  reconciliation; no-provider-wrapper packets and wrappers without required
  receipts remain compatible and are marked not applicable in the runbook.
  It also carries the ack-retained final
  `dispatch_roundtrip_route_readiness_*` sidecar breach
  proof and blocks broker-readiness feed back to provider route readiness when
  nonzero final dry-run sidecar breaches remain. It also carries nested
  `synthetic_sidecar_proof` plus flattened sidecar counts from acknowledgement
  reconciliation and blocks broker-readiness feed when synthetic provider folds
  are missing ready rehearsal sidecar proof. It also carries the
  acknowledgement-retained route-readiness provider broker round-trip synthetic
  sidecar breach counter and blocks broker-readiness feed back to provider
  route readiness when stale packets expose nonzero sidecar breaches. The provider round-trip
  summary/config now also surfaces nested broker
  vendor-market-data batch proof under both
  `roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_*` and
  `broker_dispatch_roundtrip_vendor_market_data_batch_*` fields. The final
  provider round-trip wrapper now also hydrates missing or blank acknowledgement
  `dispatch_roundtrip_*` summary fields from the acknowledgement
  `dispatch_roundtrip_provenance` config sidecar, while preserving explicit
  summary `False`/`0` values, so sparse acknowledgement CSVs do not lose validated
  live-data provenance, provider command proof, or sidecar counters before
  broker-readiness promotion. Provider broker readiness now consumes that final
  round-trip route-readiness sidecar breach proof separately from the
  runtime-session route proof, exposes it as
  `dispatch_roundtrip_route_readiness_*` summary/config/manifest fields, and
  blocks cutover review back to provider route readiness when nonzero final
  dry-run sidecar breach pairs remain. It also hydrates missing or blank final
  provider round-trip `dispatch_roundtrip_route_readiness_*` summary fields
  from the round-trip `dispatch_roundtrip_provenance` config sidecar while
  keeping explicit CSV `False`/`0` values authoritative, so sparse final
  round-trip CSVs still carry route-sidecar proof into broker-readiness review.
- Provider-data imbalance broker rehearsals can now be sealed with
  `certify-provider-market-data-imbalance-broker-rehearsal`. The certificate
  independently rechecks strict dispatch/send/ack safety, refuses enabled
  submission and any acknowledgement anomaly even when upstream thresholds
  were relaxed, recursively validates reachable manifest artifact/input
  fingerprints and recorded git provenance, and emits a deterministic cycle id
  plus certificate SHA-256. Optional sealed-receipt enforcement distinguishes
  generic dry-run proof from provider receipt/capture proof. Every certificate
  records `authorizes_submission=false` and `digitally_signed=false`; it is a
  content-integrity operator review artifact, not signer approval, and cannot
  enable broker routing. Provider ops-launch evidence requires a passed
  `live_dryrun` certificate with a 64-character certificate SHA-256 and rejects
  paper/shadow or authorizing certificate rows.
- Provider-data imbalance now has a provider route-readiness wrapper before
  scale-up. `review-provider-market-data-imbalance-route-readiness` infers the
  provider launch-evidence strategy review, auto-builds the India
  `microprice_imbalance` market-portability packet when one is not supplied,
  runs the generic `review-route-readiness` join, blocks missing ops-launch
  controls at their exact repair gate, and writes a ready route artifact that
  can be supplied to `plan-provider-market-data-imbalance-scaleup
  --route-readiness`.
- Provider-data imbalance scale-up now accepts that provider route-readiness
  wrapper root directly. The wrapper resolves the nested generic
  `route_readiness` proof, passes it into `plan-scaleup`, exposes
  `route_readiness_*` status fields in the provider scale-up summary/config,
  and preserves the provider wrapper root in the manifest for audit.
- Broker-vendor data readiness now promotes broker schema review state into the
  wrapper summary/config/runbook, including `adapter_schema_status`,
  `schema_review_mode`, and placeholder-schema active/allowed/warning fields so
  catalog and scheduler review can distinguish dry-run placeholder overrides
  from broker-reviewed Arrow.money/iRage mappings.
- Halt response and halt incident evidence now preserve runtime proof-refresh
  fields from the guard through cancel/flatten packets, response summaries,
  response config, incident timelines, and incident closure summaries.
- Strategy portfolio allocation now verifies the complete current
  `strategy_scorecard` bundle whenever its manifest is supplied and
  automatically requires that bundle for registered/family-bound research.
  CSV rows are reconciled with the scorecard summary, JSON actions, manifest
  claims, family ID, registration ID, candidate identity, matched family
  survivor, and non-authorizing state before any paper/shadow weight is
  emitted. `--require-scorecard-manifest` extends the same fail-closed boundary
  to ops-only or exploratory scorecards, while `--allow-unready` cannot bypass
  family closure.
- Portfolio allocation rows, summary/config, runbook, and manifest now retain
  the scorecard manifest hash and carried research-family proof. The portfolio
  manifest fingerprints all scorecard artifacts plus the family root and
  family manifest, and flattens transitive manifest inputs from the catalog,
  registration, robust studies, and source data. Scorecard, family, or nested
  source drift therefore invalidates the capital plan recursively. This path
  remains non-authorizing and paper/shadow-only.
- Controlled scale-up now requires every supplied strategy portfolio to carry
  a complete current `strategy_portfolio_allocation` manifest. It reconciles
  portfolio summary/allocation/config semantics, rejects authorizing claims,
  and reopens the nested scorecard and research-family artifacts to verify
  their hashes, family ID, prospective registration ID, closure, and
  family-wise error-control claim. Failed provenance keeps the source
  allocation visible but sets its usable notional to zero before limit
  calculation.
- Scale-up plan/summary/config now preserve portfolio-manifest,
  scorecard-manifest, and research-family status, identities, and hashes. The
  scale-up manifest fingerprints every portfolio artifact and recursively
  flattened catalog, scorecard, family, registration, robust-study, and source
  dependency, so later nested drift invalidates the session-limit plan. Scale-up
  remains non-authorizing.
- Runtime telemetry now requires a complete current `scaleup_plan` manifest at
  the file boundary. It reconciles scale-up plan/check/summary/config/manifest
  semantics, ready and failed-check state, identities, limits, and explicit
  non-authorizing claims, then reopens any supplied portfolio through the
  existing nested scorecard/research-family verifier. Telemetry carries the
  scale-up, portfolio, scorecard, and prospective-family identities and hashes,
  and recursively fingerprints their dependencies in its own manifest.
- Runtime guard now independently repeats the current scale-up verification
  before applying session limits and compares telemetry-carried scale-up,
  portfolio, scorecard, and research-family lineage against that source.
  Stale inputs, freshly re-manifested but semantically detached limits,
  authorizing claims, missing lineage, old scale-up snapshots, or family
  relabeling halt with explicit provenance repair actions. Telemetry and guard
  outputs cannot overwrite their source proof and remain non-authorizing.
- Runtime session monitoring now carries that verified scale-up, portfolio,
  scorecard, and prospective-family lineage through every step, its summary,
  config, runbook, and manifest. The session manifest fingerprints the current
  scale-up manifest and recursively flattens the scale-up, telemetry, guard,
  and optional halt-response dependencies, so later registration, study, or
  raw-source drift invalidates the operational packet. Session artifacts remain
  non-authorizing and cannot overwrite the scale-up source.
- Halt-response summary/config/runbook plus every cancel and flatten row now
  preserve the same lineage and telemetry comparison state. The response
  manifest binds the complete guard bundle and recursively flattened guard
  dependencies, and later upstream research drift invalidates it. Provenance
  failure remains evidence rather than an emergency-action blocker, so a
  lineage-triggered halt can still produce a ready cancel/flatten packet. Halt
  packets are explicitly non-authorizing and cannot overwrite the guard source.
- Cutover now requires and independently verifies a complete current
  `runtime_session_monitor` manifest, reconciles the carried scale-up,
  portfolio, scorecard, telemetry, and prospective-family contract across the
  session summary/config/manifest, and compares both carried scale-up hashes to
  the current cutover source. It fingerprints all session artifacts and
  recursively flattened dependencies, blocks semantic re-manifesting and
  authorizing claims, preserves the lineage in every cutover artifact, and
  remains explicitly non-authorizing.
- Route-enable repeats the boundary check against a complete current
  `cutover_gate` manifest, requires the retained runtime and cutover lineage
  gates, carries the exact family/registration and manifest hashes through its
  packet/summary/config/manifest, and recursively fingerprints cutover
  artifacts and dependencies. `route_enabled=true` is explicitly not submission
  authority. Output/source overlap is rejected at both boundaries.
- Broker dispatch planning now independently verifies the complete current
  `route_enable_packet` bundle, including the packet itself, and reconciles the
  retained cutover/runtime/research contract across packet, summary, config, and
  manifest, then compares it with the independently reopened current cutover
  bundle. It rejects stale or consistently re-manifested but source-detached
  route evidence and any authorizing claim, carries the exact family and
  manifest lineage onto every dry-run dispatch row plus summary/config/manifest,
  recursively fingerprints all route artifacts/dependencies, rejects
  output/source overlap, and remains explicitly non-submitting.
- Broker dispatch send preparation now independently verifies the complete
  current `broker_dispatch_plan` bundle and reconciles the retained
  route/cutover/runtime/research lineage across every dispatch order, summary,
  config, and manifest. It reopens the current route-enable source rather than
  trusting the dispatch label, blocks stale inputs, cross-artifact disagreement,
  consistently relabeled but source-detached route hashes, and any authorizing
  claim, then carries the exact lineage into every request row and hashed request
  envelope plus send summary/config/manifest. The send manifest recursively
  fingerprints all dispatch artifacts/dependencies, output/source overlap is
  rejected, and both `submission_enabled` and `authorizes_submission` remain
  false.
- Broker acknowledgement reconciliation can now require the complete current
  `broker_dispatch_send_packet` via `--send --require-send-packet`. The verifier
  reconciles dispatch lineage across every request row, hashed request envelope,
  expected-ack template, summary, config, and manifest, then independently
  reopens the current dispatch source and confirms it is the same dispatch being
  reconciled. Missing/stale packets, request/template disagreement, semantic
  re-manifesting, source-detached relabeling, and authorizing claims fail closed.
  Verified send/dispatch/route/runtime/research lineage is carried into every
  acknowledgement row plus ack summary/config/manifest, recursively fingerprinted
  dependencies make later preregistration drift invalidate the ack evidence, and
  acknowledgement artifacts remain explicitly non-authorizing.
- Final broker round-trip review can now require the complete current
  `broker_dispatch_ack_reconciliation` via `--require-ack-lineage`. The verifier
  reconciles every carried send-lineage field across acknowledgement rows,
  summary, config, and manifest; derives acknowledgement and failed-check counts
  from source rows; and independently reopens the current send and dispatch
  bundles. Stale ack artifacts, missing zero-valued fields, freshly re-manifested
  row disagreement, consistently relabeled send hashes, wrong send sources, and
  authorizing claims fail closed and route back to acknowledgement reconciliation.
  Verified ack/send/dispatch/route/runtime/research lineage is retained on every
  final order plus round-trip summary/config/manifest, recursive dependencies are
  fingerprinted, output/source overlap is rejected, and the final proof remains
  explicitly non-authorizing.
- The provider imbalance broker bridge now threads the same proof through
  `--require-send-packet` on provider acknowledgement,
  `--require-ack-lineage` on provider final review, and
  `--require-ack-lineage` on rehearsal certification. Provider final summary,
  config, runbook, and manifest retain the complete generic acknowledgement
  lineage; certification requires exact agreement across provider/nested
  summaries, config, and both manifests, then content-addresses that record in
  the non-authorizing certificate. A real strict provider chain, both new CLI
  flags, post-ack drift rejection, legacy compatibility paths, and certificate
  mismatch rejection pass together (`12 passed`).
- Provider rehearsal certification now requires complete current
  acknowledgement lineage by default at the CLI boundary. Existing explicit
  `--require-ack-lineage` scripts remain valid; only the conspicuous
  `--allow-legacy-ack-lineage` option relaxes the gate for migration-audited
  historical proof, and the override now requires
  `--lineage-migration-audit` for the exact covered round-trip source. The
  lower-level Python writer retains its compatibility
  default so archived fixture regeneration remains controlled. Default strict
  rejection, explicit legacy acceptance, explicit strict acceptance, and all
  certificate integrity paths pass together (`8 passed`).
- Provider final round-trip CLI review now also requires complete current
  acknowledgement lineage by default. Explicit `--require-ack-lineage` scripts
  remain valid, while `--allow-legacy-ack-lineage` makes compatibility use
  visible and auditable and now requires `--lineage-migration-audit` for the
  exact covered acknowledgement source. The strict default traverses the real
  provider acknowledgement into generic dispatch/send/ack proof; focused strict,
  blocked-ack compatibility, and clean legacy-sidecar cases pass together
  (`3 passed`). Existing multi-scenario legacy fixtures now declare their
  override rather than inheriting a permissive default.
- Provider acknowledgement CLI reconciliation now requires the complete current
  broker send packet lineage by default. Explicit `--require-send-packet`
  scripts remain valid, while `--allow-legacy-send-lineage` makes archive-only
  compatibility use visible and auditable and now requires
  `--lineage-migration-audit` for the exact covered provider-send source. The
  lower-level Python writer keeps
  its migration-compatible default so historical bundle regeneration remains
  controlled. The real strict provider chain, blocked-send behavior, and both
  clean route-readiness sidecar compatibility paths pass together (`4 passed`);
  all 15 unaudited acknowledgement and 14 unaudited round-trip fixture paths now
  use the lower-level compatibility writers rather than the production CLI.
- Archived provider broker proofs can now be assessed with
  `audit-provider-market-data-imbalance-broker-lineage-migration` under the
  strict acknowledgement defaults. The read-only audit discovers
  acknowledgement, final round-trip, and certificate bundles across bounded
  roots; verifies each manifest plus its transitive manifested inputs; and
  classifies proofs as strict-ready, safely regenerable, or blocked. It writes a
  catalog-visible summary, inventory, checks, dependency-ordered action queue,
  exact sibling-`_strict` regeneration commands, and an operator runbook without
  modifying archived evidence. Re-audits can now converge without deleting
  legacy proof: a legacy bundle is covered only by a current exact strict
  sibling with the same non-lineage policy and normalized source-evidence
  identity, and downstream coverage requires its upstream legacy dependency to
  be strict or equivalently covered. Policy-mismatched siblings fail closed and
  regeneration moves to a fresh `_strict_rebuilt*` directory instead of
  overwriting proof. Schema version 2 now seals audited bundle directories,
  every audited root manifest, and every recursively discovered source
  dependency into the audit manifest, so post-audit upstream drift invalidates
  the policy artifact itself. A shared read-only verifier additionally requires
  actual 100% coverage, zero blockers/actions, cross-artifact count agreement,
  non-authorizing claims, and exactly one policy-equivalent strict replacement
  covering the requested provider-send, acknowledgement, or round-trip source.
  Unrelated and relaxed-threshold audits fail closed. All outputs remain
  explicitly non-authorizing. Strict, legacy-regenerable,
  equivalent-replacement, exact-source verification, policy-mismatch,
  transitive/post-audit drift, recursive-discovery, collision, catalog, CLI
  exit-policy, and all three exact-source legacy override gates pass together
  (`19 passed`). Each accepted CLI override records the audit directory in its
  writer config and fingerprints the audit directory, audit manifest, and
  transitive audit dependencies in the generated proof manifest. Missing audit,
  audit-on-strict-mode, unrelated source, relaxed policy, and later source drift
  fail closed before the production CLI writer runs.
- Provider acknowledgement, final round-trip, and rehearsal-certificate writers
  now emit a common `lineage_migration_audit_ready` check and flattened summary
  fields for audit path/hash/currentness, hard policy readiness, strict-ready
  coverage, blocker counts, exact source role/status/coverage, and strict
  replacement identity. The same evidence appears in runbooks, nested config or
  certificate payload, and manifest metadata; catalog rows inherit every field
  automatically. Certificate SHA-256 now content-addresses the audit evidence,
  while all three output manifests seal its recursive dependencies. Strict and
  lower-level archive paths explicitly report `not_provided` without creating a
  false blocker.
- Retained provider proofs can now be scanned with
  `review-provider-market-data-imbalance-broker-lineage-audit-usage`. The
  aggregate policy report separates current strict proof from current audited
  legacy proof and blocks unaudited legacy, stale proof manifests, accepted
  audit or strict-replacement drift, migration audits attached to already-strict
  proof, and summary/config/manifest evidence disagreement. Every accepted audit
  is reverified for its exact source at scan time. The report writes a
  catalog-visible inventory, checks, zero-tolerance summary, dependency-ordered
  refresh queue, config, and runbook. Refreshable rows preserve recorded policy
  in strict CLI commands, omit the legacy audit, predict strict upstream
  dependencies, and target fresh non-overwriting siblings. Input-only drift is
  refreshable when every recorded artifact remains current; artifact drift,
  unsealed policy artifacts, missing input fingerprints or source paths,
  unsupported proof, or absent/authorizing non-submission metadata remain
  blocked without a command. The review remains explicitly non-authorizing and
  seals every reviewed bundle, proof manifest, and recursive dependency so later
  drift also invalidates the aggregate artifact. Strict archive, unaudited
  legacy/CLI exit, ordered non-overwriting refresh, current audited legacy,
  post-acceptance drift, aggregate-manifest drift, re-manifested evidence
  disagreement, and artifact-corruption paths pass with the complete lineage
  migration surface (`25 passed`).
- Planned strict lineage refreshes can now be closed with
  `verify-provider-market-data-imbalance-broker-lineage-refresh`. The verifier
  trusts commands only from a current, cross-artifact-consistent,
  non-authorizing audit-usage review, then binds every action to its exact output
  sibling and command source. Generated acknowledgement, round-trip, and
  certificate proofs must be current, passed, strict, audit-free,
  non-authorizing, policy-equivalent, evidence-identity-equivalent, and sourced
  from the command-recorded dependency. Missing outputs retain the sealed ready
  command; occupied invalid outputs are blocked and require replanning to a fresh
  sibling; stale source reviews suppress all commands. Zero unresolved actions
  is fixed policy, while an already-strict source review converges as a valid
  no-op. The catalog-visible convergence summary, inventory, checks, action
  queue, config, runbook, and manifest seal the source review plus every existing
  refreshed proof and recursive dependency. Missing-output/CLI failure, no-op,
  exact three-stage convergence/CLI success/catalog, post-convergence drift,
  policy mismatch, and source-review drift pass with the complete lineage suite
  (`36 passed`).
- Converged provider proofs now have a sealed active-lineage retirement contract
  via `index-provider-market-data-imbalance-broker-active-lineage`. The index
  independently revalidates each exact original/strict pair, marks only the
  current strict, audit-free, policy/evidence-equivalent sibling as
  `selectable`, and keeps the legacy original visible as `retained_only` for
  audit and reproducibility. Its verifier reconstructs expected rows from the
  sealed convergence source, while its resolver rejects stale, edited,
  ambiguous, or unready indexes and requires original-path disambiguation when
  multiple archives contain the same bundle type. Experiment catalogs can now
  consume the verified index, expose per-run selection status and eligibility,
  fail closed on supported proofs when the index is missing or does not cover
  them, and return exit `2` for retained/unindexed candidate sets with
  `--fail-on-provider-lineage-selection-blocks`. The index and catalog remain
  non-authorizing and preserve every retired proof. Exact three-pair retirement,
  no-op, pre-convergence refusal/CLI failure, strict-proof drift, two-archive
  ambiguity, cross-artifact edit rejection, resolver, CLI, and catalog
  selection gates pass (`6 passed`).
- Provider launch candidate selection now consumes that retirement contract
  end to end. Strategy evidence automatically requires a passed `selectable`
  acknowledgement, provider round-trip, and rehearsal certificate whenever
  those proof types are required; retained originals can coexist for audit but
  never satisfy coverage. The strategy scorecard carries selection coverage
  and blocked-row diagnostics, while route readiness independently rejects old
  summaries that omit or disable the contract. The explicit
  `--allow-ineligible-provider-lineage-for-audit` escape produces a sealed,
  non-ready `audit_only` review and cannot authorize a route. Direct evidence,
  CLI, scorecard, generic route-readiness, and real provider wrapper paths pass
  together (`87 passed`).
- Provider launch selection now resolves one deterministic active-strict proof
  per acknowledgement, final round-trip, and rehearsal-certificate stage even
  when newer retained archives coexist. Strategy evidence writes the exact
  three-stage roster to
  `strategy_evidence_provider_lineage_selection.csv`, distinguishes raw latest
  rows from selected rows, and seals bundle type, pair ID, selected/counterpart
  paths, role, status, timestamp, and commit in a canonical SHA-256 selection
  contract. Missing, malformed, or duplicate pair IDs fail closed. The
  strategy scorecard, generic route pair/summary/action/config artifacts, and
  provider route summary/config/runbook/manifest carry that contract and its
  ordered pair IDs; both route layers reject old or unsealed evidence. The
  focused evidence, scorecard, and generic route suites pass together (`82
  passed`), and the complete provider route-wrapper suite, including CLI,
  missing-evidence, stale-sidecar, and deliberately unsealed contract paths,
  passes (`8 passed`).
- The sealed provider active-lineage selection contract now crosses generic and
  provider scale-up plus provider runtime telemetry, guard, and session
  boundaries. A shared validator requires the exact contract version, three
  selected runs, three distinct ordered SHA-256 pair IDs, three distinct run
  directories, the contract SHA, and the roster artifact reference. Each
  provider runtime wrapper preserves those fields in summary, config, runbook,
  and manifest outputs and fails closed unless summary/config/manifest contract
  copies agree exactly. Route-less research compatibility remains intact, while
  any route-bound missing, malformed, or edited contract routes repair back to
  provider route-readiness review. Clean propagation, missing-contract,
  cross-artifact tamper, canonical sidecar precedence, and sidecar-breach paths
  pass across the focused scale-up/runtime batches (`15 passed`).
- Provider broker readiness and cutover now continue that exact active-lineage
  seal across both pre-route broker boundaries. Each boundary validates the
  route-bound source summary/config/manifest copies with the shared strict
  parser, preserves the normalized contract in its summary, config, runbook,
  and manifest, and routes missing or edited proof back to provider
  route-readiness review. Route-less broker research remains compatible. The
  focused broker-readiness and cutover ready, cross-artifact drift,
  sidecar-breach, explicit-zero, and route-less paths pass (`9 passed`), the
  downstream ready route-enable smoke passes (`1 passed`), and the shared
  validator suite passes (`3 passed`).
- Provider route enable and dry-run broker dispatch now carry the same exact
  active-lineage seal across the route-authorization and order-intent planning
  boundaries. Both wrappers require the route-bound source summary, config,
  and manifest copies to agree under the shared strict validator, preserve the
  normalized contract in summary, config, runbook, and manifest artifacts, and
  route incomplete or edited proof back to provider route-readiness review.
  Route-less compatibility and the independent synthetic-sidecar breach path
  remain unchanged. Focused ready, cross-artifact drift, sidecar-breach, and
  route-less/unready paths pass across both boundaries (`8 passed`); the sealed
  dispatch output also passes downstream non-submitting send-packet generation
  (`1 passed`), and the shared validator suite remains green (`3 passed`).
- Provider non-submitting broker-dispatch send preparation now preserves and
  enforces that active-lineage contract before request-packet generation. The
  send wrapper validates exact agreement across the source dispatch summary,
  config, and manifest, carries the normalized contract through its summary,
  config, runbook, and manifest, and routes incomplete or edited proof back to
  provider route-readiness review. The existing route-sidecar breach path and
  route-less/unready compatibility remain isolated. Focused ready,
  cross-artifact drift, sidecar-breach, and unready paths pass (`4 passed`),
  the sealed send output passes downstream acknowledgement reconciliation (`1
  passed`), and the shared validator suite remains green (`3 passed`).
- Provider broker acknowledgement reconciliation now preserves and enforces
  the same active-lineage contract before accepted or rejected responses can
  contribute to a round-trip proof. The acknowledgement wrapper validates the
  source send summary, config, and manifest copies exactly, carries the
  normalized contract through summary, config, runbook, and manifest outputs,
  remains non-authorizing, and keeps the existing lineage-migration audit
  independent. Incomplete or edited proof routes back to provider
  route-readiness review even when every synthetic acknowledgement is accepted.
  Focused ready, cross-artifact drift, sidecar-breach, and unready paths pass
  (`4 passed`); the sealed acknowledgement passes downstream final round-trip
  review (`1 passed`), and the shared validator suite remains green (`3
  passed`).
- Provider final broker round-trip review now preserves and enforces the same
  active-lineage contract before a completed dispatch/send/ack cycle can count
  as rehearsal proof. The wrapper requires exact source acknowledgement
  summary/config/manifest agreement, carries the normalized contract through
  summary, config, runbook, and manifest outputs, remains non-authorizing, and
  leaves its independent acknowledgement-lineage and migration-audit policies
  intact. Edited proof routes back to provider route-readiness review even when
  all nested round-trip checks pass. Focused ready, cross-artifact drift,
  sidecar-breach, and unready paths pass (`4 passed`); the real strict
  acknowledgement-lineage path carries the sealed final review into rehearsal
  certificate generation and recursive nested-ack drift rejection (`1
  passed`), and the shared validator suite remains green (`3 passed`).
- Provider rehearsal certification now independently validates the final
  round-trip active-lineage contract across its source summary, config, and
  manifest before issuing evidence. The normalized three-stage contract is
  bound into the certificate's hashed payload, flattened into its summary,
  repeated in the output manifest, and shown in the operator runbook. Route-less
  archives remain compatible, while any route-bound or partially present
  contract activates strict validation and routes disagreement back to provider
  route-readiness review. The real strict ready chain and final-config tamper
  rejection pass together (`2 passed`), all legacy certificate safety and
  archive paths remain green (`8 passed`), and the shared validator suite passes
  (`3 passed`).
- Provider active-lineage chain auditing is now available through
  `audit-provider-market-data-imbalance-active-lineage-chain`. Starting from one
  rehearsal certificate, the bounded audit walks the complete recursive
  manifest graph and requires exactly one ordered provider boundary for route
  readiness, scale-up, telemetry, guard, session, broker readiness, cutover,
  route enable, dispatch, send, acknowledgement, final review, and
  certification. Every stage must be ready, non-authorizing, manifest-current,
  directly bound to its immediate predecessor, internally consistent across
  summary/config/manifest contract copies, and equal to the route-readiness
  canonical contract. Route readiness now emits the full normalized contract in
  config and manifest as well as its original flattened summary fields. The
  audit also verifies the certificate payload hash and cycle ID, emits a
  deterministic 13-stage chain digest plus chain/manifest/check/action artifacts
  and an operator runbook, and fingerprints every recursive dependency in its
  own non-authorizing manifest. The real strict chain passes all `13` stages and
  `65` recursive manifests through the API and CLI, then a valid-looking
  runtime-guard contract edit fails closed through both paths (`1 passed`). The
  shared contract, legacy certificate, and manifest suites remain green (`17
  passed`).
- Provider rehearsal-certificate selection now fails closed on the chain audit.
  The audit exposes a read-side verifier that independently rebuilds the full
  13-stage graph from the covered certificate, rechecks all recursive
  manifests, contract surfaces, predecessor links, certificate hash/cycle,
  non-authorizing claims, and deterministic chain digest, and only then emits a
  certificate coverage record. `catalog-runs` accepts repeatable
  `--provider-active-lineage-chain-audit` inputs and makes a selectable
  rehearsal certificate eligible only when one trusted audit covers its exact
  directory and current manifest hash; acknowledgement and final-roundtrip
  selection remain unchanged. Catalog rows and summaries expose audit coverage,
  binding, digest, and block reasons, while strategy evidence independently
  requires the bound `covered_current` status and carries the selected audit
  path and hashes into its evidence item. A pre-existing catalog collision that
  allowed a report's textual `status` field to overwrite normalized
  `summary_status` is also closed. The real 13-stage clean/drift fixture,
  active-index/catalog integration, all strategy-evidence, all experiment
  catalog, and manifest suites pass together across focused runs (`127
  passed`), with the certificate catalog namespace regression covered
  separately (`1 passed`).
- Final file-backed provider strategy evidence now closes stale-catalog replay.
  Before a rehearsal certificate can remain selected, the writer verifies the
  source `experiment_catalog` manifest and all of its artifacts/inputs,
  independently reopens the selected 13-stage chain audit, verifies the
  selected certificate manifest and recursive inputs, and requires exact
  catalog agreement on both proof directories, both manifest hashes, the chain
  digest, and the active-lineage contract SHA. The resulting evidence manifest
  directly fingerprints the catalog CSV/manifest, selected audit
  directory/manifest, and selected certificate directory/manifest. A flat CSV
  replay is therefore non-ready, direct audit or certificate drift invalidates
  the completed evidence manifest, and rebuilding from a stale catalog after
  deep upstream chain drift fails the semantic audit check. The pure in-memory
  evaluator and explicit audit-only provider mode remain non-authorizing and
  backward compatible. Strategy-evidence, shared-manifest, and experiment-
  catalog suites pass together (`127 passed`); the real 13-stage clean/deep-
  drift path passes separately (`1 passed`).
- Completed provider strategy-evidence roots now have a semantic read-side
  verifier and CLI (`verify-strategy-evidence`) for downstream release review.
  The verifier reopens the exact manifest-bound catalog, recomputes all four
  evidence tables, reruns the retained catalog/audit/certificate proof checks,
  requires the six-input fingerprint contract, and validates the explicit
  non-authorizing manifest metadata. Direct retained-proof drift fails manifest
  integrity; recursively re-manifested upstream drift still fails the semantic
  source comparison. Experiment-catalog ingestion invokes this verifier for the
  provider launch profile and suppresses stale or inconsistent evidence instead
  of preserving its recorded ready status. Legacy and audit-only evidence stay
  backward compatible. The strategy-evidence, manifest, and experiment-catalog
  affected surface passes together (`127 passed`), including CLI, metadata-only
  tamper, provider-profile relabel bypass, direct retained-proof drift, stale-
  catalog replay, and catalog status suppression paths. The real 13-stage
  clean/deep-drift replay also passes (`1 passed`).
- Verified and ready provider strategy evidence can now advance to a local-only
  live-dry-run release-review packet through
  `prepare-provider-market-data-imbalance-release-review`. The packet preserves
  the exact evidence, catalog, active-lineage audit, chain, lineage-contract,
  rehearsal-certificate manifest, and certificate-payload hashes; its manifest
  additionally fingerprints the complete recursive evidence dependency graph.
  It emits checks, proof inventory, config, deterministic packet identity,
  action queue, runbook, and an immutable pending operator-approval template.
  Every surface records `submission_enabled=false`, `broker_api_called=false`,
  and `authorizes_submission=false`; no broker command, credential, or order
  payload is produced. Preparation fails before packet creation unless the
  source is semantically `verified && ready`, resolves to one strategy and one
  market, and selects a passed non-authorizing `live_dryrun` certificate.
  `verify-provider-market-data-imbalance-release-review` reopens both packet and
  source evidence, recomputes the deterministic proof contract, and rejects
  direct drift, out-of-tree recursive drift, or a freshly re-manifested
  authorization claim. Experiment-catalog ingestion uses that verifier and
  suppresses stale release-review readiness. The strategy-evidence, manifest,
  and experiment-catalog affected surface passes together (`127 passed`).
- A current release-review packet can now be finalized against a separately
  retained operator decision with
  `finalize-provider-market-data-imbalance-release-decision`. The release
  template carries the full deterministic packet SHA, and finalization requires
  exact review/packet/strategy/market/evidence/catalog/audit/certificate
  bindings, a non-empty operator identity and role, a UTC review timestamp, and
  explicit risk-limit, kill-switch, rollback-plan, and non-authorization
  attestations. Approved and rejected decisions are both sealed and
  semantically verifiable; only approval sets
  `approved_for_live_dryrun=true`. Generic `release_approved`, broker
  submission, and broker API flags remain false in both outcomes. Decision
  directories are write-once, fingerprint the separate operator file and the
  complete recursive release-review dependency graph, and emit deterministic
  checks, proof inventory, JSON/config, summary, runbook, and manifest
  artifacts. `verify-provider-market-data-imbalance-release-decision`
  reconstructs every artifact from current sources, while experiment-catalog
  ingestion distinguishes verified approval, verified rejection, and stale or
  inconsistent seals. Focused approval/rejection, missing-attestation,
  re-manifested authorization tamper, operator-file drift, and recursive source
  drift pass in both retained-proof variants (`2 passed`); the complete affected
  strategy-evidence, manifest, and experiment-catalog gate passes (`127
  passed`).
- A verified approved release decision can now advance into a write-once,
  controlled live-dry-run handoff through
  `prepare-provider-market-data-imbalance-live-dryrun-handoff`. A separate,
  credential-free runtime-controls JSON must bind the exact decision ID/SHA,
  retained rehearsal-certificate provider/transport/exchange/adapter identity,
  India trading session, finite integer order/position limits, notional cap,
  armed kill-switch behavior, rollback owner/procedure, and a current rollback
  runbook SHA. The emitted deterministic plan contains only ordered action
  labels: execution, broker API calls, submission, authorization, and stored
  credential values remain explicitly disabled, and a separate future runtime
  launcher is required. The handoff manifest fingerprints the approved
  decision, controls, rollback file, and complete recursive retained proof
  graph. `verify-provider-market-data-imbalance-live-dryrun-handoff`
  reconstructs every artifact and rejects source drift or a freshly
  re-manifested authorization claim; experiment-catalog ingestion invokes the
  same verifier and suppresses stale readiness. This slice does not contact a
  provider, inspect credential values, launch a session, or claim that the
  earlier operator decision attested the exact later controls file. Both
  retained-proof variants pass the focused approved/rejected, identity,
  credential-key, limit, write-once, semantic-tamper, controls/rollback drift,
  and recursive-source-drift gate (`2 passed`).
- A verified ready live-dry-run handoff can now advance through a credential-safe
  runtime connectivity preflight with
  `preflight-provider-market-data-imbalance-live-dryrun-runtime`. A strict,
  credential-free runtime profile binds the exact handoff ID/SHA,
  provider/adapter/transport/market/exchange/session identity, secure endpoint,
  built-in provider credential env-var names, and connectivity-only safety
  contract. The trusted backend boundary receives only env-var names and
  presence booleans; backend exceptions are reduced to safe codes, credential
  values are scanned out of every artifact, and no strategy or broker-order API
  capability exists on the probe interface. Ready and valid-but-blocked runs
  both emit write-once launch receipts, checks, summary, config, runbook, and a
  recursive manifest. Every surface explicitly records no strategy launch, no
  order API call, no submission authority, and the need for a separate runtime
  launcher. `verify-provider-market-data-imbalance-live-dryrun-runtime-preflight`
  reconstructs the receipt from current handoff/profile sources without
  reconnecting, while catalog ingestion distinguishes `verified_ready`,
  `verified_blocked`, and stale/tampered runs. Secure-endpoint, missing-
  credential, backend-failure, exception-redaction, and strict-entrypoint
  boundary tests pass (`11 passed`); both retained-proof variants pass the full
  CLI/catalog/write-once/authorization-tamper/profile-drift/recursive-drift gate
  (`2 passed`). Shared manifest and catalog regressions remain green (`68
  passed`). This provides the provider-neutral safety boundary only: no
  production Arrow.money/iRage connectivity backend, signed provider
  attestation, endpoint/auth contract, or live credential has been supplied.
  The configured backend remains trusted in-process code; the receipt does not
  independently prove an unaudited module's side effects or provider-side
  credential scope.
- A current ready runtime preflight can now advance through the bounded,
  simulation-only market-data launcher with
  `launch-provider-market-data-imbalance-live-dryrun-simulated-runtime`. The
  launcher enforces the handoff's exact India session window and armed kill
  switch, generates a finite deterministic quote stream, stops at the first
  session, timestamp, or quote-integrity breach, and emits write-once telemetry,
  checks, config, runbook, summary, recursive manifest, and terminal receipt.
  The execution modules have no ambient provider, network, dynamic-import,
  credential, or broker-order capability; every artifact explicitly records
  that provider networking, credential reads, strategy execution, order
  generation, broker API use, and submission were absent. Completed and
  kill-switch-halted sessions are both semantically reopenable, while only a
  completed session is progression-ready. The strict
  `verify-provider-market-data-imbalance-live-dryrun-runtime-launcher` command
  deterministically reconstructs the session without reconnecting, rejects
  source drift and freshly re-manifested authorization claims, and drives
  `verified_completed`, `verified_halted`, or stale experiment-catalog states.
  The simulator plus launcher/verifier/CLI/catalog boundary passes `17` focused
  tests, and both retained audit/certificate proof variants pass the complete
  recursive drift chain (`2 passed`). This is not real Arrow.money/iRage market
   data and does not claim provider-side behavior; choosing a production
   endpoint/auth contract and supplying credentials remain external gates.
- A semantically verified completed runtime-launcher session can now advance
  through `evaluate-provider-market-data-imbalance-live-dryrun-shadow`. The
  bounded evaluator reuses engine-independent microprice feature, entry, and
  exit semantics to produce deterministic broker-neutral intent observations,
  applies the handoff's exact order-count, gross-notional, open-order, and
  position limits, requires the retained kill switch, and terminally flattens
  hypothetical exposure. Intents are explicitly `not_routable` and
  `not_submitted`; the evaluator has no execution-engine, order-object,
  credential, provider-network, dynamic-import, or broker-order capability.
  Completed and limit-halted sessions emit write-once features, intents,
  checks, config, runbook, summary, terminal receipt, and recursive manifest.
  `verify-provider-market-data-imbalance-live-dryrun-shadow-evaluation`
  reconstructs the artifacts from current launcher telemetry and handoff
  limits without routing, submitting, or reconnecting; catalog ingestion
  distinguishes verified completion, verified halt, and stale or inconsistent
  results. The pure feature/runtime/report/CLI/catalog boundary passes `49`
  focused tests, and both retained audit/certificate drift variants pass the
  complete proof chain (`2 passed`). The current source remains deterministic
  simulation, uses a synthetic one-unit lot size unless explicitly configured,
  and provides no claim of realized fills, live edge, Arrow.money/iRage
  behavior, or production instrument metadata.
- A semantically verified completed shadow evaluation can now advance through
  `calibrate-provider-market-data-imbalance-live-dryrun-shadow`. The pure core
  binds each accepted, non-routable, non-submitted shadow intent to its exact
  source feature and measures forward directional mid and microprice response,
  executable liquidation-touch markout, gross touch PnL, adverse selection,
  observation coverage, and latency/horizon sensitivity. It also computes
  break-even sensitivity under separate repository-reference NSE index-futures
  and index-options cost schedules. Every cost row is explicitly labeled
  `repository_reference_requires_external_validation`; these rates are not
  represented as current exchange or broker terms. Completed and
  insufficient-coverage runs both emit write-once checks, markouts, cost rows,
  horizon and cost summaries, config, runbook, receipt, and recursive manifest.
  `verify-provider-market-data-imbalance-live-dryrun-shadow-calibration`
  deterministically reconstructs the entire artifact set from the current
  recursive shadow proof graph, while catalog ingestion distinguishes
  `verified_completed`, `verified_insufficient`, and stale or inconsistent
  results and suppresses stale summary status. The core/report/CLI/catalog
  boundary passes `23` focused tests and both retained audit/certificate proof
  variants pass the complete recursive drift chain (`2 passed`). This is a
  calibration-only evidence gate: it cannot authorize promotion, route, or
  submit, and the current source remains deterministic simulation rather than
  real provider observations, realized fills, or evidence of live edge.
- Two or more distinct semantically verified completed shadow calibrations can
  now advance through
  `compare-provider-market-data-imbalance-live-dryrun-shadow-calibrations`.
  The capability-free cohort core requires one exact runtime identity,
  calibration contract, horizon/cost grid, and evidence class, then measures
  cross-session coverage dispersion, directional mid-response range and sign,
  adverse-selection-rate dispersion, cost break-even-rate dispersion, and
  round-trip reference-cost dispersion. A one-session or over-dispersed cohort
  remains valid evidence but is explicitly unstable; duplicate session IDs or
  structurally incompatible grids are rejected. Stable and unstable cohorts
  both emit write-once checks, session rows, horizon/cost stability tables,
  config, runbook, receipt, and a manifest that recursively fingerprints every
  source calibration proof graph. The semantic verifier reconstructs all
  artifacts without rerunning a provider and drives `verified_stable`,
  `verified_unstable`, and stale/inconsistent catalog states. All current
  sources are explicitly `deterministic_simulation`, every reference-cost row
  still requires external validation, and stability is not a performance,
  promotion, routing, submission, or release gate. The core/report/CLI/catalog
  boundary passes `22` focused tests, including upstream telemetry drift and a
  freshly re-manifested authorization claim.

- Vendor CSV intake is now a write-once, source-current evidence boundary.
  Each persisted Arrow.money/iRage-neutral profile emits a deterministic
  `vendor_intake_receipt.json` binding the raw source fingerprint, inferred
  kind, generated mapping draft, readiness outcome, settings, and explicit
  intake-only/non-authorizing safety contract. `verify-vendor-csv-intake`
  reconstructs every CSV/JSON/runbook artifact from the current source and
  rejects source drift, artifact edits, path/config substitution, and mapping
  tampering even after the manifest is regenerated. A complete mapping is
  `verified_ready`; an honestly incomplete or ambiguous schema is
  `verified_blocked`; stale or inconsistent evidence fails closed in
  `catalog-runs`. No Arrow.money or iRage columns were invented by this slice.
- Vendor mapping review now closes the gap between a receipt-bound intake draft
  and mapped-data normalization. A provider-neutral, write-once review seals an
  approved or rejected operator decision against the exact intake receipt,
  source bytes, candidate mapping, adapter, and data kind. Approval requires
  explicit vendor-documentation, source-column, field-semantic, timestamp,
  price/quantity-unit, and transform attestations plus non-routing and
  non-submission declarations. The semantic verifier reconstructs every
  artifact and the retained intake/source graph; catalogs expose
  `verified_approved`, `verified_rejected`, and `stale_or_inconsistent`.
  Approval authorizes only exact-mapping normalization, never strategy
  research, routing, submission, or live release. The eight-test adversarial
  gate covers opaque blocked schemas, invalid approval, valid rejection,
  upstream source drift, candidate tampering after re-manifesting, write-once
  output, unknown operator claims, strict CLI behavior, and catalog
  classification.
- Reviewed mapped-data normalization now enforces that approval at execution.
  The write-once path derives the vendor source, canonical mapping, adapter, and
  data kind from a semantically verified approved review, then emits the
  standard `mapped_data_*` artifacts plus deterministic binding checks and a
  receipt. Its verifier reruns normalization and reconstructs every retained
  artifact, input fingerprint, setting, manifest field, and safety claim.
  Rejected or stale reviews are refused; data-quality failures remain honest
  `verified_blocked` evidence; source drift or re-manifested output tampering is
  stale/inconsistent. Catalogs expose `verified_ready`, `verified_blocked`, and
  `stale_or_inconsistent`, while existing data-readiness readers can consume
  the unchanged `mapped_data_summary.csv` filename. This boundary still does
  not authorize strategy research, routing, submission, or live release.
- Data readiness and the single-file vendor onboarding pipeline now enforce the
  reviewed-normalization boundary end to end. A strict readiness threshold
  distinguishes ordinary mapped data from review-bound output, retains the
  review/source/mapping fingerprints in readiness summaries, verifies the
  explicit normalization-only and non-authorizing safety fields, and routes
  repairs to `normalize-reviewed-mapped-data`. The vendor pipeline accepts a
  mutually exclusive `--mapping-review`, verifies approval and exact source,
  adapter, and kind bindings before creating output, derives the reviewed
  mapping, forces the strict readiness threshold, and fingerprints the review
  graph in its root manifest. Exact-source approvals are intentionally not
  reused by the multi-file batch pipeline; broader schema-scoped approval is a
  separate future contract.
- Exact-header mapping reuse now has that separate operator evidence contract.
  A write-once scope review starts from a semantically verified approved
  exact-source mapping review and binds its review ID/hash, canonical mapping
  hash, ordered source-header hash, adapter, and data kind. Approval requires
  explicit cross-file schema, field, timestamp, price/quantity-unit, transform,
  and partitioning attestations. The verifier reconstructs the full upstream
  graph and every artifact, checks the copied mapping byte for byte, and rejects
  drift or re-manifested authority widening. Catalogs expose
  `verified_approved`, `verified_rejected`, and `stale_or_inconsistent`. This
  seal authorizes exact-header mapping application only; target-file
  normalization, research, routing, submission, and live release remain
  unauthorized.
- Target mapping application now turns that scope into per-file evidence. A
  write-once application reconstructs the approved scope and a current target
  vendor intake, binds the target source fingerprint, requires exact ordered
  header plus adapter/kind equality, and retains the canonical mapping byte for
  byte. Opaque but semantically verified blocked intakes can be accepted only
  through this approved scope. The semantic verifier catches target-source,
  intake, and upstream scope drift as well as re-manifested safety widening;
  catalogs expose `verified_ready` and `stale_or_inconsistent`. This boundary
  records that normalization has not run and remains unauthorized.
- Target-applied mapped-data normalization now consumes that per-file proof.
  The write-once command derives source, mapping, adapter, and kind only from a
  semantically verified target application, reruns canonical normalization,
  and retains the application, scope-review, target-intake, exact source,
  ordered-header, and mapping fingerprints in the standard `mapped_data_*`
  handoff. Its verifier reconstructs the entire output and upstream application
  graph, classifies honest data-quality failures as `verified_blocked`, and
  rejects source/application drift or re-manifested artifact and authority
  tampering. A separate strict data-readiness mode requires this lineage and
  routes gaps to `normalize-applied-vendor-mapping`; it cannot be combined with
  the exact-source review mode. The application itself remains non-authorizing,
  and normalization still grants no strategy-research, routing, submission, or
  live-release authority.
- The single-file vendor onboarding pipeline now consumes target applications
  end to end. Its mutually exclusive `--mapping-application` mode reconstructs
  the verified application graph before creating output, requires the exact
  target source plus adapter/kind identity, derives normalization only from the
  retained application, and forces target-application-bound data readiness.
  Opaque blocked inference can proceed only when the application supplies the
  reviewed mapping. Pipeline summaries, config, and the root manifest retain
  the application, scope-review, target-intake, exact-source, and applied-mapping
  lineage. Output/evidence overlap, identity substitution, source drift, and
  mixed mapping modes fail before pipeline output is created.
- Multi-file vendor onboarding now accepts one distinct target application per
  dataset. The batch command aligns repeated `--mapping-application` arguments
  with inputs, reconstructs every application graph, checks exact target and
  adapter/kind identity, rejects duplicate applications and colliding sanitized
  labels, and checks the batch root against all retained evidence before any
  write. Each child is forced through strict target-application readiness. The
  batch CSV/config/runbook expose application count, uniqueness, coverage, and
  per-dataset lineage; the root manifest fingerprints every application,
  scope-review, target-intake, target-source, and applied-mapping graph and
  re-verifies them before sealing. Raw shared mappings and per-dataset
  applications remain mutually exclusive.
- The combined broker-vendor readiness pipeline now accepts the same ordered
  per-dataset target applications. It defers creation of the wrapper root until
  the nested batch preflight succeeds, directly fingerprints application and
  nested-batch evidence, and exposes mapping mode, count, uniqueness, and
  coverage at the wrapper root. Broker readiness now carries those fields into
  its own summary/config and requires complete target-application lineage for
  every dataset before accepting an application-backed vendor batch. Raw
  mapping and application modes remain mutually exclusive at both API and CLI
  boundaries.
- Controlled scale-up now retains that target-application proof at the first
  capital-control boundary. Rich broker summaries and thin summaries hydrated
  from `broker_readiness_config.json` both carry mapping mode, application
  count, uniqueness, coverage, and the complete per-dataset application,
  scope-review, target-intake, and applied-mapping lineage. Any target-mode
  signal activates fail-closed checks requiring the strict source mode, one
  distinct application per dataset, full coverage, and complete lineage;
  legacy draft-backed vendor batches remain compatible. Scale-up now also
  requires the broker-readiness current/final lineage-match decision for every
  target-backed batch and recomputes the canonical lineage digest from the
  carried datasets. When broker readiness marks final reconciliation required,
  scale-up still validates the complete ten-view compatibility decision and
  makes its own recomputation view eleven. Reconciled targets now additionally
  require broker readiness's complete eighteen-view final comparison. Scale-up
  revalidates the current, broker-final, historical scale-up-, cutover-, route-,
  dispatch-, send-, ack-, roundtrip-, readiness-, scale-up-review-,
  cutover-review-, route-enable-review-, dispatch-plan-review-,
  send-packet-review-, acknowledgement-reconciliation-review-,
  roundtrip-final-review-, and broker-readiness-review-carried digests, then
  independently recomputes the canonical digest as view nineteen. The existing
  eleven-view comparison remains unchanged for cutover compatibility. The
  complete nineteen-view handoff is retained in flattened
  `broker_readiness_final_*` summary fields and the sibling
  `scaleup_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`
  config block. Generic target onboarding keeps the established three-view
  path; legacy draft-backed batches remain compatible.
- Cutover now preserves and independently gates the same application-backed
  broker vendor batch from scale-up config or flattened scale-up summary. A
  broker-readiness config sidecar may hydrate the underlying batch and
  compatibility proof, but cannot substitute for scale-up's own final review.
  Its authorization, summary, and nested
  config retain mode, count, uniqueness, coverage, and each dataset's complete
  application/scope-review/target-intake/applied-mapping graph. Any target
  signal requires strict mode, one unique application per dataset, full
  coverage, complete lineage, an affirmative scale-up current/final match, and
  final dispatch/send/ack consistency when that final-stage decision is marked
  required before route enable can inherit the proof. Cutover continues to
  validate scale-up's eleven-view compatibility comparison and independently
  recomputes view twelve without changing that route-enable contract.
  Reconciled targets now additionally require scale-up's complete nineteen-view
  final comparison. Cutover revalidates the current, broker-final, historical
  scale-up-, cutover-, route-, dispatch-, send-, ack-, roundtrip-, readiness-,
  scale-up-review-, cutover-review-, route-enable-review-, dispatch-plan-review-,
  send-packet-review-, acknowledgement-reconciliation-review-,
  roundtrip-final-review-, broker-readiness-review-, and
  scale-up-final-review-carried digests, then independently recomputes the
  canonical digest as view twenty. The original four-view comparison and full
  twelve-view compatibility handoff remain unchanged in flattened summary
  fields and the sibling
  `cutover_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`
  config block. The complete input is retained in flattened `scaleup_final_*`
  fields and the twenty-view output is emitted under
  `cutover_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
  A reconciled target hydrated only from a broker-readiness sidecar fails
  closed until controlled scale-up emits the nineteen-view proof. Generic
  non-reconciled targets and legacy draft-backed handoffs keep their existing
  compatibility paths.
- Route enable now carries and revalidates that target-application batch before
  dry-run broker dispatch can inherit it. Current cutover config, flattened
  cutover summary, and broker-readiness sidecar inputs all retain mapping mode,
  application count, uniqueness, coverage, and full per-dataset lineage in the
  route packet, summary, and config. Summary-only recovery now selects the
  current `cutover_*` proof prefix before older `scaleup_*` compatibility
  fields. Any target signal activates the same one-application-per-dataset
  fail-closed contract and additionally requires the affirmative cutover
  lineage decision, final consistency when required, exact current/final,
  scale-up-carried, and cutover-carried digests, plus a fresh canonical digest
  recomputed from the route-carried datasets. Route enable continues to
  validate cutover's twelve-view compatibility comparison and independently
  recomputes view thirteen without changing broker dispatch's contract.
  Reconciled targets now additionally require cutover's complete twenty-view
  final comparison. Route enable revalidates the current, broker-final,
  historical scale-up-, cutover-, route-, dispatch-, send-, ack-, roundtrip-,
  readiness-, scale-up-review-, cutover-review-, route-enable-review-,
  dispatch-plan-review-, send-packet-review-,
  acknowledgement-reconciliation-review-, roundtrip-final-review-,
  broker-readiness-review-, scale-up-final-review-, and
  cutover-final-review-carried digests, then independently recomputes the
  canonical digest as view twenty-one. The original five-view comparison and
  full thirteen-view compatibility handoff remain unchanged in flattened
  summary fields and the sibling
  `route_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`
  config block. The complete input is retained in flattened `cutover_final_*`
  fields and the twenty-one-view output is emitted under
  `route_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
  Generic non-reconciled targets and legacy draft-backed handoffs keep their
  compatibility paths; thin target sidecars fail until cutover produces the
  complete twenty-view comparison.
- Broker dispatch planning now preserves and independently gates the same
  application-backed vendor batch before any sender packet can be prepared.
  Nested route config, flattened route summary, and broker-readiness sidecar
  hydration retain mapping mode, application count, uniqueness, coverage, and
  every dataset's application/scope-review/target-intake/applied-mapping
  lineage in dispatch summary and config. Any target signal must satisfy the
  one-distinct-application-per-dataset contract, the affirmative route-retained
  lineage decision, final consistency when required, exact current/final,
  scale-up-, cutover-, and route-carried digests, plus a fresh canonical digest
  recomputed from dispatch-carried datasets. Reconciled targets continue to
  require route enable's complete thirteen-view compatibility comparison and
  now additionally require its complete twenty-one-view final comparison.
  Dispatch planning revalidates the current, broker-final, historical scale-up-,
  cutover-, route-, dispatch-, send-, ack-, roundtrip-, readiness-,
  scale-up-review-, cutover-review-, route-enable-review-, dispatch-plan-review-,
  send-packet-review-, acknowledgement-reconciliation-review-,
  roundtrip-final-review-, broker-readiness-review-, scale-up-final-review-,
  cutover-final-review-, and route-final-review-carried digests, then
  independently recomputes the canonical digest as view twenty-two. The
  existing six-view comparison and full fourteen-view compatibility handoff
  remain unchanged in flattened summary fields and the sibling
  `dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`
  config block. The complete input is retained in flattened `route_final_*`
  fields and the twenty-two-view output is emitted under
  `dispatch_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
  Legacy draft-backed and generic non-reconciled batches remain compatible;
  thin reconciled-target sidecars fail until route enable produces both
  complete comparisons.
- Broker dispatch send preparation now carries and revalidates that target
  proof before non-submitting request envelopes can advance. Nested dispatch
  config, flattened dispatch summary, and broker-readiness sidecar hydration
  retain all application aggregates and per-dataset lineage in the send summary
  and config. Target signals activate the same strict one-application-per-
  dataset gate, require the affirmative dispatch-retained lineage decision and
  final consistency when marked required, verify the current, broker-final,
  scale-up-, cutover-, route-, and dispatch-carried digests, and independently
  recompute a seventh canonical digest from the send-carried datasets.
  Reconciled targets continue to require broker dispatch's complete
  fourteen-view compatibility comparison and now additionally require its
  complete twenty-two-view final comparison. Send preparation revalidates the
  current, broker-final, historical scale-up-, cutover-, route-, dispatch-,
  send-, ack-, roundtrip-, readiness-, scale-up-review-, cutover-review-,
  route-enable-review-, dispatch-plan-review-, send-packet-review-,
  acknowledgement-reconciliation-review-, roundtrip-final-review-,
  broker-readiness-review-, scale-up-final-review-, cutover-final-review-,
  route-final-review-, and dispatch-final-review-carried digests, then
  independently recomputes the canonical digest as view twenty-three. The
  existing seven-view comparison and full fifteen-view compatibility handoff
  remain unchanged in flattened summary fields and the sibling
  `send_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`
  config block. The complete input is retained in flattened `dispatch_final_*`
  fields and the twenty-three-view output is emitted under
  `send_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
  Draft-backed and generic non-reconciled packets retain their compatibility
  paths; thin reconciled-target sidecars fail until broker dispatch provides
  both complete comparisons.
- Broker dispatch acknowledgement reconciliation now preserves and independently
  gates the send-retained target proof before accepted acknowledgement evidence
  can advance. Nested send/dispatch config, flattened dispatch summary, and
  broker-readiness sidecar hydration retain mapping mode, application count,
  uniqueness, coverage, and every dataset's complete application/scope-review/
  target-intake/applied-mapping lineage in acknowledgement summary and config.
  Any target signal must satisfy the strict one-distinct-application-per-dataset
  contract, retain the affirmative sender lineage decision and final consistency,
  and match the current, broker-final, scale-up-, cutover-, route-, dispatch-, and
  send-carried digests. Reconciliation still independently recomputes the
  eighth canonical compatibility digest from the acknowledgement-carried
  datasets. Reconciled targets additionally require send preparation's complete
  fifteen-view final comparison. Acknowledgement reconciliation revalidates the
  current, broker-final, historical scale-up-, cutover-, route-, dispatch-,
  send-, ack-, final-review-, readiness-, scale-up-review-, cutover-review-,
  route-enable-review-, dispatch-plan-review-, and send-packet-review-carried
  digests, then independently recomputes the canonical digest as view sixteen.
  The existing eight-view comparison remains unchanged in the flattened summary
  and
  `ack_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`
  config block for broker-dispatch round-trip compatibility. The complete
  sixteen-view handoff is retained in flattened summary fields and the sibling
  `ack_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`
  config block. Acknowledgement reconciliation deliberately continues to
  consume send preparation's fifteen-view compatibility key and ignores the new
  twenty-three-view `send_final_*` sibling until its own contract is upgraded.
  Legacy draft-backed and generic non-reconciled acknowledgement packets remain
  compatible; thin reconciled-target sidecars fail closed until send preparation
  supplies the complete fifteen-view comparison.
- Final broker dispatch round-trip review now reconciles that target proof
  across dispatch, send, and acknowledgement components before dry-run bridge
  evidence can be trusted. It retains mapping mode, application count,
  uniqueness, coverage, and the complete per-dataset lineage graph in final
  summary/config artifacts. Any target signal requires every component to keep
  strict mode, one unique application per dataset, full coverage, complete
  lineage, and the same canonical lineage graph. Final review also requires the
  acknowledgement-retained affirmative lineage decision and final consistency,
  checks the current, broker-final, scale-up-, cutover-, route-, dispatch-,
  send-, and acknowledgement-carried digests, then independently recomputes a
  ninth canonical compatibility digest from the datasets entering final review.
  Reconciled targets additionally require acknowledgement reconciliation's
  complete sixteen-view final comparison. Round-trip review revalidates the
  current, broker-final, historical scale-up-, cutover-, route-, dispatch-,
  send-, ack-, final-review-, readiness-, scale-up-review-, cutover-review-,
  route-enable-review-, dispatch-plan-review-, send-packet-review-, and
  acknowledgement-reconciliation-review-carried digests, then independently
  recomputes the canonical digest as view seventeen. The existing nine-view
  comparison remains unchanged in the flattened summary and
  `roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`
  config block for broker-readiness compatibility. The complete seventeen-view
  handoff is retained in flattened summary fields and the sibling
  `roundtrip_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`
  config block. Legacy draft-backed and generic non-reconciled final reviews
  remain compatible; thin reconciled-target sidecars fail closed until
  acknowledgement reconciliation supplies the complete final comparison.
- Broker readiness now consumes the final reconciliation's complete nine-view
  target-application lineage handoff. Nested final config and flattened final
  summary inputs retain the required/matches decision, current and broker-final
  digests, and every scale-up-, cutover-, route-, dispatch-, send-, ack-, and
  final-review-carried digest. Readiness verifies the final batch's declared
  digest, then independently canonicalizes its datasets as a tenth compatibility
  view. Reconciled targets additionally require round-trip review's complete
  seventeen-view final comparison. Broker readiness revalidates the current,
  broker-final, historical scale-up-, cutover-, route-, dispatch-, send-, ack-,
  final-review-, readiness-, scale-up-review-, cutover-review-,
  route-enable-review-, dispatch-plan-review-, send-packet-review-,
  acknowledgement-reconciliation-review-, and roundtrip-final-review-carried
  digests, then independently recomputes the canonical digest as view eighteen.
  The existing ten-view comparison remains unchanged in summary fields and the
  `broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`
  config block for controlled scale-up compatibility. The complete
  eighteen-view handoff is retained in flattened summary fields and the sibling
  `broker_readiness_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`
  block under `dispatch_roundtrip`. Missing or negative decisions, blank or
  mismatched carried views, and post-final dataset drift fail closed. Direct
  generic onboarding proof and legacy draft-backed batches retain their
  compatibility paths and do not claim final reconciliation.
- Broker readiness and the combined broker-vendor wrapper now bind the current
  vendor batch to that final target proof. Supplying a fresh vendor artifact no
  longer shadows stronger broker-specific round-trip evidence. When current and
  final proof are both active and either one signals target mode, readiness
  canonicalizes each dataset's immutable source, mapping, scope-review,
  target-intake, and applied-mapping identities, records both SHA-256 digests,
  and fails closed unless they match. This rejects target-to-draft downgrades as
  well. The wrapper surfaces the final consistency decision and current/final
  match in its summary, config, checks, and operator runbook.

## Test Gate

Run from repo root:

```powershell
pytest
```

Current collected suite: 1956 tests. Last completed full-suite baseline: 1110
passing tests; the suite has grown materially since that baseline.

Latest broker-dispatch-send final target-lineage gate: all 79 send-preparation
tests and all 58 acknowledgement tests pass. Reconciled targets must now supply
broker dispatch's complete twenty-two-view proof; send preparation revalidates
every historical stage and review digest, binds it to the established
fifteen-view compatibility path, and independently recomputes view twenty-three.
Missing or negative proof, inherited-view drift, compatibility-anchor drift,
dispatch-final-review drift, and post-dispatch dataset drift all fail closed.
The established fifteen-view send key remains unchanged for acknowledgement
reconciliation, and a distinct-digest regression proves the new
twenty-three-view sibling is not substituted early. The full 564-test
broker-readiness -> scale-up -> cutover -> route-enable -> broker-dispatch ->
broker-dispatch-send -> broker-dispatch-acknowledgement ->
broker-dispatch-roundtrip chain passes in 320.3 seconds. The repository now
collects 1956 tests across 154 files. The full suite was not rerun for this
slice; the last completed full-suite baseline remains unchanged.

Latest broker-dispatch final target-lineage gate: all 67 broker-dispatch tests
and all 73 broker-dispatch-send tests pass. Reconciled targets must now supply
route enable's complete twenty-one-view proof; dispatch planning revalidates
every historical stage and review digest, binds it to the established
fourteen-view compatibility path, and independently recomputes view twenty-two.
Missing or negative proof, inherited-view drift, compatibility-anchor drift,
route-final-review drift, and post-route dataset drift all fail closed. The
established fourteen-view dispatch key remains unchanged for send preparation,
and a distinct-digest regression proves the new twenty-two-view sibling is not
substituted early. The full 557-test broker-readiness -> scale-up -> cutover ->
route-enable -> broker-dispatch -> broker-dispatch-send ->
broker-dispatch-acknowledgement -> broker-dispatch-roundtrip chain passes in
394 seconds. The repository now collects 1949 tests across 154 files. The full
suite was not rerun for this slice; the last completed full-suite baseline
remains unchanged.

Latest route-enable final target-lineage gate: all 66 route-enable tests pass.
Reconciled targets must now supply cutover's complete twenty-view proof; route
enable revalidates every historical stage and review digest, binds it to the
existing thirteen-view compatibility path, and independently recomputes view
twenty-one. Missing or negative proof, inherited-view drift,
compatibility-anchor drift, cutover-final-review drift, and post-cutover dataset
drift all fail closed. The established thirteen-view route key remains
unchanged for broker dispatch, and all 61 broker-dispatch tests pass, including
a distinct-digest regression proving the new twenty-one-view sibling is not
substituted early. The full 550-test broker-readiness -> scale-up -> cutover ->
route-enable -> broker-dispatch -> broker-dispatch-send ->
broker-dispatch-acknowledgement -> broker-dispatch-roundtrip chain passes in
541 seconds. The repository now collects 1942 tests across 154 files. The full
suite was not rerun for this slice; the last completed full-suite baseline
remains unchanged.

Latest cutover final target-lineage gate: all 63 cutover tests pass. Reconciled
targets must now supply scale-up's complete nineteen-view proof; cutover
revalidates every historical stage and review digest, binds it to the existing
twelve-view compatibility anchor, and independently recomputes view twenty.
Missing or negative proof, inherited-view drift, compatibility-anchor drift,
scale-up-final-review drift, and post-scale-up dataset drift all fail closed.
Broker-readiness sidecars may hydrate the underlying target batch but cannot
manufacture scale-up's final review. The established twelve-view cutover key
remains unchanged for route enable, and all 60 route-enable tests pass,
including a distinct-digest regression proving the new twenty-view sibling is
not substituted early. The full 543-test broker-readiness -> scale-up ->
cutover -> route-enable -> broker-dispatch -> broker-dispatch-send ->
broker-dispatch-acknowledgement -> broker-dispatch-roundtrip chain passes in
595 seconds. The repository now collects 1935 tests across 154 files. The full
suite was not rerun for this slice; the last completed full-suite baseline
remains unchanged.

Latest controlled scale-up final target-lineage gate: all 98 scale-up tests
pass, including nested broker-readiness config and flattened readiness-summary
recovery of the complete eighteen-view handoff; mandatory final comparison for
reconciled targets; independent nineteenth-view recomputation; missing,
negative, inherited-digest, readiness-review-digest, and post-readiness dataset
drift rejection; and generic non-reconciled target/draft compatibility. The
historical eleven-view scale-up comparison remains unchanged for cutover, while
the complete nineteen-view handoff is emitted under the sibling
`scaleup_final_*` comparison. All 57 cutover tests pass, including a
distinct-digest regression proving cutover continues to consume only the
compatibility key. The full 536-test broker-readiness -> scale-up -> cutover ->
route-enable -> broker-dispatch -> broker-dispatch-send ->
broker-dispatch-acknowledgement -> broker-dispatch-roundtrip chain passes in
350.5 seconds. The repository now collects 1928 tests across 154 files. The
full suite was not rerun for this slice; the last completed full-suite baseline
remains unchanged.

Latest broker-readiness final target-lineage gate: all 79 broker-readiness
tests pass, including nested roundtrip config and flattened roundtrip-summary
recovery of the complete seventeen-view handoff; mandatory final comparison
for reconciled targets; independent eighteenth-view recomputation; missing,
negative, inherited-digest, roundtrip-review-digest, and post-roundtrip dataset
drift rejection; and generic non-reconciled target/draft compatibility. The
historical ten-view readiness comparison remains unchanged for controlled
scale-up consumption, while the complete eighteen-view handoff is emitted under
the sibling `broker_readiness_final_*` comparison. All 92 scale-up tests pass,
including a distinct-digest compatibility regression. The full 529-test
broker-readiness -> scale-up -> cutover -> route-enable -> broker-dispatch ->
broker-dispatch-send -> broker-dispatch-acknowledgement ->
broker-dispatch-roundtrip chain passes in 325.2 seconds. The repository now
collects 1921 tests across 154 files. The full suite was not rerun for this
slice; the last completed full-suite baseline remains unchanged.

Latest broker-dispatch-roundtrip final target-lineage gate: all 54 roundtrip
tests pass, including nested acknowledgement config and flattened
acknowledgement-summary recovery of the complete sixteen-view handoff;
mandatory final comparison for reconciled targets; independent seventeenth-view
recomputation; missing, negative, inherited-digest,
acknowledgement-review-digest, and post-ack dataset drift rejection; and generic
non-reconciled target/draft compatibility. The historical nine-view roundtrip
comparison remains unchanged for broker-readiness consumption, while the
complete seventeen-view handoff is emitted under the sibling
`roundtrip_final_*` comparison. All 73 broker-readiness tests pass, including a
distinct-digest compatibility regression. The full 522-test broker-readiness ->
scale-up -> cutover -> route-enable -> broker-dispatch -> broker-dispatch-send
-> broker-dispatch-acknowledgement -> broker-dispatch-roundtrip chain passes in
327.4 seconds. The repository now collects 1914 tests across 154 files. The
full suite was not rerun for this slice; the last completed full-suite baseline
remains unchanged.

Latest broker-dispatch-acknowledgement final target-lineage gate: all 57
acknowledgement tests pass, including nested sender-config and flattened
dispatch-summary recovery of the complete fifteen-view handoff; mandatory final
comparison for reconciled targets; independent sixteenth-view recomputation;
missing, negative, inherited-digest, fresh-ack-digest, and post-send dataset
drift rejection; and generic non-reconciled target/draft compatibility. The
historical eight-view acknowledgement comparison remains byte-for-byte
compatible for broker-dispatch round-trip consumption, while the complete
sixteen-view handoff is emitted under the sibling `ack_final_*` comparison.
The full 467-test broker-readiness -> scale-up -> cutover -> route-enable ->
broker-dispatch -> broker-dispatch-send -> broker-dispatch-acknowledgement chain
passes in 303.7 seconds. All 47 broker-dispatch round-trip tests pass against
the compatibility handoff. The repository now collects 1906 tests across 154
files. The full suite was not rerun for this slice; the last completed
full-suite baseline remains unchanged.

Latest broker-dispatch-send final target-lineage gate: all 72 send-preparation
tests pass, including nested dispatch config and flattened dispatch-summary
recovery of the full fourteen-view handoff; mandatory final comparison for
reconciled targets; independent fifteenth-view recomputation; missing,
negative, inherited-digest, and post-dispatch dataset drift rejection; and
generic non-reconciled target/draft compatibility. The complete 410-test
broker-readiness -> scale-up -> cutover -> route-enable -> broker-dispatch ->
broker-dispatch-send lineage chain passes in 280.1 seconds. All 182
broker-dispatch planning, send, and acknowledgement tests pass in 143.5 seconds,
including a distinct-digest compatibility regression that prevents
acknowledgement's legacy parser from confusing the historical send view with
send preparation's new review view. The repository now collects 1898 tests
across 154 files. The full suite was not rerun for this slice; the preceding
complete-suite attempt reached the 30-minute command limit without emitting a
failure, so the last completed full-suite baseline remains unchanged.

Latest cutover final target-lineage gate: all 56 cutover tests pass, including
nested scale-up config, flattened scale-up summary, and broker-readiness
sidecar recovery of the full eleven-view handoff; mandatory final comparison
for reconciled targets; independent twelfth-view recomputation; missing,
negative, carried-digest, and post-scale-up dataset drift rejection; and
generic non-reconciled target/draft compatibility.

Latest controlled scale-up final target-lineage gate: all 91 scale-up tests
pass, including rich-summary and broker-readiness-sidecar recovery of the full
ten-view decision, mandatory final comparison for reconciled targets,
independent eleventh-view recomputation, negative decision and carried-digest
drift rejection, and generic target/draft compatibility. The repository now
collects 1867 tests across 154 files; the full suite was not rerun for this
slice.

Latest broker-readiness final target-lineage gate: all 72 broker-readiness
tests pass, including nested-config and flattened-summary recovery of the final
nine-view decision, mandatory final comparison, declared-digest validation,
independent tenth-view recomputation, current/final drift rejection, and generic
target/draft compatibility. All 7 combined broker-vendor readiness tests and
all 46 final round-trip producer tests pass against the stronger handoff. The
repository now collects 1860 tests across 154 files; the full suite was not
rerun for this slice.

Latest broker-dispatch final-roundtrip target-lineage gate: all 46 final-review
tests pass, including rich acknowledgement comparison and flattened summary
recovery, nine-view digest retention, mandatory final consistency, independent
final canonical recomputation, legacy draft-sidecar compatibility, fail-closed
thin target handling, and rejection of negative acknowledgement decisions or
post-ack dataset drift. The full 95-test acknowledgement/final-review chain and
the 79-test broker-readiness/wrapper chain pass against the richer final config.
The repository now collects 1860 tests across 154 files; the full suite was not
rerun for this slice.

Latest broker-dispatch acknowledgement target-lineage gate: all 49
acknowledgement reconciliation tests pass, including rich sender comparison and
flattened dispatch-summary recovery, eight-view digest retention, mandatory
final consistency, independent acknowledgement canonical recomputation, legacy
draft-sidecar compatibility, fail-closed thin target-sidecar handling, and
rejection of post-send dataset or retained-decision drift. All 64 sender tests
and all 46 final round-trip tests pass against the richer acknowledgement
contract, including direct sender-config overlay precedence. The repository now
collects 1854 tests across 154 files; the full suite was not rerun for this
slice.

Latest broker-dispatch sender target-lineage gate: all 64 sender tests pass,
including rich dispatch config and flattened summary recovery, seven-view digest
retention, final consistency carry, independent send canonical recomputation,
legacy draft-sidecar compatibility, fail-closed target-sidecar handling, and
rejection of carried dataset or dispatch-decision drift. All 49 acknowledgement
reconciliation tests and all 41 final round-trip tests pass against the richer
sender config. The repository now collects 1849 tests across 154 files; the full
suite was not rerun for this slice.

Latest broker-dispatch target-lineage gate: all 52 dispatch-planning tests pass,
including rich route config and flattened summary recovery, six-view digest
retention, final consistency carry, independent dispatch canonical
recomputation, legacy sidecar compatibility, fail-closed target-sidecar
handling, and rejection of carried dataset or route-decision drift. All 59
sender tests pass against the richer dispatch config. The repository now
collects 1838 tests across 154 files; the full suite was not rerun for this
slice.

Latest route-enable target-lineage gate: all 52 route-enable tests pass,
including rich cutover config and flattened summary recovery, five-view digest
retention, final consistency carry, independent route canonical recomputation,
legacy sidecar compatibility, fail-closed target-sidecar handling, and rejection
of carried dataset or cutover-decision drift. The full 148-test cutover,
route-enable, and broker-dispatch planning chain passes. The repository now
collects 1833 tests across 154 files; the full suite was not rerun for this
slice.

Latest cutover target-lineage gate: all 49 cutover tests pass, including rich
scale-up config, flattened summary, and broker-readiness sidecar recovery;
final consistency and current/final decision carry; upstream digest checks;
independent cutover canonical recomputation; and fail-closed rejection of
carried dataset drift despite unchanged upstream success flags.

Latest controlled scale-up target-lineage gate: all 84 scale-up tests pass,
including broker-readiness sidecar hydration, final consistency carry, exact
current/final digest agreement, canonical carried-batch recomputation, and
fail-closed rejection when carried application identity drifts despite upstream
success flags. All 47 then-current cutover tests passed against the richer
scale-up config.
The repository now collects 1826 tests across 154 files; the full suite was not
rerun for this slice.

Latest current-to-final target-lineage gate: all 66 broker-readiness tests pass,
including stronger-proof precedence, canonical lineage digest equality, and
fail-closed rejection when the final batch refers to a different mapping
application. All 7 combined broker vendor-data readiness tests pass with the
final consistency and current/final match surfaced at the wrapper root, and all
41 final broker round-trip tests pass against the handoff. The repository now
collects 1824 tests across 154 files; the full suite was not rerun for this
slice.

Latest target-application final broker round-trip gate: all 41 final-review
tests pass, including nested component config, flattened component-summary
recovery, broker-readiness sidecar hydration, complete aggregate and
per-dataset lineage, exact canonical lineage agreement across dispatch/send/ack,
and fail-closed rejection of downgraded, incomplete, or drifted application
proof. All 7 broker vendor-data readiness tests and all 60 broker-readiness
tests also pass against the richer final contract. The repository now collects
1818 tests across 154 files; the full suite was not rerun for this slice.

Latest target-application broker-dispatch acknowledgement gate: all 43
acknowledgement reconciliation tests pass, including nested dispatch config,
flattened dispatch summary recovery, broker-readiness sidecar hydration,
complete aggregate and per-dataset lineage, and fail-closed rejection of
downgraded or incomplete application proof. All 38 final round-trip tests also
pass against the richer acknowledgement config. The repository now collects
1815 tests across 154 files; the full suite was not rerun for this slice.

Latest target-application broker-dispatch send gate: all 59 sender tests pass,
including nested dispatch config, flattened dispatch summary recovery,
broker-readiness sidecar hydration, complete aggregate and per-dataset lineage,
and fail-closed rejection of downgraded or incomplete application proof. All 40
acknowledgement reconciliation tests also pass against the richer send config.
The repository now collects 1812 tests across 154 files; the full suite was not
rerun for this slice.

Latest target-application broker-dispatch planning gate: all 47 planning tests
pass, including nested route config, flattened route summary recovery,
broker-readiness sidecar hydration, complete aggregate and per-dataset lineage,
and fail-closed rejection of downgraded or incomplete application proof. All 56
broker-dispatch sender tests also pass against the richer plan config. The
repository now collects 1809 tests across 154 files; the full suite was not
rerun for this slice.

Latest target-application route-enable gate: all 47 route-enable tests pass,
including current cutover config, flattened cutover summary recovery,
broker-readiness sidecar hydration, complete aggregate and per-dataset lineage,
and fail-closed rejection of incomplete application proof. All 178 broker
dispatch planning, send, acknowledgement, and round-trip tests also pass
against the richer route packet. The repository now collects 1806 tests across
154 files; the full suite was not rerun for this slice.

Latest target-application cutover gate: all 47 cutover tests pass, including
nested scale-up config, flattened summary fallback, broker-sidecar hydration,
aggregate and per-dataset lineage retention, and fail-closed rejection of a
downgraded or incomplete target batch. All 44 route-enable tests also pass
against the richer cutover config. The repository now collects 1803 tests
across 154 files; the full suite was not rerun for this slice.

Latest target-application controlled scale-up gate: all 82 scale-up tests pass,
including rich-summary and thin-sidecar hydration, aggregate
mode/count/uniqueness/coverage retention, complete per-dataset lineage, and
fail-closed rejection of partial or downgraded application proof. The adjacent
broker-vendor readiness, broker readiness, cutover, and route-enable suites
pass together (`155 passed`). The repository now collects 1800 tests across
154 files; the full suite was not rerun for this slice.

Latest combined target-application broker handoff gate: all seven
broker-vendor readiness tests pass, including API and repeated CLI application
alignment, broker-side mode/count/uniqueness/coverage retention, complete
per-dataset lineage checks, direct wrapper manifest dependencies, and
fail-before-root refusal for count mismatch and swapped targets. Broker
readiness, broker-vendor readiness, and vendor onboarding pass together (`81
passed`). The expanded intake, mapping-review, scope-review,
target-application, reviewed and target-applied normalization, readiness,
comparison, mapped-data, onboarding, catalog, manifest, broker-vendor,
broker-readiness, and shared CLI surface passes together (`249 passed`). The
repository now collects 1798 tests across 154 files; the full suite was not
rerun for this slice.

Latest per-dataset target-application batch gate: all 14 vendor onboarding
tests pass. The new focused cases cover two distinct target files sharing one
approved exact-header scope through separate applications, strict readiness,
CLI argument alignment, root manifest/config/runbook lineage, and preflight
refusal for count mismatch, mixed modes, swapped or duplicate
applications, colliding labels, and evidence-path overlap. The expanded intake,
mapping-review, scope-review, target-application, reviewed and target-applied
normalization, readiness, comparison, mapped-data, onboarding, catalog,
manifest, broker-vendor, broker-readiness, and shared CLI surface passes
together (`236 passed`). The repository now collects 1796 tests across 154
files; the full suite was not rerun for this slice.

Latest target-application onboarding gate: all 12 focused onboarding tests
pass, including normal and opaque-header target applications, strict readiness,
CLI execution, root lineage retention, mapping-mode exclusivity, exact-source
and adapter/kind binding, evidence-path isolation, and stale-source refusal.
The full affected intake, mapping-review, scope-review, target-application,
reviewed and target-applied normalization, data-readiness, comparison, mapped
data, onboarding, catalog, manifest, broker-vendor, and shared CLI surface
passes together (`174 passed`). The repository now collects 1794 tests across
154 files; the full suite was not rerun for this slice.

Latest target-applied normalization gate: all 10 focused adversarial tests pass.
The affected target normalization, data-readiness, mapped-data, intake,
mapping-review, scope-review, target-application, reviewed-normalization,
vendor-onboarding, catalog, manifest, and shared CLI suites pass together
(`168 passed`). Coverage includes
different-file and opaque-header normalization, write-once/path isolation,
strict CLI and readiness behavior, catalog classification, mutually exclusive
strict readiness contracts, target-source and upstream scope drift, and
verified blocked data-quality evidence, plus re-manifested normalized-data or
authority tampering. The repository now collects 1791 tests across 154 files;
the full suite was not rerun for this
slice.

Latest target mapping-application gate: all 11 focused adversarial tests pass.
The affected intake, mapping-review, scope-review, target-application,
reviewed-normalization, vendor onboarding, catalog, manifest, and shared CLI
surface passes together (`128 passed`). Coverage includes different-day exact
headers, ordered-column mismatch, adapter/kind substitution, approved manual
mapping over opaque blocked inference, rejected scope refusal, source and
upstream decision drift, byte-preserving output, strict CLI behavior, catalog
states, write-once/path isolation, and re-manifested mapping or normalization
authority tampering. The repository now collects 1781 tests across 153 files;
the full suite was not rerun for this slice.

Latest exact-header mapping-scope gate: all 11 focused adversarial tests pass.
The affected intake, mapping-review, reviewed-normalization, mapped-data,
vendor/provider onboarding, market-data, data-readiness, catalog, manifest,
shared CLI, and broker-vendor surface passes together (`166 passed`). Coverage
includes approved and rejected write-once seals, strict CLI exit behavior,
exact review/mapping/header/adapter/kind binding, complete cross-file semantic
attestations, byte-identical mapping retention, upstream source and decision
drift, path collisions, catalog states, and re-manifested authority widening.
The repository now collects 1770 tests across 152 files; the full suite was not
rerun for this slice.

Latest review-bound onboarding/readiness gate: the strict readiness, exact-source
pipeline, and reviewed-normalization suites pass together (`40 passed`). The
broader intake, mapping review, mapped data, vendor/provider onboarding,
readiness comparison, schema audit, shared CLI, catalog, manifest, and
broker-vendor surface passes together (`160 passed`). Coverage includes
explicit safety-claim parsing, SHA-256 provenance checks, intake-to-normalized
source consistency, exact source/adapter/kind enforcement before output,
mutually exclusive mapping inputs, strict CLI handoff, missing/loose evidence
repair routing, and an operator-approved manual mapping that supersedes blocked
column inference without weakening the source binding. The repository now
collects 1759 tests across 151 files; the full suite was not rerun for that
slice.

Latest reviewed-normalization gate: all seven focused adversarial tests pass.
The full affected mapping-review, normalization, intake, onboarding,
market-data, data-readiness, catalog, manifest, shared adapter/CLI, and
broker-vendor surface passes together (`138 passed`). Coverage includes
approved-only execution, derived source/mapping/adapter/kind identity,
write-once output, strict writer and verifier exit codes, valid blocked data
quality, rejected-review refusal, source drift, re-manifested normalized-output
tampering, path collision and traversal rejection, and ready/blocked/stale
catalog states.

Latest vendor-mapping review gate: all eight focused adversarial tests pass.
The broader intake, mapping, onboarding, market-data, data-readiness, catalog,
manifest, shared adapter/CLI, and broker-vendor surface passes together (`131
passed`). This covers approved and rejected seals, exact operator/source/hash
bindings, opaque provider columns, invalid approval, unknown operator claims,
write-once output, strict CLI behavior, upstream source drift, re-manifested
candidate tampering, and approved/rejected/stale catalog states. Real
Arrow.money/iRage schema approval remains intentionally blocked on retained
vendor documentation and an operator decision; no vendor columns or semantics
were invented.

Latest vendor-intake integrity gate: legacy and adversarial intake/catalog
coverage passes together (`12 passed`), including write-once output, strict CLI
verification, valid blocked evidence, source drift, and freshly re-manifested
mapping tampering. The complete vendor intake/onboarding/market-data chain
passes (`21 passed`); catalog, manifest, and data-readiness regressions pass
(`97 passed`); shared adapter/CLI and broker-vendor readiness pass (`8 passed`).

Latest completed strategy-evidence read-verification gate: strategy evidence,
shared manifests, and experiment catalog pass together (`127 passed`). It
recomputes completed evidence from retained sources, validates all persisted
tables and manifest metadata, exposes strict CLI status, and prevents a stale
provider evidence root from remaining ready when recataloged. The provider
threshold contract keeps this gate mandatory even if mutable profile/metadata
labels are changed together. The real 13-stage clean/deep-drift replay passes
separately (`1 passed`).

Latest provider release-review gate: strategy evidence, shared manifests, and
experiment catalog pass together (`127 passed`). It covers packet preparation,
CLI verification, catalog recognition, exact retained hashes, pending approval,
non-submitting safety fields, direct audit/certificate drift, an out-of-tree
recursive certificate dependency change that leaves the top evidence manifest
current, and a fresh re-manifest after an injected authorization claim.

Latest provider release-decision gate: approved and rejected seals, exact
packet/proof/operator binding, strict UTC and risk/kill-switch/rollback
attestations, write-once output, CLI verification, catalog status/counts,
re-manifested decision authorization tamper, operator-file drift, and direct
plus recursive retained-proof drift pass in both provider evidence variants
(`2 passed`). The full affected evidence/manifest/catalog surface passes
together (`127 passed`).

Latest controlled live-dry-run handoff gate: approved-decision-only creation,
exact provider/session/risk/kill-switch/rollback bindings, credential-bearing
key rejection, finite exact-integer limit enforcement, write-once output, CLI
verification, catalog status/counts, re-manifested authorization tamper,
controls and rollback drift, and direct plus recursive retained-proof drift pass
in both provider evidence variants (`2 passed`).

Latest controlled runtime-preflight gate: the provider-neutral connectivity
boundary passes secure endpoint, query-free URI, credential-presence-only,
backend failure, exception redaction, invalid outcome, and provider-scoped
configuration tests (`11 passed`). Both complete retained-proof variants pass
ready and blocked receipt creation, CLI verification, catalog semantics,
write-once output, credential-value absence, re-manifested authorization tamper,
runtime-profile drift, and direct plus recursive source drift (`2 passed`).
Shared manifest and experiment-catalog compatibility pass together (`68
passed`), and all other strategy-evidence compatibility paths pass (`57
passed`). The affected surface therefore totals `138 passed` across split
batches; the split avoids the local Windows command-host ceiling without
omitting any collected case in those files.

Latest bounded runtime-launcher gate: deterministic market-data generation,
session bounds, first-breach kill-switch behavior, write-once artifacts,
semantic reconstruction, CLI exit semantics, catalog completed/halted/stale
states, re-manifested authorization tamper, source drift, and ambient-capability
import audits pass together (`17 passed`). Both retained-proof variants pass
the full CLI/catalog/write-once/credential-absence/direct-and-recursive-drift
chain (`2 passed`). Shared manifest/catalog compatibility passes (`68 passed`)
and the complete strategy-evidence file passes (`59 passed`), for a green
affected surface of `144 passed` across split batches.

Latest bounded shadow-evaluator gate: engine-independent microprice semantics,
deterministic long/flat/short/flat intent cycles, retained order/notional/
position limits, an always-zero open-order invariant, terminal flattening,
kill-switch halts, strict telemetry validation, write-once artifacts, semantic
reconstruction, CLI exit behavior, catalog completed/halted/stale states,
authorization tamper, recursive source drift, and direct capability audits pass
together (`49 passed`). Both retained-proof variants pass the complete
release-to-shadow chain inside the green complete strategy-evidence suite (`59
passed`), and shared manifest/catalog compatibility passes (`68 passed`). The
non-overlapping affected surface is therefore `176 passed`.

Latest shadow markout-calibration gate: exact feature/intent binding,
directional mid and microprice response, executable-touch markout, adverse
selection, bounded horizon coverage, repository-reference futures/options cost
sensitivity, completed and insufficient outcomes, write-once artifacts,
semantic reconstruction, strict CLI exits, catalog completed/insufficient/stale
states, re-manifested authorization tamper, recursive source drift, and direct
capability audits pass together (`23 passed`). Both retained-proof variants
pass inside the complete strategy-evidence suite (`59 passed`), and shared
manifest/catalog compatibility passes (`68 passed`). The non-overlapping
affected surface is therefore `199 passed`. The cost schedules remain
explicitly subject to external validation, and no result is a performance,
promotion, routing, or submission gate.

Latest multi-session shadow calibration-stability gate: distinct session and
receipt identity, exact runtime/config/evidence-class contracts, complete
horizon and reference-cost grids, bounded coverage/directional/adverse-
selection/cost dispersion, stable and verified-unstable outcomes, write-once
artifacts, deterministic reconstruction, strict CLI exits, catalog
stable/unstable/stale states, re-manifested authorization tamper, recursive
launcher-telemetry drift, and direct capability audits pass together (`22
passed`). The complete runtime-to-cohort surface passes (`94 passed`), the
legacy shadow comparison plus shared manifest/catalog compatibility surface
passes (`81 passed`), and the complete retained strategy-evidence suite passes
(`59 passed`). The non-overlapping affected surface is therefore `234 passed`.
The cohort is simulation-only and cannot establish live edge or authorize
promotion, routing, submission, or release.

Latest active-lineage downstream affected-surface gate: strategy evidence,
strategy scorecard, generic route readiness, real provider route wrapper,
experiment catalog, complete lineage migration/convergence/index, and rehearsal
certificate suites pass together (`194 passed`).

Latest provider active-lineage runtime gate: generic/provider scale-up and
provider runtime telemetry/guard/session preserve one exact three-stage
contract; ready, absent, edited-summary, edited-config, edited-manifest,
sidecar-precedence, and sidecar-breach paths pass across focused batches (`15
passed`).

Latest provider active-lineage broker-boundary gate: broker readiness and
cutover preserve and verify the same exact contract; focused ready, route-less,
cross-artifact drift, sidecar-breach, and explicit-zero paths pass (`9 passed`).
Route enable and dry-run broker dispatch preserve and verify the contract at
the next two boundaries; focused ready, cross-artifact drift, sidecar-breach,
and route-less/unready paths pass (`8 passed`). The downstream non-submitting
send boundary now preserves and verifies the contract too; focused ready,
cross-artifact drift, sidecar-breach, and unready paths pass (`4 passed`). The
acknowledgement boundary now preserves and verifies the contract too; focused
ready, cross-artifact drift, sidecar-breach, and unready paths pass (`4
passed`). Final round-trip review now preserves and verifies the contract too;
focused ready, cross-artifact drift, sidecar-breach, and unready paths pass (`4
passed`). Rehearsal certification now independently reopens the final review,
requires exact summary/config/manifest contract agreement, and binds the
normalized seal into its hashed evidence; the strict ready and contract-drift
paths pass (`2 passed`) alongside all legacy certificate paths (`8 passed`).
The operator chain audit now closes all 13 provider boundaries from route
readiness through certification, independently verifies 65 recursive manifests
in the real strict fixture, and rejects intermediate runtime-guard contract drift
through both the Python and CLI surfaces (`1 passed`). Its read-side verifier
also recomputes that graph before catalog exposure; a selectable certificate
without the exact current audit is blocked, while the covered certificate is
selected with its audit digest and becomes invalid after the same upstream
drift (`1 passed`).

Latest operational affected-surface gate: controlled scale-up, generic runtime
telemetry/guard/session, halt response/export/execution/incident, cutover,
route-readiness, route-enable, broker dispatch planning/send/acknowledgement/final
round-trip review, and research-family registration/launch/audit pass together
(`468 passed`). It now
includes a real prospective-family chain through family audit -> scorecard ->
portfolio -> controlled scale-up -> runtime telemetry -> runtime guard ->
runtime session -> cutover -> route-enable -> dry-run broker dispatch planning ->
non-submitting send preparation -> acknowledgement reconciliation -> final
round-trip review, with recursive invalidation of all six final manifests after
registration-plan drift. Cutover, route-enable, dispatch, send, acknowledgement,
and final round-trip review also
reject stale source fingerprints, freshly re-manifested cross-artifact lineage
disagreement, authorizing claims, and source/output overlap while preserving
non-authorizing family identity through each broker-facing order/request/ack/final
proof row.
The four generic dispatch plan/send/ack/round-trip suites pass together
(`178 passed`), showing that the richer lineage contracts remain additive
for downstream workflows. The focused runtime-session, halt-response, and
research-family gate passes together (`29 passed`). It covers source-output
collision rejection,
non-authorizing lineage passthrough into session and emergency action rows,
recursive session/halt manifest invalidation after registration-plan drift,
and the deliberate ability to prepare emergency cancel/flatten actions even
when provenance itself is stale. Three provider-data imbalance runtime-session
integration paths also pass, covering the ready wrapper, capture-bundle
provenance, and post-guard adapter-receipt drift. The preceding affected-surface
gate for manifests, strategy scorecard/portfolio, research-family, controlled
scale-up, generic runtime telemetry/guard/session, and experiment catalog
passed together (`254 passed`). The generic runtime
telemetry/guard suites contribute `54 passed`, including missing/stale scale-up
manifest, semantic re-manifesting, authorizing source, output collision,
recursive input drift, and telemetry lineage mismatch rejection. The real
prospective-family chain now passes family audit -> scorecard -> portfolio ->
controlled scale-up -> runtime telemetry -> runtime guard -> runtime session ->
halt response, carries the exact
family/registration and portfolio/scorecard/family manifest hashes, halts on a
relabeled telemetry family, and invalidates telemetry/guard manifests plus
session/halt-response manifests, then halts the guard after registration-plan
drift. Six provider-data imbalance
telemetry/guard paths also pass, covering ready wrappers, CLI telemetry,
post-scale-up receipt drift, post-telemetry receipt drift, and route-sidecar
breach handling. Generic cutover and route-enable compatibility now pass
together (`88 passed`).
The immediately preceding manifest, strategy portfolio, strategy scorecard,
research-family, and controlled scale-up suites pass together (`126 passed`).
Controlled scale-up passes all `80` of its tests, including
current portfolio-manifest acceptance; missing manifest, allocation drift,
fresh-but-detached config, authorizing bundle, output collision, nested family
relabeling, and post-scale-up registration-source drift rejection. The real
prospective-family chain now passes family audit -> scorecard -> portfolio ->
controlled scale-up with recursively current manifests and a non-authorizing
900,000 INR session cap. Experiment-catalog compatibility also passes
(`63 passed`). The provider-data imbalance ready scale-up wrapper path passes
(`1 passed`). The
immediately preceding strategy portfolio, strategy scorecard, and research
family suites pass together (`41 passed`), including a real prospectively
registered family closure flowing through a current scorecard into a positive
paper/shadow allocation, plus missing-manifest, stale-artifact,
fresh-but-semantically-detached contract, family relabeling,
authorizing-source, strict CLI, output-collision, and post-allocation
family/nested-input-drift rejection. Scale-up and
experiment-catalog compatibility pass together (`138 passed`), and the
provider-data imbalance ready scorecard wrapper path also passes (`1 passed`).
The immediately preceding focused gate covered prospective family
registration/closure, declared
research-family, chronological holdout, multiple-testing-aware significance,
robust-selection, CSCV backtest-overfit, manifest-bound promotion, sweep
comparison, experiment catalog, manifest, and strategy scorecard suites pass
together (`141 passed`). This covers deterministic plan locking, immutable
registered-study launch contracts, exact contract execution, unique execution
receipts, hash-chained attempt records, attested latest-attempt retry policy,
duplicate/completed replay blocking, attempt-ledger tamper rejection, resolved
semantic-digest binding, hash-chained outcome finalization, exact result-hash
binding, interruption classification, attested unfinalized-result recovery,
duplicate/inconsistent recovery rejection, outcome-ledger tamper rejection,
family-closure attempt/outcome census generation, matrix/ledger count and
latest-pointer reconciliation, retry-visible interruption history, and explicit
zero-hypothesis accounting for exact operational retries,
automatic scorecard detection of registered robust research, current
family-manifest and registration-closure enforcement, exact surviving-candidate
strategy/market/scenario binding, missing/blocked/stale/mismatched family-proof
rejection, post-scorecard family-drift detection, and CLI fail-closed family
requirements,
launch-argument and semantic-drift rejection, mutable coverage refresh without
root invalidation, recursive
post-coverage result-drift detection, current sweep and result coverage,
never-launched blocking, attested reasoned abandonment, conservative abandoned
study accounting, direct registered-row and registration-manifest source binding, exact
family/label/path/contract closure, missing registration, post-hoc registration,
source-ID mismatch, and excess-search-breadth rejection, Holm correction,
failed-attempt accounting, complete-family attestation, malformed-p-value and
drift rejection, development/holdout isolation, frozen-candidate evaluation,
exact sign-test correction, deterministic bootstrap evidence, memorized and
underpowered orchestration, strict lineage, and CLI fail-closed behavior.
Strategy portfolio and experiment-catalog compatibility also pass together
(`72 passed`) with the expanded family-bound scorecard outputs.
The provider-imbalance ready scorecard wrapper compatibility path also passes
with the new family-proof passthrough (`1 passed`).
Manifest generation, the existing surface research/launch pipeline, and
generic launch-bundle compatibility also pass together (`14 passed`).
The immediately preceding CSCV backtest-overfit audit, manifest-bound
promotion, sweep comparison, surface-MM pipeline, experiment catalog, and
strategy scorecard suites pass together (`95 passed`). This covers stable and
partition-memorized grids, odd-period partitioning, rank-1 candidate stability,
CLI fail-closed behavior, audit artifact and source-selection drift, and strict
promotion enforcement. The immediately preceding manifest,
experiment-catalog, six provider broker-rehearsal certificate paths (validity,
determinism, recursive drift, relaxed submission/count thresholds, receipt
assurance, CLI, and catalog), and provider evidence/scorecard integration
suites pass together (`131 passed`). The immediately preceding four provider
broker-dispatch-roundtrip final receipt and
compatibility paths pass. Bundle-linked clean rehearsal-loop review and
post-acknowledgement manifest/receipt/capture drift pass together (`2 passed`);
no-provider-wrapper and provider-wrapper-without-required-receipts
compatibility also pass together (`2 passed`). The immediately preceding four
broker-dispatch-ack final-roundtrip, four broker-dispatch-send final-roundtrip,
four broker-dispatch final-roundtrip, four route-enable final-roundtrip, four
cutover final-roundtrip, four broker-readiness final-roundtrip, four earlier
broker-dispatch-roundtrip, four earlier broker-dispatch-ack, four earlier
broker-dispatch-send, four earlier broker-dispatch, four earlier route-enable,
four runtime-session broker-readiness, four runtime-session, four runtime-guard,
four runtime-telemetry, four scale-up, four scorecard, eight
launch/launch-evidence, and ten research/evidence receipt-boundary paths remain
green, as do the complete receipt-aware live-evidence plus research-handoff
suites (`25 passed`). The upstream provider-adapter/live-ingest (`22 passed`),
provider live rehearsal (`5 passed`), core engine/strategy semantics (`39
passed`), launch pipelines (`45 passed`), and provider
source/fetch/client/live-contract gates (`54 passed`) also remain green. A
focused provider acknowledgement strict-default run covering the real lineage
chain, blocked send, and both clean compatibility sidecars passes (`4 passed`).
A combined 14-case provider-imbalance wrapper run previously exceeded the
25-minute local timeout without returning a result, and the full-suite run
exceeded the 20-minute timeout on the G-drive workspace. Therefore 1110 remains
the last completed full-suite green baseline rather than claiming the current
1731-test collection is fully green.

## Next Build Targets

1. Add data adapters for the first real vendor export once files are available.
2. Replace placeholder Arrow.money/iRage column maps once real export schemas
   are available.
3. Replace the built-in upload review templates with broker-signed
   Arrow.money/iRage order schemas once sample files are available.
