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
  not secret values.
- Provider market-data client dry-run packets now close the backend data-source
  handoff before live credentials: `prepare-provider-market-data-client`
  validates ready request templates, env-var contracts, normalized CSV output
  schema, runtime budgets, carried blank env-template proof, and carried
  `live_fetch_contract`, then emits a manifest-backed execution packet for the
  eventual Arrow.money/iRage client without making external API calls.
- Provider market-data live session planning now creates credential-safe capture
  packets before the market opens: `plan-provider-market-data-live-session`
  validates the dry-run client packet, NSE session windows, weekday, optional
  runtime env-var presence, carried blank env-template proof, carried
  `live_fetch_contract`, carried exchange/segment plus source-session metadata
  matching the market profile, per-window capture paths, and emits the exact
  post-capture `pipeline-provider-market-data-batch` command. Live-session
  packets now also carry structured, non-secret provider capture command
  handoffs for each window: provider, transport, endpoint, env-var names,
  start/end, output path, and command template.
- Provider market-data live preflight now checks the planned provider capture
  just before the market run: `preflight-provider-market-data-live-session`
  validates the session packet, runtime credential env-var presence, carried
  blank env-template proof, carried `live_fetch_contract`, exchange/session
  metadata consistency, writable capture and batch paths, capture/batch
  collision risk, per-window provider capture command templates, and local
  clock timing without persisting credential values. The preflight config and
  manifest surface the provider capture command list for Arrow.money/iRage
  adapter execution, and fail closed if any capture window is missing it.
- Provider market-data live capture bundling now turns a ready preflight into
  a backend adapter handoff: `bundle-provider-market-data-live-capture` writes
  per-window capture commands, a credential-safe JSON bundle, a blank env-var
  template for provider credentials, a dedicated
  `provider_market_data_adapter_handoff.json` contract with schema columns and
  rendered commands, preflight-carried source env-template proof and
  `live_fetch_contract` provenance, inherited exchange/session metadata for the
  approved source, and the exact post-capture ingest command while blocking
  missing preflight evidence, metadata drift, and capture overwrite risk.
  Capture bundling now also requires the structured provider capture command
  handoff from both the live-session packet and preflight config to match,
  then carries that command list into the bundle, adapter handoff, and manifest
  for Arrow.money/iRage adapter execution audit.
  Default adapter commands now explicitly pass the handoff JSON and blank
  capture env-template file, so Arrow.money/iRage adapter processes receive
  the same contract artifacts the bundle manifests. Bundle summary/JSON,
  adapter handoff, and manifest extras now include capture env-template and
  adapter handoff SHA-256 values for direct provider handoff audit.
- Provider market-data live rehearsal now proves the backend handoff without
  provider credentials: `rehearse-provider-market-data-live-capture` writes
  explicitly marked synthetic normalized captures from the bundle, optionally
  runs live-session ingest, fingerprints the bundle credential env-template and
  adapter handoff contract when present, carries the source env-template proof
  and `live_fetch_contract`, and reports that the result is smoke-test evidence
  only until replaced by real Arrow.money/iRage captures.
- Provider market-data live session ingest now closes the post-market loop:
  `ingest-provider-market-data-live-session` reads the session packet, verifies
  all expected capture files exist and are non-empty, then runs the structured
  provider batch ingestion and manifests the resulting proof chain. When an
  approved capture bundle is supplied, ingest also fingerprints the bundle and
  its blank credential env-template plus adapter handoff contract artifacts,
  source env-template proof, exchange/session metadata matching the live packet,
  and `live_fetch_contract` for backend handoff provenance. Ingest and evidence
  summaries/configs now also carry the capture env-template and adapter handoff
  SHA-256 values directly, so provider credential-template and adapter-contract
  provenance are visible without parsing the manifest input block. Bundle-linked
  ingest now also verifies that provider capture command handoffs match the
  live-session packet and carries the structured command list into the ingest
  summary/config/manifest for downstream live-data audit.
- Provider market-data live evidence review now protects research handoff from
  rehearsal artifacts: `review-provider-market-data-live-evidence` verifies
  live ingest, batch readiness, capture row counts, manifest proof,
  capture-bundle/env-template/adapter-handoff provenance, source env-template
  proof, exchange/session metadata, and `live_fetch_contract` when supplied, and
  credential-safe session packets while blocking `*.csv.rehearsal.json`
  synthetic captures from being marked research-ready. Bundle-linked evidence
  review also carries provider capture command counts/lists from ingest into
  summary/config/manifest artifacts and blocks research handoff if the
  capture-bundle command list is missing or no longer matches the live-session
  packet.
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
  research if the capture-bundle command handoff is missing or mismatched.
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
  capture-bundle command match proof into the imbalance research layer.
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
  proof into the research-evidence package.
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
  packet.
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
- Provider market-data imbalance scale-up planning now preserves the same live
  adapter audit trail from the provider scorecard: the scale-up summary/config
  and manifest extras carry capture env-template and adapter handoff SHA-256
  values directly, carry provider capture command counts/lists plus
  capture-bundle command match proof from scorecard into scale-up planning, and
  manifest inputs fingerprint those files for iRage/live provider handoff
  review.
