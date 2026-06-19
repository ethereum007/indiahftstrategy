# Command Reference

Run commands from the repo root:

```powershell
cd "G:\HFT Testing Codex\india-hft-strategy"
python -m hft_cli <command> [args]
```

After installing the project, the console script is also available as `hft`.

## Input Schemas

Top-of-book futures/option CSV:

```text
ts,bid,ask,bid_qty,ask_qty,last,last_qty
```

Option-chain CSV:

```text
ts,expiry,strike,call_bid,call_ask,call_bid_qty,call_ask_qty,put_bid,put_ask,put_bid_qty,put_ask_qty
```

Calibration simulated orders:

```text
client_order_id,instrument_id,ts_sent_ns,side,qty,price
```

Calibration live fills:

```text
client_order_id,instrument_id,ts_fill_ns,side,qty,price
```

Timestamps are nanoseconds by default. Use `--no-filter-session` for synthetic
fixtures outside regular NSE session hours.

Replay, sweep, proof, and selection output folders include `manifest.json` with
run parameters, input hashes, output artifact hashes, git state, and runtime
package versions.

## Experiment Catalog

Collect manifest-bearing run folders into one evidence ledger:

```powershell
python -m hft_cli catalog-runs `
  --roots runs `
  --out runs\catalog\latest `
  --fail-on-catalog-gaps `
  --fail-on-blocked-actions
```

Outputs:

```text
experiment_catalog.csv
experiment_catalog_summary.csv
experiment_catalog_action_queue.csv
experiment_catalog_action_plan.json
experiment_catalog_hygiene_gaps.csv
experiment_catalog_runbook.md
manifest.json
```

The catalog includes input provenance counters for each run, including exact
file fingerprints, directory-tree fingerprints, hashed inputs, and
unfingerprinted raw inputs. Use these columns to spot broad or unresolved
handoffs before relying on a broker, scale-up, or live-dryrun evidence chain.
`experiment_catalog_summary.csv` also carries `action_queue_count`,
`action_queue_ready_count`, `action_queue_blocked_count`, and
`action_queue_unknown_count` for scheduler-level gating. It also carries
`hygiene_gap_count` and per-gap hygiene totals for failed summaries, missing
summaries, dirty runs, and unfingerprinted inputs.
For broker dispatch round-trip proof, the summary, action plan, and runbook
also carry `broker_roundtrip_runs`, `broker_roundtrip_passed_runs`,
`broker_roundtrip_portfolio_provided_runs`,
`broker_roundtrip_portfolio_ready_runs`,
`broker_roundtrip_portfolio_safe_runs`, and
`broker_roundtrip_portfolio_breach_runs`. When the broker round-trip summary
also carries portfolio concentration fields, the catalog adds
`broker_roundtrip_portfolio_concentration_runs`,
`broker_roundtrip_portfolio_concentration_ok_runs`, and
`broker_roundtrip_portfolio_concentration_breach_runs` so final
Arrow.money/iRage dry-run review can prove whether dispatch notional stayed
inside the selected strategy portfolio allocation and whether allocation
concentration stayed inside the selected portfolio limits.
For broker schema review, the catalog summary/action plan/runbook carry
`placeholder_schema_active_runs`, `placeholder_schema_allowed_runs`,
`placeholder_schema_reviewed_runs`, `placeholder_schema_unreviewed_runs`, and
`placeholder_schema_blocked_runs`, so scheduler review can separate
broker-reviewed mappings from dry-run-only placeholder Arrow.money/iRage
schemas.
`experiment_catalog_hygiene_gaps.csv` names each catalog hygiene gap with the
run directory, gap type, and recommended fix before the catalog is reused as
strategy, broker, route, or live-dryrun proof. When the source summary exposes
`next_gate` and `next_gate_help_command`, those repair hints are carried into
the hygiene sidecar and action-plan JSON.
`experiment_catalog_action_queue.csv` consolidates cataloged `next_gate` and
`next_gate_help_command` signals from scorecards, route reviews, and other
summary files into one priority-ordered scheduler queue. It also promotes
run-local `*_action_queue.csv` sidecars, such as broker readiness and
broker-vendor data readiness blockers, into the catalog-level queue while
preserving sidecar context columns such as `action_source_file`,
`action_source`, `dataset`, `component`, `check`, and `pipeline_dir`. When
the source summary or sidecar carries first-blocker evidence, the catalog queue
also preserves `failed_check_count`, `failed_check_names`,
`first_failed_reason`, and `primary_blocker_*` columns for the selected failed
check.
`experiment_catalog_action_plan.json` mirrors that queue as typed
`ready_actions`, `blocked_actions`, `unknown_actions`, top actions, counts, and
a scheduler recommendation for automation. It also exposes root-level
`next_gate`, `next_gate_help_command`, `primary_action_status`, and
`primary_action` fields so schedulers can pick one primary handoff without
parsing every action array. The action plan also exposes root-level
`failed_check_count`, `failed_checks`, `first_failed_reason`, and structured
`primary_blocker` fields for the first blocked catalog action. Its
`catalog_hygiene_ready` flag and recommendation prioritize hygiene repair
before scheduling queued actions.
`experiment_catalog_runbook.md` mirrors the same queue with catalog readiness
and input-provenance totals for human operator review.
Use `--fail-on-blocked-actions` to return exit code 2 when blocked or unknown
catalog actions exist, or `--fail-on-actions` to fail when any ready, blocked,
or unknown action remains.
Use `--fail-on-blocked-placeholder-schema` to fail only when cataloged broker
schema evidence has unreviewed placeholders that were not explicitly allowed,
or `--fail-on-placeholder-schema` to fail whenever any placeholder broker
schema remains active in a promotion/live-readiness catalog.
Use `--fail-on-broker-roundtrip-portfolio-breach` to fail when any final
broker dispatch round-trip exceeded the selected strategy portfolio allocation,
and `--require-broker-roundtrip-portfolio-safe` when the catalog must contain
at least one portfolio-safe broker dispatch round-trip proof.
Use `--fail-on-broker-roundtrip-portfolio-concentration-breach` to fail when
any final broker round-trip concentration proof breaches its strategy/market
count or max-weight limits, and
`--require-broker-roundtrip-portfolio-concentration-ok` when the catalog must
contain at least one concentration-OK broker dispatch round-trip proof.
Use `--fail-on-catalog-gaps` to fail when cataloged runs include failed
summary status, missing summaries, dirty git state, or unfingerprinted inputs.
When that gate fails, inspect `experiment_catalog_hygiene_gaps.csv` first.

## Strategy Evidence Review

Gate a strategy from the experiment catalog before shadow scale-up:

```powershell
python -m hft_cli review-strategy-evidence `
  --catalog runs\catalog\latest `
  --out runs\evidence\leadlag_shadow `
  --required-run-type proof_report `
  --required-run-type proof_refresh_gate `
  --required-run-type stress_report `
  --required-run-type promotion_report `
  --required-run-type broker_readiness `
  --required-run-type shadow_session_comparison `
  --require-same-git-commit `
  --require-same-strategy `
  --expected-strategy lead_lag_taker `
  --require-same-market `
  --expected-market india_nse_index_derivatives `
  --fail-on-breach
```

For surface market-making research, use the named profile so surface-quality,
quote-risk, research-pipeline, and launch-pipeline proof are all mandatory
before scale-up review:

```powershell
python -m hft_cli review-strategy-evidence `
  --catalog runs\catalog\latest `
  --out runs\evidence\surface_mm_shadow `
  --profile surface_mm `
  --require-same-strategy `
  --expected-strategy surface_mm `
  --require-same-market `
  --expected-market india_nse_index_derivatives `
  --fail-on-breach
```

For lead-lag taker research, use the named profile after the measured edge,
replay walk-forward, stress, promotion, order-plan, and launch-pipeline
artifacts are present:

```powershell
python -m hft_cli review-strategy-evidence `
  --catalog runs\catalog\latest `
  --out runs\evidence\leadlag_shadow `
  --profile leadlag `
  --require-same-strategy `
  --expected-strategy lead_lag_taker `
  --require-same-market `
  --expected-market india_nse_index_derivatives `
  --fail-on-breach
```

For microprice/order-book imbalance research, use the named profile so edge
walk-forward, replay walk-forward, promotion, the top-level research pipeline,
order plan, and launch pipeline are all present before scale-up review:

```powershell
python -m hft_cli review-strategy-evidence `
  --catalog runs\catalog\latest `
  --out runs\evidence\imbalance_shadow `
  --profile imbalance `
  --require-same-strategy `
  --expected-strategy microprice_imbalance `
  --require-same-market `
  --expected-market india_nse_index_derivatives `
  --fail-on-breach
```

For parity/box research, use the named profile once the scan edge audit,
robustness sweep, promotion, multi-leg order plan, and launch pipeline are all
present:

```powershell
python -m hft_cli review-strategy-evidence `
  --catalog runs\catalog\latest `
  --out runs\evidence\parity_shadow `
  --profile parity `
  --require-same-strategy `
  --expected-strategy parity_box `
  --require-same-market `
  --expected-market india_nse_index_derivatives `
  --fail-on-breach
```

For settlement convergence, use the named profile after promotion and launch
handoff so the India-specific walk-forward, promotion, order plan, and launch
pipeline are all present:

```powershell
python -m hft_cli review-strategy-evidence `
  --catalog runs\catalog\latest `
  --out runs\evidence\settlement_shadow `
  --profile settlement `
  --require-same-strategy `
  --expected-strategy settlement_convergence `
  --require-same-market `
  --expected-market india_nse_index_derivatives `
  --fail-on-breach
```

After a strategy-specific launch pipeline has moved into scale-up,
runtime-session, cutover, route-enable, and broker dry-run dispatch proof, use
the operational launch profile to require the full non-submitting
Arrow.money/iRage handoff chain before any live-dry-run route is trusted:

```powershell
python -m hft_cli review-strategy-evidence `
  --catalog runs\catalog\latest `
  --out runs\evidence\leadlag_ops_launch `
  --profile ops_launch `
  --require-same-strategy `
  --expected-strategy lead_lag_taker `
  --require-same-market `
  --expected-market india_nse_index_derivatives `
  --fail-on-breach
```

The `leadlag` profile expands to `leadlag_edge_audit`,
`leadlag_replay_walkforward`, `stress_report`, `promotion_report`, and
`leadlag_order_plan`, and `leadlag_launch_pipeline`. The `surface_mm` profile
expands to `surface_quality_report`, `quote_risk_report`,
`surface_mm_research_pipeline`, and `surface_mm_launch_pipeline`. The
`imbalance` profile expands to
`imbalance_edge_walkforward`,
`imbalance_replay_walkforward`, `promotion_report`, and
`imbalance_research_pipeline`, `imbalance_order_plan`, and
`imbalance_launch_pipeline`. The `parity` profile expands to
`parity_edge_audit`, `parity_sweep`, `promotion_report`,
`parity_order_plan`, and `parity_launch_pipeline`. The `settlement` profile expands to
`settlement_convergence_walkforward`, `promotion_report`,
`settlement_order_plan`, and `settlement_launch_pipeline`. The `ops_launch`
profile expands to `scaleup_plan`, `runtime_telemetry_snapshot`,
`runtime_guard`, `runtime_session_monitor`,
`broker_vendor_data_readiness_pipeline`, `broker_readiness`, `cutover_gate`,
`route_enable_packet`, `broker_dispatch_plan`,
`broker_dispatch_send_packet`, `broker_dispatch_ack_reconciliation`, and
`broker_dispatch_roundtrip`; aliases include `broker_dryrun`, `launch_ops`,
and `live_dryrun`. Explicit `--required-run-type` flags still override the
profile for custom launch reviews.
If the broker-vendor wrapper proof is missing, the scorecard next gate points
to `pipeline-broker-vendor-readiness --help` so Arrow.money/iRage data-readiness
proof is generated before broker-readiness and dispatch evidence are trusted.
The `ops_launch` profile automatically requires passed required artifacts to
have file-resolved input provenance in the experiment catalog, blocking
directory-tree or unfingerprinted raw inputs before live-dryrun route review.
It also automatically blocks unreviewed placeholder broker schemas that were
not explicitly allowed, requires at least one portfolio-safe final broker
dispatch round-trip proof, requires at least one concentration-OK final broker
round-trip proof, fails when any final round-trip dispatch notional exceeded
the selected strategy portfolio allocation, and fails when any final
round-trip concentration breached selected strategy/market count or max-weight
limits.
Use `--allow-non-file-inputs` only for legacy exploratory catalogs, or
`--require-file-inputs` to apply the same fail-closed provenance rule to a
custom evidence set.
Custom evidence sets can opt into the same launch controls with
`--fail-on-blocked-placeholder-schema`, `--fail-on-placeholder-schema`,
`--require-broker-roundtrip-portfolio-safe`, and
`--fail-on-broker-roundtrip-portfolio-breach`,
`--require-broker-roundtrip-portfolio-concentration-ok`, and
`--fail-on-broker-roundtrip-portfolio-concentration-breach`.

`strategy_evidence_summary.csv` records the inferred `evidence_profile`. Ready
strategy profiles recommend `eligible_for_shadow_scaleup_review`, while a ready
`ops_launch` profile recommends `eligible_for_live_dryrun_route_review`.
It also records passed-required input provenance totals, placeholder-schema
counts, broker round-trip portfolio-safe/breach counts, and broker round-trip
portfolio concentration OK/breach counts when the catalog contains them.

Outputs:

```text
strategy_evidence_items.csv
strategy_evidence_checks.csv
strategy_evidence_summary.csv
manifest.json
```

The catalog recognizes research, proof, promotion, data-readiness, market
portability, calibration, launch, broker export/upload, broker-readiness,
shadow-session, strategy-scorecard, scale-up, surface-quality, quote-risk,
quote-lifecycle, runtime guard, runtime-session, cutover, route-enable,
broker-dispatch,
broker-dispatch-send,
broker-dispatch-ack, broker-dispatch-roundtrip, halt-response, and resume
summaries, so those run types can be promoted into explicit
`--required-run-type` evidence gates.

Use `--require-same-strategy` and `--require-same-market` before scale-up to
fail closed when required proof, stress, promotion, broker, or shadow artifacts
come from different strategy or market identities. Pair them with
`--expected-strategy` and `--expected-market` when the scale-up target is known.
The identity check also recognizes runtime identity aliases retained by
broker-readiness, shadow-session, and runtime-session summaries.

## Strategy Readiness Scorecard

Rank strategy evidence profiles from a combined experiment catalog so research
review can see which India-first candidates are closest to shadow scale-up:

```powershell
python -m hft_cli score-strategy-readiness `
  --catalog runs\catalog\latest `
  --out runs\scorecards\india_shadow `
  --market india_nse_index_derivatives `
  --fail-on-breach `
  --fail-on-blocked-actions
```

By default the scorecard reviews `leadlag`, `imbalance`, `parity`,
`settlement`, and `surface_mm`. It filters the catalog by each profile's
expected strategy identity before scoring, so shared run types such as
`promotion_report` cannot be borrowed from another strategy lane. Use repeated
`--profile` flags for a narrower review, `--require-file-inputs` to require
file-fingerprinted inputs, and `--allow-dirty-git` only for exploratory
catalogs.
Use `--fail-on-blocked-actions` to return exit code 2 when the scorecard queue
has blocked profile actions, or `--fail-on-actions` when any ready or blocked
profile action should force a scheduler handoff instead of silently passing.

To score the operational live-dry-run chain for one strategy after scale-up,
cutover, route enable, and broker dispatch proof are present, include the
`ops_launch` profile and the expected strategy:

```powershell
python -m hft_cli score-strategy-readiness `
  --catalog runs\catalog\latest `
  --out runs\scorecards\leadlag_ops_launch `
  --profile ops_launch `
  --ops-strategy lead_lag_taker `
  --market india_nse_index_derivatives `
  --require-file-inputs `
  --fail-on-breach `
  --fail-on-blocked-actions
```

If `ops_launch` is scored without `--ops-strategy`, all required artifacts must
still carry one consistent strategy identity, so mixed lead-lag/imbalance
broker evidence fails closed instead of producing a borrowed live-dry-run
readiness signal. The scorecard applies the same `ops_launch` broker controls
as strategy evidence review: blocked placeholder schemas fail, final broker
round-trip allocation breaches fail, and final broker round-trip concentration
must include at least one concentration-OK proof with no concentration
breaches. Blocked scorecard actions include the failed evidence-check names in
`strategy_scorecard_action_queue.csv` and `strategy_scorecard_next_actions.json`.

Outputs:

```text
strategy_scorecard.csv
strategy_scorecard_gaps.csv
strategy_scorecard_summary.csv
strategy_scorecard_action_queue.csv
strategy_scorecard_next_actions.json
strategy_scorecard_runbook.md
manifest.json
```

`strategy_scorecard.csv` ranks profiles by readiness and evidence completion.
`strategy_scorecard_gaps.csv` lists the missing or non-passing run types for
each profile, and the summary names the current best candidate plus whether at
least one strategy is ready for shadow scale-up review.
The scorecard and gap rows also include `next_required_run_type`/`next_gate`
or per-gap `next_gate` hints, so a blocked imbalance profile can point directly
to `walkforward-imbalance-replay`, a missing broker dry-run packet can point to
`plan-broker-dispatch`, and a ready `ops_launch` profile can point to
`review-route-readiness`.
`strategy_scorecard_next_actions.json` mirrors the ranked next actions and
open gaps in a machine-readable sidecar for schedulers or follow-up runbooks.
It includes `schema_version`, root `next_gate`/`next_gate_help_command` aliases
for the best ranked action, `primary_action_status`, `primary_action`,
`ready_actions`, `blocked_actions`, and action counts so automation can
consume ready scale-up lanes separately from blocked research or broker-proof
lanes. `strategy_scorecard_summary.csv` and
`strategy_scorecard_next_actions.json` also expose `failed_check_count`,
`failed_checks`/`failed_check_names`, `first_failed_reason`, and structured
`primary_blocker` fields for the first blocked strategy profile, including
the missing or non-passing required run type and next CLI gate.
`strategy_scorecard_action_queue.csv` flattens those ranked actions into one
priority-ordered row per profile with `queue_status`, `next_gate`, and
`next_gate_help_command` for simple runner or scheduler handoff.
Both CSV and JSON outputs include `next_gate_help_command` fields such as
`python -m hft_cli walkforward-imbalance-replay --help`, making the next CLI
entry point explicit even before concrete data paths are selected.
`strategy_scorecard_runbook.md` is a human-readable handoff generated from
the same next-action data and captured in the manifest artifact fingerprints.

## Strategy Portfolio Allocation

Allocate paper/shadow capital across strategy profiles that passed the
strategy readiness scorecard:

```powershell
python -m hft_cli allocate-strategy-portfolio `
  --scorecard runs\scorecards\india_research `
  --out runs\strategy_portfolios\india_research_paper `
  --total-capital 1000000 `
  --capital-currency INR `
  --reserve-weight 0.10 `
  --max-profile-weight 0.40 `
  --min-strategy-count 2 `
  --max-strategy-weight 0.60 `
  --fail-on-blocked-actions `
  --fail-on-breach
```

Outputs:

```text
strategy_portfolio_allocations.csv
strategy_portfolio_checks.csv
strategy_portfolio_summary.csv
strategy_portfolio_action_queue.csv
strategy_portfolio_config.json
strategy_portfolio_runbook.md
manifest.json
```

The allocator is deliberately paper/shadow-only. By default it only allocates
to scorecard profiles where `ready=true` and `readiness_score >= 1.0`, keeps
10% unallocated as reserve, and caps any one profile at 40% of capital.
Use `--min-strategy-count`, `--min-market-count`, `--max-strategy-weight`,
and `--max-market-weight` to require strategy/market diversity or cap aggregate
strategy/market concentration before a paper/shadow portfolio is treated as
ready.
`strategy_portfolio_allocations.csv` keeps one row per scorecard profile with
eligibility reason, allocation weight, notional, and next-gate context.
`strategy_portfolio_checks.csv`, `strategy_portfolio_summary.csv`, and
`strategy_portfolio_config.json` expose `failed_check_count`, failed-check
names, `first_failed_reason`, and a structured `primary_blocker`, so automation
fails closed when no strategy lane is ready instead of creating a borrowed
allocation. `strategy_portfolio_action_queue.csv` flattens ready allocations
and blocked profile/check repairs into scheduler rows with `queue_status`,
`next_gate`, `next_gate_help_command`, allocation notional, and profile context.
The summary/config mirror `action_queue_count`, `ready_action_count`,
`blocked_action_count`, `next_gate`, `next_gate_help_command`,
`primary_action_status`, `primary_action`, and the ready/blocked action arrays.
`strategy_portfolio_runbook.md` mirrors the same allocation, blocked-profile,
failed-check, and scheduler-action handoff for review. Use
`--fail-on-blocked-actions` to stop only when blocked allocation actions remain,
or `--fail-on-actions` when any portfolio action should stop automation.

## Market Profile Report

Export India/US market assumptions before a run:

```powershell
python -m hft_cli market-profile-report `
  --market india_nse_index_derivatives `
  --market us_options_regular `
  --out runs\market_profiles\india_us `
  --price 100 `
  --qty 100 `
  --per-contract-fee 0.10 `
  --per-order-fee 0.25
```

Outputs:

```text
market_profiles.csv
market_cost_examples.csv
market_profile_summary.csv
manifest.json
```

## Market Portability Report

Export the strategy-by-market readiness matrix before expanding an India-first
workflow into US equities or options:

```powershell
python -m hft_cli market-portability-report `
  --market india_nse_index_derivatives `
  --market us_equities_regular `
  --market us_options_regular `
  --strategy microprice_imbalance `
  --strategy parity_box `
  --strategy surface_market_making `
  --explicit-fee-model `
  --fail-on-gaps `
  --out runs\market_profiles\portability
```

Outputs:

```text
market_portability_matrix.csv
market_portability_gaps.csv
market_portability_summary.csv
market_portability_action_queue.csv
market_portability_runbook.md
market_portability_config.json
manifest.json
```

US rows are marked `needs_fee_model` unless explicit fees are acknowledged.
India-specific settlement convergence remains blocked for US profiles until a
separate US settlement/microstructure model is implemented. The config JSON
records ready strategy/market pairs, gap pairs, primary `next_gate`,
`next_gate_help_command`, `primary_action_status`, `primary_action`, next-gate
sets, action counts, the matching strategy-evidence profile command, and the
file-provenance-gated `ops_launch` review command for downstream US research
planning.
`market_portability_action_queue.csv` flattens ready and blocked
strategy/market pairs into scheduler order with `next_gate`,
`next_gate_help_command`, evidence gates, data requirements, workflow commands,
and a recommendation. `market_portability_runbook.md` mirrors the same queue
for operator review, and both files are included in the run manifest so
`catalog-runs` can promote the portability handoff into the top-level action
plan.
Use `--fail-on-breach` to return exit code 2 when no requested pair is ready,
`--fail-on-gaps` to fail when any requested strategy/market pair still has a
portability gap, or `--fail-on-blocked-actions` to fail when the generated
action queue contains blocked work. Use `--fail-on-actions` when any ready or
blocked portability handoff should stop the scheduler for explicit review.

## Route Readiness Review

Combine market portability, strategy evidence, and operational launch evidence
into a per-route go/no-go matrix before live dry-run review:

```powershell
python -m hft_cli review-route-readiness `
  --portability runs\market_profiles\portability `
  --strategy-evidence runs\evidence\imbalance_strategy `
  --ops-evidence runs\evidence\imbalance_ops_launch `
  --out runs\evidence\imbalance_route_readiness `
  --fail-on-breach `
  --fail-on-blocked-actions
```

Outputs:

```text
route_readiness_pairs.csv
route_readiness_gaps.csv
route_readiness_summary.csv
route_readiness_action_queue.csv
route_readiness_config.json
route_readiness_runbook.md
manifest.json
```

The review fails closed until the route is portable, matching strategy evidence
is ready, matching `ops_launch` evidence is ready, and ops evidence was reviewed
with file-fingerprinted inputs. It also verifies the `ops_launch` evidence
summary carries launch-grade broker controls: blocked placeholder schemas must
be gated, final broker round-trip allocation must have at least one
portfolio-safe proof with no allocation breaches, and final broker round-trip
concentration must have at least one concentration-OK proof with no
concentration breaches. Older ops evidence summaries that do not carry those
control flags/counts fail closed at route review instead of being treated as
live-dry-run ready. Use `--allow-non-file-ops-inputs` only for explicit dry-run
investigations that are not route-review candidates.
`route_readiness_action_queue.csv` flattens ready and blocked route pairs into
priority order with `next_gate`, `next_gate_help_command`, evidence statuses,
`ops_launch_control_failures`, broker proof counts, and the route-level
recommendation. `route_readiness_config.json` mirrors the queue as
`next_actions`, `ready_actions`, and `blocked_actions`, plus the primary next
gate/help, `primary_action_status`, and `primary_action` for scheduler
handoff. `route_readiness_runbook.md` mirrors the same handoff for
operator review before live dry-run routing.
`route_readiness_summary.csv` also carries the primary `next_gate`,
`next_gate_help_command`, and ready/blocked action counts so `catalog-runs`
can preserve the route-level scheduler signal.
Use `--fail-on-blocked-actions` to stop when blocked route actions remain, or
`--fail-on-actions` when any ready or blocked route handoff should stop the
scheduler for explicit review.

## Instrument Metadata Report

Audit option symbol parse coverage before exposure review, upload mapping, or
US portability work:

```powershell
python -m hft_cli instrument-metadata-report `
  --input runs\exports\leadlag_shadow_arrow\broker_orders.csv `
  --out runs\risk\leadlag_shadow_instruments `
  --instrument-column instrument_id `
  --fail-on-unparsed
```

Outputs:

```text
instrument_metadata.csv
instrument_metadata_gaps.csv
instrument_metadata_summary.csv
manifest.json
```

## Parity / Box Scan

```powershell
python -m hft_cli scan-parity-box `
  --chain data\chain.csv `
  --futures data\futures.csv `
  --out runs\scan_2026_06_10
```

Outputs:

```text
parity_opportunities.csv
box_opportunities.csv
opportunity_report.csv
```

## Parity / Box Edge Audit

Gate a parity/box scan before replaying or sweeping it:

```powershell
python -m hft_cli audit-parity-edge `
  --scan runs\scan_2026_06_10 `
  --out runs\parity_edge\2026_06_10 `
  --min-total-opportunities 5 `
  --min-total-net-edge 1000 `
  --min-median-net-edge 100 `
  --min-best-net-edge 250 `
  --min-median-persistence-ticks 1 `
  --min-direction-count 1 `
  --max-future-staleness-ns 100000 `
  --fail-on-breach
```

Outputs:

```text
parity_edge_metrics.csv
parity_edge_checks.csv
parity_edge_summary.csv
manifest.json
```

## Parity Replay

```powershell
python -m hft_cli replay-parity `
  --chain data\chain.csv `
  --futures data\futures.csv `
  --out runs\parity_replay_2026_06_10 `
  --signal-limit 100 `
  --feed-latency-us 50 `
  --order-latency-us 250 `
  --fill-model runs\fill_model\leadlag_shadow_latest
```

Outputs include fills, equity, summary, PnL decomposition, regime summaries,
spread pairs, spread summary, residual inventory, signals, and legging report.

## Parity Sweep

Run replay robustness scenarios across executable depth, as-of latency, and
routing latency assumptions:

```powershell
python -m hft_cli sweep-parity `
  --chain data\chain.csv `
  --futures data\futures.csv `
  --out runs\parity_sweep_2026_06_10 `
  --depth-fraction 0.10 0.25 0.50 `
  --asof-latency-ns 0 50000 100000 `
  --feed-latency-us 0 50 `
  --order-latency-us 100 250 500 `
  --signal-limit 100 `
  --min-net-pnl 1 `
  --min-fills 10 `
  --max-drawdown 5000 `
  --fail-on-breach
```

Outputs include per-scenario replay folders plus:

```text
sweep_runs.csv
sweep_summary.csv
proof/proof_metrics.csv
proof/proof_checks.csv
proof/proof_summary.csv
```

## Parity / Box Candidate Promotion

Promote a passed parity/box scan, edge audit, and replay sweep into the
launch-compatible `promotion_report` shape. This bridge preserves the selected
opportunity's executable leg prices so `plan-parity-orders` can generate the
multi-leg order template without manually re-entering prices:

```powershell
python -m hft_cli promote-parity-candidate `
  --scan runs\scan_2026_06_10 `
  --edge-audit runs\parity_edge\2026_06_10 `
  --sweep runs\parity_sweep_2026_06_10 `
  --out runs\promotion\parity_box `
  --min-candidate-net-edge 100 `
  --min-passed-scenarios 1 `
  --fail-on-breach
```

Outputs:

```text
promotion_candidate.csv
promotion_checks.csv
promotion_summary.csv
candidate_config.json
manifest.json
```

## Parity / Box Order Plan

Convert a promoted parity/box candidate into broker-neutral multi-leg
paper/shadow order templates. Candidate configs produced from scan-like
selections can carry leg prices directly; otherwise pass the target direction,
expiry, strikes, quantity, and leg prices explicitly:

```powershell
python -m hft_cli plan-parity-orders `
  --promotion runs\promotion\parity_box `
  --out runs\orders\parity_box_shadow `
  --direction buy_synthetic_sell_future `
  --expiry 2026-06-30 `
  --strike 25000 `
  --qty 75 `
  --call-price 105 `
  --put-price 95 `
  --future-price 25020 `
  --max-order-qty 75 `
  --max-notional 2000000 `
  --fail-on-breach
```

For boxes, use `--direction buy_box` or `--direction sell_box` with
`--low-strike`, `--high-strike`, `--low-call-price`, `--low-put-price`,
`--high-call-price`, and `--high-put-price`.

Outputs:

```text
parity_order_candidates.csv
parity_order_checks.csv
parity_order_summary.csv
manifest.json
```

## Parity / Box Launch Pipeline

Run the promoted multi-leg candidate through order planning, staging, launch
bundle creation, broker export, broker upload pack, and broker readiness:

```powershell
python -m hft_cli pipeline-parity-launch `
  --promotion runs\promotion\parity_box `
  --out runs\launch_pipelines\parity_box_arrow `
  --adapter arrow_money `
  --mode shadow `
  --route-tag parity_shadow `
  --direction buy_synthetic_sell_future `
  --expiry 2026-06-30 `
  --strike 25000 `
  --qty 75 `
  --call-price 105 `
  --put-price 95 `
  --future-price 25020 `
  --max-order-qty 75 `
  --max-notional 2000000 `
  --max-orders 3 `
  --allow-placeholder-schema `
  --fail-on-breach
```

Outputs:

```text
01_order_plan\...
02_staged_orders\...
03_launch\...
04_export\...
05_upload_pack\...
06_broker_readiness\...
parity_launch_pipeline_components.csv
parity_launch_pipeline_summary.csv
manifest.json
```

## Lead-Lag Measurement

```powershell
python -m hft_cli measure-leadlag `
  --leader data\futures.csv `
  --laggard data\atm_call.csv `
  --out runs\leadlag_measure_2026_06_10 `
  --leader-tick-size 0.05 `
  --laggard-tick-size 0.05 `
  --delta 0.5
```

Outputs:

```text
cross_correlation.csv
lag_profile.csv
latency_curve.csv
```

## Lead-Lag Edge Audit

Gate a measured lead-lag relationship before spending replay/sweep cycles:

```powershell
python -m hft_cli audit-leadlag-edge `
  --measure runs\leadlag_measure_2026_06_10 `
  --out runs\leadlag_edge\2026_06_10 `
  --market india_nse_index_derivatives `
  --min-events 20 `
  --min-abs-correlation 0.15 `
  --min-update-rate 0.6 `
  --max-median-update-ns 1000000 `
  --min-best-latency-net-pnl 0 `
  --min-best-latency-fills 5 `
  --min-profitable-latency-ns 250000 `
  --fail-on-breach
```

Outputs:

```text
leadlag_edge_metrics.csv
leadlag_edge_checks.csv
leadlag_edge_summary.csv
manifest.json
```

## Lead-Lag Replay

```powershell
python -m hft_cli replay-leadlag `
  --leader data\futures.csv `
  --laggard data\atm_call.csv `
  --out runs\leadlag_replay_2026_06_10 `
  --market india_nse_index_derivatives `
  --delta 0.5 `
  --trigger-ticks 3 `
  --qty 75 `
  --fill-model runs\fill_model\leadlag_shadow_latest
```

## Lead-Lag Replay Walk-Forward

Replay one lead-lag candidate across paired leader/laggard folds and aggregate
proof before promotion:

```powershell
python -m hft_cli walkforward-leadlag-replay `
  --leaders data\day1_futures.csv data\day2_futures.csv `
  --laggards data\day1_atm_call.csv data\day2_atm_call.csv `
  --label day1 `
  --label day2 `
  --out runs\leadlag_replay_walkforward_2026_06_10 `
  --market india_nse_index_derivatives `
  --delta 0.5 `
  --trigger-ticks 3 `
  --qty 75 `
  --flat-after-ns 500000000 `
  --markout-horizons-ns 100000000 1000000000 `
  --min-net-pnl 1 `
  --min-fills 10 `
  --min-folds 2 `
  --min-proof-pass-rate 1 `
  --fail-on-breach
```

Outputs:

```text
leadlag_replay_walkforward_folds.csv
leadlag_replay_walkforward_checks.csv
leadlag_replay_walkforward_summary.csv
candidate_config.json
proof/proof_metrics.csv
proof/proof_checks.csv
proof/proof_summary.csv
manifest.json
```

For US research, provide `--market us_equities_regular` or
`--market us_options_regular` plus explicit generic fee flags, or supply a
ready lead-lag `candidate_config.json` with `replay_defaults.generic_costs`.

## Lead-Lag Candidate Promotion

Convert a passed lead-lag replay walk-forward into a launch-compatible
promotion report:

```powershell
python -m hft_cli promote-leadlag-candidate `
  --walkforward runs\leadlag_replay_walkforward_2026_06_10 `
  --out runs\promotion\leadlag_2026_06_10 `
  --min-proof-pass-rate 1 `
  --min-total-fills 20 `
  --min-total-net-pnl 1 `
  --fail-on-breach
```

Outputs:

```text
promotion_candidate.csv
promotion_checks.csv
promotion_summary.csv
candidate_config.json
manifest.json
```

## Lead-Lag Order Plan

Convert a promoted lead-lag candidate into broker-neutral paper/shadow order
templates. The plan emits both signal-conditioned paths: buy the laggard after
an upward leader innovation and sell the laggard after a downward leader
innovation.

```powershell
python -m hft_cli plan-leadlag-orders `
  --promotion runs\promotion\leadlag_2026_06_10 `
  --out runs\orders\leadlag_2026_06_10 `
  --laggard-instrument-id NIFTY_20260610_25000C `
  --reference-price 10.00 `
  --entry-offset-ticks 1 `
  --max-order-qty 75 `
  --max-notional 10000 `
  --price-band-pct 0.02 `
  --fail-on-breach
```

Outputs:

```text
leadlag_order_candidates.csv
leadlag_order_checks.csv
leadlag_order_summary.csv
manifest.json
```

The generated `leadlag_order_candidates.csv` uses the broker-neutral `orders`
schema and carries `SIGNAL_TEMPLATE` lifecycle metadata, so it can be staged
for Arrow.money/iRage paper or shadow routing without losing the trigger
intent:

```powershell
python -m hft_cli stage-orders `
  --orders runs\orders\leadlag_2026_06_10\leadlag_order_candidates.csv `
  --out runs\stage\leadlag_2026_06_10 `
  --source orders `
  --adapter arrow_money `
  --max-order-qty 75 `
  --max-notional 10000 `
  --fail-on-reject
```

Run the promoted lead-lag candidate through the full paper/shadow handoff
chain in one command:

```powershell
python -m hft_cli pipeline-leadlag-launch `
  --promotion runs\promotion\leadlag_2026_06_10 `
  --out runs\pipelines\leadlag_shadow `
  --adapter arrow_money `
  --mode shadow `
  --route-tag leadlag_shadow `
  --laggard-instrument-id NIFTY_20260610_25000C `
  --reference-price 10.00 `
  --max-order-qty 75 `
  --max-notional 10000 `
  --max-orders 2 `
  --broker-vendor-data-readiness runs\broker_vendor_data\arrow_ready `
  --broker-runtime-session runs\runtime_sessions\leadlag_shadow_latest `
  --require-broker-runtime-session `
  --allow-placeholder-schema `
  --fail-on-breach
```

Pipeline outputs:

```text
01_order_plan\...
02_staged_orders\...
03_launch\...
04_export\...
05_upload_pack\...
06_broker_readiness\...
leadlag_launch_pipeline_components.csv
leadlag_launch_pipeline_summary.csv
manifest.json
```

The same `--broker-vendor-data-readiness` option is available on the imbalance,
parity, settlement, and surface-MM launch pipelines. It may point at either the
top-level `pipeline-broker-vendor-readiness` output or the nested
`01_vendor_market_data_batch` directory, and the launch pipeline forwards the
proof into broker readiness before broker dispatch planning.

## Microprice Imbalance Edge Audit

Scan normalized top-of-book ticks for imbalance/microprice signals and measure
forward-mid response before spending time on replay grids:

```powershell
python -m hft_cli audit-imbalance-edge `
  --ticks data\atm_option_ticks.csv `
  --out runs\imbalance_edge_2026_06_10 `
  --entry-imbalance 0.6 `
  --min-microprice-edge-ticks 0.25 `
  --forward-horizon-ns 100000000 `
  --min-signals 100 `
  --min-direction-count 2 `
  --min-mean-forward-edge-ticks 0.25 `
  --min-win-rate 0.52 `
  --fail-on-breach
```

Outputs:

```text
imbalance_signals.csv
imbalance_edge_metrics.csv
imbalance_edge_checks.csv
imbalance_edge_summary.csv
manifest.json
```

## Microprice Imbalance Edge Sweep

Search imbalance edge thresholds and forward horizons on raw top-of-book data
before launching replay grids:

```powershell
python -m hft_cli sweep-imbalance-edge `
  --ticks data\atm_option_ticks.csv `
  --out runs\imbalance_edge_sweep_2026_06_10 `
  --entry-imbalance 0.55 0.60 0.70 `
  --min-microprice-edge-ticks 0.25 0.50 1.00 `
  --forward-horizon-ns 100000000 500000000 `
  --min-signals 100 `
  --min-direction-count 2 `
  --min-mean-forward-edge-ticks 0.25 `
  --min-win-rate 0.52 `
  --min-best-usable-signals 100 `
  --fail-on-breach
```

Outputs:

```text
imbalance_edge_sweep_runs.csv
imbalance_edge_sweep_checks.csv
imbalance_edge_sweep_summary.csv
candidate_config.json
manifest.json
```

## Microprice Imbalance Edge Selection

Compare edge sweeps across days or folds and select only stable threshold
configs before replay work:

```powershell
python -m hft_cli compare-imbalance-edge-sweeps `
  --sweeps runs\imbalance_edge_sweep_2026_06_10 runs\imbalance_edge_sweep_2026_06_11 `
  --label day1 `
  --label day2 `
  --out runs\imbalance_edge_selection `
  --min-sweeps 2 `
  --min-pass-rate 1 `
  --min-median-usable-signals 100 `
  --min-median-mean-forward-edge-ticks 0.25 `
  --min-min-win-rate 0.52 `
  --fail-on-breach
```

Outputs:

```text
imbalance_edge_scenario_runs.csv
imbalance_edge_scenario_scores.csv
imbalance_edge_selection_checks.csv
imbalance_edge_selection_summary.csv
candidate_config.json
manifest.json
```

## Microprice Imbalance Edge Walk-Forward

Run edge sweeps across multiple tick files, compare the fold results, and emit
a stable replay-ready candidate in one command:

```powershell
python -m hft_cli walkforward-imbalance-edge `
  --ticks data\atm_option_ticks_2026_06_10.csv data\atm_option_ticks_2026_06_11.csv `
  --label day1 `
  --label day2 `
  --out runs\imbalance_edge_walkforward `
  --entry-imbalance 0.55 0.60 0.70 `
  --min-microprice-edge-ticks 0.25 0.50 1.00 `
  --forward-horizon-ns 100000000 500000000 `
  --min-signals 100 `
  --min-direction-count 2 `
  --min-mean-forward-edge-ticks 0.25 `
  --min-win-rate 0.52 `
  --min-best-usable-signals 100 `
  --min-selection-sweeps 2 `
  --min-selection-pass-rate 1 `
  --min-selection-median-usable-signals 100 `
  --min-selection-median-mean-forward-edge-ticks 0.25 `
  --min-selection-min-win-rate 0.52 `
  --fail-on-breach
```

Outputs:

```text
imbalance_edge_walkforward_folds.csv
imbalance_edge_walkforward_checks.csv
imbalance_edge_walkforward_summary.csv
candidate_config.json
manifest.json
sweeps\<fold>\...
selection\...
```

The `candidate_config.json` from the edge sweep, edge selection, or
walk-forward command can be passed directly into replay or replay-sweep
commands with `--candidate-config`.

For US research, pass a market profile such as `--market us_equities_regular`
or `--market us_options_regular` on edge, walk-forward, replay, sweep, or
pipeline commands. Candidate configs preserve `market` and `tick_size`, so
replay commands can inherit those settings from `--candidate-config`.
For non-India replay costs, provide explicit generic assumptions with
`--generic-buy-notional-rate`, `--generic-sell-notional-rate`,
`--generic-per-unit-fee`, `--generic-per-contract-fee`, and
`--generic-per-order-fee`; replay candidate configs preserve these
`generic_costs` for later replay, sweep, walk-forward, and pipeline runs.

## Microprice Imbalance Replay

Replay a single-instrument top-of-book imbalance strategy that enters when
depth imbalance and microprice displacement agree, then exits on signal decay
or a hold timer:

```powershell
python -m hft_cli replay-imbalance `
  --ticks data\atm_option_ticks.csv `
  --out runs\imbalance_replay_2026_06_10 `
  --candidate-config runs\imbalance_edge_sweep_2026_06_10 `
  --instrument-kind OPT `
  --exit-imbalance 0.15 `
  --max-spread-ticks 2 `
  --qty 75 `
  --order-latency-us 250 `
  --fill-model runs\fill_model\leadlag_shadow_latest
```

Outputs include fills, equity, summary, PnL decomposition, regime summaries,
spread pairs, spread summary, residual inventory, signals, markouts, and a
manifest.

## Microprice Imbalance Replay Walk-Forward

Replay one selected imbalance candidate across multiple tick folds, run proof
checks for each fold, and gate the aggregate result before paper/shadow work:

```powershell
python -m hft_cli walkforward-imbalance-replay `
  --ticks data\atm_option_ticks_2026_06_12.csv data\atm_option_ticks_2026_06_13.csv `
  --label day1 `
  --label day2 `
  --out runs\imbalance_replay_walkforward `
  --candidate-config runs\imbalance_edge_walkforward `
  --cooloff-ns 1000000 `
  --order-latency-us 250 `
  --min-net-pnl 0 `
  --min-fills 10 `
  --max-drawdown 5000 `
  --min-folds 2 `
  --min-proof-pass-rate 1 `
  --min-total-fills 20 `
  --min-total-net-pnl 0 `
  --fail-on-breach
```