- Provider market-data imbalance runtime telemetry now keeps that live adapter
  audit trail intact after scale-up: runtime telemetry summary/config and
  manifest extras expose capture env-template and adapter handoff SHA-256
  values directly, carry provider capture command counts/lists plus
  capture-bundle command match proof from scale-up into runtime telemetry, and
  the manifest fingerprints the same files before runtime guard monitoring.
- Provider market-data imbalance runtime guard now preserves those adapter
  fingerprints through halt/continue monitoring: guard summary/config and
  manifest extras expose capture env-template and adapter handoff SHA-256
  values directly, carry provider capture command counts/lists plus
  capture-bundle command match proof from runtime telemetry into guard
  monitoring, and keep that proof visible before runtime session review.
- Provider market-data imbalance runtime session now carries the same adapter
  fingerprints into broker-readiness handoff: session summary/config and
  manifest extras expose capture env-template and adapter handoff SHA-256
  values directly.
- Provider market-data imbalance broker readiness now preserves those adapter
  fingerprints into broker handoff review: broker-readiness summary/config and
  manifest extras expose capture env-template and adapter handoff SHA-256
  values directly.
- Provider market-data imbalance cutover now keeps the same adapter
  fingerprints in the final pre-dispatch gate: cutover summary/config and
  manifest extras expose capture env-template and adapter handoff SHA-256
  values directly.
- Provider market-data imbalance route enable now preserves those adapter
  fingerprints into broker-dispatch authorization: route-enable summary/config
  and manifest extras expose capture env-template and adapter handoff SHA-256
  values directly.
- Provider market-data imbalance broker dispatch now keeps those adapter
  fingerprints in the dry-run dispatch planner: broker-dispatch summary/config
  and manifest extras expose capture env-template and adapter handoff SHA-256
  values directly.
- Provider market-data imbalance broker dispatch send now preserves those
  adapter fingerprints into the non-submitting sender packet: send
  summary/config and manifest extras expose capture env-template and adapter
  handoff SHA-256 values directly.
- Provider market-data imbalance broker dispatch acknowledgement now carries
  those adapter fingerprints into ack reconciliation: acknowledgement
  summary/config and manifest extras expose capture env-template and adapter
  handoff SHA-256 values directly.
- Provider market-data imbalance broker dispatch round-trip now preserves those
  adapter fingerprints into the final dry-run bridge proof: round-trip
  summary/config and manifest extras expose capture env-template and adapter
  handoff SHA-256 values directly.
- Provider market-data imbalance broker readiness now also keeps those final
  dry-run bridge fingerprints when dispatch round-trip proof is supplied:
  broker-readiness summary/config and manifest extras expose the
  dispatch-roundtrip capture env-template and adapter handoff SHA-256 values
  directly.
- Provider market-data imbalance cutover now carries those dispatch-roundtrip
  fingerprints forward from broker readiness: cutover summary/config and
  manifest extras expose the dispatch-roundtrip capture env-template and
  adapter handoff SHA-256 values directly.
- Provider market-data imbalance route enable now carries those
  dispatch-roundtrip fingerprints forward from cutover: route-enable
  summary/config and manifest extras expose the dispatch-roundtrip capture
  env-template and adapter handoff SHA-256 values directly.
- Provider market-data imbalance broker dispatch now carries those
  dispatch-roundtrip fingerprints forward from route enable: broker-dispatch
  summary/config and manifest extras expose the dispatch-roundtrip capture
  env-template and adapter handoff SHA-256 values directly.
- Provider market-data imbalance broker dispatch send now carries those
  dispatch-roundtrip fingerprints forward from broker dispatch:
  broker-dispatch-send summary/config and manifest extras expose the
  dispatch-roundtrip capture env-template and adapter handoff SHA-256 values
  directly.
- Provider market-data imbalance broker dispatch ack now carries those
  dispatch-roundtrip fingerprints forward from broker dispatch send:
  broker-dispatch-ack summary/config and manifest extras expose the
  dispatch-roundtrip capture env-template and adapter handoff SHA-256 values
  directly.