Outputs:

```text
imbalance_replay_walkforward_folds.csv
imbalance_replay_walkforward_checks.csv
imbalance_replay_walkforward_summary.csv
candidate_config.json
manifest.json
proof\...
runs\<fold>\...
```

## Microprice Imbalance Candidate Promotion

Convert a passed replay walk-forward folder into the promotion-report shape
used by paper/shadow launch tooling:

```powershell
python -m hft_cli promote-imbalance-candidate `
  --walkforward runs\imbalance_replay_walkforward `
  --out runs\imbalance_promotion `
  --min-proof-pass-rate 1 `
  --min-total-fills 20 `
  --min-total-net-pnl 0 `
  --max-worst-drawdown 5000 `
  --fail-on-breach
```

Outputs:

```text
promotion_candidate.csv
promotion_checks.csv
promotion_summary.csv
candidate_config.json
manifest.json
```

## Microprice Imbalance Order Plan

Convert a promoted imbalance candidate into broker-neutral paper/shadow order
templates. The plan emits both signal-conditioned paths: buy on bid-side depth
pressure and sell on ask-side depth pressure.

```powershell
python -m hft_cli plan-imbalance-orders `
  --promotion runs\imbalance_promotion `
  --out runs\orders\imbalance_shadow `
  --instrument-id NIFTY_20260610_25000C `
  --reference-price 10.00 `
  --entry-offset-ticks 1 `
  --max-order-qty 75 `
  --max-notional 10000 `
  --price-band-pct 0.02 `
  --fail-on-breach
```

Outputs:

```text
imbalance_order_candidates.csv
imbalance_order_checks.csv
imbalance_order_summary.csv
manifest.json
```

The generated `imbalance_order_candidates.csv` uses the broker-neutral `orders`
schema and carries `SIGNAL_TEMPLATE` lifecycle metadata, so it can be staged
for Arrow.money/iRage paper or shadow routing without losing the trigger
intent.

Run the promoted imbalance candidate through the full paper/shadow handoff
chain in one command:

```powershell
python -m hft_cli pipeline-imbalance-launch `
  --promotion runs\imbalance_promotion `
  --out runs\pipelines\imbalance_shadow `
  --adapter arrow_money `
  --mode shadow `
  --route-tag imbalance_shadow `
  --instrument-id NIFTY_20260610_25000C `
  --reference-price 10.00 `
  --max-order-qty 75 `
  --max-notional 10000 `
  --max-orders 2 `
  --broker-runtime-session runs\runtime_sessions\imbalance_shadow_latest `
  --require-broker-runtime-session `
  --allow-placeholder-schema `
  --fail-on-breach
```

Pipeline outputs:

```text
01_order_plan\...
02_staged_orders\...
03_launch\...
04_export\...
05_upload_pack\...
06_broker_readiness\...
imbalance_launch_pipeline_components.csv
imbalance_launch_pipeline_summary.csv
manifest.json
```

## Microprice Imbalance Research Pipeline

Run the full imbalance research proof path in one command: edge walk-forward,
replay-proof walk-forward, and promotion into launch-compatible candidate
artifacts.

```powershell
python -m hft_cli pipeline-imbalance-research `
  --ticks data\atm_option_ticks_2026_06_10.csv data\atm_option_ticks_2026_06_11.csv `
  --label day1 `
  --label day2 `
  --market-portability runs\market_profiles\portability `
  --data-readiness-comparison runs\vendor_data\arrow_ticks_batch\comparison `
  --out runs\imbalance_pipeline `
  --entry-imbalance 0.55 0.60 0.70 `
  --min-microprice-edge-ticks 0.25 0.50 `
  --forward-horizon-ns 100000000 500000000 `
  --min-signals 100 `
  --min-direction-count 2 `
  --min-mean-forward-edge-ticks 0.25 `
  --min-win-rate 0.52 `
  --min-selection-sweeps 2 `
  --min-proof-pass-rate 1 `
  --min-total-fills 20 `
  --min-total-net-pnl 0 `
  --require-market-portability `
  --require-data-readiness-comparison `
  --fail-on-breach
```

Outputs:

```text
imbalance_pipeline_stages.csv
imbalance_pipeline_summary.csv
candidate_config.json
manifest.json
edge_walkforward\...
replay_walkforward\...
promotion\...
```

Use `--market-portability` with `--require-market-portability` to fail closed
before edge walk-forward unless `market_portability_config.json` marks
`microprice_imbalance` ready for the pipeline `--market`.

## Settlement Convergence Audit

Audit expiry-window option convergence against the running settlement average.
This is a Layer-1 gate for legitimate settlement arithmetic: it compares
expiring option touch prices with projected intrinsic value using only the
settlement window observed so far plus the current index level.

```powershell
python -m hft_cli audit-settlement-convergence `
  --index-ticks data\nifty_index_ticks.csv `
  --chain data\nifty_expiry_chain.csv `
  --out runs\settlement_convergence_2026_06_10 `
  --window-start-ns 1786536600000000000 `
  --window-end-ns 1786538400000000000 `
  --min-known-fraction 0.50 `
  --min-gross-edge-ticks 10 `
  --min-net-edge 100 `
  --min-best-net-edge 100 `
  --fail-on-breach
```

Outputs:

```text
settlement_running_average.csv
settlement_convergence_opportunities.csv
settlement_convergence_checks.csv
settlement_convergence_summary.csv
candidate_config.json
manifest.json
```

This command is intentionally an audit, not a market-impact strategy: it finds
touch-price dislocations that clear explicit edge/cost thresholds and records
whether they are ready for later replay work.

Run the same audit across expiry folds before trusting a candidate:

```powershell
python -m hft_cli walkforward-settlement-convergence `
  --index-ticks data\nifty_index_2026_06_10.csv data\nifty_index_2026_06_17.csv `
  --chains data\nifty_chain_2026_06_10.csv data\nifty_chain_2026_06_17.csv `
  --label nifty_tue_1 `
  --label nifty_tue_2 `
  --out runs\settlement_convergence_walkforward `
  --data-readiness-comparison runs\vendor_data\batch\comparison `
  --require-data-readiness-comparison `
  --window-start-ns 1786536600000000000 1787141400000000000 `
  --window-end-ns 1786538400000000000 1787143200000000000 `
  --min-known-fraction 0.50 `
  --min-gross-edge-ticks 10 `
  --min-net-edge 100 `
  --min-fold-best-net-edge 100 `
  --min-pass-rate 1 `
  --min-total-opportunities 2 `
  --fail-on-breach
```

Walk-forward outputs:

```text
settlement_convergence_walkforward_folds.csv
settlement_convergence_walkforward_checks.csv
settlement_convergence_walkforward_summary.csv
candidate_config.json
manifest.json
runs\<fold>\...
```

When `--require-data-readiness-comparison` is set, the run first checks the
multi-day vendor data-readiness comparison. If the comparison is missing or not
accepted, the walk-forward fails closed, writes the normal summary/check/config
artifacts, and skips fold audits.

Promote a passed settlement walk-forward candidate into the same
paper/shadow-ready promotion shape used by launch bundles:

```powershell
python -m hft_cli promote-settlement-candidate `
  --walkforward runs\settlement_convergence_walkforward `
  --out runs\promotion\settlement_convergence `
  --min-pass-rate 1 `
  --min-total-opportunities 2 `
  --min-total-net-edge 200 `
  --min-median-best-net-edge 100 `
  --min-median-known-fraction 0.50 `
  --fail-on-breach
```

Promotion outputs:

```text
promotion_candidate.csv
promotion_checks.csv
promotion_summary.csv
candidate_config.json
manifest.json
```

Convert a promoted settlement candidate into broker-neutral limit-order
candidates for the standard staging path:

```powershell
python -m hft_cli plan-settlement-orders `
  --promotion runs\promotion\settlement_convergence `
  --out runs\orders\settlement_convergence `
  --symbol-prefix NIFTY `
  --price-offset-ticks 1 `
  --fail-on-breach
```

Order-plan outputs:

```text
settlement_order_candidates.csv
settlement_order_checks.csv
settlement_order_summary.csv
manifest.json
```

The generated `settlement_order_candidates.csv` uses the broker-neutral
`orders` schema, so it can be passed directly into:

```powershell
python -m hft_cli stage-orders `
  --orders runs\orders\settlement_convergence\settlement_order_candidates.csv `
  --out runs\stage\settlement_convergence `
  --source orders `
  --max-order-qty 75 `
  --max-notional 10000 `
  --fail-on-reject
```

Run the promoted settlement candidate through the full paper/shadow handoff
chain in one command:

```powershell
python -m hft_cli pipeline-settlement-launch `
  --promotion runs\promotion\settlement_convergence `
  --out runs\pipelines\settlement_convergence_shadow `
  --adapter arrow_money `
  --mode shadow `
  --route-tag settlement_shadow `
  --max-order-qty 75 `
  --max-notional 10000 `
  --broker-runtime-session runs\runtime_sessions\settlement_shadow_latest `
  --require-broker-runtime-session `
  --allow-placeholder-schema `
  --fail-on-breach
```

Pipeline outputs:

```text
01_order_plan\...
02_staged_orders\...
03_launch\...
04_export\...
05_upload_pack\...
06_broker_readiness\...
settlement_launch_pipeline_components.csv
settlement_launch_pipeline_summary.csv
manifest.json
```

Without `--allow-placeholder-schema`, Arrow.money/iRage upload-pack readiness
and broker-readiness checks fail closed until real broker upload schemas are
reviewed. Add `--broker-schema-audit`, `--broker-mapping-draft`,
`--broker-mapped-orders`, `--broker-halt-export`,
`--broker-reconciliation`, or `--broker-runtime-session` when those broker
evidence folders exist; pair them with the matching `--require-broker-*` flag
to make that evidence mandatory in the final `06_broker_readiness` gate.

## Microprice Imbalance Sweep

Run replay robustness scenarios across imbalance thresholds, microprice edge
hurdles, hold timers, and latency assumptions:

```powershell
python -m hft_cli sweep-imbalance `
  --ticks data\atm_option_ticks.csv `
  --out runs\imbalance_sweep_2026_06_10 `
  --candidate-config runs\imbalance_edge_sweep_2026_06_10 `
  --feed-latency-us 0 50 `
  --order-latency-us 100 250 500 `
  --min-net-pnl 1 `
  --min-fills 10 `
  --max-drawdown 5000 `
  --fail-on-breach
```

Outputs include per-scenario replay folders plus:

```text
sweep_runs.csv
sweep_summary.csv
proof/proof_metrics.csv
proof/proof_checks.csv
proof/proof_summary.csv
manifest.json
```

## Lead-Lag Sweep

Run replay robustness scenarios across trigger and latency settings:

```powershell
python -m hft_cli sweep-leadlag `
  --leader data\futures.csv `
  --laggard data\atm_call.csv `
  --out runs\leadlag_sweep_2026_06_10 `
  --market india_nse_index_derivatives `
  --trigger-ticks 2 3 4 `
  --feed-latency-us 0 50 100 `
  --order-latency-us 100 250 500 `
  --min-net-pnl 1 `
  --min-fills 10 `
  --max-drawdown 5000 `
  --fail-on-breach
```

Outputs include per-scenario replay folders plus:

```text
sweep_runs.csv
sweep_summary.csv
proof/proof_metrics.csv
proof/proof_checks.csv
proof/proof_summary.csv
manifest.json
```

## Surface Quotes

Fit per-snapshot option surfaces and generate market-making quotes:

```powershell
python -m hft_cli quote-surface `
  --chain data\chain.csv `
  --futures data\futures.csv `
  --out runs\surface_quotes_2026_06_10 `
  --market india_nse_index_derivatives `
  --tte-years 0.08219 `
  --edge-ticks 2 `
  --max-market-spread-ticks 20 `
  --max-quotes-per-snapshot 50
```

Outputs:

```text
surface_quotes.csv
surface_quote_summary.csv
manifest.json
```

## Surface Quality Review

Check that fitted surface theoretical values beat current option mids against
future chain mids before spending replay or routing cycles:

```powershell
python -m hft_cli review-surface-quality `
  --quotes runs\surface_quotes_2026_06_10\surface_quotes.csv `
  --chain data\chain.csv `
  --out runs\surface_quotes_2026_06_10\surface_quality `
  --horizon-ns 1000000000 `
  --min-mae-improvement 0 `
  --min-improvement-rate 0.55 `
  --fail-on-breach
```

Outputs:

```text
surface_quality_details.csv
surface_quality_summary.csv
surface_quality_checks.csv
manifest.json
```

This is the surface-replay sanity gate: if the fitted theo cannot beat the
current mid as a predictor of future option mids, the market-making workflow
should remain in research.

## Surface Quote Review

Gate generated market-making quotes before replay or live routing:

```powershell
python -m hft_cli review-quotes `
  --quotes runs\surface_quotes_2026_06_10\surface_quotes.csv `
  --out runs\surface_quotes_2026_06_10\quote_review `
  --strategy surface_mm `
  --market india_nse_index_derivatives `
  --data-readiness-comparison runs\vendor_data\arrow_ticks_batch\comparison `
  --require-data-readiness-comparison `
  --min-quotes 20 `
  --min-instruments 10 `
  --max-marketable-quotes 0 `
  --min-quote-edge 0 `
  --max-market-spread-ticks 20 `
  --fail-on-breach
```

Outputs:

```text
quote_risk_summary.csv
quote_risk_checks.csv
quote_risk_by_instrument.csv
manifest.json
```

When `--require-data-readiness-comparison` is set, quote review fails closed
unless the supplied comparison summary is present and accepted. This keeps
surface market-making quotes from moving into replay or paper routing on
unproven vendor market data. The review summary and manifest retain strategy
and market identity so catalog evidence can verify that surface-quality,
quote-risk, and surface market-making pipeline artifacts all belong to the same
research track.

## Surface Quote Lifecycle Plan

Convert generated surface quote snapshots into a submit/replace/cancel plan
with exchange-message and outstanding-quote limits before paper routing:

```powershell
python -m hft_cli plan-quote-lifecycle `
  --quotes runs\surface_quotes_2026_06_10\surface_quotes.csv `
  --quote-risk-review runs\surface_quotes_2026_06_10\quote_review `
  --require-quote-risk-review `
  --surface-quality-review runs\surface_quotes_2026_06_10\surface_quality `
  --require-surface-quality `
  --out runs\surface_quotes_2026_06_10\quote_lifecycle `
  --quote-ttl-ns 1000000000 `
  --max-order-messages 500 `
  --max-active-quotes 60 `
  --max-messages-per-snapshot 40 `
  --expected-fills 25 `
  --max-order-to-trade-ratio 20 `
  --fail-on-breach
```

Outputs:

```text
quote_lifecycle_actions.csv
quote_lifecycle_route_orders.csv
quote_lifecycle_snapshots.csv
quote_lifecycle_checks.csv
quote_lifecycle_summary.csv
manifest.json
```

The planner de-duplicates each snapshot by `instrument_id` and side, replaces
quotes only when price or quantity changes, expires stale quotes when
`--quote-ttl-ns` is set, and adds final cancels unless `--no-final-cancel` is
used. The `quote_lifecycle_route_orders.csv` file contains only submit/replace
orders for staging, while cancel actions stay in the full lifecycle action log.
Lifecycle action id, reason, message count, quote age, and replace-order ids
are preserved through staged, launch, broker-neutral export, and built-in
upload-pack files. This makes OTR and quote-churn limits explicit before
Arrow.money/iRage upload preparation.
Use `--surface-quality-review` with `--require-surface-quality` to fail closed
unless `surface_quality_summary.csv` shows the fitted surface theo beat current
mids against future chain mids.

## Surface Market-Making Research Pipeline

Run the complete surface market-making research path from option-chain/futures
data through quote generation, quote review, replay sweep proof, scenario
selection, and promotion:

```powershell
python -m hft_cli pipeline-surface-mm-research `
  --chain data\chain.csv `
  --futures data\futures.csv `
  --out runs\surface_mm_pipeline_2026_06_10 `
  --market india_nse_index_derivatives `
  --market-portability runs\market_profiles\portability `
  --data-readiness-comparison runs\vendor_data\arrow_ticks_batch\comparison `
  --require-market-portability `
  --require-data-readiness-comparison `
  --surface-quality-horizon-ns 1000000000 `
  --require-surface-quality `
  --min-surface-quality-improvement-rate 0.55 `
  --max-market-spread-ticks 20 `
  --max-quotes-per-snapshot 20 `
  --quote-ttl-ns 500000000 1000000000 2000000000 `
  --order-latency-us 0 100 250 `
  --fill-depth-fraction 0.10 0.25 0.50 `
  --markout-horizon-ns 500000000 1000000000 `
  --min-net-pnl 1 `
  --min-fills 10 `
  --fail-on-breach
```

Outputs:

```text
01_quotes\surface_quotes.csv
02_surface_quality\surface_quality_summary.csv
02_quote_review\quote_risk_summary.csv
03_sweep\sweep_summary.csv
04_selection\selection_summary.csv
05_promotion\promotion_summary.csv
surface_mm_pipeline_stages.csv
surface_mm_pipeline_summary.csv
candidate_config.json
manifest.json
```

Use `--market-portability` with `--require-market-portability` to fail closed
before quote generation unless `market_portability_config.json` marks
`surface_market_making` ready for the pipeline `--market`.

## Surface Market-Making Launch Pipeline

Turn a passed surface market-making research pipeline into broker-prep artifacts
for paper or shadow trading:

```powershell
python -m hft_cli pipeline-surface-mm-launch `
  --surface-pipeline runs\surface_mm_pipeline_2026_06_10 `
  --out runs\surface_mm_launch_2026_06_10 `
  --mode shadow `
  --adapter arrow_money `
  --expected-strategy surface_mm `
  --expected-market india_nse_index_derivatives `
  --max-order-qty 75 `
  --max-notional 10000 `
  --price-band-pct 0.02 `
  --max-quote-order-messages 500 `
  --max-active-quotes 60 `
  --max-quote-messages-per-snapshot 40 `
  --expected-quote-fills 25 `
  --max-quote-otr 20 `
  --broker-runtime-session runs\runtime_sessions\surface_mm_shadow_latest `
  --require-broker-runtime-session `
  --allow-placeholder-schema `
  --fail-on-breach
```

Outputs:

```text
00_quote_lifecycle\quote_lifecycle_summary.csv
01_staged_orders\staged_orders.csv
02_launch\launch_orders.csv
03_export\broker_orders.csv
04_upload_pack\broker_upload_summary.csv
05_broker_readiness\broker_readiness_summary.csv
surface_mm_launch_pipeline_components.csv
surface_mm_launch_pipeline_summary.csv
manifest.json
```

The launch pipeline runs quote lifecycle planning before staging and blocks the
handoff when the generated quotes would exceed message, active-quote, churn, or
OTR limits. Staging uses `00_quote_lifecycle\quote_lifecycle_route_orders.csv`
so stale raw quote rows and unchanged repeated quotes are not routed, while
replace metadata survives into `03_export\broker_orders.csv`.
The root surface research preflight checks that the upstream research pipeline
is ready and that its strategy/market identity matches `--expected-strategy`
and `--expected-market` before any quote lifecycle or broker-prep artifacts are
created.
Use `--broker-runtime-session` and `--require-broker-runtime-session` to make
the nested `05_broker_readiness` gate require a continuing runtime guard before
surface-MM paper/shadow handoff.

## Order Exposure Review

Review staged, launch, or exported option order batches for notional, side
imbalance, instrument concentration, and Black-76 delta/vega exposure:

```powershell
python -m hft_cli review-order-exposure `
  --orders runs\launch\leadlag_shadow\launch_orders.csv `
  --out runs\risk\leadlag_shadow_exposure `
  --forward 1000 `
  --tte-years 0.08219 `
  --vol 0.20 `
  --max-abs-net-delta 1000 `
  --max-abs-net-vega 50000 `
  --max-gross-notional 1000000 `
  --max-side-imbalance 0.25 `
  --max-instrument-concentration 0.50 `
  --fail-on-breach
```

Outputs:

```text
order_exposure.csv
order_exposure_by_instrument.csv
order_exposure_checks.csv
order_exposure_summary.csv
manifest.json
```

If `option_type` and `strike` are absent, the review attempts to infer them
from supported `instrument_id` formats, including internal `CALL_1000_0`,
settlement `NIFTY_20260610_100C`, NSE compact `NIFTY24JUN22500CE`, and OCC
`SPY250620C00500000` symbols.

## Surface Market-Making Replay

Replay passive surface quotes against later option-chain snapshots. A bid quote
fills when a later best ask is at or below the quote; an ask quote fills when a
later best bid is at or above the quote.

```powershell
python -m hft_cli replay-surface-mm `
  --quotes runs\surface_quotes_2026_06_10\surface_quotes.csv `
  --chain data\chain.csv `
  --out runs\surface_mm_replay_2026_06_10 `
  --quote-risk-review runs\surface_quotes_2026_06_10\quote_review `
  --require-quote-risk-review `
  --quote-ttl-ns 1000000000 `
  --markout-horizon-ns 1000000000 `
  --fill-depth-fraction 0.25 `
  --order-latency-us 250 `
  --fill-model runs\fill_model\leadlag_shadow_latest
```

Outputs:

```text
quotes.csv
fills.csv
unfilled_quotes.csv
equity.csv
summary.csv
markouts.csv
markout_summary.csv
manifest.json
```

When the quote-risk review is required, replay writes empty replay artifacts
and a blocked `summary.csv` instead of simulating quotes that have not cleared
the hygiene gate.

## Surface Market-Making Sweep

Run passive surface quote replay across TTL, latency, fill-depth, and markout
horizon assumptions, then evaluate every replay folder with the proof gate:

```powershell
python -m hft_cli sweep-surface-mm `
  --quotes runs\surface_quotes_2026_06_10\surface_quotes.csv `
  --chain data\chain.csv `
  --out runs\surface_mm_sweep_2026_06_10 `
  --quote-risk-review runs\surface_quotes_2026_06_10\quote_review `
  --require-quote-risk-review `
  --quote-ttl-ns 500000000 1000000000 2000000000 `
  --order-latency-us 0 100 250 `
  --fill-depth-fraction 0.10 0.25 0.50 `
  --markout-horizon-ns 500000000 1000000000 `
  --min-net-pnl 1 `
  --min-fills 10 `
  --max-otr 50 `
  --fail-on-breach
```

Outputs include per-scenario replay folders plus:

```text
sweep_runs.csv
sweep_summary.csv
proof/proof_metrics.csv
proof/proof_checks.csv
proof/proof_summary.csv
manifest.json
```

When `--require-quote-risk-review` is set, the sweep writes failed proof and
sweep artifacts and skips replay scenarios unless the supplied quote-risk
summary passed. This keeps proof grids focused on quote sets that already
cleared pre-trade hygiene.

## Sweep Comparison

Rank parameter scenarios across multiple sweep output folders:

```powershell
python -m hft_cli compare-sweeps `
  --sweeps runs\leadlag_sweep_2026_06_10 runs\leadlag_sweep_2026_06_11 `
  --label 2026-06-10 `
  --label 2026-06-11 `
  --out runs\selection\leadlag `
  --min-pass-rate 1 `
  --min-sweeps 2 `
  --min-median-net-pnl 1 `
  --max-worst-drawdown 5000 `
  --fail-on-breach
```

Outputs:

```text
scenario_runs.csv
scenario_scores.csv
selection_summary.csv
```

## Scenario Promotion Gate

Convert a `compare-sweeps` selection folder into a paper/shadow promotion
decision and candidate config:

```powershell
python -m hft_cli promote-scenario `
  --selection runs\selection\leadlag `
  --out runs\promotion\leadlag `
  --min-pass-rate 1 `
  --min-sweeps 2 `
  --min-median-net-pnl 1 `
  --min-min-net-pnl 0 `
  --max-worst-drawdown 5000 `
  --min-median-fills 10 `
  --max-otr 50 `
  --fail-on-breach
```

Outputs:

```text
promotion_candidate.csv
promotion_checks.csv
promotion_summary.csv
candidate_config.json
manifest.json
```

## Launch Bundle

Package a promoted scenario and staged broker-neutral orders into a fail-closed
paper/shadow launch bundle:

```powershell
python -m hft_cli launch-bundle `
  --promotion runs\promotion\leadlag `
  --staged-orders runs\surface_quotes_2026_06_10\staged_orders `
  --out runs\launch\leadlag_shadow `
  --mode shadow `
  --adapter arrow_money `
  --require-quote-risk-review `
  --min-accepted-orders 10 `
  --min-acceptance-rate 1 `
  --max-total-notional 1000000 `
  --fail-on-breach
```

Outputs:

```text
launch_orders.csv
launch_checks.csv
launch_summary.csv
launch_config.json
manifest.json
```

For surface market-making orders staged from `surface_quotes`,
`--require-quote-risk-review` rejects launch bundles unless staging carries a
passed quote-risk review from `review-quotes`.

## Launch Order Export

Export a launch bundle into an adapter-labelled broker/paper order file. The
`arrow_money` and `irage` exports currently use the normalized schema with an
explicit placeholder status until real vendor upload samples are mapped:

```powershell
python -m hft_cli export-launch-orders `
  --launch runs\launch\leadlag_shadow `
  --out runs\exports\leadlag_shadow_arrow `
  --adapter arrow_money `
  --route-tag shadow_nse `
  --max-orders 100 `
  --fail-on-breach
```

Outputs:

```text
broker_orders.csv
broker_order_checks.csv
broker_order_summary.csv
broker_order_schema.csv
manifest.json
```

## Broker Upload Pack

Create a reviewable broker-upload pack from `broker_orders.csv` using the
built-in Arrow.money/iRage placeholder templates. By default this command
fails closed while the adapter schema is still marked as a placeholder; use
`--allow-placeholder-schema` only for dry-run or paper-review artifacts:

```powershell
python -m hft_cli pack-broker-upload `
  --export runs\exports\leadlag_shadow_arrow `
  --out runs\uploads\leadlag_shadow_arrow `
  --adapter arrow_money `
  --product MIS `
  --exchange NFO `
  --allow-placeholder-schema `
  --fail-on-breach `
  --fail-on-blocked-actions
```

Outputs:

```text
broker_upload_orders.csv
broker_upload_mapping.csv
broker_upload_checks.csv
broker_upload_summary.csv
broker_upload_schema.csv
broker_upload_action_queue.csv
broker_upload_config.json
broker_upload_runbook.md
manifest.json
```

The mapping file is emitted beside the upload-shaped orders so the final
Arrow.money/iRage column semantics can be reviewed before any live route is
enabled.
`broker_upload_summary.csv` also exposes `failed_check_count`,
`failed_check_names`, `first_failed_reason`, `primary_blocker_*`,
`action_queue_count`, `blocked_action_count`, `next_gate`,
`next_gate_help_command`, and `primary_action_status` fields so
schema-placeholder, built-in mapping, and empty-order blockers can be routed
from the one-row upload handoff. `broker_upload_action_queue.csv`,
`broker_upload_config.json`, and `broker_upload_runbook.md` mirror those
actions back to `pack-broker-upload` for scheduler handoff. Use
`--fail-on-blocked-actions` to fail only when blocked upload actions exist, or
`--fail-on-actions` when any upload action should stop automation.

## Vendor CSV Intake

Profile the first Arrow.money/iRage sample CSV, infer whether it is tick,
option-chain, order, or fill data, and emit a normalized mapping draft for
review:

```powershell
python -m hft_cli intake-vendor-csv `
  --sample vendor\arrow_ticks_sample.csv `
  --out mappings\arrow_ticks_intake `
  --adapter arrow_money `
  --kind auto `
  --fail-on-breach `
  --fail-on-blocked-actions `
  --fail-on-actions
```

Outputs:

```text
vendor_intake_columns.csv
vendor_intake_kind_scores.csv
vendor_intake_mapping_candidates.csv
vendor_intake_source_profile.json
vendor_intake_action_queue.csv
vendor_intake_config.json
vendor_intake_runbook.md
vendor_mapping_draft.csv
vendor_intake_summary.csv
manifest.json
```

The generated `vendor_mapping_draft.csv` uses `normalized_column`,
`source_column`, `default_value`, `required`, and `transform` columns so it can
be reviewed and then passed to `normalize-mapped-data`. The source profile and
manifest retain file, header, and mapping-draft SHA-256 fingerprints so a later
Arrow.money/iRage sample can be matched exactly to the reviewed mapping.
`vendor_intake_summary.csv` also exposes `failed_check_count`,
`failed_check_names`, `first_failed_reason`, and `primary_blocker_*` fields for
ambiguous auto-kind detection or the first unmapped normalized column.
It also writes `vendor_intake_action_queue.csv`,
`vendor_intake_config.json`, and `vendor_intake_runbook.md` with blocked
mapping or kind-selection actions, `next_gate`, `next_gate_help_command`,
`primary_action_status`, `primary_action`, and `next_actions`/
`blocked_actions` so `catalog-runs` can route raw Arrow.money/iRage sample
blockers directly back to `intake-vendor-csv --help`.
Use `--fail-on-blocked-actions` to fail only when blocked intake actions exist,
or `--fail-on-actions` when any raw-sample intake action should stop automation.

## Vendor Order Mapping Draft

Draft a reviewable mapping from the broker-neutral `broker_orders.csv` export
to a vendor upload/sample header. The draft can be edited and passed directly
to `map-broker-orders` after Arrow.money/iRage column semantics are reviewed:

```powershell
python -m hft_cli draft-order-mapping `
  --export runs\exports\leadlag_shadow_arrow `
  --sample vendor\arrow_order_upload_sample.csv `
  --out mappings\arrow_order_upload_draft `
  --adapter arrow_money `
  --default product=MIS `
  --fail-on-blocked-actions `
  --fail-on-unmapped
```

Outputs:

```text
order_mapping_draft.csv
order_mapping_draft_checks.csv
order_mapping_draft_action_queue.csv
order_mapping_draft_config.json
order_mapping_draft_runbook.md
order_mapping_draft_summary.csv
manifest.json
```

The draft marks suggested mappings, manual defaults, optional gaps, and
unmapped required vendor columns before any broker-specific upload file is
generated.
`order_mapping_draft_summary.csv` exposes `failed_check_count`,
`failed_check_names`, `first_failed_reason`, and `primary_blocker_*` fields so
the first unmapped required Arrow.money/iRage vendor column is schedulable from
the summary row. It also carries `action_queue_count`, `blocked_action_count`,
`next_gate`, `next_gate_help_command`, and `primary_action_status`.
`order_mapping_draft_action_queue.csv`, `order_mapping_draft_config.json`, and
`order_mapping_draft_runbook.md` mirror unmapped required vendor upload fields
so `catalog-runs` can route the broker-upload mapping repair back to
`draft-order-mapping`. Use `--fail-on-blocked-actions` to fail only when
blocked draft actions exist, or `--fail-on-actions` when any draft action should
stop the scheduler.

## Mapped Broker Order Export

Convert `broker_orders.csv` into a vendor-specific CSV shape using a mapping
file supplied from the reviewed Arrow.money/iRage sample schema:

```powershell
python -m hft_cli map-broker-orders `
  --export runs\exports\leadlag_shadow_arrow `
  --mapping vendor\arrow_order_upload_mapping.csv `
  --out runs\exports\leadlag_shadow_arrow_mapped `
  --adapter arrow_money `
  --output-file arrow_orders.csv `
  --fail-on-blocked-actions `
  --fail-on-breach
```

Mapping CSV:

```text
target_column,source_column,default_value,required,transform
symbol,instrument_id,,true,string
transaction_type,side,,true,side_text
quantity,qty,,true,int
limit_price,price,,true,float
product,,MIS,true,uppercase
validity,time_in_force,DAY,true,uppercase
```

Supported transforms are `identity`, `string`, `uppercase`, `lowercase`,
`int`, `float`, `side_text`, and `side_signed`.

Outputs:

```text
mapped_broker_orders.csv
mapped_order_checks.csv
mapped_order_action_queue.csv
mapped_order_config.json
mapped_order_runbook.md
mapped_order_summary.csv
mapped_order_schema.csv
manifest.json
```

`mapped_order_summary.csv` exposes `failed_check_count`,
`failed_check_names`, `first_failed_reason`, and `primary_blocker_*` fields for
the first failed vendor target column, so broker-readiness automation can route
Arrow.money/iRage mapping gaps directly to the missing field without opening
`mapped_order_checks.csv`. It also carries `action_queue_count`,
`blocked_action_count`, `next_gate`, `next_gate_help_command`, and
`primary_action_status`. `mapped_order_action_queue.csv`,
`mapped_order_config.json`, and `mapped_order_runbook.md` mirror missing or
blank mapped vendor targets so `catalog-runs` can route final upload-shape
mapping repairs back to `map-broker-orders`. Use `--fail-on-blocked-actions`
to fail only when blocked mapped-order actions exist, or `--fail-on-actions`
when any mapped-order action should stop the scheduler.

## Broker Integration Readiness

Combine adapter schema review, broker-neutral export, mapped/upload files,
optional halt-export, optional reconciliation, optional runtime-session,
optional resume-gate, and optional dispatch round-trip evidence into one
go/no-go record before Arrow.money/iRage paper or shadow routing:

```powershell
python -m hft_cli review-broker-readiness `
  --adapter arrow_money `
  --schema-audit runs\schema_audit\arrow_orders `
  --order-export runs\exports\leadlag_shadow_arrow `
  --mapping-draft mappings\arrow_order_upload_draft `
  --mapped-orders runs\exports\leadlag_shadow_arrow_mapped `
  --upload-pack runs\uploads\leadlag_shadow_arrow `
  --runtime-session runs\runtime_sessions\leadlag_shadow_latest `
  --resume-gate runs\resume\leadlag_shadow_latest `
  --dispatch-roundtrip runs\dispatch_roundtrip\leadlag_shadow_live_dryrun `
  --out runs\broker_readiness\leadlag_shadow_arrow `
  --require-mapping-draft `
  --require-mapped-orders `
  --require-runtime-session `
  --require-resume-gate `
  --require-route-readiness `
  --require-dispatch-roundtrip `
  --fail-on-blocked-actions `
  --fail-on-breach
```

Use `--allow-placeholder-schema` only for dry-run review while Arrow.money/iRage
schemas are still placeholders. Without it, placeholder schemas fail closed
unless schema audit, order-mapping draft, and mapped-order export artifacts are
all supplied and ready for the same adapter; in that case the readiness summary
records `schema_review_mode=reviewed_vendor_mapping` and can emit
`broker_integration_ready`. When dispatch round-trip evidence is supplied for
live dry-run readiness, broker readiness also verifies the carried
`route_readiness` proof for strategy/market identity and zero route gaps before
Arrow.money/iRage handoff. Scale-up, cutover, and route-enable artifacts carry
`schema_reviewed` and `schema_review_mode` forward so downstream route decisions
can distinguish reviewed vendor mappings from unreviewed placeholders.
When broker-neutral exports contain quote lifecycle fields, the built-in
normalized, Arrow.money, and iRage review templates carry `lifecycle_action`,
`lifecycle_action_id`, `lifecycle_reason`, `lifecycle_message_count`,
`quote_age_ns`, and `replaces_order_id` into the upload-shaped CSV for broker
schema review.
`--order-export` and `--upload-pack` may point at a launch-pipeline root;
broker readiness resolves nested `04_export`/`05_upload_pack` or surface-MM
`03_export`/`04_upload_pack` summaries and fingerprints the resolved files in
the manifest, including the broker dispatch round-trip config and manifest when
supplied.
When `--runtime-session` is supplied, broker readiness requires the runtime
guard to be continuing. `--require-runtime-session` makes that evidence
mandatory before paper/shadow routing. Runtime-session target mode, strategy,
and market identity are retained in the broker readiness summary for later
scale-up continuity checks.
When `--resume-gate` is supplied, broker readiness retains the resume
authorization's strategy/market identity, incident identity, and
`proof_refresh_*` context. `--require-resume-gate` fails closed unless
`resume_summary.csv` is present and ready, which is useful for post-halt restart
reviews.
When `--dispatch-roundtrip` is supplied, broker readiness retains the proved
dry-run target mode, strategy, market, scenario, dispatch batch, request count,
accepted acknowledgements, and missing/rejected/unmatched acknowledgement
counts, failed-check count, route-enable dispatch round-trip failed-check
count from the round-trip config when present, the round-trip shadow
broker-readiness aggregate, the broker-readiness-carried shadow broker
aggregate, plus the nested route dispatch round-trip proof
batch and quality counters. If the round-trip config carries shadow-broker
broker-vendor wrapper aggregates, broker readiness revalidates coverage and
retains them as `shadow_broker_vendor_data_readiness_*` plus nested
`shadow_broker_readiness.broker_vendor_data_readiness` config, and as
`broker_shadow_broker_vendor_data_readiness_*` plus nested
`broker_shadow_broker_readiness.broker_vendor_data_readiness` config, failing
closed when either wrapper aggregate is partial, unready, or dirty. If the
round-trip config carries
`roundtrip_vendor_market_data_batch`, broker readiness revalidates the
adapter/market, dataset, source-file, header-fingerprint, mapping, and
comparison proof and retains it as `dispatch_roundtrip_vendor_market_data_batch_*`
summary fields plus `dispatch_roundtrip.vendor_market_data_batch` config.
`--vendor-market-data-batch` may point directly at a
`pipeline-vendor-market-data-batch` output directory or
`vendor_market_data_batch_config.json`; broker readiness merges that artifact
as both the generic round-trip vendor-data proof and the broker-specific
readiness-native proof, then fingerprints the batch config and manifest.
If the round-trip config carries
`roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch`, broker
readiness revalidates the broker-readiness final dispatch batch proof and
retains it as `broker_dispatch_roundtrip_vendor_market_data_batch_*` summary
fields plus `dispatch_roundtrip.broker_dispatch_roundtrip_vendor_market_data_batch`
config. If the round-trip config carries
`roundtrip_broker_vendor_data_readiness`, broker readiness revalidates the
wrapper and retains it as `broker_vendor_data_readiness_*` summary fields plus
`dispatch_roundtrip.broker_vendor_data_readiness` config. When both
readiness-native broker vendor-data blocks and older round-trip or
component-retained broker vendor-data proof blocks are present, broker
readiness prefers the readiness-native blocks and fails closed from that
selected proof.
`--require-dispatch-roundtrip` fails closed unless the dry-run
dispatch plan, non-submitting send packet, acknowledgement reconciliation, and
route proof chain passed as one round-trip proof with zero failed component
checks, zero carried route-enable dispatch round-trip failed checks, and clean
shadow broker-readiness, broker-vendor wrapper, and vendor market-data batch
proofs when supplied.

Outputs:

```text
broker_readiness_items.csv
broker_readiness_checks.csv
broker_readiness_summary.csv
broker_readiness_action_queue.csv
broker_readiness_config.json
broker_readiness_runbook.md
manifest.json
```

If the schema audit directory contains `adapter_schema_review_checklist.csv`,
broker readiness records it as a manifest input and carries checklist presence,
blocked-check names, and review-check names into `broker_readiness_summary.csv`
and `broker_readiness_config.json`.
`broker_readiness_action_queue.csv` flattens failed readiness checks into a
priority-ordered blocked-action queue with the inferred component, next CLI
gate, and `next_gate_help_command` for runner or operator handoff.
`broker_readiness_config.json` mirrors that queue as `ready_action_count`,
`blocked_action_count`, `next_gate`, `next_gate_help_command`, `next_actions`,
`ready_actions`, `blocked_actions`, `primary_action_status`, and
`primary_action`, so schedulers can consume broker readiness blockers from JSON
without parsing the CSV.
`broker_readiness_runbook.md` is a human-readable handoff generated from the
same summary, component, and action-queue data and is fingerprinted in the
manifest. Use `--fail-on-blocked-actions` to stop automation only when blocked
broker-readiness actions exist, or `--fail-on-actions` when any readiness
handoff action should stop the run.

## Broker Fill Reconciliation

Reconcile exported paper/shadow orders against normalized broker or drop-copy
fills:

```powershell
python -m hft_cli reconcile-broker-fills `
  --export runs\exports\leadlag_shadow_arrow `
  --fills logs\arrow_shadow_fills.csv `
  --out runs\reconciliation\leadlag_shadow_arrow `
  --adapter arrow_money `
  --min-order-fill-rate 0.8 `
  --max-overfilled-orders 0 `
  --max-mismatched-orders 0 `
  --max-unmatched-fills 0 `
  --max-adverse-slippage 0.05 `
  --fail-on-breach `
  --fail-on-blocked-actions
```

Outputs:

```text
order_reconciliation.csv
unmatched_fills.csv
reconciliation_checks.csv
reconciliation_summary.csv
reconciliation_action_queue.csv
reconciliation_config.json
reconciliation_runbook.md
manifest.json
```

`reconciliation_summary.csv` carries `failed_check_count`,
`failed_check_names`, `first_failed_reason`, `primary_blocker_*`,
`action_queue_count`, `blocked_action_count`, `next_gate`,
`next_gate_help_command`, and `primary_action_status` so failed fill-rate,
overfill, mismatch, unmatched-fill, and slippage gates are scheduler-visible.
`reconciliation_action_queue.csv`, `reconciliation_config.json`, and
`reconciliation_runbook.md` mirror those failed checks back to
`reconcile-broker-fills` for broker-readiness handoff. Use
`--fail-on-blocked-actions` to fail only when blocked reconciliation actions
exist, or `--fail-on-actions` when any reconciliation action should stop
automation.

## Shadow Session Report

Gate a full paper/shadow loop by combining launch, export, reconciliation, and
optional runtime-session monitor and broker-readiness artifacts:

```powershell
python -m hft_cli shadow-session-report `
  --launch runs\launch\leadlag_shadow `
  --export runs\exports\leadlag_shadow_arrow `
  --reconciliation runs\reconciliation\leadlag_shadow_arrow `
  --runtime-session runs\runtime_sessions\leadlag_shadow_latest `
  --broker-readiness runs\broker_readiness\leadlag_shadow_arrow `
  --out runs\sessions\leadlag_shadow_2026_06_10 `
  --require-runtime-session `
  --require-broker-readiness `
  --min-order-fill-rate 0.8 `
  --max-unmatched-fills 0 `
  --max-mismatched-orders 0 `
  --max-overfilled-orders 0 `
  --max-adverse-slippage 0.05 `
  --fail-on-breach