- Provider market-data imbalance broker dispatch round-trip now carries those
  dispatch-roundtrip fingerprints forward from broker dispatch ack:
  broker-dispatch-roundtrip summary/config and manifest extras expose the
  dispatch-roundtrip capture env-template and adapter handoff SHA-256 values
  directly.
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
  match proof, provider capture-command proof, and `live_fetch_contract` into
  provider summary/config/runbook
  artifacts plus manifest, writes provider
  checks/summary/action/config/runbook artifacts, and routes ready runs to
  `review-provider-market-data-imbalance-cutover`.
- Provider-data imbalance now has a provider cutover wrapper after provider
  broker-readiness. `review-provider-market-data-imbalance-cutover` infers
  nested generic scale-up, broker-readiness, and runtime-session evidence,
  reruns `review-cutover-gate` under a nested folder, carries capture
  bundle/env-template/adapter handoff provenance, source env-template proof,
  exchange/session metadata, capture-bundle session match proof, provider
  capture-command proof, and `live_fetch_contract` into provider
  summary/config/runbook artifacts plus manifest, preserves cutover safety
  blockers such as missing route-readiness proof, and routes fully clean runs to
  `review-route-enable`.
- Provider-data imbalance now has a provider route-enable wrapper after cutover.
  `review-provider-market-data-imbalance-route-enable` infers the nested generic
  cutover and broker upload/order-export inputs, reruns `review-route-enable`
  under a nested folder, carries capture bundle/env-template/adapter handoff
  provenance, source env-template proof, exchange/session metadata,
  capture-bundle session match proof, provider capture-command proof, and
  `live_fetch_contract` into provider summary/config/runbook artifacts plus
  manifest, writes provider
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
  summary/config/runbook artifacts plus manifest, writes provider
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
  summary/config/runbook artifacts plus manifest, writes provider
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
  provider summary/config/runbook artifacts plus manifest, writes provider
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
  summary/config/runbook artifacts plus manifest metadata, writes provider
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
  capture-bundle session match proof, and `live_fetch_contract` proof beside
  runtime-session provenance, fails closed if both sides provide conflicting
  file provenance or exchange/session/live-fetch identity, and keeps all proof
  roots, including the round-trip
  source credential env-template, in the manifest for audit.
- Provider-data imbalance cutover now carries that broker-dispatch round-trip
  audit trail forward from provider broker-readiness. The provider cutover
  summary/config/manifest preserve both the provider wrapper root and nested
  generic `broker_dispatch_roundtrip` path, broker-dispatch
  vendor-market-data batch proof, any upstream proof lineage, and upstream
  vendor-market-data batch lineage. It now also keeps the broker-readiness
  validated round-trip capture bundle/env-template/adapter handoff paths,
  source credential env-template proof, round-trip exchange/session metadata,
  capture-bundle session match proof, live-fetch exchange/session identity,
  `live_fetch_contract`, and
  provenance-consistency flags in summary/config/runbook/manifest artifacts so
  route-enable and later broker dispatch stages can trace the same proof chain
  before live-data dry-runs. Cutover now also hydrates missing or blank
  `dispatch_roundtrip_*` summary fields from broker-readiness
  `dispatch_roundtrip_provenance` config sidecars, while keeping explicit CSV
  `False` values authoritative, so mixed-version broker-readiness outputs still
  preserve the validated iRage/Arrow live-data handoff trail.
- Provider-data imbalance route-enable now preserves the cutover-carried
  provider broker-dispatch round-trip wrapper and nested generic
  `broker_dispatch_roundtrip` paths, broker-dispatch vendor-market-data batch
  proof, upstream proof lineage, and upstream vendor-market-data batch lineage
  in route-enable summary/config/manifest artifacts. It also carries the
  cutover-retained validated round-trip capture bundle/env-template/adapter
  handoff paths, source credential env-template proof, round-trip
  exchange/session metadata, capture-bundle session match proof, live-fetch
  exchange/session identity, `live_fetch_contract`, and provenance-consistency
  flags into summary/config/runbook artifacts plus manifest inputs/metadata,
  keeping dry-run broker proof visible through the handoff to provider
  broker-dispatch planning. Route-enable now also hydrates missing or blank
  cutover `dispatch_roundtrip_*` summary fields from the cutover
  `dispatch_roundtrip_provenance` config block before falling back to the
  broker-readiness config block, while preserving explicit summary `False`
  values, so sparse cutover CSVs do not lose the validated live-data handoff.