```

Outputs:

```text
shadow_session_metrics.csv
shadow_session_checks.csv
shadow_session_summary.csv
manifest.json
```

When `--runtime-session` is supplied, a halted runtime guard blocks session
acceptance by default. Use `--require-runtime-session` to fail closed until the
paper/shadow monitor evidence is present. Runtime-session target mode,
strategy, and market are retained in the shadow session metrics and summary so
later comparison and evidence-review gates can prove which strategy was
actually monitored. If the runtime session includes proof-refresh evidence, the
shadow-session gate retains its ready/source/identity fields and fails closed
when the runtime proof-refresh evidence is unready, mixed, or for a different
strategy/market. Runtime broker resume-gate evidence is also carried as
`runtime_broker_resume_*` metrics and summary fields; when the runtime session
requires or provides that gate, the shadow-session report requires a ready
resume authorization plus matching strategy, market, and resume proof-refresh
identity. When broker-readiness evidence is supplied, the session gate retains
adapter/schema review state plus the carried broker route-readiness and dispatch
round-trip proof, and fails closed on broker readiness, adapter, strategy,
market, scenario, acknowledgement, rejection, route-gap, or broker vendor-data
wrapper readiness mismatches. The summary also exposes
`broker_vendor_data_readiness_*` fields so Arrow.money/iRage data-readiness
proof remains visible at the shadow-session acceptance layer. Use
`--require-broker-readiness` to require that proof for every session record.

## Shadow Session Comparison

Compare multiple paper/shadow session reports before allowing the workflow to
scale up:

```powershell
python -m hft_cli compare-shadow-sessions `
  --sessions runs\sessions\leadlag_shadow_2026_06_10 runs\sessions\leadlag_shadow_2026_06_11 `
  --out runs\sessions\leadlag_shadow_comparison `
  --label 2026-06-10 `
  --label 2026-06-11 `
  --min-sessions 2 `
  --min-acceptance-rate 1 `
  --min-median-order-fill-rate 0.8 `
  --min-worst-order-fill-rate 0.7 `
  --max-runtime-halted-sessions 0 `
  --max-worst-adverse-slippage 0.05 `
  --fail-on-breach
```

Outputs:

```text
shadow_session_runs.csv
shadow_session_comparison_checks.csv
shadow_session_comparison_summary.csv
manifest.json
```

When runtime-session evidence is present, the comparison gate fails closed if
accepted sessions mix runtime strategy or market identities. The comparison
summary exposes `strategy`, `market`, and missing/mixed identity counts for the
experiment catalog and strategy-evidence review. Accepted sessions with runtime
proof-refresh evidence must also have ready, non-mixed proof-refresh identity
for the same strategy/market across the comparison set. If accepted sessions
carry runtime broker resume-gate evidence, the comparison also requires ready
resume authorization, ready resume proof-refresh state, and one consistent
broker resume strategy/market/proof identity across the comparison set. If any
accepted session carries broker-readiness evidence, all accepted sessions must
carry ready broker-readiness evidence for one adapter, one broker route-readiness
strategy/market, and one broker dispatch round-trip strategy/market/scenario
with ready broker vendor-data wrapper proof and zero route gaps, missing
request acknowledgements, rejected orders, wrapper failed checks, and
unmatched acknowledgements.

## Controlled Scale-Up Plan

Convert accepted evidence and shadow sessions into explicit size limits and
kill switches:

```powershell
python -m hft_cli plan-scaleup `
  --evidence runs\evidence\leadlag_shadow `
  --shadow-comparison runs\sessions\leadlag_shadow_comparison `
  --launch runs\launch\leadlag_shadow `
  --order-exposure runs\risk\leadlag_shadow_exposure `
  --instrument-metadata runs\risk\leadlag_shadow_instruments `
  --proof-refresh runs\proof_refresh\leadlag_shadow_latest `
  --data-readiness runs\data_readiness\india_nse_2026_06_10 `
  --data-readiness-comparison runs\data_readiness\india_nse_comparison `
  --strategy-portfolio runs\strategy_portfolios\india_research_paper `
  --route-readiness runs\evidence\leadlag_route_readiness `
  --broker-readiness runs\broker_readiness\leadlag_shadow_arrow `
  --out runs\scaleup\leadlag_shadow `
  --target-mode shadow `
  --expected-strategy lead_lag_taker `
  --expected-market india_nse_index_derivatives `
  --allowed-adapter arrow_money `
  --min-shadow-sessions 2 `
  --min-shadow-acceptance-rate 1 `
  --min-worst-order-fill-rate 0.8 `
  --max-worst-adverse-slippage 0.05 `
  --max-scale-multiplier 1 `
  --max-orders-per-session 100 `
  --max-session-notional 100000 `
  --max-gross-notional 1000000 `
  --max-telemetry-age-ns 5000000000 `
  --max-lifecycle-orders 300 `
  --max-replace-orders 100 `
  --max-open-order-count 10 `
  --max-open-order-qty 500 `
  --max-open-order-notional 100000 `
  --max-open-order-age-ns 5000000000 `
  --max-gross-position-qty 1000 `
  --max-abs-net-position-qty 250 `
  --max-abs-net-delta 100 `
  --max-abs-net-vega 250 `
  --stop-loss 5000 `
  --require-instrument-metadata `
  --require-proof-refresh `
  --require-data-readiness `
  --require-data-readiness-comparison `
  --require-strategy-portfolio `
  --require-route-readiness `
  --require-broker-readiness `
  --require-resume-gate `
  --require-dispatch-roundtrip `
  --fail-on-breach
```

Outputs:

```text
scaleup_plan.csv
scaleup_checks.csv
scaleup_summary.csv
scaleup_config.json
manifest.json
```

`scaleup_config.json` keeps the legacy `failed_checks` name list and also
adds `failed_check_count` plus `primary_blocker`, the first failed check as a
structured record with value, operator, threshold, passed, and reason fields.

For lead-lag, imbalance, parity-box, settlement convergence, or surface
market-making handoffs, `--launch` may point at the launch-pipeline root. In
that case scale-up reads the nested launch summary and automatically includes
nested broker-readiness evidence when present, so `--require-broker-readiness`
can gate the pipeline folder directly. Scale-up also reads the root
`*_launch_pipeline_summary.csv`, preserves it in the generic
`launch_pipeline` config block, and fails closed if its ready status or
strategy/market identity disagrees with the evidence or explicit expected
identity. Surface-MM keeps the legacy `surface_launch_pipeline` block as a
compatibility alias.
If broker readiness included runtime-session evidence, `scaleup_summary.csv`
and `scaleup_config.json` retain the runtime guard action/halt status plus the
runtime target mode, strategy, and market for the session that fed the broker
gate.
If the shadow-session comparison carried broker vendor-data wrapper proof,
scale-up retains `shadow_broker_vendor_data_readiness_*` fields and a nested
`shadow_broker_readiness.broker_vendor_data_readiness` config block, and fails
closed when the comparison-level Arrow.money/iRage wrapper proof is partial,
unready, or has failed checks.
`manifest.json` fingerprints the resolved evidence, shadow-comparison, launch,
launch-pipeline, proof-refresh, metadata, data-readiness, data-readiness
comparison, exposure, route-readiness, broker-readiness summary CSVs, and
broker-readiness config JSON sidecars rather than only the input folders, so
scale-up handoffs can prove the exact records behind each recommendation. If a
strategy portfolio allocation is supplied, scale-up reads
`strategy_portfolio_summary.csv` and `strategy_portfolio_allocations.csv`,
requires a ready positive allocation for the scale-up strategy/market when
`--require-strategy-portfolio` is set, and caps
`max_notional_per_session` at the selected allocation notional. The previous
pre-portfolio notional cap, selected allocation, eligibility reason, and
whether the portfolio cap was applied are retained in `scaleup_summary.csv`
and the nested `strategy_portfolio` block in `scaleup_config.json`. Scale-up
also carries the portfolio-level strategy/market diversity requirements,
allocated strategy/market counts, top concentration names, and maximum
strategy/market allocation weights so later runtime and broker gates can audit
why the selected allocation was allowed without reopening the portfolio folder.
If a launch-pipeline broker-readiness summary is thin but its
`broker_readiness_config.json` retains
`broker_dispatch_roundtrip_vendor_market_data_batch`, scale-up hydrates the
operator-visible `broker_dispatch_roundtrip_vendor_market_data_batch_*` summary
fields and carries the same proof into `scaleup_config.json`. When the
data-readiness comparison comes from a vendor onboarding batch, scale-up also
fingerprints the sibling `vendor_market_data_batch_config.json` and carries its
dataset/header/mapping proof into `scaleup_config.json`.
Use `--route-readiness` with `--require-route-readiness` to fail closed unless
the market-portability, strategy-evidence, and file-provenance-gated
`ops_launch` evidence chain has accepted the exact strategy/market route.
If broker readiness included resume-gate evidence, scale-up also retains the
resume authorization identity, prior incident identity, and resume
`proof_refresh_*` context. `--require-resume-gate` fails closed unless broker
readiness supplied a ready resume gate with strategy/market and proof-refresh
identity matching the scale-up identity.
If broker readiness included dispatch round-trip evidence, scale-up also
retains the proved dry-run target mode, strategy, market, scenario, dispatch
batch, request count, accepted acknowledgements, failed-check count, and
route-enable dispatch round-trip failed-check count, and missing, rejected, and
unmatched acknowledgement counts, plus the nested route proof target, identity,
batch, request, and ack quality fields. `--require-dispatch-roundtrip` fails
closed unless that broker dry-run proof and its route proof are present, ready,
identity-matched, count-matched, and clean.
If broker readiness carried final vendor market-data batch proof from the dry-run
round-trip, scale-up revalidates the adapter/market, dataset, source-file,
header-fingerprint, mapping, and comparison evidence and retains it as
`broker_dispatch_roundtrip_vendor_market_data_batch_*` summary fields plus
`broker_readiness.dispatch_roundtrip.vendor_market_data_batch` config. Broker
readiness may also supply the same broker-specific proof under
`broker_readiness.dispatch_roundtrip.broker_dispatch_roundtrip_vendor_market_data_batch`
after revalidating the round-trip broker proof chain. Scale-up prefers that
broker-specific block when present and falls back to the generic
`vendor_market_data_batch` block for older readiness artifacts.
If broker readiness carried dispatch round-trip shadow broker-readiness proof,
scale-up revalidates it and retains the separate `broker_shadow_broker_*`
fields so broker-stage proof can be audited independently from the
shadow-session comparison aggregate. If that broker-readiness shadow proof
included Arrow.money/iRage broker-vendor wrapper evidence, scale-up also
retains `broker_shadow_broker_vendor_data_readiness_*` fields plus nested
`broker_readiness.shadow_broker_readiness.broker_vendor_data_readiness` config,
and fails closed when the wrapper proof is partial, unready, or failed.
If the shadow-session comparison carries broker-readiness evidence, scale-up
also verifies that accepted sessions all carried ready broker proof for one
adapter, one route-readiness strategy/market, and one broker dispatch
round-trip strategy/market/scenario with zero route gaps and clean
acknowledgement quality before emitting the controlled scale-up config.
Use `--expected-strategy` and `--expected-market` to fail closed unless the
strategy-evidence summary carries the intended strategy and market identity.
Those identities are retained in `scaleup_summary.csv` and `scaleup_config.json`
for runtime guard, halt, and resume traceability.
When proof-refresh evidence is supplied, scale-up also requires its
strategy/market identity to match the evidence or explicit expected identity,
and blocks summaries that report mixed proof-refresh identities. If the shadow
comparison carried runtime proof-refresh evidence, scale-up validates that
accepted sessions used ready, non-mixed proof-refresh identity for the same
strategy/market before writing a scale-up config.
When `--target-mode live_dryrun` is used, scale-up automatically requires
route readiness, broker readiness plus broker runtime-session evidence with a
continuing runtime guard, broker dispatch round-trip proof with clean
acknowledgements, matching route proof, and matching runtime/dispatch
strategy-market identity.

## Runtime Telemetry Snapshot

Build a guard-ready telemetry row from scale-up config, broker export, broker
upload pack, reconciliation, instrument metadata, PnL, open-order, and position
snapshots:

```powershell
python -m hft_cli build-runtime-telemetry `
  --scaleup runs\scaleup\leadlag_shadow `
  --export runs\exports\leadlag_shadow_latest `
  --upload-pack runs\uploads\leadlag_shadow_arrow `
  --reconciliation runs\reconciliation\leadlag_shadow_latest `
  --instrument-metadata runs\instrument_metadata\leadlag_shadow_latest `
  --pnl logs\leadlag_shadow_pnl.csv `
  --open-orders logs\open_orders.csv `
  --positions logs\positions.csv `
  --out runs\telemetry\leadlag_shadow_latest `
  --fail-on-breach
```

Outputs:

```text
runtime_telemetry.csv
runtime_telemetry_sources.csv
runtime_telemetry_checks.csv
runtime_telemetry_summary.csv
manifest.json
```

For lead-lag, imbalance, parity-box, settlement convergence, or surface
market-making handoffs, `--export` and `--upload-pack` may point at the
launch-pipeline root; telemetry will read the nested broker export and
upload-pack summaries from that folder. Upload-pack summaries carry
`lifecycle_orders` and `replace_orders` into runtime guardrails.
`runtime_telemetry_sources.csv` records the resolved CSV path for each supplied
source, and `manifest.json` fingerprints those resolved files for audit
traceability.
Telemetry carries the scale-up `strategy` and `market` identities from
`scaleup_config.json`; missing identity fails closed before guard evaluation.
When scale-up required proof-refresh evidence, telemetry also carries
`proof_refresh_*` fields from the scale-up config and fails closed if the proof
is missing, unready, mixed, or for a different strategy/market.
When scale-up required broker resume-gate evidence, telemetry also carries
`broker_resume_*` fields from the scale-up config and fails closed if the
resume authorization, its strategy/market identity, or its proof-refresh
identity is missing or stale.
When scale-up required or supplied strategy portfolio allocation evidence,
telemetry also carries `strategy_portfolio_*` fields from the scale-up config,
including selected profile, strategy, market, allocation notional, and whether
the portfolio cap was applied. These telemetry fields now also include
portfolio-level strategy/market diversity requirements, allocated
strategy/market counts, top concentration names, and maximum aggregate
strategy/market allocation weights.
Position snapshots can provide total Greek columns such as `net_delta` and
`net_vega`, or unit columns such as `unit_delta` and `unit_vega` with
`net_qty`/`position`/`qty`; telemetry emits `abs_net_delta` and `abs_net_vega`
for runtime guard checks. Position notional is derived from total columns such
as `signed_notional`, `net_notional`, or `gross_notional`, or from quantities
with mark columns such as `mark_price`, `last`, `price`, or bid/ask midpoint.
Open-order notional is derived from remaining/open notional fields when present,
or from active remaining quantity and `limit_price`/`price`/side-aware bid/ask
marks. Stale-order age uses `open_order_age_ns`/`order_age_ns` when provided,
or active order timestamps such as `created_ts_ns`, `order_ts_ns`, or `ts_ns`
with `--snapshot-ts-ns`.

## Runtime Scale-Up Guard

Evaluate live or paper telemetry snapshots against the scale-up limits, kill
switches, and optional telemetry freshness window:

```powershell
python -m hft_cli monitor-scaleup-guard `
  --scaleup runs\scaleup\leadlag_shadow `
  --telemetry runs\telemetry\leadlag_shadow_latest `
  --out runs\guards\leadlag_shadow_latest `
  --as-of-ts-ns 1781248200000000000 `
  --max-telemetry-age-ns 5000000000 `
  --fail-on-halt `
  --fail-on-actions
```

`--telemetry` accepts either the telemetry output folder or the
`runtime_telemetry.csv` file directly.

Telemetry CSV columns:

```text
target_mode,strategy,market,scenario_key,adapter,orders_sent,lifecycle_orders,replace_orders,session_notional,realized_pnl,total_failed_component_checks,broker_upload_pack_provided,broker_upload_pack_ready,broker_upload_failed_checks,unmatched_fills,mismatched_orders,overfilled_orders,worst_adverse_slippage,instrument_metadata_provided,instrument_metadata_passed,instrument_parse_coverage,min_instrument_parse_coverage,unparsed_instruments,proof_refresh_provided,proof_refresh_ready,proof_refresh_strategy,proof_refresh_market,proof_refresh_mixed_identity,broker_resume_gate_provided,broker_resume_gate_ready,broker_resume_strategy,broker_resume_market,broker_resume_proof_refresh_ready,broker_resume_proof_refresh_strategy,broker_resume_proof_refresh_market,open_order_count,open_order_qty,open_order_notional,oldest_open_order_age_ns,gross_position_qty,abs_net_position_qty,gross_position_notional,net_position_notional,abs_net_position_notional,net_delta,abs_net_delta,net_vega,abs_net_vega
```

The runtime guard compares telemetry `strategy` and `market` against the
scale-up config, the same way it checks scenario and adapter continuity.
If proof refresh was required or supplied at scale-up, the guard also requires
runtime telemetry to carry ready, non-mixed proof-refresh identity matching the
scale-up proof target.
If broker resume-gate evidence was required or supplied at scale-up, the guard
also requires runtime telemetry to carry a ready resume authorization and ready
resume proof-refresh identity matching the scale-up strategy and market.
If strategy portfolio allocation evidence was required or supplied at scale-up,
the guard also requires the selected allocation to be ready, eligible, identity
matched, positive, and large enough for the observed `session_notional`; this
appears as an explicit `strategy_portfolio_session_notional` check in
`runtime_guard_checks.csv`. The guard summary/config preserves the same
portfolio concentration fields carried by telemetry, so a halt packet or
runtime session can explain the paper/shadow allocation context without
reopening the scale-up folder.

Outputs:

```text
runtime_guard_metrics.csv
runtime_guard_checks.csv
runtime_guard_summary.csv
runtime_guard_action_queue.csv
runtime_guard_config.json
runtime_guard_runbook.md
manifest.json
```

`runtime_guard_summary.csv` and `runtime_guard_config.json` expose
`failed_check_count`, `failed_check_names`, `first_failed_reason`,
`primary_blocker_*`, `action_queue_count`, `ready_action_count`,
`blocked_action_count`, `next_gate`, `next_gate_help_command`, and
`primary_action_status`. `runtime_guard_action_queue.csv` and
`runtime_guard_runbook.md` turn guard halts into scheduler-ready actions,
usually routing runtime limit and risk breaches to `plan-halt-response`, while
scale-up readiness, proof-refresh, and resume-gate identity blockers point back
to their repair gates. Use `--fail-on-actions` to fail whenever a guard action
is queued, or `--fail-on-blocked-actions` to fail only when blocked guard
actions appear.

## Runtime Session Monitor

Build telemetry, evaluate the scale-up guard, and write a halt-response packet
when the guard asks routing to stop:

```powershell
python -m hft_cli monitor-runtime-session `
  --scaleup runs\scaleup\leadlag_shadow `
  --export runs\launch_pipelines\surface_mm_arrow `
  --upload-pack runs\launch_pipelines\surface_mm_arrow `
  --reconciliation runs\reconciliation\leadlag_shadow_latest `
  --instrument-metadata runs\instrument_metadata\leadlag_shadow_latest `
  --pnl logs\leadlag_shadow_pnl.csv `
  --open-orders logs\open_orders.csv `
  --positions logs\positions.csv `
  --out runs\runtime_sessions\leadlag_shadow_latest `
  --as-of-ts-ns 1781248200000000000 `
  --max-telemetry-age-ns 5000000000 `
  --fail-on-breach `
  --fail-on-blocked-actions
```

Outputs:

```text
01_telemetry\runtime_telemetry.csv
02_guard\runtime_guard_summary.csv
03_halt_response\halt_response_summary.csv
runtime_session_steps.csv
runtime_session_summary.csv
runtime_session_action_queue.csv
runtime_session_config.json
runtime_session_runbook.md
manifest.json
```

`03_halt_response` is created only when the guard halts and
`--skip-halt-response` is not set. This gives paper/shadow automation one
top-level go/no-go artifact while preserving the detailed telemetry, guard, and
halt-response evidence folders. The session summary carries
`guard_failed_check_names` and `guard_first_failed_reason` when the runtime
guard blocks routing, plus `proof_refresh_*` fields from telemetry/guard so
shadow-session and broker-readiness reviews can trace the proof freshness state
that fed the monitor. It also retains `broker_resume_*` fields so post-halt
resume authorization and proof identity remain visible after runtime guard
evaluation. When scale-up uses strategy portfolio allocation, the session
steps and summary also retain `strategy_portfolio_*` fields, including selected
strategy/market, eligibility, allocation weight/notional, pre-cap notional, and
whether the portfolio cap constrained session notional, plus the carried
strategy/market concentration counts and maximum aggregate allocation weights.
`runtime_session_summary.csv` and `runtime_session_config.json` also expose
`failed_check_count`, `failed_check_names`, `first_failed_reason`,
`primary_blocker_*`, `action_queue_count`, `ready_action_count`,
`blocked_action_count`, `next_gate`, `next_gate_help_command`, and
`primary_action_status`. `runtime_session_action_queue.csv` and
`runtime_session_runbook.md` hand off blocked telemetry repairs back to
`monitor-runtime-session`, skipped or failed halt-response packets back to
`plan-halt-response`, and ready halt packets forward to
`export-halt-response`. Use `--fail-on-actions` to fail on any queued runtime
action, or `--fail-on-blocked-actions` to fail only when runtime-session
actions are blocked.
The top-level `manifest.json` fingerprints the resolved scale-up config,
runtime source snapshots, telemetry artifacts, guard artifacts, child
manifests, and halt-response artifacts when a halt packet is created, so the
session report can prove the exact runtime chain that fed the go/no-go outcome.

## Halt Response Plan

Convert a runtime guard halt into broker-neutral cancel and flatten action files:

```powershell
python -m hft_cli plan-halt-response `
  --guard runs\guards\leadlag_shadow_latest `
  --open-orders logs\open_orders.csv `
  --positions logs\positions.csv `
  --out runs\halt_response\leadlag_shadow_latest `
  --fail-on-breach `
  --fail-on-blocked-actions
```

Open-order CSV inputs may include `client_order_id`, `broker_order_id`,
`instrument_id`, `side`, `qty`, `filled_qty`, `open_qty`, and `status`.
Position CSV inputs should include `instrument_id`, `net_qty`, and executable
flatten prices such as `market_bid`/`market_ask`, `bid`/`ask`, `last`, or
`price`.

Outputs:

```text
halt_cancel_orders.csv
halt_flatten_orders.csv
halt_response_checks.csv
halt_response_summary.csv
halt_response_action_queue.csv
halt_response_runbook.md
halt_response_config.json
manifest.json
```

`halt_response_config.json` keeps the guard-trigger context and also exposes
the response-plan `failed_check_count`, `failed_checks`, and structured
`primary_blocker`, so emergency automation can distinguish the guard halt from
the first failed cancel/flatten packet check. It also mirrors the scheduler
handoff as `action_queue_count`, `next_gate`, `next_gate_help_command`,
`primary_action`, `next_actions`, and status-sliced `ready_actions`,
`blocked_actions`, and `review_actions`.

`halt_response_summary.csv`, `halt_cancel_orders.csv`, and
`halt_flatten_orders.csv` include the guard failed check names, first halt
reason, strategy, and market so emergency action files show why the
cancel/flatten packet exists and which scaled strategy produced it. They also
retain `proof_refresh_*` and `proof_source` fields from the runtime guard so a
halt packet can be tied back to the fresh proof state that authorized the
runtime session.
`halt_response_action_queue.csv` and `halt_response_runbook.md` route non-halt
guard states and missing executable flatten prices back to the next CLI gate
before a scheduler trusts the cancel/flatten packet. Add `--fail-on-actions` to
fail on any queued response-plan action, or `--fail-on-blocked-actions` to fail
only when the queue contains blocked actions.
The manifest fingerprints the resolved runtime guard summary/check files plus
the open-order and position snapshots used to create the cancel/flatten packet.

## Halt Response Export

Map halt-response cancel and flatten actions into broker/vendor file shapes
using reviewed CSV mappings:

```powershell
python -m hft_cli export-halt-response `
  --halt-response runs\halt_response\leadlag_shadow_latest `
  --cancel-mapping mappings\arrow_cancel_orders.csv `
  --flatten-mapping mappings\arrow_flatten_orders.csv `
  --adapter arrow_money `
  --cancel-output-file arrow_cancel_orders.csv `
  --flatten-output-file arrow_flatten_orders.csv `
  --out runs\halt_exports\leadlag_shadow_latest `
  --fail-on-breach `
  --fail-on-blocked-actions
```

Both mapping files use:

```text
target_column,source_column,default_value,required,transform
```

If no mapping is supplied for an action type, the broker-neutral action file is
passed through unchanged. This keeps the halt workflow usable before the real
Arrow.money/iRage emergency action schemas arrive.
The manifest fingerprints the exact halt-response summary, cancel actions,
flatten actions, and any cancel/flatten mapping files used for the broker
export.

Outputs:

```text
broker_cancel_orders.csv
broker_flatten_orders.csv
halt_response_export_checks.csv
halt_response_export_summary.csv
halt_response_export_schema.csv
halt_response_export_action_queue.csv
halt_response_export_config.json
halt_response_export_runbook.md
manifest.json
```

`halt_response_export_summary.csv` carries `failed_check_count`,
`failed_check_names`, `first_failed_reason`, and `primary_blocker_*` fields so
automation can identify the first broker mapping or readiness blocker without
opening the per-column checks file. It also carries `action_queue_count`,
`blocked_action_count`, `next_gate`, `next_gate_help_command`, and
`primary_action_status`. `halt_response_export_action_queue.csv`,
`halt_response_export_config.json`, and `halt_response_export_runbook.md`
mirror response-readiness, adapter-consistency, cancel-mapping, and
flatten-mapping blockers back to `plan-halt-response` or
`export-halt-response`. Add `--fail-on-actions` to fail on any queued export
action, or `--fail-on-blocked-actions` to fail only when export actions are
blocked.

## Halt Execution Reconciliation

Verify that emergency cancels were acknowledged, flatten orders were filled,
and final positions are flat after a halt response:

```powershell
python -m hft_cli reconcile-halt-execution `
  --halt-response runs\halt_response\leadlag_shadow_latest `
  --cancel-acks logs\cancel_acks.csv `
  --flatten-fills logs\flatten_fills.csv `
  --positions logs\positions_after_halt.csv `
  --out runs\halt_execution\leadlag_shadow_latest `
  --fail-on-breach `
  --fail-on-blocked-actions
```

Cancel acknowledgements can match on `action_id`, `broker_order_id`, or
`client_order_id`. Flatten fills can match on `action_id` or
`instrument_id` plus `side`.

Outputs:

```text
halt_cancel_execution.csv
halt_flatten_execution.csv
halt_position_execution.csv
halt_execution_checks.csv
halt_execution_summary.csv
halt_execution_action_queue.csv
halt_execution_runbook.md
manifest.json
```

`halt_execution_summary.csv` carries `failed_check_count`,
`failed_check_names`, `first_failed_reason`, and `primary_blocker_*` fields so
post-halt schedulers can distinguish missing acknowledgements, incomplete
flatten fills, and residual positions from the one-row summary.
It also carries `action_queue_count`, `blocked_action_count`, `next_gate`,
`next_gate_help_command`, and `primary_action_status`.
`halt_execution_action_queue.csv` and `halt_execution_runbook.md` mirror failed
response, cancel-ack, flatten-fill, and final-position checks back to the next
recovery CLI gate. Use `--fail-on-blocked-actions` to fail only when blocked
halt-execution actions exist, or `--fail-on-actions` when any halt-execution
action should stop automation.
The manifest fingerprints the halt-response summary/action files plus the
cancel acknowledgement, flatten fill, and final-position snapshots supplied for
execution reconciliation.

## Halt Incident Review

Combine runtime guard, halt response, optional halt export, and halt execution
evidence into one incident-closure record:

```powershell
python -m hft_cli review-halt-incident `
  --guard runs\guards\leadlag_shadow_latest `
  --halt-response runs\halt_response\leadlag_shadow_latest `
  --halt-export runs\halt_exports\leadlag_shadow_latest `
  --halt-execution runs\halt_execution\leadlag_shadow_latest `
  --out runs\halt_incidents\leadlag_shadow_latest `
  --require-export `
  --fail-on-breach `
  --fail-on-blocked-actions
```

Outputs:

```text
halt_incident_timeline.csv
halt_incident_checks.csv
halt_incident_summary.csv
halt_incident_action_queue.csv
halt_incident_runbook.md
manifest.json
```

The timeline and summary retain guard-trigger, strategy, market, and
`proof_refresh_*` fields so the incident closure record shows both the failed
guard checks that caused the halt and the proof-freshness context that fed the
scaled runtime.
The incident summary also exposes `failed_check_count`, `failed_check_names`,
`first_failed_reason`, and `primary_blocker_*` fields for the first failed
closure gate, such as missing export evidence or incomplete execution
reconciliation.
It also carries `action_queue_count`, `blocked_action_count`, `next_gate`,
`next_gate_help_command`, and `primary_action_status`.
`halt_incident_action_queue.csv` and `halt_incident_runbook.md` mirror failed
guard, response, export, and execution checks back to the next recovery CLI
gate. Use `--fail-on-blocked-actions` to fail only when blocked incident
actions exist, or `--fail-on-actions` when any incident action should stop
automation.
The manifest fingerprints each component summary/check file from the guard,
halt response, optional halt export, and halt execution folders.

## Resume Gate

Authorize a post-halt resume only after the halt incident is closed and a fresh
scale-up plan is ready:

```powershell
python -m hft_cli review-resume-gate `
  --incident runs\halt_incidents\leadlag_shadow_latest `
  --scaleup runs\scaleup\leadlag_shadow_resume `
  --operator-review ops\resume_review.csv `
  --out runs\resume\leadlag_shadow_latest `
  --require-operator-approval `
  --require-operator-trigger-ack `
  --fail-on-breach `
  --fail-on-blocked-actions
```

Outputs:

```text
resume_authorization.csv
resume_checks.csv
resume_summary.csv
resume_action_queue.csv
resume_config.json
resume_runbook.md
manifest.json
```

`resume_config.json` keeps the legacy `failed_checks` name list and also adds
`failed_check_count` plus `primary_blocker`, so post-halt resume automation can
surface the first failed resume gate without parsing `resume_checks.csv`.
`resume_summary.csv` and `resume_config.json` also expose `failed_check_names`,
`first_failed_reason`, `primary_blocker_*`, `action_queue_count`,
`blocked_action_count`, `next_gate`, `next_gate_help_command`, and
`primary_action_status`. `resume_action_queue.csv` and `resume_runbook.md`
map open incident, scale-up, identity, proof-refresh, and operator-review
blockers to their next CLI gate. Use `--fail-on-blocked-actions` to fail only
when blocked resume actions exist, or `--fail-on-actions` when any resume
action should stop automation.

`resume_authorization.csv`, `resume_summary.csv`, and `resume_config.json`
retain the prior incident's guard-trigger, strategy, market, and proof-refresh
fields so resume approval is tied back to the exact halt that was closed.
Strategy, market, and proof-refresh identity continuity are checked by default
alongside scenario and adapter continuity. If the incident or new scale-up plan
contains proof freshness, the resume gate also requires the new scale-up proof
to be provided, ready, non-mixed, and strategy/market-matched to the incident.

When the scale-up target mode is `live_dryrun`, the resume gate automatically
requires both operator approval and acknowledgement of the prior guard trigger,
even if the explicit `--require-operator-approval` or
`--require-operator-trigger-ack` flags are omitted.

When `--require-operator-trigger-ack` is set, the latest operator review row
must include a matching `guard_failed_check_names`,
`incident_guard_failed_check_names`, `ack_guard_failed_check_names`, or
`acknowledged_guard_failed_check_names` value. The manifest fingerprints the
resolved incident summary, scale-up summary/config/checks, and optional
operator-review file that formed the resume authorization.

## Cutover Gate

Authorize the final paper/shadow/live-dryrun cutover after scale-up, broker
readiness, runtime-session, and operator-review evidence agree:

```powershell
python -m hft_cli review-cutover-gate `
  --scaleup runs\scaleup\leadlag_shadow_live_dryrun `
  --broker-readiness runs\broker_readiness\leadlag_shadow_arrow `
  --runtime-session runs\runtime_sessions\leadlag_shadow_latest `
  --operator-review ops\cutover_review.csv `
  --out runs\cutover\leadlag_shadow_live_dryrun `
  --target-mode live_dryrun `
  --require-route-readiness `
  --require-dispatch-roundtrip `
  --fail-on-breach `
  --fail-on-blocked-actions
```

Outputs:

```text
cutover_authorization.csv
cutover_checks.csv
cutover_summary.csv
cutover_action_queue.csv
cutover_config.json
cutover_runbook.md
manifest.json
```

`cutover_config.json` keeps the legacy `failed_checks` name list and also adds
`failed_check_count` plus `primary_blocker`, so schedulers can route the first
failed authorization check without parsing `cutover_checks.csv`. It also
mirrors `action_queue_count`, `blocked_action_count`, `next_gate`,
`next_gate_help_command`, `primary_action_status`, `primary_action`, and the
`next_actions` arrays from the scheduler queue. `cutover_action_queue.csv` and
`cutover_runbook.md` route failed scale-up, route-readiness, broker-readiness,
runtime-session, dispatch-roundtrip, vendor-data, resume-gate, and operator
review checks to the next CLI gate before route-enable automation can proceed.
Use `--fail-on-blocked-actions` to fail only when blocked cutover actions exist,
or `--fail-on-actions` when any cutover action should stop automation.

For `live_dryrun`, the cutover gate automatically requires route-readiness
proof retained in the scale-up plan, operator approval, operator
acknowledgement of the strategy/market identity, acknowledgement of the
scale-up order/notional limits, a continuing runtime guard, and clean dispatch
round-trip proof carried by both scale-up and broker readiness. It validates
runtime and dispatch strategy/market/target-mode identity against the scale-up
plan, requires matching clean route proof from both scale-up and broker
readiness, rejects nonzero dispatch round-trip and route-enable dispatch
round-trip failed-check counts, carries proof-refresh state, enforces any
multi-session shadow broker-readiness aggregate retained in the scale-up config,
revalidates any broker-readiness-carried shadow broker proof retained under
`broker_shadow_broker_*`, and validates any supplied broker resume-gate proof
identity before broker routing is allowed. If scale-up carried vendor
wrapper proof inside the shadow broker-readiness aggregate, cutover carries it
as `scaleup_shadow_broker_vendor_data_readiness_*` fields plus
`scaleup_shadow_broker_readiness.broker_vendor_data_readiness` config and fails
closed when that comparison-level wrapper proof is partial, unready, or dirty.
If scale-up carried the broker-readiness shadow broker wrapper, cutover carries
it as `scaleup_broker_shadow_broker_vendor_data_readiness_*` fields plus
`scaleup_broker_shadow_broker_readiness.broker_vendor_data_readiness` config and
fails closed on the same partial, unready, or dirty states.
If scale-up carried vendor
market-data batch provenance from Arrow.money/iRage onboarding, cutover carries
the dataset/header/mapping proof into `cutover_summary.csv` and
`cutover_config.json`. If scale-up carried broker-readiness final dispatch
round-trip vendor market-data batch proof, cutover revalidates adapter, market,
dataset, provenance, and comparison acceptance checks and preserves it as
`scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_*` fields plus the
`scaleup_broker_dispatch_roundtrip_vendor_market_data_batch` config block.
When the scale-up config includes both
`broker_readiness.dispatch_roundtrip.broker_dispatch_roundtrip_vendor_market_data_batch`
and the older `broker_readiness.dispatch_roundtrip.vendor_market_data_batch`
block, cutover prefers the broker-specific block. For older or thin scale-up
configs, cutover also reads the resolved broker-readiness config sidecar and
hydrates missing broker vendor-data proof from
`dispatch_roundtrip.broker_dispatch_roundtrip_vendor_market_data_batch` before
revalidating and carrying it downstream. Cutover also carries
`broker_readiness.broker_vendor_data_readiness` into
`scaleup_broker_vendor_data_readiness_*` summary fields and fails closed if the
wrapper readiness sidecar is failed even when the nested vendor batch is valid.
When runtime-session evidence carries strategy portfolio allocation, cutover
preserves it as `runtime_strategy_portfolio_*` fields and
`runtime_session.strategy_portfolio` config, and fails closed if that selected
allocation is unready, ineligible, nonpositive, or for a different
strategy/market than the scale-up identity. The same handoff preserves
portfolio concentration context, including minimum distinct strategy/market
counts, observed allocated strategy/market counts, top concentration names, and
maximum strategy/market allocation weights.
`--broker-readiness` may point at a broker-readiness folder or a launch-pipeline
root; cutover resolves nested `06_broker_readiness` and `05_broker_readiness`
summaries and fingerprints the resolved scale-up summary/config/checks,
broker-readiness summary, broker-readiness config sidecar when present,
optional runtime-session summary, and optional operator-review file in the
manifest.

## Route Enable Packet

Convert a ready cutover authorization plus broker upload evidence into the
final broker route-enable packet:

```powershell
python -m hft_cli review-route-enable `
  --cutover runs\cutover\leadlag_shadow_live_dryrun `
  --upload-pack runs\uploads\leadlag_shadow_arrow `
  --order-export runs\exports\leadlag_shadow_arrow `
  --out runs\route_enable\leadlag_shadow_live_dryrun `
  --target-mode live_dryrun `
  --require-order-export `
  --require-route-readiness `
  --require-dispatch-roundtrip `
  --fail-on-breach `
  --fail-on-blocked-actions
```

Outputs:

```text
route_enable_packet.csv
route_enable_checks.csv
route_enable_summary.csv
route_enable_action_queue.csv
route_enable_config.json
route_enable_runbook.md
manifest.json
```

`route_enable_config.json` keeps the legacy `failed_checks` name list and also
adds `failed_check_count` plus `primary_blocker`, giving broker-route
automation one compact blocker record before it reads the full check CSV. It
also mirrors `action_queue_count`, `blocked_action_count`, `next_gate`,
`next_gate_help_command`, `primary_action_status`, `primary_action`, and the
`next_actions` arrays from the scheduler queue. `route_enable_action_queue.csv`
and `route_enable_runbook.md` route failed cutover, upload-pack, order-export,
route-readiness, dispatch-roundtrip, vendor-data, resume-gate, and identity
checks to their next CLI gate before broker dispatch planning can proceed. Use
`--fail-on-blocked-actions` to fail only when blocked route-enable actions
exist, or `--fail-on-actions` when any route-enable action should stop
automation.

The packet does not submit orders. It carries the approved target mode,
strategy, market, scenario, adapter, order limit, notional limit, upload file,
proof/resume context, dispatch round-trip proof, and any cutover-carried vendor
market-data batch provenance into one machine-readable
artifact. It fails closed if cutover is not ready, the upload pack is not
ready, the adapter or target mode does not match, cutover route-readiness proof
is missing, unready, or for a different strategy/market, dispatch round-trip
proof is missing, dirty, or has failed component checks for live dry-run
routing, the carried route-enable dispatch round-trip failed-check counter is
nonzero, the nested cutover route proof is missing, mismatched, or dirty, any
cutover-carried shadow broker-readiness aggregate or broker-readiness-carried
shadow broker proof is mixed or dirty, the upload order count exceeds the
cutover limit, or the optional order-export notional exceeds the cutover
notional cap. If cutover retained strategy portfolio allocation from the
runtime-session guard chain, route-enable carries it as `strategy_portfolio_*`
fields and a `strategy_portfolio` config block, including the carried
concentration counts, top concentration names, and maximum allocation weights.
It also fails closed when the optional order-export notional exceeds the
selected paper/shadow allocation even if the broader cutover notional limit
would allow it. `--require-route-readiness` is automatic for `--target-mode
live_dryrun`; the explicit flag keeps paper/shadow route reviews equally
strict. If `cutover_config.json` retained Arrow.money/iRage vendor market-data
batch evidence, route-enable carries the dataset/header/mapping proof into
`route_enable_summary.csv` and `route_enable_config.json` as
`cutover_vendor_market_data_batch_*` audit fields. If cutover retained the
shadow-broker broker-vendor wrapper aggregate, route-enable revalidates the
per-session wrapper coverage and carries it as
`shadow_broker_vendor_data_readiness_*` plus nested
`shadow_broker_readiness.broker_vendor_data_readiness` config, and does the
same for `cutover_broker_shadow_broker_readiness`, failing closed when either
wrapper aggregate is partial, unready, or dirty. If cutover retained the
broker-readiness final dispatch round-trip vendor market-data batch proof,
route-enable revalidates adapter, market, dataset, provenance, and comparison
acceptance checks and carries it as
`cutover_broker_dispatch_roundtrip_vendor_market_data_batch_*` audit fields
plus the `cutover_broker_dispatch_roundtrip_vendor_market_data_batch` config
block. If cutover retained the broker-vendor wrapper readiness state,
route-enable carries it as `cutover_broker_vendor_data_readiness_*` audit
fields plus `cutover_broker_vendor_data_readiness` config, and fails closed
when the wrapper is not ready or has failed checks even if the nested vendor
batch itself is valid. When both `cutover_broker_dispatch_roundtrip_vendor_market_data_batch`
and the scale-up-retained
`scaleup_broker_dispatch_roundtrip_vendor_market_data_batch` blocks are present,
route-enable prefers the cutover-specific block. For older or thin cutover
configs, route-enable can also read the cutover manifest's
`broker_readiness_config` input and hydrate missing broker vendor-data proof
and wrapper readiness before revalidating them. `--upload-pack` and
`--order-export` may point at a launch-pipeline root; route-enable resolves nested `05_upload_pack`/`04_export` or surface-MM
`04_upload_pack`/`03_export` summaries and fingerprints the resolved cutover
summary, cutover config, cutover manifest when present, upload summary, and
optional order export summary in the manifest.

## Broker Dispatch Plan

Bind the enabled route to the exact broker upload rows and create a dry-run
dispatch batch with deterministic idempotency keys:

```powershell
python -m hft_cli plan-broker-dispatch `
  --route-enable runs\route_enable\leadlag_shadow_live_dryrun `
  --upload-pack runs\uploads\leadlag_shadow_arrow `
  --out runs\dispatch\leadlag_shadow_live_dryrun `
  --target-mode live_dryrun `
  --require-route-readiness `
  --require-dispatch-roundtrip `
  --fail-on-breach `
  --fail-on-blocked-actions
```

Outputs:

```text
broker_dispatch_orders.csv
broker_dispatch_checks.csv
broker_dispatch_summary.csv
broker_dispatch_action_queue.csv
broker_dispatch_config.json
broker_dispatch_runbook.md
manifest.json
```

`broker_dispatch_config.json` keeps the legacy `failed_checks` name list and
also adds `failed_check_count` plus `primary_blocker`, giving sender
automation the first failed dispatch gate as a structured record before it
opens `broker_dispatch_checks.csv`. The summary/config now also mirror
`action_queue_count`, `blocked_action_count`, `next_gate`,
`next_gate_help_command`, `primary_action_status`, `primary_action`, and
`next_actions`, while `broker_dispatch_action_queue.csv` and
`broker_dispatch_runbook.md` give schedulers a manifest-tracked handoff. Route
disabled and identity blockers point back to `review-route-enable`, allocation
blockers to `review-cutover-gate`, route-readiness blockers to
`review-route-readiness`, round-trip blockers to
`review-broker-dispatch-roundtrip`, vendor-data blockers to their vendor
pipelines, and malformed dispatch-order inputs back to `plan-broker-dispatch`.
Use `--fail-on-blocked-actions` to fail only when blocked dispatch actions
exist, or `--fail-on-actions` when any broker dispatch action should stop
automation.