- Provider-data imbalance broker-dispatch now preserves the route-enable-carried
  provider broker-dispatch round-trip wrapper and nested generic
  `broker_dispatch_roundtrip` paths, broker-dispatch vendor-market-data batch
  proof, upstream proof lineage, and upstream vendor-market-data batch lineage
  in broker-dispatch summary/config/manifest artifacts. It also carries the
  route-enable-retained validated round-trip capture bundle/env-template/adapter
  handoff paths, source credential env-template proof, round-trip
  exchange/session metadata, capture-bundle session match proof, live-fetch
  exchange/session identity, `live_fetch_contract`, and source/capture
  provenance-consistency flags through summary/config/runbook artifacts plus
  manifest inputs/metadata before the non-submitting send packet is prepared.
  Broker-dispatch now also hydrates missing or blank route-enable
  `dispatch_roundtrip_*` summary fields from the route-enable
  `dispatch_roundtrip_provenance` config sidecar, while preserving explicit
  summary `False` values, so sparse route-enable CSVs do not lose the
  validated live-data handoff before send packet preparation.
- Provider-data imbalance broker-dispatch-send now preserves the same
  provider/nested broker-dispatch round-trip paths, broker-dispatch
  vendor-market-data batch proof, upstream proof lineage, and upstream
  vendor-market-data batch lineage in send summary/config/runbook artifacts
  and manifests. It now also carries the broker-dispatch-retained validated
  round-trip capture bundle/env-template/adapter handoff paths, source
  credential env-template proof, round-trip exchange/session metadata,
  capture-bundle session match proof, live-fetch exchange/session identity,
  `live_fetch_contract`, and source/capture provenance-consistency flags
  through send summary/config/runbook artifacts plus manifest inputs/metadata
  while still keeping `submission_enabled=false`. Broker-dispatch-send now also
  hydrates missing or blank broker-dispatch `dispatch_roundtrip_*` summary
  fields from the broker-dispatch `dispatch_roundtrip_provenance` config
  sidecar, while preserving explicit summary `False` values, so sparse
  broker-dispatch CSVs do not lose validated live-data provenance before
  dry-run request envelopes are produced.
- Provider-data imbalance broker-dispatch acknowledgement now preserves those
  provider/nested broker-dispatch round-trip paths, broker-dispatch
  vendor-market-data batch proof, upstream proof lineage, and upstream
  vendor-market-data batch lineage in acknowledgement summary/config/runbook
  artifacts and manifests. It now also carries the send-retained validated
  round-trip capture bundle/env-template/adapter handoff paths, source
  credential env-template proof, round-trip exchange/session metadata,
  capture-bundle session match proof, live-fetch exchange/session identity,
  `live_fetch_contract`, and source/capture provenance-consistency flags
  through acknowledgement summary/config/runbook artifacts plus manifest
  inputs/metadata before the final provider round-trip wrapper is trusted.
  Acknowledgement now also hydrates missing or blank send-packet
  `dispatch_roundtrip_*` summary fields from the send
  `dispatch_roundtrip_provenance` config sidecar, while preserving explicit
  summary `False` values, so sparse send CSVs do not lose validated live-data
  provenance before final round-trip review.
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
  capture-bundle session match proof, live-fetch exchange/session identity,
  `live_fetch_contract`, and source/capture provenance-consistency flags, in
  provider summary/config/runbook artifacts plus manifest inputs/extra
  metadata. The provider round-trip summary/config now also surfaces nested broker
  vendor-market-data batch proof under both
  `roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_*` and
  `broker_dispatch_roundtrip_vendor_market_data_batch_*` fields. The final
  provider round-trip wrapper now also hydrates missing or blank acknowledgement
  `dispatch_roundtrip_*` summary fields from the acknowledgement
  `dispatch_roundtrip_provenance` config sidecar, while preserving explicit
  summary `False` values, so sparse acknowledgement CSVs do not lose validated
  live-data provenance before broker-readiness promotion.
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

## Test Gate

Run from repo root:

```powershell
pytest
```

Current passing suite: 1110 tests.

Latest focused gate: provider route-readiness plus scale-up targeted tests pass
(`10 passed`), and the generic route-readiness suite passes (`8 passed`). A
single-file run of `tests/test_provider_market_data_imbalance_research.py`
exceeded the local timeout after this provider path work, so the full-suite
count above is left at the last completed full run.

## Next Build Targets

1. Add data adapters for the first real vendor export once files are available.
2. Replace placeholder Arrow.money/iRage column maps once real export schemas
   are available.
3. Replace the built-in upload review templates with broker-signed
   Arrow.money/iRage order schemas once sample files are available.