This command still does not submit orders. It hashes the route-enable
authorization and upload file, creates one dry-run dispatch row per upload
order, and requires unique source order IDs, unique dispatch IDs, route-enabled
state, matching target mode, clean route-readiness proof from route-enable,
clean nested route proof from route-enable for live dry-run routing, zero
nested route-enable dispatch round-trip failed checks, any route-carried shadow
broker-readiness aggregate and broker-readiness-carried shadow broker proof to
remain clean and identity-consistent, and order counts within the approved route
limits. When route-enable retained strategy portfolio allocation, dispatch
planning carries the `strategy_portfolio_*` fields into summary/config,
including concentration counts, top concentration names, and maximum allocation
weights. It computes `source_order_notional` for each upload row, records
upload `total_notional`, and fails closed if the resolved upload-order file
exceeds the selected paper/shadow allocation. `--require-route-readiness` is
automatic for `--target-mode live_dryrun`; the explicit flag keeps paper/shadow
dispatch plans equally strict. The resulting
`broker_dispatch_orders.csv` carries the route proof batch id into each dry-run
dispatch row, while the summary/config carry the broker schema review
status/mode, route-readiness proof, `shadow_broker_*`, and
`route_broker_shadow_broker_*` proof from route-enable. If route-enable carried
the shadow-broker broker-vendor wrapper aggregate, dispatch planning revalidates
the per-session wrapper coverage and carries it as
`shadow_broker_vendor_data_readiness_*` plus nested
`shadow_broker_readiness.broker_vendor_data_readiness` config, and does the
same for `route_broker_shadow_broker_readiness`, failing closed when either
wrapper aggregate is partial, unready, or dirty. If route-enable carried
Arrow.money/iRage vendor market-data batch evidence, dispatch planning preserves
the dataset/header/mapping proof as `route_vendor_market_data_batch_*` fields
and a nested `route_vendor_market_data_batch` config block. If route-enable
carried the broker-readiness final dispatch round-trip vendor market-data batch
proof, dispatch planning revalidates adapter, market, dataset, provenance, and
comparison acceptance checks and preserves it as
`route_broker_dispatch_roundtrip_vendor_market_data_batch_*` fields plus the
`route_broker_dispatch_roundtrip_vendor_market_data_batch` config block. If
route-enable carried the broker-vendor wrapper readiness state, dispatch
planning carries it as `route_broker_vendor_data_readiness_*` fields plus
`route_broker_vendor_data_readiness` config, and fails closed when the wrapper
is not ready or has failed checks even if the nested vendor batch itself is
valid.
When both `route_broker_dispatch_roundtrip_vendor_market_data_batch` and the
cutover-retained `cutover_broker_dispatch_roundtrip_vendor_market_data_batch`
blocks are present, dispatch planning prefers the route-native block.
For older or thin route-enable configs, dispatch planning can follow the
route-enable manifest to the cutover manifest and hydrate missing broker
vendor-data proof and wrapper readiness from the recorded
`broker_readiness_config` sidecar before revalidating them.
`broker_dispatch_config.json` is the artifact a future Arrow.money or iRage
sender can consume. `--upload-pack` may point at a
launch-pipeline root; dispatch planning resolves nested `05_upload_pack` or
surface-MM `04_upload_pack` upload-order files and fingerprints the resolved
route-enable summary, route-enable config, route-enable manifest when present,
and upload CSV in the manifest.

## Broker Dispatch Send Packet

Prepare a non-submitting dry-run sender packet from an approved dispatch plan:

```powershell
python -m hft_cli prepare-broker-dispatch-send `
  --dispatch runs\dispatch\leadlag_shadow_live_dryrun `
  --out runs\dispatch_send\leadlag_shadow_live_dryrun `
  --require-route-readiness `
  --require-dispatch-roundtrip `
  --fail-on-breach `
  --fail-on-blocked-actions
```

Outputs:

```text
broker_dispatch_send_requests.csv
broker_dispatch_expected_acks.csv
broker_dispatch_send_checks.csv
broker_dispatch_send_summary.csv
broker_dispatch_send_action_queue.csv
broker_dispatch_send_config.json
broker_dispatch_send_runbook.md
manifest.json
```

`broker_dispatch_send_config.json` keeps the legacy `failed_checks` name list
and also adds `failed_check_count` plus `primary_blocker`, so a non-submitting
sender loop can surface the first request-packet blocker without parsing the
full check CSV. The summary/config also mirror `action_queue_count`,
`blocked_action_count`, `next_gate`, `next_gate_help_command`,
`primary_action_status`, `primary_action`, and `next_actions`, while
`broker_dispatch_send_action_queue.csv` and
`broker_dispatch_send_runbook.md` provide a manifest-tracked scheduler
handoff. Dispatch-plan blockers point back to `plan-broker-dispatch`,
sender-envelope blockers stay on `prepare-broker-dispatch-send`, route
readiness and round-trip blockers point to their proof review gates,
broker-readiness shadow-proof blockers point to `review-broker-readiness`, and
vendor-data blockers route to their vendor pipelines. Use
`--fail-on-blocked-actions` to fail only when blocked send-packet actions
exist, or `--fail-on-actions` when any send action should stop automation.

This packet still does not submit orders. It creates adapter-scoped endpoint
names, dry-run request envelopes, payload hashes, unique idempotency keys, and
an acknowledgement-log template while forcing `submission_enabled=false`. It
carries route dispatch round-trip proof into the sender request envelope and
expected acknowledgement rows, then fails closed if the dispatch plan is not
ready and armed, target mode does not match, route-readiness proof is missing
or identity-mismatched, route round-trip proof is missing or dirty for live
dry-run sending, route-enable dispatch round-trip failed checks read from the
dispatch config are nonzero, any dispatch row or request carries a mismatched
route proof batch id, any dispatch-carried shadow broker-readiness aggregate is
mixed or dirty, any dispatch-carried broker-readiness shadow broker proof is
mixed or dirty, the adapter is unknown, payload JSON is invalid, idempotency
keys are not unique, request limits are exceeded, or any request is not
dry-run-only. If dispatch planning retained strategy portfolio allocation
evidence, the sender packet preserves the `strategy_portfolio_*` fields and
`dispatch_total_notional` in summary/config, including concentration counts,
top concentration names, and maximum allocation weights. It fails closed when
the dispatch notional exceeds the selected paper/shadow allocation.
`--require-route-readiness` is automatic for `--target-mode live_dryrun`; the
explicit flag keeps paper/shadow sender packets equally strict. It also
carries the dispatch config broker schema review status/mode,
route-readiness proof, `shadow_broker_readiness`, and
`route_broker_shadow_broker_readiness` into the sender summary/config. If the
dispatch config retained the shadow-broker broker-vendor wrapper aggregate, the
sender packet revalidates the per-session wrapper coverage and carries it as
`shadow_broker_vendor_data_readiness_*` plus nested
`shadow_broker_readiness.broker_vendor_data_readiness` config, and does the
same for `route_broker_shadow_broker_readiness`, failing closed when either
wrapper aggregate is partial, unready, or dirty. If the
dispatch config retained Arrow.money/iRage vendor market-data batch evidence,
the sender packet preserves the dataset/header/mapping proof as
`dispatch_vendor_market_data_batch_*` fields and a nested
`dispatch_vendor_market_data_batch` config block. If the dispatch config
retained broker-readiness final dispatch round-trip vendor market-data batch
proof, the sender packet preserves it as
`dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_*` fields plus the
`dispatch_broker_dispatch_roundtrip_vendor_market_data_batch` config block. If
the dispatch config retained broker-vendor wrapper readiness, the sender packet
carries it as `dispatch_broker_vendor_data_readiness_*` fields plus
`dispatch_broker_vendor_data_readiness` config, and fails closed when the
wrapper is not ready or has failed checks even if the nested vendor batch itself
is valid. When
both `dispatch_broker_dispatch_roundtrip_vendor_market_data_batch` and
`route_broker_dispatch_roundtrip_vendor_market_data_batch` blocks are present,
the sender packet prefers the dispatch-native block. The
sender can also follow the dispatch manifest to the route-enable and cutover
manifests to hydrate missing broker vendor-data proof from the recorded
`broker_readiness_config` sidecar before preserving it, including the wrapper
readiness gate.
manifest fingerprints the exact dispatch
summary, dispatch orders, dispatch config, and dispatch manifest when present
consumed by the sender packet.

## Broker Dispatch Acknowledgement Reconciliation

Reconcile the dispatch batch against Arrow.money/iRage acknowledgement logs
before trusting a dry-run broker bridge:

```powershell
python -m hft_cli reconcile-broker-dispatch `
  --dispatch runs\dispatch\leadlag_shadow_live_dryrun `
  --acks logs\broker_dispatch_acks.csv `
  --out runs\dispatch_acks\leadlag_shadow_live_dryrun `
  --require-route-readiness `
  --require-dispatch-roundtrip `
  --fail-on-blocked-actions `
  --fail-on-breach
```

Outputs:

```text
broker_dispatch_acknowledgements.csv
broker_dispatch_unmatched_acks.csv
broker_dispatch_ack_checks.csv
broker_dispatch_ack_summary.csv
broker_dispatch_ack_action_queue.csv
broker_dispatch_ack_config.json
broker_dispatch_ack_runbook.md
manifest.json
```

`broker_dispatch_ack_config.json` keeps the legacy `failed_checks` name list
and also adds `failed_check_count` plus `primary_blocker`, giving
ack-reconciliation automation the first failed broker acknowledgement gate as a
compact JSON record. The summary/config also mirror `action_queue_count`,
`blocked_action_count`, `next_gate`, `next_gate_help_command`,
`primary_action_status`, and `next_actions` arrays from the scheduler queue.
`broker_dispatch_ack_action_queue.csv` and
`broker_dispatch_ack_runbook.md` provide a manifest-tracked scheduler handoff:
ack-evidence blockers route back to `reconcile-broker-dispatch`, stale dispatch
proof routes to `plan-broker-dispatch`, route-readiness blockers route to
`review-route-readiness`, round-trip blockers route to
`review-broker-dispatch-roundtrip`, broker-readiness blockers route to
`review-broker-readiness`, vendor-data blockers route to the vendor pipelines,
and allocation blockers route to `review-cutover-gate`. Use
`--fail-on-blocked-actions` when blocked acknowledgement actions should stop
automation, or `--fail-on-actions` when any ack action should stop automation.

The gate matches acknowledgements by `dispatch_order_id` with
`source_order_id` fallback, accepts common broker success status names, and
fails closed on unready dispatch plans, missing acknowledgements, rejected
orders, duplicate acknowledgement rows, missing or mismatched route-readiness
proof, dirty route round-trip proof for live dry-run dispatches, nonzero
route-enable dispatch round-trip failed checks read from the dispatch config,
dirty send-stage shadow broker-readiness aggregates, dirty send-stage
broker-readiness shadow broker proof, dispatch rows or acknowledgement rows
that carry a stale route proof batch id, missing
acknowledgement route proof tags, or acknowledgement rows that do not belong to
the dispatch batch. If dispatch planning retained strategy portfolio
allocation evidence, the ack gate preserves the `strategy_portfolio_*` fields
and `dispatch_total_notional` in summary/config, including concentration
counts, top concentration names, and maximum allocation weights. It fails
closed when dispatch notional exceeds the selected paper/shadow allocation.
`--require-route-readiness` is automatic for `live_dryrun`; the explicit flag
keeps paper/shadow acknowledgement reviews equally strict.
It carries the dispatch config broker schema review status/mode,
route-readiness proof, `shadow_broker_readiness`, and
`route_broker_shadow_broker_readiness` into the ack summary/config. If the
sender config retained the shadow-broker broker-vendor wrapper aggregate, the
ack gate revalidates per-session wrapper coverage and carries it as
`shadow_broker_vendor_data_readiness_*` plus nested
`shadow_broker_readiness.broker_vendor_data_readiness` config, and does the
same for `route_broker_shadow_broker_readiness`, failing closed when either
wrapper aggregate is partial, unready, or dirty. If the
dispatch config retained Arrow.money/iRage vendor market-data batch evidence,
the ack gate preserves the dataset/header/mapping proof as
`ack_vendor_market_data_batch_*` fields and a nested
`ack_vendor_market_data_batch` config block. If the dispatch config retained
broker-readiness final dispatch round-trip vendor market-data batch proof, the
ack gate preserves it as
`ack_broker_dispatch_roundtrip_vendor_market_data_batch_*` fields plus the
`ack_broker_dispatch_roundtrip_vendor_market_data_batch` config block. When
`ack_broker_dispatch_roundtrip_vendor_market_data_batch` is present alongside
dispatch- or route-retained broker vendor-data blocks, the ack gate prefers the
ack-stage block. If the dispatch config retained broker-vendor wrapper
readiness, the ack gate carries it as `ack_broker_vendor_data_readiness_*`
fields plus `ack_broker_vendor_data_readiness` config, and fails closed when
the wrapper is not ready or has failed checks even if the nested vendor batch is
valid. For older or thin dispatch configs, the ack gate can also follow the
dispatch manifest to the route-enable and cutover manifests to hydrate missing
broker vendor-data proof and wrapper readiness from the recorded
`broker_readiness_config` sidecar before preserving them. The
manifest fingerprints the exact dispatch summary, dispatch orders, dispatch
config, dispatch manifest when present, and broker acknowledgement log files
used in the reconciliation.

## Broker Dispatch Round-Trip Review

Review dispatch, send-packet, and acknowledgement evidence as one dry-run
broker proof:

```powershell
python -m hft_cli review-broker-dispatch-roundtrip `
  --dispatch runs\dispatch\leadlag_shadow_live_dryrun `
  --send runs\dispatch_send\leadlag_shadow_live_dryrun `
  --ack runs\dispatch_acks\leadlag_shadow_live_dryrun `
  --out runs\dispatch_roundtrip\leadlag_shadow_live_dryrun `
  --require-route-readiness `
  --require-dispatch-roundtrip `
  --fail-on-blocked-actions `
  --fail-on-breach
```

Outputs:

```text
broker_dispatch_roundtrip_orders.csv
broker_dispatch_roundtrip_checks.csv
broker_dispatch_roundtrip_summary.csv
broker_dispatch_roundtrip_action_queue.csv
broker_dispatch_roundtrip_config.json
broker_dispatch_roundtrip_runbook.md
manifest.json
```

`broker_dispatch_roundtrip_config.json` keeps the legacy `failed_checks` name
list and also adds `failed_check_count` plus `primary_blocker`, so the final
broker dry-run proof exposes the first failed cross-component check directly in
the config. The summary/config also mirror `action_queue_count`,
`blocked_action_count`, `next_gate`, `next_gate_help_command`,
`primary_action_status`, and `next_actions` arrays from the scheduler queue.
`broker_dispatch_roundtrip_action_queue.csv` and
`broker_dispatch_roundtrip_runbook.md` provide the manifest-tracked final
broker proof handoff: dispatch-plan blockers route to `plan-broker-dispatch`,
sender blockers to `prepare-broker-dispatch-send`, acknowledgement blockers to
`reconcile-broker-dispatch`, route-readiness blockers to
`review-route-readiness`, broker-readiness blockers to
`review-broker-readiness`, vendor-data blockers to the vendor pipelines, and
cross-component proof blockers back to `review-broker-dispatch-roundtrip`.
Use `--fail-on-blocked-actions` when blocked round-trip actions should stop
automation, or `--fail-on-actions` when any final proof action should stop
automation.

This gate proves the broker dry-run bridge as a whole. It joins dispatch rows
to sender requests and acknowledgement rows, including the raw ack-log route
proof tag recorded by the acknowledgement reconciler, then fails closed unless
the dispatch plan, non-submitting sender packet, and acknowledgement
reconciliation all pass with matching strategy/market/scenario/adapter
identity, disabled live submission, dry-run-only requests, consistent
route-readiness proof, consistent route round-trip proof, zero carried
route-enable dispatch round-trip failed checks from upstream configs,
consistent shadow broker-readiness proof across dispatch/send/ack configs, one
consistent broker-readiness shadow broker proof across dispatch/send/ack
configs, consistent vendor market-data batch provenance across component
configs, consistent broker-readiness final dispatch round-trip vendor
market-data proof across component configs, consistent broker-vendor wrapper
readiness across component configs, consistent strategy portfolio allocation
evidence across dispatch/send/ack configs, one request per dispatch order, and
an accepted acknowledgement for every request. If component configs retained
strategy portfolio allocation evidence, the round-trip summary/config preserve
`strategy_portfolio_*` and `dispatch_total_notional`, including concentration
counts, top concentration names, and maximum allocation weights. It then fails
closed on selected strategy/market/profile/allocation mismatches or dispatch
notional above the selected paper/shadow allocation.
`--require-route-readiness` is automatic for `live_dryrun`; the explicit flag
keeps paper/shadow round-trip reviews equally strict. The manifest fingerprints the exact
dispatch, send-packet, and acknowledgement summary/order/config CSV or JSON
files plus component manifests that formed the proof, and the final
summary/config retain the broker schema review status/mode, route-readiness
proof, and shadow broker-readiness proof plus `broker_shadow_broker_readiness`.
If the component configs retained the shadow-broker broker-vendor wrapper
aggregate, the round-trip review revalidates component-wide wrapper coverage
and carries it as `shadow_broker_vendor_data_readiness_*` plus nested
`shadow_broker_readiness.broker_vendor_data_readiness` config, and does the
same for `broker_shadow_broker_readiness`, failing closed when either wrapper
aggregate is partial, unready, or dirty. It also retains
`roundtrip_vendor_market_data_batch` reconciled from the component configs,
plus `roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch` reconciled
from the broker-readiness component proof chain and
`roundtrip_broker_vendor_data_readiness` reconciled from the wrapper proof
chain. If a component config carries
`roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch`, the round-trip
review prefers that block before falling back through ack-, dispatch-, and
route-retained broker vendor-data blocks. If a component config carries
broker-vendor wrapper readiness, the round-trip review fails closed when the
wrapper is not ready or has failed checks even if the nested vendor batch is
valid. For older or thin component configs, the round-trip review can also
follow the dispatch manifest through the route-enable and cutover manifests to
hydrate missing broker vendor-data proof and wrapper readiness from the
recorded `broker_readiness_config` sidecar before enforcing component
consistency.

## Calibration

```powershell
python -m hft_cli calibrate `
  --simulated-orders logs\sim_orders.csv `
  --live-fills logs\live_fills.csv `
  --out runs\calibration_2026_06_10 `
  --adapter normalized
```

`arrow_money` and `irage` adapter names exist, but currently use the normalized
schema until real export samples are mapped.

## Fill-Model Calibration

Convert broker/drop-copy reconciliation evidence into conservative replay
assumptions for queue, latency, slippage, and edge buffers:

```powershell
python -m hft_cli calibrate-fill-model `
  --reconciliation runs\reconciliation\leadlag_shadow_latest `
  --out runs\fill_model\leadlag_shadow_latest `
  --tick-size 0.05 `
  --min-orders 25 `
  --min-live-fill-rate 0.5 `
  --max-adverse-slippage-ticks 2 `
  --base-edge-ticks 1 `
  --fail-on-breach `
  --fail-on-blocked-actions
```

Outputs:

```text
fill_model_metrics.csv
fill_model_recommendations.csv
fill_model_checks.csv
fill_model_summary.csv
fill_model_action_queue.csv
fill_model_config.json
fill_model_runbook.md
manifest.json
```

`fill_model_summary.csv` carries `failed_check_count`,
`failed_check_names`, `first_failed_reason`, `primary_blocker_*`,
`action_queue_count`, `blocked_action_count`, `next_gate`,
`next_gate_help_command`, and `primary_action_status` so sample-size,
fill-rate, mismatch, overfill, unmatched-fill, and slippage calibration blockers
are scheduler-visible. `fill_model_action_queue.csv`,
`fill_model_config.json`, and `fill_model_runbook.md` mirror those actions back
to `calibrate-fill-model` while preserving the replay-ready `global` and
`by_instrument` config blocks. Use `--fail-on-blocked-actions` to fail only
when blocked calibration actions exist, or `--fail-on-actions` when any
calibration action should stop automation.

## Fill-Model Drift

Compare a baseline fill-model config against the latest shadow/live calibration
before reusing old proof runs:

```powershell
python -m hft_cli compare-fill-models `
  --baseline runs\fill_model\leadlag_shadow_baseline `
  --latest runs\fill_model\leadlag_shadow_latest `
  --out runs\fill_model_drift\leadlag_shadow_latest `
  --max-queue-conservatism-increase-pct 0.25 `
  --max-order-latency-increase-us 100 `
  --require-same-instruments `
  --fail-on-breach `
  --fail-on-blocked-actions
```

Outputs:

```text
fill_model_drift.csv
fill_model_drift_checks.csv
fill_model_drift_summary.csv
fill_model_drift_action_queue.csv
fill_model_drift_config.json
fill_model_drift_runbook.md
manifest.json
```

`fill_model_drift_summary.csv` carries `failed_check_count`,
`failed_check_names`, `first_failed_reason`, `primary_blocker_*`,
`action_queue_count`, `blocked_action_count`, `next_gate`,
`next_gate_help_command`, and `primary_action_status` so unready calibration
configs, instrument-set changes, and queue/latency/slippage/edge drift are
scheduler-visible before proof reuse. `fill_model_drift_action_queue.csv`,
`fill_model_drift_config.json`, and `fill_model_drift_runbook.md` mirror those
actions back to `compare-fill-models`. Use `--fail-on-blocked-actions` to fail
only when blocked drift actions exist, or `--fail-on-actions` when any drift
action should stop automation.

## Calibrated Replay Plan

Apply `fill_model_config.json` to strategy replay parameters without running the
replay yet:

```powershell
python -m hft_cli plan-calibrated-replay `
  --strategy leadlag `
  --fill-model runs\fill_model\leadlag_shadow_latest `
  --order-latency-us 100 `
  --trigger-ticks 2 `
  --out runs\calibrated_replay\leadlag_shadow_latest `
  --fail-on-breach
```

Outputs:

```text
calibrated_replay_params.json
calibrated_replay_checks.csv
calibrated_replay_summary.csv
manifest.json
```

## Proof Refresh Gate

Decide whether an old proof report can be reused after fill-model drift, or
whether a fresh calibrated proof run is required before promotion/scale-up:

```powershell
python -m hft_cli review-proof-refresh `
  --drift runs\fill_model_drift\leadlag_shadow_latest `
  --baseline-proof runs\proof\leadlag_shadow_baseline `
  --latest-proof runs\proof\leadlag_shadow_calibrated `
  --calibrated-replay runs\calibrated_replay\leadlag_shadow_latest `
  --strategy leadlag `
  --market india_nse_index_derivatives `
  --require-calibrated-replay `
  --out runs\proof_refresh\leadlag_shadow_latest `
  --fail-on-breach `
  --fail-on-blocked-actions
```

Outputs:

```text
proof_refresh_decision.csv
proof_refresh_checks.csv
proof_refresh_summary.csv
proof_refresh_action_queue.csv
proof_refresh_config.json
proof_refresh_runbook.md
manifest.json
```

The gate records strategy/market identity from baseline proof, latest proof,
and calibrated replay summaries. Mixed available strategy or market identities
fail closed, and `--strategy`/`--market` enforce the expected target when those
identities are present. `proof_refresh_summary.csv` also carries
`failed_check_count`, `failed_check_names`, `first_failed_reason`,
`primary_blocker_*`, `action_queue_count`, `blocked_action_count`, `next_gate`,
`next_gate_help_command`, and `primary_action_status`. The
`proof_refresh_action_queue.csv`, `proof_refresh_config.json`, and
`proof_refresh_runbook.md` sidecars mirror missing proof, failed proof,
calibrated replay, and identity blockers back to `review-proof-refresh`. Use
`--fail-on-blocked-actions` to fail only when blocked proof-refresh actions
exist, or `--fail-on-actions` when any proof-refresh action should stop
automation.

## Adapter Schema Audit

Audit a vendor sample CSV header before wiring a real adapter map:

```powershell
python -m hft_cli audit-adapter-schema `
  --sample vendor\arrow_ticks_sample.csv `
  --adapter arrow_money `
  --kind ticks `
  --out runs\schema_audit\arrow_ticks_sample `
  --fail-on-missing `
  --fail-on-blocked-actions
```

Supported `--kind` values include `ticks`, `chain`, `orders`, and `fills`.
The command reads only the CSV header and writes:

```text
adapter_schema_summary.csv
adapter_schema_columns.csv
adapter_mapping_template.csv
adapter_schema_review_checklist.csv
adapter_schema_action_queue.csv
adapter_schema_config.json
adapter_schema_runbook.md
manifest.json
```

For `arrow_money` and `irage`, the summary is marked
`placeholder_normalized_pending_vendor_schema` until real vendor source columns
replace the normalized placeholders.
`adapter_schema_summary.csv` also exposes `failed_check_count`,
`failed_check_names`, `first_failed_reason`, and `primary_blocker_*` fields for
the first missing required source column, so vendor sample blockers are visible
without opening the column-level CSV.
`adapter_schema_review_checklist.csv` separates hard blockers such as missing
required columns from review tasks such as classifying extra vendor fields and
approving replacement Arrow.money/iRage source mappings.
`adapter_schema_action_queue.csv`, `adapter_schema_config.json`, and
`adapter_schema_runbook.md` mirror missing-column blockers, placeholder-schema
review debt, and extra-column review actions with `next_gate`,
`next_gate_help_command`, `primary_action_status`, `primary_action`, and
`blocked_actions`/`review_actions`. Use `--fail-on-blocked-actions` to fail
only on hard schema blockers, or `--fail-on-actions` when any open review task
should stop the scheduler.

## Mapped Vendor Data Normalization

After a schema audit and review, apply the mapping to a real vendor CSV and
write a normalized file that existing research, replay, calibration, and
diagnostic commands can consume:

```powershell
python -m hft_cli normalize-mapped-data `
  --input vendor\arrow_fills_2026_06_10.csv `
  --mapping mappings\arrow_fills_mapping.csv `
  --out data\normalized\arrow_fills_2026_06_10 `
  --adapter arrow_money `
  --kind fills `
  --output-file normalized_fills.csv `
  --fail-on-blocked-actions `
  --fail-on-breach
```

Supported `--kind` values match the schema audit workflow: `ticks`, `chain`,
`orders`, and `fills`. Mapping files use `normalized_column`, `source_column`,
optional `default_value`, optional `required`, and optional `transform`.
Supported transforms are `identity`, `string`, `uppercase`, `lowercase`,
`int`, `float`, `side_text`, and `side_signed`.

Outputs:

```text
normalized_data.csv
mapped_data_checks.csv
mapped_data_action_queue.csv
mapped_data_config.json
mapped_data_runbook.md
mapped_data_summary.csv
manifest.json
```

`mapped_data_summary.csv` exposes `failed_check_count`,
`failed_check_names`, `first_failed_reason`, and `primary_blocker_*` fields for
the first required normalized column that could not be mapped from the vendor
CSV. It also carries `action_queue_count`, `blocked_action_count`,
`next_gate`, `next_gate_help_command`, and `primary_action_status`.
`mapped_data_action_queue.csv`, `mapped_data_config.json`, and
`mapped_data_runbook.md` mirror unmapped required columns and zero-row
normalization blockers so `catalog-runs` can schedule the next
`normalize-mapped-data` repair step.

The command fails closed when required normalized columns are not mapped, and
tick/chain outputs pass through the same session, timestamp, and data-quality
normalizers used by the strategy backtests. Use `--fail-on-blocked-actions` to
fail when mapped-data repair actions exist, or `--fail-on-actions` for any
open mapped-data action.

## Vendor Market Data Onboarding Pipeline

Run the full first-mile market-data path for a raw Arrow.money/iRage tick or
option-chain CSV: vendor intake, mapping draft, normalized data, diagnostics,
and data-readiness evidence in one manifest-backed folder:

```powershell
python -m hft_cli pipeline-vendor-market-data `
  --input vendor\arrow_ticks_2026_06_10.csv `
  --out runs\vendor_data\arrow_ticks_2026_06_10 `
  --adapter arrow_money `
  --kind ticks `
  --timestamp-unit datetime `
  --tick-size 0.05 `
  --min-rows 100000 `
  --max-p99-gap-ns 1000000000 `
  --max-median-spread-ticks 2 `
  --fail-on-blocked-actions `
  --fail-on-breach
```

Use `--kind chain` for option-chain snapshots. If `--mapping` is not supplied,
the pipeline uses the intake-generated `vendor_mapping_draft.csv`; review and
edit that mapping before treating the run as broker/vendor-approved evidence.

Outputs:

```text
01_vendor_intake\vendor_intake_summary.csv
02_normalized\normalized_ticks.csv
03_diagnostics\diagnostic_summary.csv
04_data_readiness\data_readiness_summary.csv
vendor_market_data_pipeline_components.csv
vendor_market_data_pipeline_config.json
vendor_market_data_pipeline_action_queue.csv
vendor_market_data_pipeline_runbook.md
vendor_market_data_pipeline_summary.csv
manifest.json
```

The pipeline summary carries market identity, the raw source file hash, header
hash, mapping hash, mapping source, and component manifest paths. The root
manifest fingerprints the intake, mapped-data, and data-readiness manifests, so
reruns can prove whether a changed Arrow.money/iRage file, header, or mapping
is the reason readiness changed. `vendor_market_data_pipeline_config.json` is
the machine-readable handoff for strategy research or future vendor adapters.
The root action queue and runbook promote nested data-readiness blockers into
catalog-visible next gates, so operators do not have to inspect
`04_data_readiness` before deciding the next command to run.
`vendor_market_data_pipeline_config.json` also mirrors the queue as
`next_actions`, `ready_actions`, and `blocked_actions`, plus root-level
`primary_action_status` and `primary_action` fields for scheduler handoff.
Use `--fail-on-blocked-actions` to fail closed only on blocked repair gates,
or `--fail-on-actions` to fail whenever the promoted action queue is non-empty.

For multi-day onboarding, run each raw file through the same pipeline and
compare data-readiness evidence before walk-forward research:

```powershell
python -m hft_cli pipeline-vendor-market-data-batch `
  --input vendor\arrow_ticks_2026_06_10.csv vendor\arrow_ticks_2026_06_11.csv `
  --label day1 `
  --label day2 `
  --out runs\vendor_data\arrow_ticks_batch `
  --adapter arrow_money `
  --kind ticks `
  --timestamp-unit datetime `
  --tick-size 0.05 `
  --min-datasets 2 `
  --min-ready-rate 1 `
  --fail-on-blocked-actions `
  --fail-on-breach
```

Batch outputs:

```text
datasets\<label>\vendor_market_data_pipeline_summary.csv
comparison\data_readiness_comparison_summary.csv
vendor_market_data_batch_datasets.csv
vendor_market_data_batch_config.json
vendor_market_data_batch_action_queue.csv
vendor_market_data_batch_runbook.md
vendor_market_data_batch_summary.csv
manifest.json
```

The batch summary adds `market`, `unique_source_files`,
`unique_header_fingerprints`, and `mapping_sources`; the batch manifest
fingerprints each dataset pipeline manifest plus the comparison manifest.
`vendor_market_data_batch_config.json` keeps the accepted dataset list,
comparison thresholds, and per-dataset fingerprints together for walk-forward
research handoff. The batch action queue promotes per-dataset pipeline blockers
and comparison blockers to the batch root, including the exact
`python -m hft_cli ... --help` next-gate command.
`vendor_market_data_batch_config.json` also mirrors the promoted queue as
`next_actions`, `ready_actions`, and `blocked_actions`, plus root-level
`primary_action_status` and `primary_action` fields.
Use `--fail-on-blocked-actions` to stop only when batch repair work is blocked,
or `--fail-on-actions` to require an empty promoted batch action queue.

To run the vendor batch proof and broker-readiness review as one auditable
handoff recipe:

```powershell
python -m hft_cli pipeline-broker-vendor-readiness `
  --input vendor\arrow_ticks_2026_06_10.csv vendor\arrow_ticks_2026_06_11.csv `
  --label day1 `
  --label day2 `
  --out runs\broker_vendor_data\arrow_ready `
  --adapter arrow_money `
  --kind ticks `
  --timestamp-unit datetime `
  --tick-size 0.05 `
  --schema-audit runs\broker_schema\arrow_money `
  --order-export runs\launch\04_export `
  --upload-pack runs\launch\05_upload_pack `
  --dispatch-roundtrip runs\broker_dispatch_roundtrip `
  --allow-placeholder-schema `
  --require-dispatch-roundtrip `
  --fail-on-blocked-actions `
  --fail-on-breach
```

This writes `01_vendor_market_data_batch`, `02_broker_readiness`,
`broker_vendor_data_readiness_components.csv`,
`broker_vendor_data_readiness_summary.csv`,
`broker_vendor_data_readiness_checks.csv`,
`broker_vendor_data_readiness_action_queue.csv`,
`broker_vendor_data_readiness_config.json`,
`broker_vendor_data_readiness_runbook.md`, and a root manifest. It is the
current one-command Arrow.money/iRage data proof path before broker dry-run
handoff. The root summary/config also surfaces source-file fingerprint
coverage, minimum mapping coverage, and mapping-draft provenance, so operators
can verify the broker-vendor proof without drilling into nested batch files;
the checks file names the exact fail-closed reason when the wrapper root is not
ready. The wrapper summary/config/runbook also surfaces `adapter_schema_status`,
`schema_review_required`, `schema_reviewed`, `schema_review_mode`,
`placeholder_schema_active`, `placeholder_schema_allowed`, and
`placeholder_schema_warning`, so dry-run placeholder schema overrides remain
visible in catalogs until real Arrow.money/iRage mappings are reviewed.
`broker_vendor_data_readiness_summary.csv` also exposes
`failed_check_count`, `failed_check_names`, `first_failed_reason`, and
`primary_blocker_*` fields for the first failed wrapper check.
`broker_vendor_data_readiness_action_queue.csv` and
`broker_vendor_data_readiness_runbook.md` turn those failed checks into
next-gate handoffs for vendor batch, broker-readiness, or wrapper reruns.
`broker_vendor_data_readiness_config.json` mirrors the same queue as
`ready_action_count`, `blocked_action_count`, `next_gate`,
`next_gate_help_command`, `next_actions`, `ready_actions`, `blocked_actions`,
`primary_action_status`, and `primary_action`, plus `failed_check_count`,
`failed_checks`, `first_failed_reason`, and structured `primary_blocker`, so
schedulers can read the wrapper handoff from JSON. Use
`--fail-on-blocked-actions` to stop on blocked broker/vendor handoff work, or
`--fail-on-actions` to stop whenever the wrapper queues any action.
Launch and broker-readiness commands honor the wrapper root's own
`broker_vendor_data_readiness_config.json`, so a failed wrapper root cannot be
masked by a valid nested vendor batch. Scale-up also hydrates the same wrapper
state from `broker_readiness_config.json` and blocks controlled scale increases
when the wrapper readiness sidecar is failed, even if the nested batch proof is
otherwise valid. Cutover applies the same wrapper readiness gate before route
enable can inherit scale-up-carried broker/vendor proof, and route-enable
applies it again before broker dispatch can inherit cutover-carried proof.
Broker dispatch planning applies the same gate before sender packets can
inherit route-enable-carried proof, and broker dispatch send applies it again
before request packets can advance. Broker dispatch ack applies it again before
accepted acknowledgement evidence can advance, and broker dispatch round-trip
review applies it once more before the final dry-run proof can advance.

## Order Staging

Stage generated quote or order candidates into a broker-neutral pre-trade file
before any Arrow.money/iRage-specific routing adapter is wired in:

```powershell
python -m hft_cli stage-orders `
  --orders runs\surface_quotes_2026_06_10\surface_quotes.csv `
  --source surface_quotes `
  --out runs\surface_quotes_2026_06_10\staged_orders `
  --quote-risk-review runs\surface_quotes_2026_06_10\quote_review `
  --require-quote-risk-review `
  --surface-quality-review runs\surface_quotes_2026_06_10\surface_quality `
  --require-surface-quality `
  --max-order-qty 75 `
  --max-notional 10000 `
  --price-band-pct 0.02 `
  --max-orders 100 `
  --fail-on-reject
```

For `--source surface_quotes`, requiring quote-risk or surface-quality review
blocks all orders unless the supplied summaries passed. This keeps market
making quotes from moving into broker-neutral staging before data hygiene,
quote hygiene, and surface-theo quality gates are accepted.

For `--source orders`, the input CSV must include:

```text
instrument_id,side,qty,price
```

Optional columns include `client_order_id`, `ts`/`ts_signal_ns`,
`market_bid`, `market_ask`, `marketable`, `strategy`, `order_type`, and
`time_in_force`.

Outputs:

```text
staged_orders.csv
staged_order_rejections.csv
staged_order_summary.csv
manifest.json
```

## Data Diagnostics

```powershell
python -m hft_cli diagnose-ticks `
  --ticks data\futures.csv `
  --out runs\diagnostics\futures `
  --tick-size 0.05 `
  --market india_nse_index_derivatives
```

```powershell
python -m hft_cli diagnose-chain `
  --chain data\chain.csv `
  --out runs\diagnostics\chain `
  --tick-size 0.05 `
  --market india_nse_index_derivatives
```

Outputs:

```text
diagnostic_summary.csv
diagnostic_issues.csv
```

## Data Readiness Gate

Combine vendor sample intake, adapter schema audit, mapped-data normalization,
tick/chain diagnostics, market profile fees, market-portability approval, and
instrument metadata into one go/no-go record before edge scans,
walk-forwards, or replay pipelines:

```powershell
python -m hft_cli review-data-readiness `
  --vendor-intake mappings\arrow_ticks_intake `
  --schema-audit runs\schema_audit\arrow_ticks `
  --mapped-data data\normalized\arrow_ticks_2026_06_10 `
  --tick-diagnostics runs\diagnostics\futures `
  --chain-diagnostics runs\diagnostics\chain `
  --market-profile runs\market_profiles\india_us `
  --market-portability runs\market_profiles\portability `
  --instrument-metadata runs\risk\leadlag_shadow_instruments `
  --out runs\data_readiness\india_nse_2026_06_10 `
  --require-vendor-intake `
  --require-schema-audit `
  --require-mapped-data `
  --require-chain-diagnostics `
  --require-market-profile `
  --require-explicit-fee-model `
  --require-market-portability `
  --require-instrument-metadata `
  --expected-strategy microprice_imbalance `
  --expected-market india_nse_index_derivatives `
  --expected-adapter arrow_money `
  --expected-vendor-data-kind ticks `
  --max-tick-p99-gap-ns 1000000000 `
  --max-tick-median-spread-ticks 2 `
  --max-chain-median-spread-ticks 20 `
  --fail-on-breach `
  --fail-on-blocked-actions
```

Outputs:

```text
data_readiness_items.csv
data_readiness_checks.csv
data_readiness_summary.csv
data_readiness_action_queue.csv
data_readiness_config.json
data_readiness_runbook.md
manifest.json
```

When `--market-portability` is supplied with `--expected-strategy` and
`--expected-market`, the gate reads `market_portability_config.json` and fails
closed unless that exact strategy-market pair is in `ready_pairs`.
`data_readiness_action_queue.csv` flattens failed checks into blocked actions
with the inferred upstream gate, `next_gate_help_command`, observed value,
threshold, reason, and recommendation. `data_readiness_summary.csv` also
exposes `failed_check_count`, `failed_check_names`, `first_failed_reason`, and
`primary_blocker_*` fields for the first failed readiness check. The
`data_readiness_config.json` handoff mirrors the same queue as `next_actions`,
`ready_actions`, and `blocked_actions`, plus root-level
`primary_action_status`, `primary_action`, `failed_check_count`,
`failed_checks`, `first_failed_reason`, and structured `primary_blocker`
fields, summary, component, and failed-check state for scheduler handoff.
`data_readiness_runbook.md` mirrors the same handoff with component readiness
and failed checks, and these sidecars are manifest-tracked so `catalog-runs`
can promote blocked vendor-data work into the top-level action plan.
Use `--fail-on-blocked-actions` to stop when blocked data-readiness actions
remain, or `--fail-on-actions` when any queued data-readiness handoff should
stop automation for operator review.

Compare multiple data-readiness runs before walk-forward research:

```powershell
python -m hft_cli compare-data-readiness `
  --readiness runs\data_readiness\india_nse_2026_06_10 runs\data_readiness\india_nse_2026_06_11 `
  --label 2026-06-10 `
  --label 2026-06-11 `
  --out runs\data_readiness\india_nse_comparison `
  --min-datasets 2 `
  --min-ready-rate 1 `
  --fail-on-breach `
  --fail-on-blocked-actions
```

Outputs:

```text
data_readiness_runs.csv
data_readiness_comparison_checks.csv
data_readiness_comparison_summary.csv
data_readiness_comparison_action_queue.csv
data_readiness_comparison_config.json
data_readiness_comparison_runbook.md
manifest.json
```

`data_readiness_comparison_action_queue.csv` maps failed multi-day checks to
the next gate, such as `review-data-readiness` for failed dataset readiness or
`pipeline-vendor-market-data-batch` for missing distinct source files,
fingerprints, or mapping coverage. `data_readiness_comparison_config.json`
mirrors dataset rows, failed-check names, action counts, and
`next_actions`/`ready_actions`/`blocked_actions` plus root-level
`primary_action_status` and `primary_action` fields for schedulers.
`data_readiness_comparison_runbook.md` mirrors the blocked actions, dataset
rows, and failed checks for operator review, and these sidecars are
manifest-tracked for catalog promotion.
Use `--fail-on-blocked-actions` to stop on blocked multi-day data-proof
actions, or `--fail-on-actions` when any queued comparison action should pause
the scheduler.

## Proof Report

Evaluate one or more replay output folders against explicit proof thresholds:

```powershell
python -m hft_cli proof-report `
  --runs runs\leadlag_replay_2026_06_10 runs\leadlag_replay_2026_06_11 `
  --out runs\proof\leadlag `
  --min-net-pnl 1 `
  --min-fills 10 `
  --max-drawdown 5000 `
  --max-otr 50 `
  --min-worst-regime-equity-change 0 `
  --fail-on-breach
```

Outputs:

```text
proof_metrics.csv
proof_checks.csv
proof_summary.csv
```

Proof reports retain strategy and market identity from replay summaries,
scenario keys, or replay manifests. A proof bundle that mixes provided strategy
or market identities fails even when individual PnL, fill, regime, spread, and
markout checks pass.

## Stress Replay

Apply extra fee, slippage, and adverse-fill shocks to replay output folders:

```powershell
python -m hft_cli stress-replay `
  --runs runs\leadlag_replay_2026_06_10 runs\leadlag_replay_2026_06_11 `
  --out runs\stress\leadlag `
  --cost-multiplier 1 1.25 1.50 `
  --slippage-ticks 0 1 2 `
  --adverse-bps 0 1 2 `
  --tick-size 0.05 `
  --min-net-pnl 1 `
  --fail-on-breach
```

Outputs:

```text
stress_results.csv
stress_summary.csv
manifest.json
```

Stress reports retain strategy and market identity from replay summaries,
scenario keys, or replay manifests. A stress bundle that mixes provided
strategy or market identities fails even when all numeric stress scenarios pass.
