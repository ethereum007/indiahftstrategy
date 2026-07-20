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
When round-trip summaries carry post-halt resume-route proof, the catalog also
adds `broker_roundtrip_resume_route_provided_runs`,
`broker_roundtrip_resume_route_ready_runs`,
`broker_roundtrip_resume_route_primary_ready_runs`,
`broker_roundtrip_resume_route_incident_ready_runs`,
`broker_roundtrip_resume_route_breach_runs`, and breach subtype counters for
route gaps, launch controls, portfolio proof, and concentration proof. These
metrics let scheduler gates reject partial or stale resume authorization
before Arrow.money/iRage dry-run evidence is treated as reusable.
When provider imbalance broker round-trip summaries carry final synthetic
sidecar proof, the catalog also adds
`provider_broker_roundtrip_runs`, `provider_broker_roundtrip_passed_runs`,
`provider_broker_roundtrip_synthetic_dataset_count`,
`provider_broker_roundtrip_synthetic_sidecar_count`,
`provider_broker_roundtrip_synthetic_sidecar_readable_count`,
`provider_broker_roundtrip_synthetic_sidecar_proof_runs`,
`provider_broker_roundtrip_synthetic_sidecar_ready_runs`, and
`provider_broker_roundtrip_synthetic_sidecar_breach_runs` so schedulers can
prove the final Arrow.money/iRage-ready provider path retained readable
synthetic sidecars before treating broker dispatch proof as reusable.
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
Use `--fail-on-broker-roundtrip-resume-route-breach` to fail when any final
round-trip contains incomplete, gapped, launch-control-failed, portfolio-unsafe,
or concentration-unsafe resume-route proof, and
`--require-broker-roundtrip-resume-route-ready` when the catalog must contain
at least one final round-trip with both primary and incident resume-route
branches ready.
Use `--fail-on-provider-broker-roundtrip-synthetic-sidecar-breach` to fail when
any provider imbalance broker round-trip expected synthetic sidecars but did
not retain a ready/readable proof, and
`--require-provider-broker-roundtrip-synthetic-sidecar-ready` when the catalog
must contain at least one final provider broker round-trip with ready synthetic
sidecar proof.
When cataloging provider acknowledgement, round-trip, or rehearsal-certificate
archives, pass a current retirement index with
`--provider-broker-active-lineage-index <index_dir>`. Covered strict siblings
are marked `selectable`; covered legacy originals remain catalog-visible as
`retained_only` but have `provider_lineage_selection_eligible=false`.
Supported provider proofs absent from a supplied index are fail-closed as
`unindexed`; supported proofs cataloged without any index are
`index_not_provided` and are also ineligible. The catalog summary reports
indexed, selectable, retained-only, unindexed/missing-index, and total
selection-blocked counts. Use
`--fail-on-provider-lineage-selection-blocks` for candidate catalogs that must
contain no retained-only or unindexed provider proof.
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

For the provider-data imbalance wrapper chain, use the provider ops-launch
profile after the provider scorecard, route-readiness, runtime, broker
readiness, cutover, route-enable, dispatch-send, acknowledgement, and final
round-trip wrappers plus the broker rehearsal certificate are cataloged:

```powershell
python -m hft_cli review-strategy-evidence `
  --catalog runs\catalog\latest `
  --out runs\evidence\provider_imbalance_ops_launch `
  --profile provider_market_data_imbalance_ops_launch `
  --require-same-strategy `
  --expected-strategy microprice_imbalance `
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
and `live_dryrun`. The `provider_imbalance_ops_launch` profile expands to the
provider-data imbalance scorecard, route-readiness, scale-up, runtime,
broker-readiness, cutover, route-enable, dispatch, send, acknowledgement, and
final round-trip and broker-rehearsal-certificate run types; aliases include
`provider_market_data_imbalance_ops_launch` and
`provider_imbalance_live_dryrun`. Explicit `--required-run-type` flags still
override the profile for custom launch reviews.
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
limits. It also requires at least one final broker round-trip with ready
primary and incident resume-route proof and fails when any final round-trip
contains resume-route gaps, launch-control failures, portfolio breaches, or
concentration breaches.
The `provider_imbalance_ops_launch` profile inherits those same launch checks
and also requires at least one final provider broker round-trip with ready
synthetic sidecar proof, failing when any provider broker round-trip expected
synthetic sidecars but did not retain readable sidecar evidence. It also
requires the non-authorizing broker rehearsal certificate, so a catalog with
round-trip evidence but no sealed manifest-chain sign-off remains incomplete.
That certificate must be a passed `live_dryrun` artifact, must retain a
64-character certificate SHA-256, and must not claim submission authority.
Acknowledgement, provider round-trip, and rehearsal-certificate evidence also
default to the verified active-lineage selection contract. Build the catalog
with `--provider-broker-active-lineage-index <index_dir>`; each required stage
must have enough passed rows marked both
`provider_lineage_selection_status=selectable` and
`provider_lineage_selection_eligible=true`. Retained originals may remain in
the same catalog for audit and reproduction, but they are not counted as
launch candidates. Missing-index, unindexed, retained-only, or internally
inconsistent selection fields fail closed. Use
`--allow-ineligible-provider-lineage-for-audit` only to render a historical
review: the resulting evidence is explicitly `audit_only`, remains
`ready=false`, and cannot satisfy route readiness.
Use `--allow-non-file-inputs` only for legacy exploratory catalogs, or
`--require-file-inputs` to apply the same fail-closed provenance rule to a
custom evidence set.
Custom evidence sets can opt into the same launch controls with
`--fail-on-blocked-placeholder-schema`, `--fail-on-placeholder-schema`,
`--require-broker-roundtrip-portfolio-safe`, and
`--fail-on-broker-roundtrip-portfolio-breach`,
`--require-broker-roundtrip-portfolio-concentration-ok`, and
`--fail-on-broker-roundtrip-portfolio-concentration-breach`,
`--require-broker-roundtrip-resume-route-ready`, and
`--fail-on-broker-roundtrip-resume-route-breach`,
`--require-provider-broker-roundtrip-synthetic-sidecar-ready`, and
`--fail-on-provider-broker-roundtrip-synthetic-sidecar-breach`.

`strategy_evidence_summary.csv` records the inferred `evidence_profile`. Ready
strategy profiles recommend `eligible_for_shadow_scaleup_review`, while ready
`ops_launch` and `provider_imbalance_ops_launch` profiles recommend
`eligible_for_live_dryrun_route_review`.
It also records passed-required input provenance totals, placeholder-schema
counts, broker round-trip portfolio-safe/breach counts, and broker round-trip
portfolio concentration OK/breach counts, plus broker resume-route ready and
breach counts when the catalog contains them. Provider ops-launch evidence also
records provider broker round-trip synthetic sidecar proof, ready, and breach
counts plus broker rehearsal certificate passed, live-dry-run, authorizing,
and SHA-256-backed counts. It also records the effective provider-lineage
policy, required and covered lineage run-type counts, selectable passed rows,
and blocked retained/unindexed rows. Strategy scorecards carry those fields,
and route readiness independently rejects provider ops evidence that omits or
disables the selection contract.

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
`settlement`, and `surface_mm`. It also accepts
`provider_market_data_imbalance_ops_launch` when the provider wrapper chain is
ready for live-dry-run review. It filters the catalog by each profile's
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
breaches. It also requires clean final broker round-trip resume-route proof for
both primary and incident branches. Blocked scorecard actions include the
failed evidence-check names in
`strategy_scorecard_action_queue.csv` and `strategy_scorecard_next_actions.json`.
For provider-data imbalance, `--profile provider_market_data_imbalance_ops_launch`
uses the provider wrapper run types and applies those same launch controls to
the provider final broker-dispatch roundtrip. It also carries provider
broker round-trip synthetic sidecar counts into `strategy_scorecard.csv` and
fails closed when the final provider roundtrip expected synthetic sidecars but
did not retain ready/readable sidecar proof.

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
`plan-broker-dispatch`, and ready `ops_launch` or
`provider_imbalance_ops_launch` profiles can point to `review-route-readiness`.
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
  --require-scorecard-manifest `
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
When the scorecard contains registered research or an enabled research-family
gate, allocation automatically requires the complete current
`strategy_scorecard` manifest and a current `research_family_audit` manifest.
The allocator reconciles the scorecard CSV against its summary, JSON actions,
manifest claims, family ID, registration ID, surviving candidate, and family
manifest hash. Missing, stale, semantically detached, mismatched, or
authorizing proof makes every affected profile ineligible and routes repair to
`score-strategy-readiness` or `audit-research-family`. This family boundary
cannot be bypassed with `--allow-unready`.
Use `--require-scorecard-manifest` to apply the same bundle-integrity gate to
ops-only or exploratory scorecards that do not automatically require family
proof. A supplied manifest is always verified even when the flag is omitted.
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
Allocation rows, summary/config, and runbook retain scorecard-manifest status
and SHA-256 plus research-family ID, registration ID, family path, manifest
SHA-256, candidate identity, and matched study label. The portfolio manifest
fingerprints every scorecard artifact, the scorecard manifest, and the family
root/manifest. It also flattens transitive manifest dependencies, so later
catalog, family-registration, robust-study, or raw-source drift invalidates the
portfolio allocation manifest instead of silently preserving an obsolete
capital plan. All outputs remain non-authorizing and do not enable broker
submission.

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
concentration breaches. It also requires final broker round-trip resume-route
proof with ready primary/incident branches and no route-gap, launch-control,
portfolio, or concentration breaches. Provider-data imbalance ops evidence also
must carry ready final provider broker round-trip synthetic sidecar proof with
zero sidecar breaches; stale provider ops summaries that lose those counts fail
closed here before live dry-run route review. Older ops evidence summaries that
do not carry those control flags/counts fail closed at route review instead of
being treated as live-dry-run ready. Use `--allow-non-file-ops-inputs` only for
explicit dry-run investigations that are not route-review candidates.
`route_readiness_action_queue.csv` flattens ready and blocked route pairs into
priority order with `next_gate`, `next_gate_help_command`, evidence statuses,
`ops_launch_control_failures`, broker proof counts including resume-route
breach counters plus provider synthetic sidecar proof counters, and the
route-level recommendation.
`route_readiness_config.json` mirrors the queue as
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
When the proof root carries broker-readiness route-control evidence, the launch
root summary also exposes `broker_readiness_route_readiness_*` and
`broker_readiness_route_broker_route_readiness_*` fields, including launch
control, allocation-safe, and concentration-safe broker round-trip counts.

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

## Backtest Overfit Audit

Measure whether the scenario selected in one subset of sweep periods retains
its rank on the complementary periods:

```powershell
python -m hft_cli audit-backtest-overfit `
  --selection runs\selection\leadlag `
  --out runs\overfit\leadlag `
  --score-column robust_score `
  --min-partitions 4 `
  --min-scenarios 3 `
  --max-probability-overfit 0.25 `
  --min-median-oos-score 0 `
  --min-oos-positive-rate 0.50 `
  --min-median-rank-correlation 0 `
  --min-candidate-selection-rate 0.25 `
  --max-candidate-overfit-rate 0.25 `
  --min-candidate-oos-positive-rate 0.50 `
  --fail-on-blocked-actions `
  --fail-on-breach
```

The audit builds an even set of at most 12 chronological partitions from the
selection's sweep labels, evaluates every symmetric half-in-sample/half-OOS
combination, selects the best in-sample scenario, and ranks that scenario on
the complementary partitions. Probability of backtest overfitting (PBO) is the
fraction of combinations where the in-sample winner lands at or below the OOS
median. Odd or larger period sets are grouped contiguously without dropping
periods. Scenarios missing any partition are reported and fail the default
complete-grid check. The rank-1 scenario from `scenario_scores.csv` must also
clear candidate-specific selection-frequency, overfit-rate, and OOS-positive
checks; a stable alternative cannot mask a fragile promotion candidate. The
selection manifest is required by default.

Outputs:

```text
backtest_overfit_combinations.csv
backtest_overfit_scenario_stability.csv
backtest_overfit_partition_scores.csv
backtest_overfit_partition_map.csv
backtest_overfit_checks.csv
backtest_overfit_summary.csv
backtest_overfit_action_queue.csv
backtest_overfit_config.json
backtest_overfit_runbook.md
manifest.json
```

This is a parameter-selection risk diagnostic, not a forecast or guarantee of
future profitability. Use independent chronological sweep periods; repeated
resamples of the same underlying session are not independent evidence.

## Backtest Significance Audit

Test whether the selected candidate's partition scores remain credibly
positive after accounting for the number of scenarios searched:

```powershell
python -m hft_cli audit-backtest-significance `
  --overfit-audit runs\overfit\leadlag `
  --out runs\significance\leadlag `
  --min-observations 6 `
  --min-nonzero-observations 6 `
  --min-positive-rate 0.50 `
  --max-adjusted-sign-pvalue 0.10 `
  --bootstrap-samples 10000 `
  --confidence-level 0.95 `
  --min-bootstrap-probability-positive 0.95 `
  --min-bootstrap-mean-lower 0 `
  --fail-on-actions `
  --fail-on-breach
```

The audit reads the selected candidate from a current, passed CSCV overfit
audit. It applies an exact one-sided sign test to nonzero partition scores,
multiplies that p-value by the number of searched scenarios (Bonferroni), and
computes a deterministic bootstrap interval for the mean partition score.
Defaults require six disjoint chronological observations, adjusted
`p <= 0.10`, at least 95% bootstrap support for a positive mean, and a
nonnegative lower 95% bound.

Outputs:

```text
backtest_significance_observations.csv
backtest_significance_bootstrap_quantiles.csv
backtest_significance_checks.csv
backtest_significance_summary.csv
backtest_significance_action_queue.csv
backtest_significance_config.json
backtest_significance_runbook.md
manifest.json
```

This is conservative evidence against a zero-edge candidate, not proof of
future profitability. The diagnostics treat disjoint chronological partition
scores as exchangeable; dependence, regime change, and execution slippage can
invalidate inference. Relabeled or repeated samples do not create power.

## Chronological Holdout Audit

Evaluate only the already-selected scenario on later, manifest-backed sweep
periods that were not consumed by `compare-sweeps`:

```powershell
python -m hft_cli audit-backtest-holdout `
  --selection runs\selection\leadlag `
  --holdout-sweeps `
    runs\surface_sweep\2026_06_07 `
    runs\surface_sweep\2026_06_08 `
    runs\surface_sweep\2026_06_09 `
  --out runs\holdout\leadlag `
  --group-cols quote_ttl_ns order_latency_us fill_depth_fraction `
  --min-sweeps 3 `
  --min-candidate-coverage-rate 1 `
  --min-proof-pass-rate 1 `
  --min-worst-score 0 `
  --min-worst-net-pnl 0 `
  --fail-on-actions `
  --fail-on-breach
```

The audit reads the frozen rank-1 scenario and development paths from the
current selection artifacts. It rejects any overlap between development and
holdout paths, requires current source-fingerprinted manifests for every
holdout, and never ranks or substitutes candidates using holdout outcomes.
Defaults require three distinct holdouts, full candidate coverage, every
underlying proof to pass, nonnegative mean/median/worst score and net PnL, and
at least one fill per holdout.

Outputs:

```text
backtest_holdout_observations.csv
backtest_holdout_provenance.csv
backtest_holdout_checks.csv
backtest_holdout_summary.csv
backtest_holdout_action_queue.csv
backtest_holdout_config.json
backtest_holdout_runbook.md
manifest.json
```

Selection isolation proves the holdout files were not inputs to the recorded
selection. It cannot prove that a human never inspected them. Treat a failed
holdout as consumed evidence and reserve new future periods for another test.

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
  --overfit-audit runs\overfit\leadlag `
  --require-overfit-audit `
  --significance-audit runs\significance\leadlag `
  --require-significance-audit `
  --holdout-audit runs\holdout\leadlag `
  --require-holdout-audit `
  --fail-on-breach
```

When an overfit audit is supplied, promotion always requires it to pass. It
also verifies that the audit's stored selection-manifest SHA matches the
current selection and that every audit artifact still matches the audit
manifest. `--require-overfit-audit` additionally blocks a missing audit.
When significance evidence is supplied, promotion likewise requires a passed,
current manifest from the same selection. `--require-significance-audit`
blocks promotion when that proof is missing. Supplied holdout evidence must
also pass, evaluate the promoted scenario, match the selection-manifest SHA,
and remain current. `--require-holdout-audit` blocks missing holdout proof.

Outputs:

```text
promotion_candidate.csv
promotion_checks.csv
promotion_summary.csv
candidate_config.json
manifest.json
```

## Robust Selection Pipeline

Run multi-period comparison, CSCV overfit audit, and strict promotion as one
manifest-backed workflow. Supply independent sweep folders in chronological
order:

```powershell
python -m hft_cli pipeline-robust-selection `
  --sweeps `
    runs\surface_sweep\2026_06_01 `
    runs\surface_sweep\2026_06_02 `
    runs\surface_sweep\2026_06_03 `
    runs\surface_sweep\2026_06_04 `
    runs\surface_sweep\2026_06_05 `
    runs\surface_sweep\2026_06_06 `
    runs\surface_sweep\2026_06_07 `
    runs\surface_sweep\2026_06_08 `
    runs\surface_sweep\2026_06_09 `
  --out runs\robust_selection\surface_mm `
  --group-cols quote_ttl_ns order_latency_us fill_depth_fraction markout_horizon_ns `
  --strategy surface_mm `
  --market india_nse_index_derivatives `
  --research-registration runs\research_registration\india_index_microstructure_v1 `
  --registered-study-label surface_mm `
  --require-research-registration `
  --min-selection-pass-rate 1 `
  --max-probability-overfit 0.25 `
  --min-candidate-selection-rate 0.25 `
  --max-candidate-overfit-rate 0.25 `
  --min-candidate-oos-positive-rate 0.50 `
  --max-significance-adjusted-sign-pvalue 0.10 `
  --min-significance-bootstrap-probability-positive 0.95 `
  --min-significance-bootstrap-mean-lower 0 `
  --holdout-sweeps 3 `
  --min-holdout-proof-pass-rate 1 `
  --min-holdout-worst-score 0 `
  --min-holdout-worst-net-pnl 0 `
  --min-promotion-sweeps 6 `
  --fail-on-actions `
  --fail-on-breach
```

The final three supplied sweeps are reserved as holdouts by default. Selection,
CSCV, and significance consume only the earlier development sweeps, and the
default selection threshold requires every development period. Every sweep
must have a readable experiment manifest that lists the exact consumed
`sweep_runs.csv`; all artifact hashes and recorded source-input fingerprints
must still be current. The pipeline requires current selection, overfit,
significance, and holdout manifests and cannot relax their promotion
requirements. Sweep provenance is carried into nested promotion checks, so
`03_promotion` cannot appear ready when root preflight is blocked. Fewer than
nine total periods, development/holdout overlap, missing or drifted provenance,
incomplete grids, unstable candidates, weak corrected significance, losing
holdouts, selection/audit drift, and promotion breaches block the candidate. A
ready result advances only to broker-neutral `stage-orders`;
`authorizes_submission` remains `false` throughout.

When `--research-registration` is supplied, the pipeline loads the current
registration manifest and exact `--registered-study-label` row. It verifies
the planned result root, strategy, market, primary metric, scenario ceiling,
and exact development/holdout counts. The registration ID and manifest SHA are
written into the root summary, candidate config, and manifest inputs.
`--require-research-registration` fails closed when either binding argument is
missing. Registration proof and sweep provenance form one promotion preflight,
so a mismatched, failed, or drifted registration cannot yield a ready leaf.

The generated family launcher also supplies `--research-launch-matrix`,
`--research-launch-contract-id`, and
`--require-research-launch-contract`. The official executor additionally
creates a unique execution receipt and supplies
`--research-launch-execution-receipt` with
`--require-research-launch-execution-receipt`. These preflights verify the current
matrix artifact, immutable contract-core hash, exact study/output identity,
ordered sweeps and labels, grouping columns, holdout count, and registration
fingerprint. The receipt binds the exact stored argv and a canonical digest of
the resolved selection, overfit, significance, holdout, and promotion
semantics. The root manifest fingerprints the immutable contract, receipt, and
attempt record while recording the matrix-manifest SHA observed at launch. A
later coverage refresh therefore
cannot invalidate an otherwise unchanged robust result, while manual dispatch,
argument drift, changed defaults, and threshold overrides fail closed.
The receipt must also resolve to exactly one valid record in the launch
matrix's hash-chained attempt ledger. The root fingerprints that immutable
record file rather than the mutable append-only ledger, so later attempts do
not create false result drift.
After the nested robust command returns, the executor appends a separate
immutable outcome record. It binds the attempt/receipt/record hashes, executor
exit status, completion or exception state, result readiness, and exact robust
summary/manifest hashes. A successful executor return is accepted only when the
outcome classifies as `completed_ready`.

Outputs:

```text
01_selection\...
02_backtest_overfit\...
02_backtest_significance\...
02_backtest_holdout\...
03_promotion\...
robust_selection_pipeline_sweep_provenance.csv
robust_selection_pipeline_research_registration.csv
robust_selection_pipeline_research_launch_contract.csv
robust_selection_pipeline_research_launch_execution_receipt.csv
robust_selection_pipeline_preflight.csv
robust_selection_pipeline_stages.csv
robust_selection_pipeline_summary.csv
robust_selection_pipeline_action_queue.csv
robust_selection_pipeline_runbook.md
candidate_config.json
manifest.json
```

When multiple strategies or research questions are tested as one program,
declare every robust-selection root in the research-family audit below before
treating any candidate as a family-wise survivor.

## Prospective Research Family Registration

Create a plan CSV before running any studies. Paths are resolved relative to
the plan file and may point to result folders that do not exist yet:

```csv
study_label,strategy,market,hypothesis,planned_study_path,primary_metric,max_scenarios,development_sweeps,holdout_sweeps
leadlag,leadlag,india_nse_index_derivatives,Leader moves predict laggard net of costs,results/leadlag,robust_score,24,6,3
imbalance,imbalance,india_nse_index_derivatives,Queue imbalance predicts executable edge,results/imbalance,robust_score,36,6,3
```

Lock and manifest the normalized plan:

```powershell
python -m hft_cli register-research-family `
  --plan research\india_index_microstructure_v1.csv `
  --family-id india_index_microstructure_v1 `
  --out runs\research_registration\india_index_microstructure_v1 `
  --min-studies 2 `
  --min-development-sweeps 6 `
  --min-holdout-sweeps 3 `
  --fail-on-actions `
  --fail-on-breach
```

The registration validates unique labels and future result roots, required
hypotheses and metrics, positive search breadth, and development/holdout period
counts. Its deterministic registration ID hashes the family ID plus normalized
plan. `registration.lock.json` and the manifest bind that ID to the original
plan file. Changing the plan requires a new registration.

Run each planned robust study with the registration root, its exact
`study_label`, and `--require-research-registration`. This creates prospective
source binding at study time; retrospective path matching alone is not enough
to close the family.

Outputs:

```text
research_family_registration_studies.csv
research_family_registration_checks.csv
research_family_registration_summary.csv
research_family_registration_action_queue.csv
research_family_registration_config.json
research_family_registration_runbook.md
registration.lock.json
manifest.json
```

Manifest timestamps now retain microsecond UTC precision so closure can fail
when registration was generated after a result manifest. Clock ordering is
supporting evidence, not an external timestamp authority; preserve registration
and result manifests in version control for stronger auditability.

## Registered Research Launch Matrix

To materialize immutable launch contracts, add `sweep_paths_json`,
`group_cols_json`, and optionally `sweep_labels_json` columns to the
prospective registration plan. Each value is a JSON string array. These
columns are preserved in the normalized plan and included in its registration
ID.

Generate one deterministic `pipeline-robust-selection` argv contract per
registered row and audit result coverage:

```powershell
python -m hft_cli plan-research-family-launches `
  --registration runs\research_registration\india_index_microstructure_v1 `
  --out runs\research_launches\india_index_microstructure_v1 `
  --fail-on-actions `
  --fail-on-breach
```

Execute a pending contract by ID rather than reconstructing its argv manually:

```powershell
python -m hft_cli run-research-family-study `
  --launch-matrix runs\research_launches\india_index_microstructure_v1 `
  --contract-id CONTRACT_ID_FROM_THE_MATRIX
```

The executor accepts only a current matrix artifact whose selected row is both
contract-valid and launch-ready. Before dispatch it writes a unique receipt
under `executions\`, then runs the exact stored argv with that receipt path and
mandatory registration, launch-contract, and execution-receipt gates. The
receipt records the dispatch ID and time, matrix/contract fingerprints, exact
argv digest, resolved semantic parameters and digest, and
`authorizes_submission=false`.

Every receipt is also an attempt ID. The executor writes an immutable matching
record under `executions\records\` and appends that record to
`executions\attempts.jsonl` under an OS-level lock. Each ledger row hashes the
previous row. The executor and every coverage refresh revalidate record order,
receipt and file hashes, retry lineage, unique attempt/dispatch IDs, and the
non-authorizing claim. The
dynamic `executions\` tree is excluded from the mutable launch-matrix manifest;
completed robust roots still fingerprint their exact receipt and attempt
record.

An interrupted attempt with no robust summary can be retried only by naming the
latest attempt and attesting a reason:

```powershell
python -m hft_cli run-research-family-study `
  --launch-matrix runs\research_launches\india_index_microstructure_v1 `
  --contract-id CONTRACT_ID_FROM_THE_MATRIX `
  --retry-of-attempt-id LATEST_ATTEMPT_ID `
  --retry-reason "worker stopped before the pipeline completed" `
  --attest-retry
```

A duplicate without these fields, a retry of an older attempt, a missing or
unattested reason, ledger drift, or any retry after a robust summary exists is
blocked. Intentional re-research after a completed result requires a new
prospective registered study and contract.

Normal outcomes are `completed_ready` or `completed_blocked`. A returned result
whose exit status, readiness, or manifest integrity disagrees is
`completed_inconsistent`. An exception or dispatch without a readable summary
and manifest is `interrupted`. The latter can follow the attested retry path;
once any robust summary exists, replay remains blocked even if outcome
finalization is missing. Coverage labels that narrow case
`completed_unfinalized` so it can be reconciled explicitly rather than hidden.

Recover a result-bearing attempt only when the executor stopped after writing
the robust result but before appending its outcome:

```powershell
python -m hft_cli recover-research-family-study-outcome `
  --launch-matrix runs\research_launches\india_index_microstructure_v1 `
  --attempt-id LATEST_ATTEMPT_ID `
  --exit-status 0 `
  --recovery-reason "executor stopped after writing the result manifest" `
  --attest-recovery
```

Recovery never invokes the stored launch argv. It accepts only the latest
attempt for that contract, requires a current manifest-bound root whose summary
names the same attempt, receipt, and contract, and requires exit status `0` for
a ready root or nonzero for a blocked root. Missing attestation, an empty
reason, stale files, mismatched identity/readiness, an older attempt, or an
existing outcome all fail closed. The resulting outcome carries
`recovered=true`, the attested reason, and the same non-authorizing claim.

The command verifies the registration, exact sweep and label counts, unique
scenario-group columns, every sweep manifest, and any existing robust root.
Existing results count as covered only when their current root manifest binds
the same registration ID, study label, registration-manifest SHA, immutable
contract ID, contract-file SHA, and execution-receipt ID/SHA. The root must
also reproduce the receipt's exact semantic digest from its actual runtime
configuration and bind the same immutable attempt record carried by the current
hash chain. A completed root additionally requires one outcome whose stored
summary/manifest hashes match the current files and whose status agrees with
root readiness. Pending
rows retain both a machine-readable argv array and display command. Contract
IDs are deterministic hashes of the registered row and exact launch arguments.

If a registered study cannot be run, provide a reason ledger:

```csv
study_label,reason
imbalance,Required historical feed segment was unavailable
```

Rerun with `--abandonments path\to\abandonments.csv` and
`--attest-abandonments`. An abandonment without a unique registered label,
non-empty reason, and explicit attestation remains `never_launched`. This
evidence never authorizes order submission.

Outputs:

```text
contracts\*.json
executions\<contract>_<dispatch>.json
executions\attempts.jsonl
executions\records\*.json
executions\outcomes.jsonl
executions\outcomes\*.json
research_family_launch_matrix.csv
research_family_launch_checks.csv
research_family_launch_summary.csv
research_family_launch_action_queue.csv
research_family_launch_config.json
research_family_launch_runbook.md
manifest.json
```

## Research Family Audit

Apply Holm-Bonferroni correction across a declared family of robust candidate
studies. Include passed, failed, and abandoned completed attempts:

```powershell
python -m hft_cli audit-research-family `
  --studies `
    runs\robust_selection\leadlag `
    runs\robust_selection\imbalance `
    runs\robust_selection\surface_mm `
  --label leadlag `
  --label imbalance `
  --label surface_mm `
  --family-id india_index_microstructure_v1 `
  --registration runs\research_registration\india_index_microstructure_v1 `
  --require-prospective-registration `
  --launch-matrix runs\research_launches\india_index_microstructure_v1 `
  --require-launch-coverage `
  --attest-complete-family `
  --min-studies 2 `
  --max-holm-adjusted-pvalue 0.10 `
  --min-family-candidates 1 `
  --out runs\research_family\india_index_microstructure_v1 `
  --fail-on-actions `
  --fail-on-breach
```

The audit verifies every robust root and source-input fingerprint, then applies
Holm correction to each study's already scenario-count-adjusted sign-test
p-value. Non-ready and failed studies remain in the family size but cannot
become candidates. Surviving rows must also retain passed holdout proof and a
non-authorizing source root. When registration is supplied, closure verifies
the current registration manifest and lock ID, exact family/label/path match,
strategy, market, primary metric, actual scenario count within registered
search breadth, exact development/holdout counts, and that registration
predates every study manifest. Every source root must also report a passed
binding to its own registered study label and fingerprint the exact same
registration-manifest SHA used for closure. A supplied registration always
binds the audit; `--require-prospective-registration` also blocks when it is
missing.

When a launch matrix is supplied, it also becomes mandatory evidence. Every
completed robust root must be explicitly included, never-launched rows block,
and a current attested abandonment is added to the family at conservative
adjusted p-value `1.0`. Abandoned rows remain in Holm's family size but can
never become candidates. `--require-launch-coverage` blocks closure when the
matrix is missing.

`--attest-complete-family` is mandatory for a passing report. It records the
operator's assertion that every attempted study in the defined family is
present. Software cannot discover omitted experiments, so the family-wise
error-control claim is invalid if attempts are excluded or registered only
after outcomes are inspected.

Outputs:

```text
research_family_studies.csv
research_family_checks.csv
research_family_summary.csv
research_family_action_queue.csv
research_family_config.json
research_family_runbook.md
manifest.json
```

A passed family audit advances to `score-strategy-readiness`. It does not
authorize order submission, capital allocation, or live trading.

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
vendor_intake_receipt.json
vendor_mapping_draft.csv
vendor_intake_summary.csv
manifest.json
```

The generated `vendor_mapping_draft.csv` uses `normalized_column`,
`source_column`, `default_value`, `required`, and `transform` columns so it can
be reviewed and then passed to `normalize-mapped-data`. Keep the receipt-bound
draft unchanged; if review requires corrections, write them to a separate
reviewed mapping file before normalization. The source profile and
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
The persisted intake directory is write-once. Verify that its source file is
still current and reconstruct every generated artifact before using the draft:

```powershell
python -m hft_cli verify-vendor-csv-intake `
  --intake mappings\arrow_ticks_intake `
  --fail-on-breach
```

The verifier returns success under `--fail-on-breach` only for a semantically
verified, mapping-ready intake. Without the gate, a current incomplete schema
is reported as `verified_blocked`; changed source bytes, edited generated
artifacts, or re-manifested mapping tampering are stale/inconsistent. Catalogs
surface the same `verified_ready`, `verified_blocked`, and
`stale_or_inconsistent` states. The receipt is intake-only: it does not
authorize normalization, strategy research, routing, or order submission.

## Vendor Mapping Review

Seal an operator-reviewed vendor mapping against the exact write-once intake,
raw source, and candidate mapping before normalization. The candidate mapping
and operator decision must be separate files outside the intake directory:

```powershell
python -m hft_cli review-vendor-mapping `
  --intake mappings\arrow_ticks_intake `
  --mapping mappings\arrow_ticks_candidate.csv `
  --decision mappings\arrow_ticks_decision.csv `
  --out mappings\arrow_ticks_review `
  --fail-on-rejected
```

The mapping uses `normalized_column`, `source_column`, `default_value`,
`required`, and `transform`. The one-row decision uses these columns:

```text
intake_receipt_id
source_file_sha256
mapping_candidate_sha256
adapter
kind
decision
operator_id
operator_role
reviewed_at_utc
vendor_documentation_checked
source_columns_confirmed
field_semantics_confirmed
timestamp_semantics_confirmed
price_quantity_units_confirmed
transform_semantics_confirmed
notes
authorizes_routing
authorizes_submission
```

Set `decision` to `approved` or `rejected`. An approval requires every
attestation field to be true and both authorization fields to be explicitly
false. The candidate must cover the intake contract exactly, reference only
columns present in the profiled source header, preserve required fields, and
use a transform supported by `normalize-mapped-data`. An honestly incomplete
mapping can be sealed as rejected evidence; it cannot be approved.

Outputs:

```text
reviewed_vendor_mapping.csv
vendor_mapping_review_checks.csv
vendor_mapping_review_action_queue.csv
vendor_mapping_review_summary.csv
vendor_mapping_review_receipt.json
vendor_mapping_review_config.json
vendor_mapping_review_runbook.md
manifest.json
```

Verify the retained intake/source graph, candidate and decision fingerprints,
canonical mapping, and every generated artifact before normalization:

```powershell
python -m hft_cli verify-vendor-mapping-review `
  --review mappings\arrow_ticks_review `
  --fail-on-breach
```

The receipt is an operator-attested review record, not a cryptographic
signature or vendor endorsement. A verified approval authorizes only the exact
reviewed mapping for normalization. It never authorizes strategy research,
routing, submission, or live release. Catalogs distinguish
`verified_approved`, `verified_rejected`, and `stale_or_inconsistent` review
evidence.

## Exact-Header Mapping Reuse Review

Seal a separate operator decision before reusing an approved canonical mapping
across daily files. The decision binds the existing exact-source mapping review,
canonical mapping bytes, adapter, data kind, and the seed source's ordered-header
SHA-256. The operator decision must remain outside both evidence directories:

```powershell
python -m hft_cli review-vendor-mapping-scope `
  --review mappings\arrow_ticks_review `
  --decision mappings\arrow_ticks_scope_decision.csv `
  --out mappings\arrow_ticks_exact_header_scope `
  --fail-on-rejected
```

The one-row scope decision uses these columns:

```text
mapping_review_id
mapping_review_sha256
reviewed_mapping_sha256
source_header_sha256
adapter
kind
reuse_scope
decision
operator_id
operator_role
reviewed_at_utc
vendor_documentation_checked
schema_stability_confirmed
field_semantics_stable_across_files_confirmed
timestamp_semantics_stable_across_files_confirmed
price_quantity_units_stable_across_files_confirmed
transform_semantics_stable_across_files_confirmed
partitioning_semantics_confirmed
notes
authorizes_header_scoped_application
authorizes_routing
authorizes_submission
```

Set `reuse_scope` to `exact_header` and `decision` to `approved` or
`rejected`. Every semantic attestation must be explicitly true. An approval
requires `authorizes_header_scoped_application=true`; a rejection requires it
to be false. Routing and submission authorization must always be false.

Outputs:

```text
scope_approved_vendor_mapping.csv
vendor_mapping_scope_review_checks.csv
vendor_mapping_scope_review_action_queue.csv
vendor_mapping_scope_review_summary.csv
vendor_mapping_scope_review_receipt.json
vendor_mapping_scope_review_config.json
vendor_mapping_scope_review_runbook.md
manifest.json
```

Verify the base review graph, decision fingerprint, exact mapping bytes, every
generated artifact, and all non-authorizing safety surfaces before use:

```powershell
python -m hft_cli verify-vendor-mapping-scope-review `
  --scope-review mappings\arrow_ticks_exact_header_scope `
  --fail-on-breach
```

A verified approval grants mapping application only when a future source has
the exact same ordered header. It does not approve that future source, perform
normalization, or authorize strategy research, routing, submission, or live
release. Target-file binding and normalization evidence remain separate gates.
Catalogs distinguish `verified_approved`, `verified_rejected`, and
`stale_or_inconsistent` scope evidence.

## Target Mapping Application

Bind an approved exact-header scope to one future vendor file before
normalization. First retain a write-once intake for the target file, using the
same adapter and data kind as the scope:

```powershell
python -m hft_cli intake-vendor-csv `
  --sample data\arrow\2026-07-15-ticks.csv `
  --out mappings\arrow_ticks_2026_07_15_intake `
  --adapter arrow_money `
  --kind ticks
```

Apply the scope to that retained intake:

```powershell
python -m hft_cli apply-vendor-mapping-scope `
  --scope-review mappings\arrow_ticks_exact_header_scope `
  --intake mappings\arrow_ticks_2026_07_15_intake `
  --out mappings\arrow_ticks_2026_07_15_application `
  --fail-on-breach
```

The command reconstructs both evidence graphs before writing anything. It
requires an approved current scope, a semantically verified current target
intake, matching adapter and kind, and an exact match of the ordered-header
SHA-256. A blocked intake with opaque vendor column names can be accepted when
its exact header and the operator-approved mapping scope match; inferred
semantics are not substituted for that approval.

Outputs:

```text
target_applied_vendor_mapping.csv
vendor_mapping_application_checks.csv
vendor_mapping_application_action_queue.csv
vendor_mapping_application_summary.csv
vendor_mapping_application_receipt.json
vendor_mapping_application_config.json
vendor_mapping_application_runbook.md
manifest.json
```

Verify the retained scope, target intake/source, byte-identical mapping, and
all generated artifacts before a later normalization gate consumes the proof:

```powershell
python -m hft_cli verify-vendor-mapping-application `
  --application mappings\arrow_ticks_2026_07_15_application `
  --fail-on-breach
```

The application receipt is target-file specific. Reordered, added, removed, or
renamed columns change the header hash and are refused before output. The proof
does not execute or authorize normalization, strategy research, routing,
submission, or live release. Catalogs report `verified_ready` or
`stale_or_inconsistent` application evidence.

## Target-Applied Vendor Data Normalization

Normalize the exact target source with the exact mapping retained by a
verified target application. Source path, mapping path, adapter, and data kind
are all derived from the application and cannot be replaced on the command
line:

```powershell
python -m hft_cli normalize-applied-vendor-mapping `
  --application mappings\arrow_ticks_2026_07_15_application `
  --out runs\data\arrow_ticks_2026_07_15_applied `
  --timestamp-unit datetime `
  --timestamp-tz Asia/Kolkata `
  --fail-on-breach `
  --fail-on-blocked-actions
```

Outputs:

```text
normalized_data.csv
mapped_data_checks.csv
mapped_data_application_checks.csv
mapped_data_action_queue.csv
mapped_data_summary.csv
mapped_data_receipt.json
mapped_data_config.json
mapped_data_runbook.md
manifest.json
```

The write-once operation reconstructs the mapping application before writing,
then derives and records the exact source, ordered-header, mapping, intake,
scope-review, adapter, and kind lineage. The application itself remains
non-authorizing; explicit invocation of this command performs normalization
only. Opaque vendor headers are accepted only when the earlier operator review,
exact-header scope, and per-file application all verify.

Reconstruct the normalized data and every retained input before downstream
readiness checks consume it:

```powershell
python -m hft_cli verify-applied-vendor-mapping-normalization `
  --normalization runs\data\arrow_ticks_2026_07_15_applied `
  --fail-on-breach
```

Catalogs distinguish `verified_ready`, `verified_blocked`, and
`stale_or_inconsistent`. Target-source drift, upstream application/scope drift,
and edited artifacts remain invalid even when a new manifest is generated.
This proof does not authorize strategy research, routing, submission, or live
release.

## Reviewed Vendor Data Normalization

Normalize the exact raw source with the exact canonical mapping from a verified
approved mapping review. Source path, mapping path, adapter, and data kind are
derived from the retained approval and cannot be substituted on the command
line:

```powershell
python -m hft_cli normalize-reviewed-mapped-data `
  --review mappings\arrow_ticks_review `
  --out runs\data\arrow_ticks_reviewed `
  --timestamp-unit datetime `
  --timestamp-tz Asia/Kolkata `
  --fail-on-breach `
  --fail-on-blocked-actions
```

Outputs:

```text
normalized_data.csv
mapped_data_checks.csv
mapped_data_review_checks.csv
mapped_data_action_queue.csv
mapped_data_summary.csv
mapped_data_receipt.json
mapped_data_config.json
mapped_data_runbook.md
manifest.json
```

The output is write-once. A rejected or stale review is refused before an
output directory is created. An approved mapping can still produce valid
blocked evidence when timestamps, session filtering, values, or transforms
yield no usable normalized rows. `mapped_data_summary.csv` preserves the
existing data-readiness contract while adding the review ID, exact source and
mapping fingerprints, binding checks, and explicit non-research/non-routing
safety fields.

Reconstruct the normalization from the current approved review, source, mapping,
and settings before using it downstream:

```powershell
python -m hft_cli verify-reviewed-mapped-data `
  --normalization runs\data\arrow_ticks_reviewed `
  --fail-on-breach
```

Catalogs distinguish `verified_ready`, `verified_blocked`, and
`stale_or_inconsistent`. A verified normalization proves deterministic mapping
under the operator approval only. It does not authorize strategy research,
routing, submission, or live release; the data-readiness and later promotion
gates remain mandatory.

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
Arrow.money/iRage handoff. When route-readiness proof is required, broker
readiness also verifies that the route proof preserved direct launch-control
evidence (`ops_launch_controls_present`, blocked pairs, and broker
allocation/concentration breach pairs) plus the legacy broker
allocation/concentration proof counts when older artifacts provide them, and
fails closed if those controls are missing, stale, or breached. If the final
round-trip config carries `route_broker_route_readiness`, broker readiness
retains it as `route_broker_route_readiness_*` summary fields and
`dispatch_roundtrip.route_broker_route_readiness` JSON, revalidating launch
controls plus allocation-safe/concentration-OK broker run counts before the
broker handoff can pass. Scale-up,
cutover, and route-enable artifacts carry
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
`proof_refresh_*` context. If the resume summary carries
`broker_route_readiness_*` or `incident_broker_route_readiness_*` evidence,
broker readiness revalidates that proof for ready state, strategy/market
identity, zero route gaps, launch-control readiness, and clean broker
portfolio/concentration round-trip counters. Resume-carried route proof is
retained in `broker_readiness_summary.csv` as
`resume_broker_route_readiness_*` and
`resume_incident_broker_route_readiness_*`, and in
`broker_readiness_config.json` under `resume_gate.broker_route_readiness` and
`resume_gate.incident_broker_route_readiness`. Stale resume route blockers
route to `review-route-readiness`. `--require-resume-gate` fails closed unless
`resume_summary.csv` is present and ready, which is useful for post-halt
restart reviews.
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
as the current generic round-trip vendor-data proof and seeds the broker-specific
readiness-native proof only when no stronger broker-specific source is already
present. A final round-trip, acknowledgement, dispatch, route, cutover, or
scale-up proof therefore keeps precedence. Broker readiness fingerprints the
supplied batch config and manifest regardless.
If the round-trip config carries
`roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch`, broker
readiness revalidates the broker-readiness final dispatch batch proof and
retains it as `broker_dispatch_roundtrip_vendor_market_data_batch_*` summary
fields plus `dispatch_roundtrip.broker_dispatch_roundtrip_vendor_market_data_batch`
config. For a target-application-backed final batch, that block also carries
`application_lineage_consistency_required` and
`application_lineage_consistent` plus the final batch's declared
`application_lineage_sha256`. Broker readiness requires the affirmative final
comparison and all nine retained lineage views from current, broker-final,
scale-up, cutover, route, dispatch, send, acknowledgement, and final review,
whether they came from nested config or flattened final-summary fields. It then
independently canonicalizes the final datasets as a tenth view and stores that
digest under
`dispatch_roundtrip.broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Reconciled targets additionally require the final roundtrip's complete
seventeen-view comparison. Broker readiness verifies its current, broker-final,
scale-up-, cutover-, route-, dispatch-, send-, acknowledgement-,
prior-roundtrip-, readiness-, scale-up-review-, cutover-review-,
route-enable-review-, dispatch-plan-review-, send-packet-review-,
acknowledgement-reconciliation-review-, and roundtrip-final-review-carried
digests, then independently recomputes view eighteen from the final datasets.
The existing ten-view compatibility proof remains unchanged for controlled
scale-up. The complete eighteen-view proof is emitted in flattened summary
fields and
`dispatch_roundtrip.broker_readiness_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`,
where `roundtrip_final_review_carried_application_lineage_sha256` retains
roundtrip view seventeen and `carried_application_lineage_sha256` is the fresh
broker-readiness digest. Missing, negative, blank, mismatched, or
post-final-drifted proof fails closed. Broker readiness now also requires the
round-trip `roundtrip_complete_final_*` twenty-five-view sibling for reconciled
targets, accepting nested config or flattened `ack_complete_final_*` summary
recovery. It verifies every historical stage and review digest, anchors the
complete proof to the established seventeen-view contract, retains
`ack_complete_final_review_carried_application_lineage_sha256`, retains round-trip
view twenty-five as
`roundtrip_complete_final_review_carried_application_lineage_sha256`, and
independently recomputes view twenty-six. The result is emitted under
`dispatch_roundtrip.broker_readiness_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Broker readiness now also consumes nested `roundtrip_extended_complete_final_*`
view-thirty-three config or flattened `ack_extended_complete_final_*` summary
fields. It verifies every inherited stage and review digest through
roundtrip-extended-complete-final review, requires agreement with the
established view-twenty-five broker and roundtrip-complete-final anchors, and
independently recomputes view thirty-four. The additive result is emitted under
`dispatch_roundtrip.broker_readiness_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`,
where `roundtrip_extended_complete_final_review_carried_application_lineage_sha256`
retains round-trip view thirty-three and `carried_application_lineage_sha256`
is the fresh readiness digest.
The established eighteen-view `broker_readiness_final_*` handoff remains
unchanged for controlled scale-up. Controlled scale-up now consumes the
additive twenty-six-view sibling while preserving the established handoff for
cutover.
Broker readiness additionally consumes nested
`roundtrip_latest_extended_complete_final_*` view-forty-one config or flattened
`ack_latest_extended_complete_final_*` summary fields. It revalidates every
inherited stage and review digest through roundtrip-latest-extended-complete-
final review, requires agreement with the established view-thirty-three broker
and roundtrip-extended-complete-final-review anchors, and independently
recomputes view forty-two. The additive result is emitted under
`dispatch_roundtrip.broker_readiness_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`,
where `roundtrip_latest_extended_complete_final_review_carried_application_lineage_sha256`
retains final roundtrip view forty-one and
`carried_application_lineage_sha256` is the fresh readiness digest. The
established view-thirty-four `broker_readiness_extended_complete_final_*`
handoff remains unchanged for controlled-scale-up compatibility. Controlled
scale-up now consumes the additive view-forty-two sibling and emits view
forty-three under
`broker_readiness.dispatch_roundtrip.scaleup_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-thirty-five `scaleup_extended_complete_final_*` output
remains unchanged as cutover's compatibility anchor. Cutover separately
consumes view forty-three and emits additive view forty-four under
`cutover_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-thirty-six `cutover_extended_complete_final_*` output
remains unchanged as route-enable's compatibility anchor. Route-enable
separately consumes view forty-four and emits additive view forty-five under
`route_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-thirty-seven `route_extended_complete_final_*` output
remains unchanged as broker dispatch's compatibility anchor. Broker dispatch
consumes additive view forty-five and emits fresh view forty-six under
`dispatch_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-thirty-eight `dispatch_extended_complete_final_*` output
remains unchanged for sender compatibility. Sender preparation consumes view
forty-six, revalidates the inherited chain against the established view-thirty-
eight anchors, and emits additive view forty-seven under
`send_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-thirty-nine output remains unchanged for acknowledgement
compatibility. Acknowledgement consumes view forty-seven, retains the inherited
`ack_latest_*` digest, independently recomputes `ack_current_latest_*`, and
emits additive view forty-eight under
`ack_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-forty output remains unchanged for roundtrip
compatibility. Roundtrip consumes view forty-eight from nested acknowledgement
config or flattened `send_latest_extended_complete_final_*` summary fields,
revalidates the inherited chain against the established view-forty anchors,
retains inherited `roundtrip_latest_*`, independently recomputes
`roundtrip_current_latest_*`, and emits additive view forty-nine under
`roundtrip_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-forty-one output remains unchanged for broker-readiness
compatibility. Broker readiness consumes view forty-nine from nested roundtrip
config or flattened `ack_current_latest_extended_complete_final_*` summary
fields, revalidates the inherited chain against the established view-forty-two
anchors, retains inherited `broker_readiness_latest_*`, independently
recomputes `broker_readiness_current_latest_*`, and emits additive view fifty
under
`dispatch_roundtrip.broker_readiness_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-forty-two output remains unchanged for controlled-scale-up
compatibility, and scale-up ignores additive view fifty.
Generic onboarding target proof without a final cross-stage result and legacy
draft-backed proof keep their compatibility paths. If the round-trip and
current generic proofs are both active and either one signals target mode,
broker readiness separately canonicalizes each dataset's source, mapping,
scope-review, target-intake, and applied-mapping identity. It records the
current and final lineage SHA-256 digests under
`dispatch_roundtrip.vendor_market_data_batch_lineage_comparison` and fails
closed unless the graphs match; dataset labels and generated output paths do
not affect that identity comparison. If the round-trip config carries
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
identity. If the nested broker-readiness folder is unavailable but the launch
root summary carries `broker_readiness_route_*` proof, scale-up hydrates that
broker route proof for `--require-broker-readiness`. Surface-MM keeps the
legacy `surface_launch_pipeline` block as a compatibility alias.
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
Any supplied strategy portfolio must now be a complete current
`strategy_portfolio_allocation` artifact, even when
`--require-strategy-portfolio` is omitted. Scale-up verifies the portfolio
manifest and all required artifacts, reconciles summary/allocation/config
semantics, rejects submission-authorizing claims, and reopens the carried
strategy scorecard and research-family manifests to verify their hashes,
family ID, prospective registration ID, closure, and family-wise error-control
claim. Missing, stale, detached, relabeled, or authorizing portfolio proof
blocks scale-up. The source allocation remains visible for audit, but its
usable notional becomes zero and no portfolio cap is applied.
`scaleup_summary.csv` and `scaleup_config.json` retain portfolio-manifest,
scorecard-manifest, and family-closure status and hashes. The scale-up manifest
fingerprints all portfolio artifacts plus the recursively flattened portfolio,
scorecard, family, registration, robust-study, and source-data dependencies,
so later nested drift invalidates the scale-up plan. Scale-up remains
non-authorizing and cannot enable broker submission.
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
`ops_launch` evidence chain has accepted the exact strategy/market route. The
scale-up gate now also verifies that supplied route-readiness summaries carry
launch-grade ops broker controls, and it preserves blocked/breach counts in
`scaleup_summary.csv` and `scaleup_config.json`. Route-readiness resume-route
proof is preserved too: direct route-readiness inputs add
`route_readiness_ops_broker_roundtrip_resume_route_*_pairs`, while
broker-carried route proof adds
`broker_route_readiness_ops_broker_roundtrip_resume_route_*_runs`; scale-up
requires at least one broker-carried resume-route ready run and zero breach,
gap, launch-control, portfolio, or concentration resume-route breach runs
before controlled capital increases.
If broker readiness included resume-gate evidence, scale-up also retains the
resume authorization identity, prior incident identity, and resume
`proof_refresh_*` context. `--require-resume-gate` fails closed unless broker
readiness supplied a ready resume gate with strategy/market and proof-refresh
identity matching the scale-up identity.
When the broker-readiness summary or `broker_readiness_config.json` sidecar
also carries resume-gate broker route-readiness proof, scale-up exports
`broker_resume_broker_route_readiness_*` and
`broker_resume_incident_broker_route_readiness_*` fields, mirrors them under
`broker_readiness.resume_gate`, and fails closed on stale route identity, route
gaps, missing launch controls, or portfolio allocation/concentration breaches
before controlled capital increases.
If broker readiness included dispatch round-trip evidence, scale-up also
retains the proved dry-run target mode, strategy, market, scenario, dispatch
batch, request count, accepted acknowledgements, failed-check count, and
route-enable dispatch round-trip failed-check count, and missing, rejected, and
unmatched acknowledgement counts, plus the nested route proof target, identity,
batch, request, and ack quality fields. `--require-dispatch-roundtrip` fails
closed unless that broker dry-run proof and its route proof are present, ready,
identity-matched, count-matched, and clean. If broker readiness carried
route-readiness ops broker controls, scale-up revalidates those allocation and
concentration proof counts before allowing promotion.
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
For an application-backed batch, any target-application mode, source, count,
or coverage signal activates the stricter scale-up contract. The mapping mode
must be `per_dataset_verified_target_application`, application and unique
application counts must both equal the dataset count, coverage must be 100%,
and every dataset must retain its application path/ID/hash, scope-review
ID/hash, target-intake receipt ID, and applied-mapping hash. These fields are
preserved in both the scale-up summary and nested config, including when they
are hydrated from a thin broker-readiness summary plus its config sidecar.
Target-backed scale-up now also requires broker readiness to carry a successful
current/final lineage comparison. Scale-up validates the two upstream SHA-256
digests, recomputes the canonical digest from the carried dataset identities,
and fails closed if either digest disagrees. When final consistency is required,
scale-up continues to require the broker-readiness ten-view compatibility
comparison, verifies its current, broker-final, prior scale-up-, cutover-,
route-, dispatch-, send-, acknowledgement-, final-review-, and
readiness-carried digests plus the final batch's declared digest, then treats
its independent recomputation as view eleven. Reconciled targets additionally
require
`broker_readiness_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`
from nested readiness config or its flattened `roundtrip_final_*` summary
projection. Scale-up revalidates the current, broker-final, historical
scale-up-, cutover-, route-, dispatch-, send-, acknowledgement-, roundtrip-,
readiness-, scale-up-review-, cutover-review-, route-enable-review-,
dispatch-plan-review-, send-packet-review-, acknowledgement-reconciliation-
review-, roundtrip-final-review-, and broker-readiness-review-carried digests,
then independently recomputes view nineteen. Missing or negative final
decisions, blank or mismatched views, and post-readiness dataset drift block
promotion. Generic target onboarding without a final reconciliation keeps the
current/final/recomputed compatibility path.
The summary retains final-consistency, match, and digest fields;
`broker_readiness.dispatch_roundtrip.vendor_market_data_batch` retains the
consistency state and recomputed digest, while
`broker_readiness.dispatch_roundtrip.vendor_market_data_batch_lineage_comparison`
retains the current, broker-final, and scale-up-carried digests for cutover. The
sibling
`broker_readiness.dispatch_roundtrip.broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`
retains all ten broker-readiness views plus the scale-up-carried compatibility
digest. That eleven-view block remains unchanged for cutover. The complete
nineteen-view proof is emitted in flattened `broker_readiness_final_*` summary
fields and
`broker_readiness.dispatch_roundtrip.scaleup_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`,
where `broker_readiness_review_carried_application_lineage_sha256` retains
broker-readiness view eighteen and `carried_application_lineage_sha256` is the
fresh scale-up digest. Reconciled targets now also require broker readiness's
`broker_readiness_complete_final_*` twenty-six-view sibling. Controlled
scale-up accepts it from nested readiness config or flattened
`roundtrip_complete_final_*` summary fields, revalidates every historical stage
and review digest through broker-readiness-complete-final review, binds it to
the established eighteen-view anchors, and independently recomputes view
twenty-seven. Flattened `broker_readiness_complete_final_*` summary fields
retain the input and fresh review digests, while
`broker_readiness.dispatch_roundtrip.scaleup_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`
retains all twenty-seven views. The established nineteen-view `scaleup_final_*`
handoff remains unchanged for compatibility. Cutover now consumes the additive
twenty-seven-view sibling while retaining that established nineteen-view
contract. Controlled scale-up now also consumes broker readiness's
view-thirty-four `broker_readiness_extended_complete_final_*` sibling from
nested readiness config or flattened `roundtrip_extended_complete_final_*`
summary fields. It revalidates every inherited stage and review digest,
requires agreement with the established view-twenty-six broker and broker-
readiness-complete-final-review anchors, and independently recomputes view
thirty-five. The additive result is emitted under
`broker_readiness.dispatch_roundtrip.scaleup_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`,
where `broker_readiness_extended_complete_final_review_carried_application_lineage_sha256`
retains readiness view thirty-four and `carried_application_lineage_sha256` is
the fresh scale-up digest. The established view-twenty-seven
`scaleup_complete_final_*` handoff remains unchanged as cutover's compatibility
anchor and the source for the established view-twenty-eight proof. Cutover now
also consumes view thirty-five and emits the additive view-thirty-six proof
described in the cutover section below.
Controlled scale-up additionally consumes broker readiness's view-forty-two
`broker_readiness_latest_extended_complete_final_*` sibling from nested
readiness config or flattened `roundtrip_latest_extended_complete_final_*`
summary fields. It revalidates every inherited stage and review digest through
broker-readiness-latest-extended-complete-final review, requires agreement with
the established view-thirty-four broker and broker-readiness-extended-complete-
final-review anchors, and independently recomputes view forty-three. The
additive result is emitted under
`broker_readiness.dispatch_roundtrip.scaleup_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`,
where `broker_readiness_latest_extended_complete_final_review_carried_application_lineage_sha256`
retains readiness view forty-two and `carried_application_lineage_sha256` is
the fresh scale-up digest. The established view-thirty-five
`scaleup_extended_complete_final_*` handoff remains unchanged as cutover's
compatibility anchor. Cutover now consumes additive view forty-three from
nested scale-up config or flattened
`broker_readiness_latest_extended_complete_final_*` summary fields, revalidates
the complete inherited chain, and emits fresh view forty-four under
`cutover_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Route-enable now consumes additive view forty-four from nested cutover config
or flattened `scaleup_latest_extended_complete_final_*` summary fields,
revalidates the complete inherited chain, and emits fresh view forty-five under
`route_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Broker dispatch consumes additive view forty-five from nested route config or
flattened `cutover_latest_extended_complete_final_*` summary fields, revalidates
the complete inherited chain, and emits fresh view forty-six under
`dispatch_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Its established view-thirty-eight output remains unchanged. Sender preparation
now consumes additive view forty-six from nested dispatch config or flattened
`route_latest_extended_complete_final_*` summary fields, revalidates the full
chain, and emits fresh view forty-seven under
`send_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Its established view-thirty-nine output remains unchanged, and acknowledgement
now consumes additive view forty-seven from nested send config or flattened
`dispatch_latest_extended_complete_final_*` summary fields, revalidates the
full chain, and emits fresh view forty-eight under
`ack_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Its established view-forty output remains unchanged, and roundtrip continues to
use it as the compatibility anchor. Roundtrip now consumes additive view forty-
eight from nested acknowledgement config or flattened
`send_latest_extended_complete_final_*` summary fields, revalidates the full
chain, retains inherited `roundtrip_latest_*`, and emits fresh view forty-nine
under
`roundtrip_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Its established view-forty-one output remains unchanged as broker readiness's
compatibility anchor. Broker readiness now consumes additive view forty-nine
from nested roundtrip config or flattened
`ack_current_latest_extended_complete_final_*` summary fields, revalidates the
full chain, retains inherited `broker_readiness_latest_*`, and emits fresh view
fifty under
`broker_readiness_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Its established view-forty-two output remains unchanged. Controlled scale-up
now also consumes additive view fifty from nested broker-readiness config or
flattened `roundtrip_current_latest_extended_complete_final_*` summary fields,
revalidates the full inherited and latest/current-stage chain against the
established view-forty-three broker and scale-up-latest anchors, and emits fresh
view fifty-one under
`broker_readiness.dispatch_roundtrip.scaleup_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-forty-three `scaleup_latest_extended_complete_final_*`
handoff remains unchanged. Cutover now consumes additive view fifty-one from
nested scale-up config or flattened
`broker_readiness_current_latest_extended_complete_final_*` summary fields,
revalidates the inherited and latest/current-stage chain against the
established view-forty-four broker and cutover-latest anchors, and emits fresh
view fifty-two under
`cutover_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-forty-four `cutover_latest_extended_complete_final_*`
handoff remains unchanged. Route-enable now consumes additive view fifty-two
from nested cutover config or flattened
`scaleup_current_latest_extended_complete_final_*` summary fields,
revalidates the full inherited and latest/current-stage chain against the
established view-forty-four broker and independently recomputed route-latest
anchors, and emits fresh view fifty-three under
`route_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-forty-five `route_latest_extended_complete_final_*`
handoff remains unchanged. Broker dispatch now consumes additive view
fifty-three from nested route config or flattened
`cutover_current_latest_extended_complete_final_*` summary fields,
revalidates the inherited and latest/current-stage chain against the
established view-forty-five broker and independently recomputed dispatch-
latest anchors, and emits fresh view fifty-four under
`dispatch_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-forty-six `dispatch_latest_extended_complete_final_*`
handoff remains unchanged. Sender preparation now consumes additive view
fifty-four from nested dispatch config or flattened
`route_current_latest_extended_complete_final_*` summary fields, revalidates
the inherited and latest/current-stage chain against the established view-
forty-six broker and independently recomputed send-latest anchors, and emits
fresh view fifty-five under
`send_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-forty-seven `send_latest_extended_complete_final_*`
handoff remains unchanged. Acknowledgement now consumes additive view fifty-
five from nested sender config or flattened
`dispatch_current_latest_extended_complete_final_*` summary fields,
revalidates the inherited and latest/current-stage chain against the
established view-forty-seven broker and independently recomputed
acknowledgement anchors, and emits fresh view fifty-six under
`ack_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-forty-eight `ack_current_latest_extended_complete_final_*`
handoff remains unchanged. Roundtrip now consumes additive view fifty-six from
nested acknowledgement config or flattened
`send_current_latest_extended_complete_final_*` summary fields, revalidates
the inherited and latest/current-stage chain against the established view-
forty-eight broker and independently recomputed roundtrip anchors, and emits
fresh view fifty-seven under
`roundtrip_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-forty-nine `roundtrip_current_latest_extended_complete_final_*`
handoff remains unchanged. Broker readiness now consumes additive view fifty-
seven from nested roundtrip config or flattened
`ack_reconciled_current_latest_extended_complete_final_*` summary fields,
revalidates the full inherited and reconciled chain against the established
view-forty-nine broker and independently recomputed broker-readiness anchors,
and emits fresh view fifty-eight under
`broker_readiness_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-fifty handoff remains unchanged. Controlled scale-up now
consumes additive view fifty-eight from nested broker-readiness config or
flattened `roundtrip_reconciled_current_latest_extended_complete_final_*`
summary fields, revalidates the inherited, latest/current, and reconciled
chain against established view-fifty broker and independently recomputed
scale-up anchors, and emits fresh view fifty-nine under
`broker_readiness.dispatch_roundtrip.scaleup_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-fifty-one handoff remains unchanged. Cutover now consumes
additive view fifty-nine from nested scale-up config or flattened
`broker_readiness_reconciled_current_latest_extended_complete_final_*` summary
fields, revalidates the complete reconciled chain against the established
view-fifty-one broker and independently recomputed cutover anchors, and emits
fresh view sixty under
`cutover_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-fifty-two handoff remains unchanged. Route-enable now
consumes additive view sixty from nested cutover config or flattened
`scaleup_reconciled_current_latest_extended_complete_final_*` summary fields,
revalidates the complete reconciled chain against the established view-fifty-
two broker and independently recomputed route anchors, and emits fresh view
sixty-one under
`route_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-fifty-three handoff remains unchanged. Broker dispatch
now consumes additive view sixty-one from nested route config or flattened
`cutover_reconciled_current_latest_extended_complete_final_*` summary fields,
revalidates the complete reconciled chain against the established view-fifty-
three broker and independently recomputed dispatch anchors, and emits fresh
view sixty-two under
`dispatch_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-fifty-four handoff remains unchanged, and sender
preparation now consumes additive view sixty-two from nested dispatch config
or flattened `route_reconciled_current_latest_extended_complete_final_*`
summary fields, revalidates the complete reconciled chain against the
established view-fifty-four broker and independently recomputed send anchors,
and emits fresh view sixty-three under
`send_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-fifty-five handoff remains unchanged, and
acknowledgement now consumes additive view sixty-three from nested sender
config, a separate sender-config handoff, or flattened
`dispatch_reconciled_current_latest_extended_complete_final_*` summary fields,
revalidates the complete reconciled chain against the established view-fifty-
five broker and independently recomputed acknowledgement anchors, and emits
fresh view sixty-four under
`ack_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-fifty-six handoff remains unchanged. Roundtrip now
consumes additive view sixty-four from nested acknowledgement config or
flattened `send_reconciled_current_latest_extended_complete_final_*` summary
fields, revalidates the complete verified-reconciled chain against the
established view-fifty-six broker and independently recomputed roundtrip
anchors, and emits fresh view sixty-five under
`roundtrip_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-fifty-seven handoff remains unchanged. Broker readiness
now consumes additive view sixty-five from nested roundtrip config or
flattened `ack_verified_reconciled_current_latest_extended_complete_final_*`
summary fields, revalidates the exact verified-reconciled chain against the
established view-fifty-seven broker and independently recomputed readiness
anchors, and emits fresh view sixty-six under
`broker_readiness_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-fifty-eight handoff remains unchanged. Controlled scale-
up now consumes additive view sixty-six from flattened broker-readiness summary
fields or nested `broker_readiness_config.json`, revalidates the exact verified-
reconciled chain against the established view-fifty-eight broker and
independently recomputed scale-up anchors, and emits fresh view sixty-seven
under
`scaleup_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-fifty-nine handoff remains unchanged. Cutover now
consumes additive view sixty-seven from nested scale-up config or flattened
`broker_readiness_verified_reconciled_current_latest_extended_complete_final_*`
summary fields, revalidates the exact verified-reconciled chain against the
established view-fifty-nine broker and independently recomputed cutover
anchors, and emits fresh view sixty-eight under
`cutover_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-sixty handoff remains unchanged. Route-enable now
consumes additive view sixty-eight from nested cutover config or flattened
`scaleup_verified_reconciled_current_latest_extended_complete_final_*` summary
fields, revalidates the exact verified-reconciled chain against the established
view-sixty broker and independently recomputed route anchors, and emits fresh
view sixty-nine under
`route_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-sixty-one handoff remains unchanged. Broker dispatch now
consumes additive view sixty-nine from nested route config or flattened
`cutover_verified_reconciled_current_latest_extended_complete_final_*` summary
fields, revalidates the exact verified-reconciled chain against the established
view-sixty-one broker and independently recomputed dispatch anchors, and emits
fresh view seventy under
`dispatch_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-sixty-two handoff remains unchanged for sender
preparation. Sender preparation now consumes additive view seventy from nested
dispatch config or flattened
`route_verified_reconciled_current_latest_extended_complete_final_*` summary
fields, revalidates the exact verified-reconciled chain against the established
view-sixty-two broker and independently recomputed send anchors, and emits
fresh view seventy-one under
`send_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-sixty-three handoff remains unchanged for acknowledgement,
which now consumes additive view seventy-one from nested sender config or
flattened
`dispatch_verified_reconciled_current_latest_extended_complete_final_*`
summary fields, revalidates the exact verified-reconciled chain against the
established view-sixty-three broker and independently recomputed
acknowledgement anchors, and emits fresh view seventy-two under
`ack_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-sixty-four handoff remains unchanged for roundtrip, which
now consumes additive view seventy-two from nested acknowledgement config or
flattened `send_verified_reconciled_current_latest_extended_complete_final_*`
summary fields, revalidates the exact confirmed verified-reconciled chain
against the established view-sixty-four broker and independently recomputed
roundtrip anchors, and emits fresh view seventy-three under
`roundtrip_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-sixty-five handoff remains unchanged for broker readiness,
which now consumes additive view seventy-three from nested roundtrip config or
flattened
`ack_confirmed_verified_reconciled_current_latest_extended_complete_final_*`
summary fields, revalidates the exact confirmed verified-reconciled chain
against the established view-sixty-five broker and independently recomputed
broker-readiness anchors, and emits fresh view seventy-four under
`broker_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-sixty-six handoff remains unchanged for controlled scale-
up, which now consumes additive view seventy-four from nested broker-readiness
config or flattened
`roundtrip_confirmed_verified_reconciled_current_latest_extended_complete_final_*`
summary fields, revalidates the exact confirmed verified-reconciled chain
against the established view-sixty-six broker and independently recomputed
controlled-scale-up anchors, and emits fresh view seventy-five under
`scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-sixty-seven handoff remains unchanged for cutover, which
now consumes additive view seventy-five from nested controlled-scale-up config
or flattened
`broker_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_*`
summary fields, revalidates the exact confirmed verified-reconciled chain
against the established view-sixty-seven broker and independently recomputed
cutover anchors, and emits fresh view seventy-six under
`cutover_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-sixty-eight handoff remains unchanged for route
enablement, which continues to derive established view sixty-nine from view
sixty-eight. Route enablement now also consumes additive view seventy-six from
nested cutover config or flattened
`scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_*`
summary fields, revalidates the exact confirmed verified-reconciled chain
against the established view-sixty-eight broker and independently recomputed
route anchors, and emits fresh view seventy-seven under
`route_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Broker dispatch continues to derive established view seventy from view sixty-
nine. It now also consumes additive view seventy-seven from nested route config
or flattened
`cutover_confirmed_verified_reconciled_current_latest_extended_complete_final_*`
summary fields, revalidates the exact 76-field confirmed verified-reconciled
chain against the established view-sixty-nine broker and independently
recomputed dispatch anchors, and emits fresh view seventy-eight under
`dispatch_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Sender preparation continues to derive established view seventy-one from view
seventy and intentionally ignores additive view seventy-eight.
Legacy draft-backed batches continue through the existing provenance checks.
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
File-based telemetry now requires `--scaleup` to resolve to a complete current
`scaleup_plan` bundle, not a standalone `scaleup_config.json`. It verifies the
plan, checks, summary, config, manifest run type, artifact hashes, and every
recursive scale-up input before accepting session limits. It also reconciles
ready state, failed-check count, identity, limits, and explicit
`authorizes_submission=false` claims across those artifacts. A config that was
edited and freshly re-manifested without matching summary/plan semantics still
fails closed. The telemetry output must be separate from the source scale-up
directory so it cannot overwrite the proof it consumes.
Telemetry carries the scale-up `strategy` and `market` identities from
`scaleup_config.json`; missing identity fails closed before guard evaluation.
When scale-up required proof-refresh evidence, telemetry also carries
`proof_refresh_*` fields from the scale-up config and fails closed if the proof
is missing, unready, mixed, or for a different strategy/market.
When scale-up required broker resume-gate evidence, telemetry also carries
`broker_resume_*` fields from the scale-up config and fails closed if the
resume authorization, its strategy/market identity, or its proof-refresh
identity is missing or stale.
When scale-up required or supplied broker route-readiness evidence, telemetry
also carries `broker_route_readiness_*` fields from the scale-up config and
fails closed if the route proof, route-ready/gap pairs, launch-control proof,
portfolio-safe runs, or concentration-safe runs are missing, mismatched, or
stale.
When scale-up required or supplied strategy portfolio allocation evidence,
telemetry also carries `strategy_portfolio_*` fields from the scale-up config,
including selected profile, strategy, market, allocation notional, and whether
the portfolio cap was applied. These telemetry fields now also include
portfolio-level strategy/market diversity requirements, allocated
strategy/market counts, top concentration names, and maximum aggregate
strategy/market allocation weights.
Telemetry now additionally carries the current scale-up manifest SHA-256,
contract and non-authorizing status, recursively verified dependency count,
portfolio-manifest SHA-256, scorecard-manifest SHA-256, and registered
research-family ID, registration ID, and manifest SHA-256. When portfolio
evidence is present, telemetry reopens the portfolio source named by the
scale-up manifest and re-runs its nested scorecard/family verifier rather than
trusting copied `*_current` flags. The telemetry manifest fingerprints the
scale-up manifest, all required scale-up artifacts, and its flattened
dependencies, so later portfolio, scorecard, registration, robust-study, or
raw-source drift invalidates the snapshot. Telemetry outputs remain explicitly
non-authorizing.
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
`runtime_telemetry.csv` file directly. For a portfolio- or family-bound
scale-up, a direct CSV must carry the provenance fields emitted by
`build-runtime-telemetry`; a hand-written row without that lineage halts.

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
If broker route-readiness evidence was required or supplied at scale-up, the
guard also requires runtime telemetry to carry ready route proof with matching
strategy/market identity, zero route gaps, ready launch controls, at least one
portfolio-safe and concentration-safe broker round-trip run, and zero breach
runs. Route-proof blockers are queued to `review-route-readiness`.
If strategy portfolio allocation evidence was required or supplied at scale-up,
the guard also requires the selected allocation to be ready, eligible, identity
matched, positive, and large enough for the observed `session_notional`; this
appears as an explicit `strategy_portfolio_session_notional` check in
`runtime_guard_checks.csv`. The guard summary/config preserves the same
portfolio concentration fields carried by telemetry, so a halt packet or
runtime session can explain the paper/shadow allocation context without
reopening the scale-up folder.
Before applying any limit, the guard independently re-verifies the current
scale-up manifest, artifact contract, recursive inputs, and non-authorizing
status. It then compares the scale-up manifest hash and, when applicable, the
portfolio, scorecard, and research-family hashes/identities carried by
telemetry against the current source. A snapshot built from an older scale-up,
a relabeled family, or drifted upstream research proof therefore produces a
halt and a `plan-scaleup` repair action instead of consuming stale limits.
Guard summary/config and manifest retain this lineage and remain explicitly
non-authorizing. Guard output must not overwrite either the scale-up or
telemetry input directory.

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
scale-up readiness, proof-refresh, resume-gate identity, and broker
route-readiness blockers point back to their repair gates. Use
`--fail-on-actions` to fail whenever a guard action is queued, or
`--fail-on-blocked-actions` to fail only when blocked guard actions appear.

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
evaluation. When scale-up uses broker route-readiness evidence, the session
steps, summary, and config also retain `broker_route_readiness_*` route-ready,
gap-pair, launch-control, portfolio-safe, and concentration-safe proof from the
telemetry/guard chain. When scale-up uses strategy portfolio allocation, the
session steps and summary also retain `strategy_portfolio_*` fields, including
selected strategy/market, eligibility, allocation weight/notional, pre-cap
notional, and whether the portfolio cap constrained session notional, plus the
carried strategy/market concentration counts and maximum aggregate allocation
weights.
The session steps, summary, config, runbook, and manifest now also carry the
guard-verified scale-up manifest SHA-256, portfolio and scorecard manifest
SHA-256 values, prospective research-family and registration IDs, family
manifest SHA-256, and telemetry-to-current-lineage comparisons. Config JSON
groups these under `scaleup_provenance` and `runtime_telemetry_lineage`, and
both config and manifest explicitly record `authorizes_submission=false`.
The session output directory cannot be the scale-up source directory.
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
The top-level `manifest.json` fingerprints the resolved scale-up config and
manifest, runtime source snapshots, telemetry artifacts, guard artifacts,
child manifests, and halt-response artifacts when a halt packet is created.
It also flattens the scale-up, telemetry, guard, and optional halt-response
manifest dependencies, so later portfolio, scorecard, family, registration,
study, or raw-source drift invalidates the session packet.

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
runtime session. When the guard carried broker route-readiness evidence, these
same halt artifacts also retain `broker_route_readiness_*` route-ready,
gap-pair, launch-control, portfolio-safe, and concentration-safe fields so
emergency cancel/flatten packets remain auditable to the route controls that
were active when routing stopped.
They additionally retain the guard-verified scale-up, portfolio, scorecard,
and prospective-family lineage plus the telemetry lineage-comparison fields.
`halt_response_config.json` groups the same values under
`scaleup_provenance` and `runtime_telemetry_lineage`; config, summary, and
manifest all record `authorizes_submission=false`. A stale provenance state is
preserved as evidence but deliberately does not block emergency cancel or
flatten readiness: a provenance failure may itself be the reason the guard
halted. `halt_response_runbook.md` surfaces the provenance currentness,
research-family ID, and non-authorizing state for human review.
`halt_response_action_queue.csv` and `halt_response_runbook.md` route non-halt
guard states and missing executable flatten prices back to the next CLI gate
before a scheduler trusts the cancel/flatten packet. Add `--fail-on-actions` to
fail on any queued response-plan action, or `--fail-on-blocked-actions` to fail
only when the queue contains blocked actions.
The manifest fingerprints the resolved runtime guard bundle, guard manifest,
recursively flattened guard dependencies, and the open-order and position
snapshots used to create the cancel/flatten packet. Later research-source drift
therefore invalidates the packet. The halt-response output directory cannot
overwrite the runtime-guard source directory.

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
scaled runtime. They also retain `broker_route_readiness_*` fields from the
guard or halt-response record, preserving the broker route-ready/gap-pair and
ops-control proof that was active when the halt was closed.
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
map open incident, scale-up, identity, proof-refresh, broker route-readiness,
and operator-review blockers to their next CLI gate. Use
`--fail-on-blocked-actions` to fail only when blocked resume actions exist, or
`--fail-on-actions` when any resume action should stop automation.

`resume_authorization.csv`, `resume_summary.csv`, and `resume_config.json`
retain the prior incident's guard-trigger, strategy, market, proof-refresh, and
broker route-readiness fields so resume approval is tied back to the exact halt
that was closed. Strategy, market, proof-refresh, and broker route-readiness
identity continuity are checked by default alongside scenario and adapter
continuity. If the incident or new scale-up plan contains proof freshness, the
resume gate also requires the new scale-up proof to be provided, ready,
non-mixed, and strategy/market-matched to the incident.

If the halt incident or new scale-up plan contains broker route-readiness
evidence, the resume gate requires the incident and scale-up route proof to be
provided, ready, strategy/market-matched, gap-free, and backed by clean
launch-control plus broker round-trip portfolio/concentration-safe runs.
Broker route-readiness blockers route to `review-route-readiness --help`.

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
identity before broker routing is allowed.

Cutover also revalidates scale-up route-readiness ops broker controls before
live-dryrun authorization: direct route-readiness proof must retain launch
control evidence with zero blocked pairs and zero broker round-trip
allocation/concentration breach pairs, and broker-readiness-carried route proof
must retain clean launch-control, allocation-safe, and concentration-OK run
counts. These fields are preserved in `cutover_summary.csv` and
`cutover_config.json` as `scaleup_route_readiness_*` and
`scaleup_broker_route_readiness`.
If scale-up also carried broker resume-gate route proof, cutover revalidates
the primary and incident resume-route branches and preserves them as
`scaleup_broker_resume_broker_route_readiness_*`,
`scaleup_broker_resume_incident_broker_route_readiness_*`, and nested
`scaleup_broker_resume_gate` config blocks. Stale post-halt route identity,
route gaps, missing launch controls, or broker round-trip portfolio breaches
block cutover before route-enable can inherit the authorization.

If scale-up carried vendor wrapper proof inside the shadow broker-readiness
aggregate, cutover carries it as
`scaleup_shadow_broker_vendor_data_readiness_*` fields plus
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
Application-backed proof also retains mapping mode, application count,
application uniqueness, target coverage, and per-dataset application,
scope-review, target-intake, and applied-mapping lineage. Any target signal
activates strict cutover checks requiring
`per_dataset_verified_target_application`, one distinct application per
dataset, 100% coverage, and complete lineage. Cutover additionally requires
the affirmative scale-up current/final lineage decision, verifies the two
upstream SHA-256 digests and the scale-up-carried digest, and independently
recomputes the canonical digest from the datasets it received. The scale-up
final dispatch/send/ack consistency decision and current, broker-final,
scale-up-carried, and cutover-carried digests remain visible in
`cutover_summary.csv` and the
`scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`
config block. When final consistency is required, cutover continues to require
the scale-up eleven-view compatibility comparison, revalidates it, and makes
its own canonical recomputation view twelve. The original four-view block and
full twelve-view handoff remain unchanged in flattened summary fields and the
sibling
`cutover_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`
retain all twelve views. Reconciled targets additionally require scale-up's
nineteen-view `scaleup_final_*` comparison. Cutover revalidates its current,
broker-final, prior scale-up-, cutover-, route-, dispatch-, send-, ack-,
roundtrip-, readiness-, scale-up-review-, cutover-review-, route-enable-review-,
dispatch-plan-review-, send-packet-review-, acknowledgement-reconciliation-review-,
roundtrip-final-review-, broker-readiness-review-, and
scale-up-final-review-carried digests, then independently computes view twenty.
Flattened `scaleup_final_*` fields retain the complete input and
`cutover_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`
retains all twenty views. The same contract applies when cutover reconstructs
the batch from flattened scale-up summary fields. A broker-readiness config
sidecar can hydrate the batch and compatibility comparisons, but cannot mint
scale-up's final review; a reconciled target relying only on that sidecar fails
closed. Reconciled targets also require scale-up's twenty-seven-view
`scaleup_complete_final_*` sibling. Cutover accepts it from nested scale-up
config or flattened `broker_readiness_complete_final_*` summary fields,
revalidates every historical stage and review digest through scale-up-complete-
final review, binds it to the established nineteen-view anchors, and
independently computes view twenty-eight. The additive result is emitted under
`cutover_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established twenty-view `cutover_final_*` handoff remains unchanged for
route-enable compatibility. Route enable now consumes the additive twenty-
eight-view sibling while retaining that established twenty-view contract.
Cutover now also requires scale-up's view-thirty-five
`scaleup_extended_complete_final_*` sibling. It accepts the proof from nested
scale-up config or flattened `broker_readiness_extended_complete_final_*`
summary fields, revalidates every inherited stage and review digest through
roundtrip-extended-complete-final, broker-readiness-extended-complete-final,
and scale-up-extended-complete-final review, and binds it to the established
view-twenty-seven broker and scale-up-complete-final-review anchors. Cutover's
fresh canonical digest becomes view thirty-six under
`cutover_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Missing or negative proof, any inherited digest drift, either compatibility-
anchor drift, or disagreement with cutover's recomputed datasets fails closed.
The established view-twenty-eight `cutover_complete_final_*` output remains
unchanged for route enable. Cutover additionally requires scale-up's
view-forty-three `scaleup_latest_extended_complete_final_*` sibling from nested
scale-up config or flattened
`broker_readiness_latest_extended_complete_final_*` summary fields. It
revalidates the complete chain through scale-up-latest-extended-complete-final
review, binds the proof to the established view-thirty-five broker and
scale-up-extended-complete-final-review anchors, and emits fresh view forty-four
under
`cutover_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-thirty-six `cutover_extended_complete_final_*` output
remains unchanged as route-enable's compatibility anchor. Route-enable
additionally consumes view forty-four from nested cutover config or flattened
`scaleup_latest_extended_complete_final_*` summary fields, revalidates the
complete chain through cutover-latest-extended-complete-final review, and emits
fresh view forty-five under
`route_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Route-enable now also requires cutover's view-fifty-two
`cutover_current_latest_extended_complete_final_*` sibling from nested cutover
config or flattened `scaleup_current_latest_extended_complete_final_*` summary
fields. It revalidates all inherited and latest/current-stage digests, binds
the proof to the established view-forty-four broker and independently
recomputed route-latest anchors, and emits fresh view fifty-three under
`route_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-forty-five output remains unchanged. Broker dispatch
now also requires route-enable's view-fifty-three
`route_current_latest_extended_complete_final_*` sibling from nested route
config or flattened `cutover_current_latest_extended_complete_final_*`
summary fields. It revalidates all inherited and latest/current-stage digests,
binds the proof to the established view-forty-five broker and independently
recomputed dispatch-latest anchors, and emits fresh view fifty-four under
`dispatch_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-forty-six output remains unchanged. Sender preparation
now also requires broker dispatch's view-fifty-four
`dispatch_current_latest_extended_complete_final_*` sibling from nested
dispatch config or flattened `route_current_latest_extended_complete_final_*`
summary fields. It revalidates all inherited and latest/current-stage digests,
binds the proof to the established view-forty-six broker and independently
recomputed send-latest anchors, and emits fresh view fifty-five under
`send_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-forty-seven output remains unchanged. Acknowledgement
now also requires sender's view-fifty-five
`send_current_latest_extended_complete_final_*` sibling from nested sender
config or flattened `dispatch_current_latest_extended_complete_final_*`
summary fields. It revalidates all inherited and latest/current-stage digests,
binds the proof to the established view-forty-seven broker and independently
recomputed acknowledgement anchors, and emits fresh view fifty-six under
`ack_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-forty-eight output remains unchanged. Roundtrip now also
requires acknowledgement's view-fifty-six
`ack_reconciled_current_latest_extended_complete_final_*` sibling from nested
acknowledgement config or flattened
`send_current_latest_extended_complete_final_*` summary fields. It revalidates
all inherited and latest/current-stage digests, binds the proof to the
established view-forty-eight broker and independently recomputed roundtrip
anchors, and emits fresh view fifty-seven under
`roundtrip_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-forty-nine output remains unchanged for broker readiness.
Broker readiness now consumes view fifty-seven from nested roundtrip config or
flattened `ack_reconciled_current_latest_extended_complete_final_*` summary
fields, revalidates all 37 inherited digests plus the latest/current and
reconciled stage fields, binds the proof to established view forty-nine, and
emits fresh view fifty-eight under
`broker_readiness_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-fifty output remains unchanged. Controlled scale-up now
consumes view fifty-eight from nested broker-readiness config or flattened
`roundtrip_reconciled_current_latest_extended_complete_final_*` summary fields,
revalidates all 37 inherited digest fields, nine latest/current stage fields,
seven current/reconciled transition fields, and fresh broker-readiness and
scale-up anchors, and emits fresh view fifty-nine under
`scaleup_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-fifty-one output remains unchanged. Cutover now consumes
view fifty-nine from nested scale-up config or flattened
`broker_readiness_reconciled_current_latest_extended_complete_final_*` summary
fields, revalidates all 37 inherited digest fields, nine latest/current stage
fields, seven current/reconciled transition fields, and fresh broker-
readiness, scale-up, and cutover anchors, and emits fresh view sixty under
`cutover_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-fifty-two output remains unchanged. Route-enable now
consumes view sixty from nested cutover config or flattened
`scaleup_reconciled_current_latest_extended_complete_final_*` summary fields,
revalidates all 37 inherited digest fields, nine latest/current stage fields,
seven current/reconciled transition fields, and fresh broker-readiness, scale-
up, cutover, and route anchors, and emits fresh view sixty-one under
`route_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-fifty-three output remains unchanged. Broker dispatch now
consumes view sixty-one from nested route config or flattened
`cutover_reconciled_current_latest_extended_complete_final_*` summary fields,
revalidates all 37 inherited digest fields, nine latest/current stage fields,
seven current/reconciled transition fields, and fresh broker-readiness, scale-
up, cutover, route, and dispatch anchors, and emits fresh view sixty-two under
`dispatch_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-fifty-four output remains unchanged for sender
preparation. Sender preparation now consumes view sixty-two from nested
dispatch config or flattened
`route_reconciled_current_latest_extended_complete_final_*` summary fields,
revalidates all 37 inherited digest fields, nine latest/current stage fields,
seven current/reconciled transition fields, and fresh broker-readiness, scale-
up, cutover, route, dispatch, and send anchors, and emits fresh view sixty-
three under
`send_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-fifty-five output remains unchanged for acknowledgement,
which now consumes view sixty-three from nested sender config, a separate
sender-config handoff, or flattened
`dispatch_reconciled_current_latest_extended_complete_final_*` summary fields.
It revalidates all 37 inherited digest fields, nine latest/current stage
fields, seven current/reconciled transition fields, and fresh broker-readiness,
scale-up, cutover, route, dispatch, send, and acknowledgement anchors, and
emits fresh view sixty-four under
`ack_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-fifty-six output remains unchanged for roundtrip, which
now consumes additive view sixty-four from nested acknowledgement config or
flattened `send_reconciled_current_latest_extended_complete_final_*` summary
fields. It revalidates all 37 inherited digest fields, nine latest/current
stage fields, seven current/reconciled transition fields, six reconciled stage
reviews, and acknowledgement's verified-reconciled review against the
established broker and a fresh canonical recomputation, and emits a 64-field
view sixty-five under
`roundtrip_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-fifty-seven output remains unchanged for broker
readiness, which now consumes additive view sixty-five from nested roundtrip
config or flattened
`ack_verified_reconciled_current_latest_extended_complete_final_*` summary
fields. It revalidates the exact 64-field verified-reconciled source against
the established broker and a fresh canonical broker-readiness recomputation,
and emits a 65-field view sixty-six under
`broker_readiness_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-fifty-eight output remains unchanged for controlled
scale-up, which now consumes additive view sixty-six from flattened broker-
readiness summary fields or the nested launch-pipeline sidecar. It revalidates
the exact 65-field verified-reconciled source against the established broker
and a fresh canonical scale-up recomputation, and emits a 66-field view sixty-
seven under
`scaleup_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-fifty-nine output remains unchanged for cutover, which
now consumes additive view sixty-seven from nested scale-up config or
flattened
`broker_readiness_verified_reconciled_current_latest_extended_complete_final_*`
summary fields. It revalidates the exact 66-field verified-reconciled source
against the established broker and a fresh canonical cutover recomputation,
and emits a 67-field view sixty-eight under
`cutover_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-sixty output remains unchanged for route-enable, which
now consumes additive view sixty-eight from nested cutover config or flattened
`scaleup_verified_reconciled_current_latest_extended_complete_final_*` summary
fields. It revalidates the exact 67-field verified-reconciled source against
the established broker and a fresh canonical route recomputation, and emits a
68-field view sixty-nine under
`route_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-sixty-one output remains unchanged for broker dispatch,
which now consumes additive view sixty-nine from nested route config or
flattened
`cutover_verified_reconciled_current_latest_extended_complete_final_*` summary
fields. It revalidates the exact 68-field verified-reconciled source against
the established broker and a fresh canonical dispatch recomputation, and emits
a 69-field view seventy under
`dispatch_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-sixty-two output remains unchanged for sender preparation,
which now consumes additive view seventy from nested dispatch config or
flattened
`route_verified_reconciled_current_latest_extended_complete_final_*` summary
fields. It revalidates the exact 69-field verified-reconciled source against
the established broker and a fresh canonical send recomputation, and emits a
70-field view seventy-one under
`send_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-sixty-three output remains unchanged for acknowledgement,
which now consumes additive view seventy-one from nested sender config or
flattened
`dispatch_verified_reconciled_current_latest_extended_complete_final_*`
summary fields. It revalidates the exact 70-field verified-reconciled source
against the established broker and a fresh canonical acknowledgement
recomputation, and emits a 71-field view seventy-two under
`ack_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-sixty-four output remains unchanged for roundtrip, which
now consumes additive view seventy-two from nested acknowledgement config or
flattened `send_verified_reconciled_current_latest_extended_complete_final_*`
summary fields. It revalidates the exact 71-field confirmed verified-reconciled
source against the established broker and a fresh canonical roundtrip
recomputation, and emits a 72-field view seventy-three under
`roundtrip_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-sixty-five output remains unchanged for broker readiness,
which now consumes additive view seventy-three from nested roundtrip config or
flattened
`ack_confirmed_verified_reconciled_current_latest_extended_complete_final_*`
summary fields. It revalidates the exact 72-field confirmed verified-
reconciled source against the established broker and a fresh canonical broker-
readiness recomputation, and emits a 73-field view seventy-four under
`broker_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-sixty-six output remains unchanged for controlled scale-
up, which now consumes additive view seventy-four from nested broker-readiness
config or flattened
`roundtrip_confirmed_verified_reconciled_current_latest_extended_complete_final_*`
summary fields. It revalidates the exact 73-field confirmed verified-reconciled
source against the established broker and a fresh canonical controlled-scale-
up recomputation, and emits a 74-field view seventy-five under
`scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-sixty-seven output remains unchanged for cutover, which
now consumes additive view seventy-five from nested controlled-scale-up config
or flattened
`broker_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_*`
summary fields. It revalidates the exact 74-field confirmed verified-reconciled
source against the established broker and a fresh canonical cutover
recomputation, and emits a 75-field view seventy-six under
`cutover_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-sixty-eight output remains unchanged for route
enablement, which continues to derive established view sixty-nine from view
sixty-eight. Route enablement now also consumes additive view seventy-six from
nested cutover config or flattened
`scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_*`
summary fields. It revalidates the exact 75-field confirmed verified-
reconciled source against the established broker and a fresh canonical route
recomputation, and emits a 76-field view seventy-seven under
`route_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Broker dispatch continues to derive established view seventy from view sixty-
nine. It now also consumes additive view seventy-seven from nested route config
or flattened
`cutover_confirmed_verified_reconciled_current_latest_extended_complete_final_*`
summary fields. It revalidates the exact 76-field confirmed verified-reconciled
source against the established broker and a fresh canonical dispatch
recomputation, and emits a 77-field view seventy-eight under
`dispatch_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Sender preparation continues to derive established view seventy-one from view
seventy and intentionally ignores additive view seventy-eight.
The established view-thirty-seven `route_extended_complete_final_*` output
remains unchanged as broker dispatch's compatibility anchor. Broker dispatch
additionally consumes view forty-five from nested route config or flattened
`cutover_latest_extended_complete_final_*` summary fields, revalidates the
complete chain through route-latest-extended-complete-final review, and emits
fresh view forty-six under
`dispatch_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-thirty-eight output remains unchanged for sender
compatibility. Sender preparation additionally consumes view forty-six from
nested dispatch config or flattened `route_latest_extended_complete_final_*`
summary fields, revalidates the complete chain, and emits fresh view forty-
seven under
`send_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-thirty-nine output remains unchanged for acknowledgement
compatibility. Acknowledgement additionally consumes view forty-seven from
nested send config or flattened `dispatch_latest_extended_complete_final_*`
summary fields, revalidates the complete chain, and emits fresh view forty-
eight under
`ack_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-forty output remains unchanged for roundtrip
compatibility. Roundtrip additionally consumes view forty-eight from nested
acknowledgement config or flattened `send_latest_extended_complete_final_*`
summary fields, revalidates the complete chain, and emits fresh view forty-nine
under
`roundtrip_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-forty-one output remains unchanged for broker-readiness
compatibility. Broker readiness additionally consumes view forty-nine from
nested roundtrip config or flattened
`ack_current_latest_extended_complete_final_*` summary fields, revalidates the
complete chain, and emits fresh view fifty under
`broker_readiness_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established view-forty-two output remains unchanged for controlled-scale-up
compatibility; scale-up ignores additive view fifty.
Generic targets that do not require final consistency and legacy draft-backed
proof keep the existing provenance checks.
When the scale-up config includes both
`broker_readiness.dispatch_roundtrip.broker_dispatch_roundtrip_vendor_market_data_batch`
and the older `broker_readiness.dispatch_roundtrip.vendor_market_data_batch`
block, cutover prefers the broker-specific block. For older or thin scale-up
configs, cutover also reads the resolved broker-readiness config sidecar and
hydrates missing broker vendor-data proof from
`dispatch_roundtrip.broker_dispatch_roundtrip_vendor_market_data_batch` plus
its sibling `vendor_market_data_batch_lineage_comparison` and, when present,
`broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison` before
revalidating and carrying it downstream. This hydration does not create the
nineteen-view `scaleup_final_*` proof. Cutover also carries
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
Cutover now also requires the resolved runtime-session bundle to have a complete,
current `runtime_session_monitor` manifest. It reconciles every carried scale-up,
portfolio, scorecard, runtime-telemetry, and prospective research-family field
across the session summary, config, and manifest; compares the carried scale-up
hashes with the current cutover scale-up manifest; and rejects authorizing
claims. The verified state is preserved as `runtime_lineage_*`,
`runtime_scaleup_*`, and `runtime_telemetry_*` fields plus the flat
`runtime_lineage` config block. The cutover manifest fingerprints the complete
runtime-session artifact set and recursively flattened upstream dependencies,
so later registration, study, scorecard, portfolio, scale-up, or session drift
invalidates the cutover packet. Cutover artifacts set
`authorizes_submission=false`; authorization here is operational evidence, not
permission to submit an order.
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
would allow it. Route-enable also revalidates cutover-retained route-readiness
ops broker controls before enabling the broker route: direct route-readiness
proof must retain launch-control evidence with zero blocked pairs and zero
broker round-trip allocation/concentration breach pairs, while broker-carried
route proof must retain clean launch-control, allocation-safe, and
concentration-OK run counts. These counters are preserved in
`route_enable_summary.csv` and `route_enable_config.json` as
`route_readiness_*` and `cutover_broker_route_readiness`. `--require-route-readiness`
is automatic for `--target-mode live_dryrun`; the explicit flag keeps
paper/shadow route reviews equally strict. When cutover carries scale-up
post-halt resume route proof, route-enable also revalidates both the primary
broker resume route branch and the closed-incident route branch, preserving
them as `cutover_broker_resume_broker_route_readiness_*`,
`cutover_broker_resume_incident_broker_route_readiness_*`, and nested
`cutover_broker_resume_gate` config blocks. Stale strategy/market identity,
route gaps, missing launch controls, allocation breaches, or concentration
breaches route back to `review-resume-gate` before broker dispatch planning can
inherit the route-enable packet. If `cutover_config.json` retained
Arrow.money/iRage vendor market-data
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
block. For application-backed proof, route-enable also retains mapping mode,
application count, uniqueness, coverage, and each dataset's application,
scope-review, target-intake, and applied-mapping lineage. Any target signal
requires `per_dataset_verified_target_application`, one distinct application
per dataset, 100% coverage, complete lineage, an affirmative cutover lineage
decision, and final dispatch/send/ack consistency when required. Route-enable
verifies the current and broker-final digests, the scale-up-carried and
cutover-carried digests, and a fresh canonical digest recomputed from its own
datasets. Route-enable continues to require cutover's twelve-view compatibility
comparison, revalidates it, and independently computes view thirteen. The
original five-view comparison and full thirteen-view compatibility handoff
remain in the flattened summary and the
`cutover_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`
config block, including `route_carried_application_lineage_sha256`; the full
thirteen-view handoff is emitted as
`route_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Reconciled targets additionally require cutover's twenty-view
`cutover_final_*` comparison. Route-enable revalidates its current,
broker-final, prior scale-up-, cutover-, route-, dispatch-, send-, ack-,
roundtrip-, readiness-, scale-up-review-, cutover-review-, route-enable-review-,
dispatch-plan-review-, send-packet-review-, acknowledgement-reconciliation-review-,
roundtrip-final-review-, broker-readiness-review-, scale-up-final-review-, and
cutover-final-review-carried digests, then independently computes view
twenty-one. Flattened `cutover_final_*` fields retain the complete input and
`route_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`
retains all twenty-one views. This applies to current cutover config and
flattened cutover summary recovery. Reconciled targets also require cutover's
twenty-eight-view `cutover_complete_final_*` sibling. Route enable accepts it
from nested cutover config or flattened `scaleup_complete_final_*` summary
fields, revalidates every historical stage and review digest through cutover-
complete-final review, binds it to the established twenty-view anchors, and
independently computes view twenty-nine. The additive result is emitted under
`route_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established twenty-one-view `route_final_*` handoff remains unchanged for
broker-dispatch compatibility. Broker dispatch now consumes the additive
twenty-nine-view sibling while retaining that established twenty-one-view
contract.
Route enable now also requires cutover's view-thirty-six
`cutover_extended_complete_final_*` sibling. It accepts the proof from nested
cutover config or flattened `scaleup_extended_complete_final_*` summary fields,
revalidates every inherited stage and review digest through roundtrip-extended-
complete-final, broker-readiness-extended-complete-final, scale-up-extended-
complete-final, and cutover-extended-complete-final review, and binds it to the
established view-twenty-eight broker and cutover-complete-final-review anchors.
Route enable's fresh canonical digest becomes view thirty-seven under
`route_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Missing or negative proof, any inherited digest drift, either compatibility-
anchor drift, or disagreement with route enable's recomputed datasets fails
closed. The established view-twenty-nine `route_complete_final_*` output
remains unchanged as broker dispatch's compatibility anchor and the source for
the established view-thirty output. Broker dispatch now additionally requires
the view-thirty-seven sibling from nested route config or flattened
`cutover_extended_complete_final_*` summary fields, revalidates every inherited
stage and review digest through roundtrip-extended-complete-final, broker-
readiness-extended-complete-final, scale-up-extended-complete-final, cutover-
extended-complete-final, and route-extended-complete-final review, and binds it
to the view-twenty-nine broker and route-complete-final-review anchors. Its
fresh canonical digest becomes additive view thirty-eight under
`dispatch_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Missing or negative proof, inherited digest drift, either compatibility-anchor
drift, or disagreement with dispatch's recomputed datasets fails closed. The
established view-thirty `dispatch_complete_final_*` output remains unchanged
as send preparation's compatibility anchor and the source for the established
view-thirty-one output. Send preparation now additionally requires the view-
thirty-eight sibling from nested dispatch config or flattened
`route_extended_complete_final_*` summary fields, revalidates every inherited
stage and review digest through roundtrip-extended-complete-final, broker-
readiness-extended-complete-final, scale-up-extended-complete-final, cutover-
extended-complete-final, route-extended-complete-final, and dispatch-extended-
complete-final review, and binds it to the view-thirty broker and dispatch-
complete-final-review anchors. Its fresh canonical digest becomes additive
view thirty-nine under
`send_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Missing or negative proof, inherited digest drift, either compatibility-anchor
drift, or disagreement with send's recomputed datasets fails closed. The
established view-thirty-one `send_complete_final_*` output remains unchanged
as acknowledgement's compatibility anchor and the source for the established
view-thirty-two output. Acknowledgement now additionally requires the view-
thirty-nine sibling from nested send config, the produced sender-config
handoff, or flattened `dispatch_extended_complete_final_*` summary fields. It
revalidates every inherited stage and review digest through roundtrip-extended-
complete-final, broker-readiness-extended-complete-final, scale-up-extended-
complete-final, cutover-extended-complete-final, route-extended-complete-final,
dispatch-extended-complete-final, and send-extended-complete-final review, then
binds the proof to the view-thirty-one broker and send-complete-final-review
anchors. Its fresh canonical digest becomes additive view forty under
`ack_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Missing or negative proof, inherited digest drift, either compatibility-anchor
drift, or disagreement with acknowledgement's recomputed datasets fails
closed. The established view-thirty-two `ack_extended_complete_final_*` output
remains unchanged as final roundtrip's compatibility anchor and the source for
the established view-thirty-three output. Final roundtrip now additionally
requires the view-forty sibling from nested acknowledgement config or flattened
`send_extended_complete_final_*` summary fields, revalidates every inherited
stage and review digest through roundtrip-extended-complete-final, broker-
readiness-extended-complete-final, scale-up-extended-complete-final, cutover-
extended-complete-final, route-extended-complete-final, dispatch-extended-
complete-final, send-extended-complete-final, and acknowledgement-latest-
extended-complete-final review, then binds the proof to the view-thirty-two
broker and acknowledgement-extended-complete-final-review anchors. Its fresh
canonical digest becomes additive view forty-one under
`roundtrip_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Missing or negative proof, inherited digest drift, either compatibility-anchor
drift, or disagreement with final roundtrip's recomputed datasets fails closed.
The established view-thirty-three `roundtrip_extended_complete_final_*` output
remains unchanged as broker readiness's compatibility anchor. Broker readiness
now additionally consumes additive view forty-one, revalidates the complete
lineage chain, and emits fresh view forty-two under
`broker_readiness_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Its established view-thirty-four output remains unchanged. Controlled scale-up
now consumes view forty-two, revalidates the complete lineage chain, and emits
fresh view forty-three under
`scaleup_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Its established view-thirty-five output remains unchanged. Cutover now consumes
view forty-three, revalidates the complete lineage chain, and emits fresh view
forty-four under
`cutover_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Its established view-thirty-six output remains unchanged. Route-enable now
consumes view forty-four, revalidates the complete lineage chain, and emits
fresh view forty-five under
`route_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Its established view-thirty-seven output remains unchanged. Broker dispatch
consumes view forty-five, revalidates the complete lineage chain, and emits
fresh view forty-six under
`dispatch_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
It still derives established view thirty-eight from view thirty-seven. Sender
preparation now consumes view forty-six and emits additive view forty-seven
under
`send_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`,
while preserving established view thirty-nine from view thirty-eight.
Acknowledgement now consumes view forty-seven and emits additive view forty-
eight under
`ack_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`,
while preserving established view forty from view thirty-nine. Roundtrip
uses view forty as its compatibility anchor, consumes additive view forty-eight,
and emits fresh view forty-nine under
`roundtrip_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`
while preserving established view forty-one. Broker readiness continues to
derive view forty-two from view forty-one as its compatibility path, consumes
additive view forty-nine, and emits fresh view fifty under
`broker_readiness_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`
while preserving established view forty-two. Controlled scale-up continues to
derive established view forty-three from view forty-two, now consumes additive
view fifty, and emits fresh view fifty-one under
`scaleup_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Cutover continues to derive established view forty-four from view forty-three,
now consumes additive view fifty-one, and emits fresh view fifty-two under
`cutover_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Route-enable continues to derive view forty-five from view forty-four and
now consumes additive view fifty-two to emit fresh view fifty-three under
`route_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Broker dispatch continues to derive view forty-six from view forty-five and
now consumes additive view fifty-three to emit fresh view fifty-four under
`dispatch_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Sender preparation continues to derive view forty-seven from view forty-six
and now consumes additive view fifty-four to emit fresh view fifty-five under
`send_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Acknowledgement continues to derive established view forty-eight from view
forty-seven, now consumes additive view fifty-five, and emits fresh view
fifty-six under
`ack_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Roundtrip continues to derive established view forty-nine from view forty-
eight, now consumes additive view fifty-six, and emits fresh view fifty-seven
under
`roundtrip_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Broker readiness continues to derive established view fifty from view forty-
nine, now consumes additive view fifty-seven, and emits fresh view fifty-eight
under
`broker_readiness_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Controlled scale-up continues to derive established view fifty-one from view
fifty, now consumes additive view fifty-eight, and emits fresh view fifty-nine
under
`scaleup_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Cutover continues to derive established view fifty-two from view fifty-one,
now consumes additive view fifty-nine, and emits fresh view sixty under
`cutover_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Route-enable continues to derive established view fifty-three from view fifty-
two, now consumes additive view sixty, and emits fresh view sixty-one under
`route_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Broker dispatch continues to derive established view fifty-four from view
fifty-three, now consumes additive view sixty-one, and emits fresh view sixty-
two under
`dispatch_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Sender preparation continues to derive established view fifty-five from view
fifty-four, now consumes additive view sixty-two, and emits fresh view sixty-
three under
`send_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Acknowledgement continues to derive established view fifty-six from view
fifty-five, now consumes additive view sixty-three, and starts the verified-
reconciled epoch with fresh view sixty-four under
`ack_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Roundtrip continues to derive established view fifty-seven from view fifty-
six, now consumes additive view sixty-four, and extends the verified-
reconciled epoch with fresh view sixty-five under
`roundtrip_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Broker readiness continues to derive established view fifty-eight from view
fifty-seven, now consumes additive view sixty-five, and emits fresh view sixty-
six under
`broker_readiness_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Controlled scale-up continues to derive established view fifty-nine from view
fifty-eight, now consumes additive view sixty-six, and emits fresh view sixty-
seven under
`scaleup_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Cutover continues to derive established view sixty from view fifty-nine, now
consumes additive view sixty-seven, and emits fresh view sixty-eight under
`cutover_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Route-enable continues to derive established view sixty-one from view sixty,
now consumes additive view sixty-eight, and emits fresh view sixty-nine under
`route_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Broker dispatch continues to derive established view sixty-two from view
sixty-one, now consumes additive view sixty-nine, and emits fresh view seventy
under
`dispatch_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Sender preparation continues to derive established view sixty-three from view
sixty-two, now consumes additive view seventy, and emits fresh view seventy-one
under
`send_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Acknowledgement continues to derive established view sixty-four from view
sixty-three, now consumes additive view seventy-one, and starts the confirmed
verified-reconciled epoch with fresh view seventy-two under
`ack_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Roundtrip continues to derive established view sixty-five from view sixty-four,
now consumes additive view seventy-two, and extends the confirmed verified-
reconciled epoch with fresh view seventy-three under
`roundtrip_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Broker readiness continues to derive established view sixty-six from view
sixty-five, now consumes additive view seventy-three, and extends the confirmed
verified-reconciled epoch with fresh view seventy-four under
`broker_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Controlled scale-up continues to derive established view sixty-seven from view
sixty-six, now consumes additive view seventy-four, and extends the confirmed
verified-reconciled epoch with fresh view seventy-five under
`scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Cutover continues to derive established view sixty-eight from view sixty-seven
and now consumes additive view seventy-five, extending the confirmed verified-
reconciled epoch with fresh view seventy-six under
`cutover_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Route enablement continues to derive established view sixty-nine from view
sixty-eight, now consumes additive view seventy-six, and extends the confirmed
verified-reconciled epoch with fresh view seventy-seven under
`route_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Broker dispatch continues to derive established view seventy from view sixty-
nine, now consumes additive view seventy-seven, and extends the confirmed
verified-reconciled epoch with fresh view seventy-eight under
`dispatch_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Sender preparation continues to derive established view seventy-one from view
seventy and intentionally ignores additive view seventy-eight; distinct-digest
regressions cover all thirty compatibility boundaries.
Summary-only recovery prefers the current `cutover_*` vendor columns and the
cutover-produced `scaleup_*` final-lineage columns before older compatibility
fields. If cutover retained the
broker-vendor wrapper readiness state,
route-enable carries it as `cutover_broker_vendor_data_readiness_*` audit
fields plus `cutover_broker_vendor_data_readiness` config, and fails closed
when the wrapper is not ready or has failed checks even if the nested vendor
batch itself is valid. When both `cutover_broker_dispatch_roundtrip_vendor_market_data_batch`
and the scale-up-retained
`scaleup_broker_dispatch_roundtrip_vendor_market_data_batch` blocks are present,
route-enable prefers the cutover-specific block. For older or thin cutover
configs, route-enable can also read the cutover manifest's
`broker_readiness_config` input and hydrate missing broker vendor-data proof
and wrapper readiness before revalidating them. Legacy draft-backed sidecars
remain compatible. A reconciled target-application sidecar without cutover's
complete twenty-view comparison fails closed; rerun controlled scale-up and
cutover so route-enable receives the complete handoff rather than fabricating
those decisions.
`--upload-pack` and
`--order-export` may point at a launch-pipeline root; route-enable resolves nested `05_upload_pack`/`04_export` or surface-MM
`04_upload_pack`/`03_export` summaries and fingerprints the resolved cutover
summary, cutover config, cutover manifest when present, upload summary, and
optional order export summary in the manifest.
Route-enable additionally requires a complete, current `cutover_gate` manifest,
reconciles the cutover-carried runtime lineage across cutover summary, config,
and manifest, and requires both the runtime-lineage and cutover-lineage gates to
remain true. The packet, summary, manifest, and flat `cutover_lineage` config
block preserve the exact cutover, runtime-session, scale-up, portfolio,
scorecard, and prospective-family hashes and identities. Its manifest
fingerprints all cutover artifacts and recursively flattened cutover
dependencies, so upstream research or operational drift invalidates an emitted
route packet. `route_enabled=true` still does not authorize broker submission:
all route-enable artifacts explicitly set `authorizes_submission=false`.

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

When the provider route-enable wrapper retained validated dispatch round-trip
capture provenance, broker-dispatch carries the same
`dispatch_roundtrip_capture_bundle_*`,
`dispatch_roundtrip_capture_env_template_*`,
`dispatch_roundtrip_adapter_handoff_*`, and
`dispatch_roundtrip_capture_provenance_consistent` fields into its
summary/config/runbook and manifest inputs/extra metadata. That keeps the
capture bundle, blank credential env-template, and adapter handoff traceable
before broker send packets and acknowledgement checks inherit the dispatch
plan.

This command still does not submit orders. It hashes the route-enable
authorization and upload file, creates one dry-run dispatch row per upload
order, and requires unique source order IDs, unique dispatch IDs, route-enabled
state, matching target mode, clean route-readiness proof from route-enable,
clean nested route proof from route-enable for live dry-run routing, zero
nested route-enable dispatch round-trip failed checks, any route-carried shadow
broker-readiness aggregate and broker-readiness-carried shadow broker proof to
remain clean and identity-consistent, and order counts within the approved route
limits. Dispatch planning now also requires a complete, current
`route_enable_packet` manifest and reconciles every
cutover/runtime/scale-up/portfolio/scorecard/research-family
field across the route packet, summary, config, and manifest. Explicit
`authorizes_submission=false` claims are required in all four route artifacts.
The carried cutover fields are also compared with the independently reopened
current cutover bundle, so a consistently re-manifested route-family relabel
cannot detach dispatch from its source proof.
The verified state is carried as `route_enable_lineage_*` and
`route_enable_cutover_*` fields in the dispatch summary, config, manifest, and
every dry-run dispatch-order row, including the exact prospective-family and
registration identity. The dispatch manifest fingerprints the full route-enable
artifact set and recursively flattened route dependencies, so later research or
operational drift invalidates the plan. Dispatch output may not overlap its
route-enable or upload source directory.

When route-enable retained strategy portfolio allocation, dispatch
planning carries the `strategy_portfolio_*` fields into summary/config,
including concentration counts, top concentration names, and maximum allocation
weights. It computes `source_order_notional` for each upload row, records
upload `total_notional`, and fails closed if the resolved upload-order file
exceeds the selected paper/shadow allocation. Dispatch planning also revalidates
the route-enable-retained route-readiness ops broker controls: direct route
proof must retain launch controls and zero allocation/concentration breach
pairs, while the broker-carried route proof must retain clean launch-control,
allocation-safe, and concentration-OK run counts. These counters are carried in
`broker_dispatch_summary.csv` and `broker_dispatch_config.json` as
`route_readiness_*` plus `route_broker_route_readiness`. `--require-route-readiness`
is automatic for `--target-mode live_dryrun`; the explicit flag keeps
paper/shadow dispatch plans equally strict. When route-enable carried
post-halt resume route proof from cutover, dispatch planning revalidates both
the broker resume route branch and the closed-incident branch, preserving them
as `route_broker_resume_broker_route_readiness_*`,
`route_broker_resume_incident_broker_route_readiness_*`, and nested
`route_broker_resume_gate` config blocks. Strategy/market drift, route gaps,
missing launch controls, allocation breaches, or concentration breaches route
back to `review-resume-gate` before dry-run send packets can inherit the
dispatch plan. The resulting
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
`route_broker_dispatch_roundtrip_vendor_market_data_batch` config block. For
application-backed proof, the planner also retains mapping mode, application
count, uniqueness, coverage, and each dataset's application, scope-review,
target-intake, and applied-mapping lineage. Any target signal requires
`per_dataset_verified_target_application`, one distinct application per
dataset, 100% coverage, complete lineage, an affirmative route-retained lineage
decision, and final dispatch/send/ack consistency when required. Dispatch
planning verifies the current and broker-final digests, the scale-up-, cutover-,
and route-carried digests, and a fresh canonical digest recomputed from its own
datasets. Reconciled targets continue to require route enable's complete
thirteen-view compatibility comparison and now additionally require its
complete twenty-one-view final comparison. Dispatch planning revalidates the
historical scale-up-, cutover-, route-, dispatch-, send-, acknowledgement-,
roundtrip-, readiness-, scale-up-review-, cutover-review-, route-enable-review-,
dispatch-plan-review-, send-packet-review-,
acknowledgement-reconciliation-review-, roundtrip-final-review-,
broker-readiness-review-, scale-up-final-review-, cutover-final-review-, and
route-final-review-carried digests against the final broker proof, then
independently computes view twenty-two. The existing six-view comparison and
full fourteen-view compatibility handoff remain in flattened summary fields
and the
`dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`
config block. The complete input is retained in flattened `route_final_*`
fields and the twenty-two-view handoff is emitted as
`dispatch_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The same contract applies to nested route config and flattened route summary
recovery. Reconciled targets also require route enable's twenty-nine-view
`route_complete_final_*` sibling. Broker dispatch accepts it from nested route
config or flattened `cutover_complete_final_*` summary fields, revalidates
every historical stage and review digest through route-complete-final review,
binds it to the established twenty-one-view anchors, and independently
computes view thirty. The additive result is emitted under
`dispatch_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established twenty-two-view `dispatch_final_*` handoff remains unchanged
for send-preparation compatibility. Send preparation now consumes the additive
thirty-view sibling while retaining that established input contract. If
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
`broker_readiness_config` sidecar before revalidating them. Legacy draft-backed
sidecars and generic non-reconciled targets remain compatible. A reconciled
target-application sidecar without route enable's complete thirteen-view final
comparison fails closed; rerun the intervening gates so dispatch planning
receives the complete route handoff rather than fabricating those decisions.
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

When the provider broker-dispatch wrapper retained validated dispatch
round-trip capture provenance, the send packet carries the same
`dispatch_roundtrip_capture_bundle_*`,
`dispatch_roundtrip_capture_env_template_*`,
`dispatch_roundtrip_adapter_handoff_*`, and
`dispatch_roundtrip_capture_provenance_consistent` fields into its
summary/config/runbook and manifest inputs/extra metadata. That keeps the
live-capture bundle, blank credential env-template, and adapter handoff lineage
visible before acknowledgement reconciliation consumes the send packet.

This packet still does not submit orders. It creates adapter-scoped endpoint
names, dry-run request envelopes, payload hashes, unique idempotency keys, and
an acknowledgement-log template while forcing `submission_enabled=false`. It
also requires a complete, current `broker_dispatch_plan` manifest and verifies
all dispatch artifacts before preparing requests. The sender reconciles the
route-enable lineage across every dispatch order, summary, config, and manifest,
requires explicit non-authorizing claims, and independently reopens the current
route-enable source. This blocks stale dispatch files, freshly re-manifested
cross-artifact disagreement, and a consistently relabeled dispatch bundle that
no longer matches its route source. Verified fields are carried as
`broker_dispatch_*` columns in every request row and hashed request envelope,
plus a flat `broker_dispatch_lineage` config block and send summary/manifest
metadata. The send manifest fingerprints the complete dispatch artifact set and
recursively flattened dependencies; later research or operational drift
invalidates it. Send output may not overlap the dispatch source, and both
`submission_enabled=false` and `authorizes_submission=false` are enforced. It
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
`route_broker_shadow_broker_readiness` into the sender summary/config. It
revalidates the route-readiness ops broker controls before the sender packet is
trusted: the direct route proof must retain launch controls and zero allocation
or concentration breach pairs, and any broker-carried route proof must retain
clean launch-control, allocation-safe, and concentration-OK dry-run counts. The
sender artifacts preserve these controls as `route_readiness_*` and
`route_broker_route_readiness` fields in `broker_dispatch_send_summary.csv` and
`broker_dispatch_send_config.json`. If dispatch planning retained post-halt
resume route proof, the sender packet revalidates both the broker resume route
branch and the closed-incident branch before dry-run request envelopes are
trusted. It preserves the branches as
`route_broker_resume_broker_route_readiness_*`,
`route_broker_resume_incident_broker_route_readiness_*`, and nested
`route_broker_resume_gate` config blocks, and routes stale identity, route
gaps, missing launch controls, allocation breaches, or concentration breaches
back to `review-resume-gate`. If the dispatch config retained the
shadow-broker broker-vendor wrapper aggregate, the
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
`dispatch_broker_dispatch_roundtrip_vendor_market_data_batch` config block. For
application-backed proof, send preparation also carries mapping mode,
application count, uniqueness, coverage, and each dataset's application,
scope-review, target-intake, and applied-mapping lineage. Any target signal
requires `per_dataset_verified_target_application`, one distinct application
per dataset, 100% coverage, complete lineage, an affirmative dispatch-retained
current/final match decision, and final dispatch/send/ack consistency when that
decision is marked required. Send preparation verifies the current and
broker-final digests, the scale-up-, cutover-, route-, and dispatch-carried
digests, then independently recomputes a seventh canonical digest from the
datasets entering the request packet. Reconciled targets continue to require
broker dispatch's complete fourteen-view compatibility comparison and now
additionally require its complete twenty-two-view final comparison. Send
preparation revalidates the historical scale-up-, cutover-, route-, dispatch-,
send-, acknowledgement-, roundtrip-, readiness-, scale-up-review-,
cutover-review-, route-enable-review-, dispatch-plan-review-,
send-packet-review-, acknowledgement-reconciliation-review-,
roundtrip-final-review-, broker-readiness-review-, scale-up-final-review-,
cutover-final-review-, route-final-review-, and dispatch-final-review-carried
digests against the final broker proof, then independently computes view
twenty-three. The existing seven-view comparison and full fifteen-view
compatibility handoff remain in the flattened send summary and the
`dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`
config block; the complete input is retained in flattened `dispatch_final_*`
fields and the twenty-three-view handoff is emitted as
`send_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Send preparation now additionally requires broker dispatch's thirty-view
`dispatch_complete_final_*` sibling. It accepts the proof from nested dispatch
config or flattened `route_complete_final_*` dispatch-summary fields,
revalidates every historical stage and review digest through
acknowledgement-complete-final, roundtrip-complete-final, and
dispatch-complete-final review, binds it to the established twenty-two-view
anchors, and independently computes view thirty-one. The additive result is
emitted as
`send_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
The established twenty-three-view `send_final_*` handoff remains unchanged for
acknowledgement compatibility.
The established fifteen-view handoff is still emitted as
`send_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Acknowledgement reconciliation consumes the established fifteen-view and
twenty-three-view comparisons plus the additive thirty-one-view
`send_complete_final_*` sibling for reconciled targets while retaining the
seven-view compatibility artifact for its historical eight-view output. It
preserves the established fifteen-to-sixteen-view contract, independently
extends the final proof from view twenty-three to view twenty-four, and validates
the additive sender proof before independently emitting view thirty-two under
`ack_extended_complete_final_*`. The established twenty-three-view proof remains
an independent compatibility anchor. Round-trip review consumes additive view
thirty-two and independently emits view thirty-three while preserving view
twenty-four as its compatibility anchor. Distinct-digest regressions lock all
three boundaries. This
applies to nested dispatch config and flattened dispatch summary recovery.
Legacy draft-backed broker-readiness
sidecars and generic non-reconciled targets remain compatible; a reconciled
target-application sidecar without broker dispatch's complete fourteen- and
twenty-two-view comparisons plus its additive thirty-view proof fails closed
and must be regenerated through
scale-up, cutover, route-enable, and dispatch planning. If
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
  --send runs\dispatch_send\leadlag_shadow_live_dryrun `
  --acks logs\broker_dispatch_acks.csv `
  --out runs\dispatch_acks\leadlag_shadow_live_dryrun `
  --require-route-readiness `
  --require-dispatch-roundtrip `
  --require-send-packet `
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

`--send` activates complete send-packet lineage verification, and
`--require-send-packet` makes the proof mandatory. A supplied packet must have a
current `broker_dispatch_send_packet` manifest with every required artifact and
fingerprinted input. Reconciliation compares the retained dispatch lineage
across request rows, hashed request envelopes, the expected-ack template,
summary, config, and manifest, requires explicit non-authorizing and
submission-disabled claims, independently reopens the current dispatch source,
and confirms that source is the same `--dispatch` bundle being reconciled.
Missing or stale packets, cross-artifact disagreement, consistently relabeled
but source-detached dispatch hashes, and authorizing claims route back to
`prepare-broker-dispatch-send`. Verified fields are carried as
`broker_dispatch_send_*` columns on every acknowledgement row, in the flat
`broker_dispatch_send_lineage` config block, and in ack summary/manifest
metadata. The ack manifest fingerprints all send artifacts and recursively
flattened dependencies, so later research or operational drift invalidates the
ack evidence. Dispatch/send source overlap is rejected and acknowledgement
outputs remain explicitly non-authorizing.

When the provider broker-dispatch-send wrapper retained validated dispatch
round-trip capture provenance, acknowledgement reconciliation carries the same
`dispatch_roundtrip_capture_bundle_*`,
`dispatch_roundtrip_capture_env_template_*`,
`dispatch_roundtrip_adapter_handoff_*`, and
`dispatch_roundtrip_capture_provenance_consistent` fields into its
summary/config/runbook and manifest inputs/extra metadata. That keeps the
live-capture bundle, blank credential env-template, and adapter handoff lineage
visible before the final provider round-trip wrapper consumes ack evidence.

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
`route_broker_shadow_broker_readiness` into the ack summary/config. The ack
gate revalidates the dispatch-retained route-readiness ops broker controls
before accepted acknowledgement evidence can advance: direct route proof must
retain launch controls and zero allocation or concentration breach pairs, and
broker-carried route proof must retain clean launch-control, allocation-safe,
and concentration-OK dry-run counts. The ack artifacts preserve these controls
as `route_readiness_*` and `route_broker_route_readiness` fields in
`broker_dispatch_ack_summary.csv` and `broker_dispatch_ack_config.json`. If
dispatch planning retained post-halt resume route proof, the ack gate
revalidates the broker resume route branch and the closed-incident branch
before accepted acknowledgement evidence can advance. It preserves the branches
as `route_broker_resume_broker_route_readiness_*`,
`route_broker_resume_incident_broker_route_readiness_*`, and nested
`route_broker_resume_gate` config blocks, and routes stale identity, route
gaps, missing launch controls, allocation breaches, or concentration breaches
back to `review-resume-gate`. If the
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
`ack_broker_dispatch_roundtrip_vendor_market_data_batch` config block. For
application-backed proof, acknowledgement reconciliation also carries mapping
mode, application count, uniqueness, coverage, and each dataset's application,
scope-review, target-intake, and applied-mapping lineage. Any target signal
requires `per_dataset_verified_target_application`, one distinct application
per dataset, 100% coverage, complete lineage, the affirmative sender-retained
lineage decision, and final dispatch/send/ack consistency before accepted
evidence can advance. With `--send`, reconciliation consumes the sender's
lineage-comparison config, verifies the current and broker-final digests plus
the scale-up-, cutover-, route-, dispatch-, and send-carried digests, and then
independently recomputes an eighth canonical digest from the datasets entering
the acknowledgement record. Reconciled targets additionally require the
sender's complete fifteen-view compatibility comparison and complete
twenty-three-view final comparison. Reconciliation verifies its current,
broker-final, scale-up-, cutover-, route-, dispatch-, send-, acknowledgement-,
final-review-, readiness-, scale-up-review-, cutover-review-, route-enable-review-,
dispatch-plan-review-, and send-packet-review-carried digests, then independently
recomputes view sixteen from the acknowledgement-carried datasets. The existing
eight-view compatibility proof is retained unchanged in the flattened ack
summary and
`ack_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`,
including `ack_carried_application_lineage_sha256`; broker-dispatch round-trip
continues to consume this stable contract. The complete sixteen-view proof is
emitted in flattened summary fields and
`ack_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`,
where `send_packet_review_carried_application_lineage_sha256` retains sender
view fifteen and `carried_application_lineage_sha256` is the fresh
acknowledgement-review digest. Reconciliation also consumes the nested
`send_final_*` config or flattened `dispatch_final_*` sender-summary fields,
retains them as flattened `send_final_*` acknowledgement fields, verifies every
historical digest through
`dispatch_final_review_carried_application_lineage_sha256`, retains send view
twenty-three as `send_final_review_carried_application_lineage_sha256`, and
recomputes acknowledgement view twenty-four. The result is emitted as
`ack_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Reconciliation now also consumes nested `send_complete_final_*` config or
flattened `dispatch_complete_final_*` sender-summary fields. It verifies every
inherited stage and review digest through dispatch-complete-final and
send-complete-final review, requires agreement with the established
view-twenty-three broker and send-final-review anchors, and independently
recomputes acknowledgement view thirty-two. The additive result is emitted as
`ack_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`,
where `send_complete_final_review_carried_application_lineage_sha256` retains
sender view thirty-one and `carried_application_lineage_sha256` is the fresh
acknowledgement digest. The established view-twenty-four `ack_complete_final_*`
handoff remains unchanged as an independent compatibility anchor. Round-trip
review additionally consumes the view-thirty-two sibling before emitting its
additive view-thirty-three proof.
This applies to nested send/dispatch config,
flattened dispatch summary recovery, and broker-readiness sidecar hydration.
Legacy draft-backed and generic non-reconciled sidecars remain compatible; a
reconciled target-application sidecar without the established sender
comparisons and additive view-thirty-one proof fails closed and must be
regenerated through the sender handoff. When
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
  --require-ack-lineage `
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

`--require-ack-lineage` makes the final proof independently verify the complete
current acknowledgement bundle. It requires a current
`broker_dispatch_ack_reconciliation` manifest with all required artifacts and
fingerprinted inputs, reconciles every retained send-lineage field across ack
rows, summary, config, and manifest, and recomputes acknowledgement plus failed
check counts from the source rows. The verifier then reopens the ack-linked send
packet, validates its dispatch source, and confirms it is the same `--send` and
`--dispatch` pair supplied to final review. Stale artifacts, missing contract
fields, freshly re-manifested row disagreement, consistently relabeled but
source-detached hashes, wrong send sources, and authorizing claims route back to
`reconcile-broker-dispatch`. Verified lineage is carried as
`broker_dispatch_ack_*` columns on every final order, in the nested
`broker_dispatch_ack_lineage` config block, and in summary/manifest metadata.
The final manifest fingerprints all acknowledgement artifacts and recursively
flattened dependencies, source/output overlap is rejected, and final artifacts
remain explicitly non-authorizing.

When the provider broker-dispatch-ack wrapper retained validated dispatch
round-trip capture provenance, the final provider round-trip wrapper carries
the same `dispatch_roundtrip_capture_bundle_*`,
`dispatch_roundtrip_capture_env_template_*`,
`dispatch_roundtrip_adapter_handoff_*`, and
`dispatch_roundtrip_capture_provenance_consistent` fields into its
summary/config/runbook and manifest inputs/extra metadata. That keeps the
live-capture bundle, blank credential env-template, and adapter handoff lineage
attached to the final dry-run broker proof.

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
The final proof revalidates route-readiness ops broker controls across
dispatch, send, and ack artifacts: direct route proof must retain launch
controls with zero blocked, allocation-breach, or concentration-breach pairs,
and broker-carried route proof must remain present, ready, identity-consistent,
allocation-safe, and concentration-OK in every component. The round-trip
artifacts preserve these controls as `route_readiness_*` and
`route_broker_route_readiness` fields in
`broker_dispatch_roundtrip_summary.csv` and
`broker_dispatch_roundtrip_config.json`. If component configs retained
post-halt resume route proof, the final round-trip review revalidates the
broker resume route branch and the closed-incident branch across dispatch,
send, and ack artifacts. It preserves the reconciled branches as
`route_broker_resume_broker_route_readiness_*`,
`route_broker_resume_incident_broker_route_readiness_*`, and nested
`route_broker_resume_gate` config blocks, and routes stale identity, route
gaps, missing launch controls, allocation breaches, or concentration breaches
back to `review-resume-gate`.
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
chain. For application-backed proof, final review reconciles mapping mode,
application count, uniqueness, coverage, and every dataset's application,
scope-review, target-intake, and applied-mapping lineage across dispatch, send,
and acknowledgement components. Any target signal requires every component to
retain `per_dataset_verified_target_application`, one distinct application per
dataset, 100% coverage, complete lineage, and the same canonical lineage graph.
It must also retain the acknowledgement's affirmative lineage decision and
final-consistency result. Final review checks the current, broker-final,
scale-up-, cutover-, route-, dispatch-, send-, and acknowledgement-carried
SHA-256 views, then independently recomputes a ninth digest from the carried
dataset identities. The flattened summary and
`roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`
config retain all nine views, including
`roundtrip_carried_application_lineage_sha256`. Reconciled targets additionally
require acknowledgement reconciliation's complete sixteen-view compatibility
comparison and complete twenty-four-view final comparison. Final review verifies
its current, broker-final, scale-up-, cutover-, route-,
dispatch-, send-, acknowledgement-, prior-roundtrip-, readiness-,
scale-up-review-, cutover-review-, route-enable-review-, dispatch-plan-review-,
send-packet-review-, and acknowledgement-reconciliation-review-carried digests,
then independently recomputes view seventeen from the final-review datasets.
The existing nine-view compatibility proof remains unchanged for broker
readiness. The complete seventeen-view proof is emitted in flattened summary
fields and
`roundtrip_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`,
where `ack_reconciliation_review_carried_application_lineage_sha256` retains
acknowledgement view sixteen and `carried_application_lineage_sha256` is the
fresh roundtrip-review digest. Final review also consumes the nested
`ack_complete_final_*` config or flattened `send_final_*` acknowledgement
summary, retains it as flattened `ack_complete_final_*` fields, verifies every
historical digest through
`send_final_review_carried_application_lineage_sha256`, retains acknowledgement
view twenty-four as
`ack_complete_final_review_carried_application_lineage_sha256`, and recomputes
round-trip view twenty-five. The result is emitted as
`roundtrip_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`.
Round-trip review now also consumes the nested view-thirty-two
`ack_extended_complete_final_*` config or flattened `send_complete_final_*`
acknowledgement-summary fields. It verifies every inherited stage and review
digest through acknowledgement-extended-complete-final review, requires
agreement with the established view-twenty-four broker and acknowledgement-
complete-final anchors, and independently recomputes view thirty-three. The
additive result is emitted as
`roundtrip_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison`,
where `ack_extended_complete_final_review_carried_application_lineage_sha256`
retains acknowledgement view thirty-two and
`carried_application_lineage_sha256` is the fresh round-trip digest. The
established view-twenty-five `roundtrip_complete_final_*` handoff remains
unchanged as an independent compatibility anchor. Broker readiness consumes
view thirty-three and emits additive view thirty-four while preserving view
twenty-five; a distinct-digest regression locks that boundary.
This applies equally to nested component configs and flattened component-summary
recovery. Legacy draft and generic non-reconciled sidecars remain compatible;
reconciled target sidecars hydrated only from broker readiness fail closed until
both complete acknowledgement comparisons are supplied.
If a component
config carries `roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch`,
the round-trip
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

## Market Data Source Planning

Before wiring Arrow.money/iRage live feeds or replaying a vendor file, create a
credential-safe source plan:

```powershell
python -m hft_cli plan-market-data-source `
  --out runs\market_data_sources\arrow_ws_nse `
  --provider arrow_money `
  --kind ticks `
  --transport websocket `
  --source-uri wss://feed.arrow.money/market-data/nse `
  --auth-env ARROW_MONEY_API_KEY `
  --auth-env ARROW_MONEY_API_SECRET `
  --market india_nse_index_derivatives `
  --exchange NFO `
  --session-timezone Asia/Kolkata `
  --session-open 09:15:00 `
  --session-close 15:30:00 `
  --fail-on-blocked-actions `
  --fail-on-breach
```

For historical replay or vendor onboarding from a file, use `--transport file`
and point `--source-uri` at the raw CSV. The generated
`market_data_source_config.json` stores provider, adapter, kind, transport,
market, exchange/segment, session timezone/window, sanitized source URI,
credential environment variable names, and the next gate. It also writes a
blank `market_data_source_env_template.env` sidecar
and records a `live_fetch_contract` command template for REST/websocket sources.
The source plan also includes a hashable `provider_profile` contract with the
built-in provider adapter, supported transports, capabilities, default
credential env-var names, auth requirement, and `values_stored=false`, so
Arrow.money/iRage credentials can be staged by environment variable name before
any provider API call is attempted. It never stores credential values and fails
closed if secrets appear in query parameters or `--auth-env` values. File
sources emit a ready action for `pipeline-vendor-market-data`; REST/websocket
sources emit a ready action for the provider fetcher implementation that will
consume the same config.

Turn a ready source plan into a credential-safe fetch contract before writing
any provider-specific Arrow.money/iRage client code:

```powershell
python -m hft_cli plan-market-data-fetch `
  --source-plan runs\market_data_sources\arrow_ws_nse\market_data_source_config.json `
  --out runs\market_data_fetch\arrow_ws_nse `
  --symbol NIFTY-I `
  --symbol BANKNIFTY-I `
  --max-latency-ms 150 `
  --expected-market india_nse_index_derivatives `
  --fail-on-blocked-actions `
  --fail-on-breach
```

For REST backfills, include `--window-start` and `--window-end`. The command
does not call external APIs; it validates the source plan, market identity,
credential env-var references, the source-plan env-template sidecar, symbols,
timing budget, output file contract, and next gate. The fetch manifest
fingerprints `market_data_source_env_template.env` for live REST/websocket
plans, and `market_data_fetch_config.json` carries the provider profile hash,
the credential template hash, and the upstream `live_fetch_contract`. File sources route to the existing
`pipeline-vendor-market-data` command, while REST/websocket sources route to
the provider fetcher with `market_data_fetch_config.json`.

Prepare the provider fetcher handoff from a ready REST/websocket fetch plan:

```powershell
python -m hft_cli plan-provider-market-data-fetcher `
  --fetch-plan runs\market_data_fetch\arrow_ws_nse\market_data_fetch_config.json `
  --out runs\provider_market_data_fetchers\arrow_ws_nse `
  --connect-timeout-ms 5000 `
  --read-timeout-ms 1000 `
  --heartbeat-timeout-ms 30000 `
  --max-reconnects 3 `
  --batch-size 5000 `
  --fail-on-blocked-actions `
  --fail-on-breach
```

This writes `provider_market_data_request_template.json` plus checks,
summary, action queue, runbook, config, and manifest artifacts. It does not
call the provider; it validates the ready fetch plan, live transport,
credential env-var names, the carried source-plan env-template proof, the
upstream `live_fetch_contract`, optional runtime env-var presence, symbol
coverage, and runtime budgets. The request template carries only the blank
env-template path/hash and env-var names, never credential values. It also
writes an `adapter_execution_contract` with provider/adapter/transport/mode,
endpoint, output filename, dry-run status, env-var names, and API-contract
approval requirements for the future Arrow.money/iRage backend adapter. The
request template and adapter contract both retain the provider-profile SHA so
real adapter code can prove it is satisfying the same reviewed provider
capabilities and transport profile. Use
`--require-env-present` only in the deployment shell where Arrow.money/iRage
credentials are already configured, since the artifacts store presence booleans
but never credential values.

Generate the final dry-run client packet that an Arrow.money/iRage adapter
implementation must satisfy before any live provider call is allowed:

```powershell
python -m hft_cli prepare-provider-market-data-client `
  --fetcher-plan runs\provider_market_data_fetchers\arrow_ws_nse\provider_market_data_fetcher_config.json `
  --out runs\provider_market_data_clients\arrow_ws_nse `
  --session-label arrow_ws_nse_day1 `
  --max-clock-skew-ms 250 `
  --max-local-buffer-rows 100000 `
  --fail-on-blocked-actions `
  --fail-on-breach
```

This writes `provider_market_data_client_packet.json`,
`provider_market_data_output_schema.csv`, summary/check/action artifacts, and a
manifest. The packet is still dry-run only: it stores request details,
normalized output schema, runtime budgets, credential env-var names/presence
booleans, the blank env-template path/hash, and the upstream
`live_fetch_contract`, but never credential values. It preserves the
`adapter_execution_contract` with the session label, output schema columns,
clock-skew budget, local buffer budget, and provider-profile SHA so a backend
runner can bind the exact dry-run contract. Its ready action is the explicit
live-run approval gate for the provider client.

Plan the live capture windows before running a credentialed provider client:

```powershell
python -m hft_cli plan-provider-market-data-live-session `
  --client-packet runs\provider_market_data_clients\arrow_ws_nse\provider_market_data_client_packet.json `
  --out runs\provider_market_data_live_sessions\arrow_ws_nse_2026_06_23 `
  --trade-date 2026-06-23 `
  --window open=09:15-10:00 `
  --window close=14:45-15:30 `
  --capture-dir captures\provider_market_data `
  --batch-output-dir runs\provider_market_data_batches\arrow_ws_nse_2026_06_23 `
  --min-capture-rows 100000 `
  --pipeline-min-rows 100000 `
  --tick-size 0.05 `
  --max-p99-gap-ns 1000000000 `
  --max-median-spread-ticks 2 `
  --require-env-present `
  --fail-on-blocked-actions `
  --fail-on-breach
```

This writes `provider_market_data_live_session_windows.csv`,
`provider_market_data_live_session_packet.json`, summary/check/action/config
artifacts, and a runbook. It records only credential environment-variable
names, runtime presence booleans, the blank env-template path/hash, and the
upstream `live_fetch_contract`. It also verifies that the provider client
packet still carries the provider-profile contract and SHA matching the
selected provider, adapter, and transport. It then verifies that the client
packet still carries exchange/segment plus source-session metadata matching the
selected market profile, then preserves that proof in the session packet. The
session packet preserves the upstream `adapter_execution_contract` with
live-session readiness, trade date, capture-window count, command count, and
the same provider-profile SHA/capabilities, plus the exact post-capture
`pipeline-provider-market-data-batch` command and per-window capture paths.

Run a pre-market preflight against that session packet before starting the
credentialed provider client:

```powershell
python -m hft_cli preflight-provider-market-data-live-session `
  --live-session-packet runs\provider_market_data_live_sessions\arrow_ws_nse_2026_06_23\provider_market_data_live_session_packet.json `
  --out runs\provider_market_data_live_preflight\arrow_ws_nse_2026_06_23 `
  --require-env-present `
  --fail-on-blocked-actions `
  --fail-on-breach
```

This verifies the session packet is ready, credential env-var names are present
and available in the runtime when required, the blank source env-template
path/hash and upstream `live_fetch_contract` survived the live-session handoff,
the provider-profile contract/SHA still matches the live-session
provider/adapter/transport, exchange/session metadata still matches the
live-session capture profile, capture output directories are writable, planned
capture files do not already exist, the batch output has not already been
ingested, and the local clock has not passed the final capture window. It writes
`provider_market_data_live_preflight_summary.csv`,
`provider_market_data_live_preflight_windows.csv`,
`provider_market_data_live_preflight_checks.csv`,
`provider_market_data_live_preflight_action_queue.csv`, config/runbook
artifacts, and a manifest that fingerprints the blank env-template without
storing credential values. The preflight config and manifest also preserve the
`adapter_execution_contract`, adding live-preflight readiness, timing status,
capture counts, existing-capture count, provider-profile SHA/capabilities, and
credential env-var names for the backend runner.

Bundle the preflighted session into a per-window provider adapter handoff:

```powershell
python -m hft_cli bundle-provider-market-data-live-capture `
  --live-session-packet runs\provider_market_data_live_sessions\arrow_ws_nse_2026_06_23\provider_market_data_live_session_packet.json `
  --preflight-config runs\provider_market_data_live_preflight\arrow_ws_nse_2026_06_23\provider_market_data_live_preflight_config.json `
  --out runs\provider_market_data_live_capture_bundles\arrow_ws_nse_2026_06_23 `
  --ingest-output-dir runs\provider_market_data_live_ingest\arrow_ws_nse_2026_06_23 `
  --fail-on-blocked-actions `
  --fail-on-breach
```

This writes `provider_market_data_live_capture_commands.csv`,
`provider_market_data_live_capture_bundle.json`,
`provider_market_data_live_capture_env_template.env`,
`provider_market_data_adapter_handoff.json`, summary/check/action artifacts, a
runbook, and a manifest. It fails closed when the ready preflight does not carry
the source blank env-template proof, upstream `live_fetch_contract`, or
the provider-profile contract/SHA or exchange/session metadata inherited from
preflight, then fingerprints that source env-template in the bundle manifest.
The command queue is adapter-neutral by default (`provider-adapter capture ...
--exchange NFO ...`) and can be replaced with `--adapter-command-template` once
the Arrow.money or iRage client command is approved. The adapter handoff
contract carries provider, transport, exchange, endpoint, source/market session
metadata, provider-profile SHA/capabilities, output schema columns, per-window
capture commands, credential env-var names, source and capture blank
env-template references, runtime presence booleans, the live-fetch contract, and
the carried `adapter_execution_contract` with capture-bundle readiness, rendered
capture commands, handoff/env-template file names, command count, and the exact
post-capture
`ingest-provider-market-data-live-session` command without storing credential
values.

The default `provider-adapter capture` command is now an installed, fail-closed
runner rather than a placeholder executable. Configure a reviewed provider
backend as a trusted Python `module:function` entrypoint before running a
generated capture command:

```powershell
$env:ARROW_MONEY_PROVIDER_ADAPTER_BACKEND = "approved_arrow_backend.capture:capture"
$env:ARROW_MONEY_API_KEY = "<runtime value>"
$env:ARROW_MONEY_API_SECRET = "<runtime value>"

provider-adapter capture `
  --handoff runs\provider_market_data_live_capture_bundles\arrow_ws_nse_2026_06_23\provider_market_data_adapter_handoff.json `
  --env-template runs\provider_market_data_live_capture_bundles\arrow_ws_nse_2026_06_23\provider_market_data_live_capture_env_template.env `
  --provider arrow_money `
  --transport websocket `
  --endpoint wss://feed.arrow.money/market-data/nse `
  --market india_nse_index_derivatives `
  --exchange NFO `
  --kind ticks `
  --start 2026-06-23T09:15:00+05:30 `
  --end 2026-06-23T09:45:00+05:30 `
  --output captures\provider_market_data\arrow_money\2026-06-23\open.csv
```

The backend callable receives one `ProviderCaptureRequest`, reads credential
values from the runtime environment, and writes the exact requested output
path. The runner validates handoff identity, blank credential-template
contents, runtime credential presence, the exact capture window, ordered CSV
schema, timestamps (UTC nanoseconds or contract-local/offset datetimes), quote
ordering, and quantities. Datetime values are normalized to UTC nanoseconds for
window checks without changing the backend CSV representation. It then writes
`<capture>.adapter.json` with handoff, template, backend, window, row-count, and
output-hash proof while retaining only credential variable names and presence
booleans. It refuses to run when the backend is absent, untrusted, mismatched,
or produces drifted data. The generic `PROVIDER_ADAPTER_BACKEND` variable is a
fallback; prefer the provider-specific variable recorded in
`provider_market_data_adapter_handoff.json`. The repository still does not
implement Arrow.money or iRage network APIs; those approved backend callables
remain the real-provider integration boundary.

Before using real provider credentials, rehearse the backend handoff with
synthetic normalized captures:

```powershell
python -m hft_cli rehearse-provider-market-data-live-capture `
  --capture-bundle runs\provider_market_data_live_capture_bundles\arrow_ws_nse_2026_06_23\provider_market_data_live_capture_bundle.json `
  --out runs\provider_market_data_live_rehearsal\arrow_ws_nse_2026_06_23 `
  --rows-per-window 100 `
  --ingest-output-dir runs\provider_market_data_live_rehearsal_ingest\arrow_ws_nse_2026_06_23 `
  --fail-on-blocked-actions `
  --fail-on-breach
```

This writes small synthetic `ts,bid,ask,bid_qty,ask_qty,last,last_qty`
captures to the planned capture paths, sidecar files marking them as rehearsal
data, `provider_market_data_live_rehearsal_*` artifacts, and optionally runs
`ingest-provider-market-data-live-session` against those synthetic captures.
Each sidecar also preserves the rendered adapter command hash, capture
env-template hash, adapter handoff hash, source env-template proof, upstream
`live_fetch_contract`, and credential-safe `adapter_execution_contract` it
rehearsed. The rehearsal manifest fingerprints the sidecars, bundle credential
env-template, adapter handoff artifacts, source env-template proof,
`live_fetch_contract`, and `adapter_execution_contract`, without storing
credential values. Treat the result only as a backend smoke test; real research
evidence still requires replacing the synthetic captures with Arrow.money/iRage
provider captures from the approved bundle.

After those live capture files land, ingest the whole planned session from the
session packet:

```powershell
python -m hft_cli ingest-provider-market-data-live-session `
  --live-session-packet runs\provider_market_data_live_sessions\arrow_ws_nse_2026_06_23\provider_market_data_live_session_packet.json `
  --capture-bundle runs\provider_market_data_live_capture_bundles\arrow_ws_nse_2026_06_23\provider_market_data_live_capture_bundle.json `
  --out runs\provider_market_data_live_ingest\arrow_ws_nse_2026_06_23 `
  --fail-on-blocked-actions `
  --fail-on-breach
```

This verifies every expected capture file exists and is non-empty, then runs
the structured `pipeline-provider-market-data-batch` configuration from the
session packet. It writes `provider_market_data_live_ingest_summary.csv`,
`provider_market_data_live_ingest_windows.csv`,
`provider_market_data_live_ingest_action_queue.csv`, config/runbook artifacts,
and a manifest that fingerprints the session packet, client packet, captures,
batch output manifest, and optionally the approved capture bundle plus its
credential env-template, adapter handoff artifacts, source env-template proof,
exchange/session metadata matching the live session packet, and upstream
`live_fetch_contract`. Bundle-linked ingest also requires the carried
provider-profile contract plus `adapter_execution_contract` to be present,
credential-safe, and matched to the live-session packet before batch ingestion
can become ready; the provider-profile SHA/capabilities are carried into the
ingest summary/config/manifest for downstream audit. Every bundle-linked real
capture must also retain its adjacent `<capture>.adapter.json` receipt. Ingest
recomputes the capture, handoff, environment-template, and receipt hashes and
verifies provider identity, credential-presence proof, schema, backend, and
window contract before accepting the capture. The receipt fingerprints and
per-check results are carried in the ingest summary, config, windows table, and
manifest. Explicit rehearsal sidecars are exempt from the real-capture receipt
gate, but remain synthetic smoke evidence and cannot pass the downstream
research-evidence review as real provider data.

Review the live ingest output before treating it as research evidence:

```powershell
python -m hft_cli review-provider-market-data-live-evidence `
  --live-ingest-dir runs\provider_market_data_live_ingest\arrow_ws_nse_2026_06_23 `
  --out runs\provider_market_data_live_evidence\arrow_ws_nse_2026_06_23 `
  --min-capture-rows 100000 `
  --fail-on-blocked-actions `
  --fail-on-breach
```

This writes `provider_market_data_live_evidence_summary.csv`,
`provider_market_data_live_evidence_captures.csv`, check/action/config
artifacts, and a manifest. If the live ingest carried a capture bundle, the
evidence manifest also fingerprints that bundle, its credential env-template,
the adapter handoff contract, source env-template proof, exchange/session
metadata, upstream `live_fetch_contract`, provider-profile contract/SHA, and
`adapter_execution_contract` before research handoff. It blocks captures that
still have rehearsal sidecars (`*.csv.rehearsal.json`) from being marked
research-ready, even if the ingest and batch pipelines passed. When synthetic
rehearsal is explicitly allowed for a smoke run, the review also verifies each
sidecar's adapter command hash, capture env-template hash, adapter handoff hash,
source env-template proof, provider-fetcher handoff, credential-safe adapter
contract, and rehearsal-only invariants against the live ingest provenance
when carried, or against the referenced files when the rehearsal ingest did not
carry the bundle block, before classifying it as backend smoke evidence. It
fails closed if capture-bundle source metadata, provider-profile metadata,
adapter-contract metadata, or rehearsal sidecar proof drifts from the live
session packet. For bundle-linked real captures, evidence review also reruns
the adapter receipt validator against the current capture, handoff, credential
template, provider identity, schema, and session window. It requires every
receipt hash and record to match both the ingest config and ingest manifest,
then fingerprints the receipts again in the evidence manifest. A capture or
receipt changed after ingest therefore blocks research readiness and routes
back through provider adapter plus live ingest.
Use `--allow-synthetic-rehearsal` only to classify a smoke test; the
recommendation remains to replace synthetic captures with real Arrow.money/iRage
provider captures before feeding walk-forward research.

Turn research-ready live evidence into concrete strategy research commands:

```powershell
python -m hft_cli handoff-provider-market-data-research `
  --live-evidence-dir runs\provider_market_data_live_evidence\arrow_ws_nse_2026_06_23 `
  --out runs\provider_market_data_research_handoff\arrow_ws_nse_2026_06_23 `
  --strategy imbalance `
  --output-root runs\provider_market_data_research\arrow_ws_nse_2026_06_23 `
  --min-tick-folds 2 `
  --tick-size 0.05 `
  --fail-on-blocked-actions `
  --fail-on-breach
```

This writes `provider_market_data_research_handoff_datasets.csv`,
`provider_market_data_research_handoff_commands.csv`, action/config/runbook
artifacts, and a manifest. The first supported handoff maps top-of-book provider
tick folds to `walkforward-imbalance-edge` and the follow-on
`walkforward-imbalance-replay` command that consumes the edge
`candidate_config.json`. If the live evidence came from an approved capture
bundle, the handoff summary/config/runbook and manifest retain the capture
bundle, blank credential env-template, adapter handoff contract paths, upstream
source credential env-template proof, exchange/session metadata, and
`live_fetch_contract` before strategy research starts. They also retain the
provider-profile contract/SHA plus credential-safe
`adapter_execution_contract` and block if either is missing, stores credential
values, or no longer matches live evidence. The handoff also requires the
evidence receipt proof to match between evidence config and manifest, then
recomputes every provider capture and required receipt hash before emitting a
strategy command. Post-evidence file changes route back to live-evidence review.
Synthetic smoke evidence remains
blocked by default, but the handoff still carries the live-evidence
`synthetic_sidecar_proof` into summary/config/runbook and manifest artifacts;
if smoke mode is explicitly enabled, missing or stale sidecar proof routes back
to `review-provider-market-data-live-evidence` before any strategy handoff can
be treated as ready. Source-metadata drift, provider-profile drift, and
unsupported strategy lanes stay blocked: lead-lag needs explicit
leader/laggard groups, while settlement, parity, and surface market-making need
option-chain or surface inputs in addition to top-of-book ticks.

Run the first full provider-data imbalance research pilot directly from
research-ready live evidence:

```powershell
python -m hft_cli run-provider-market-data-imbalance-research `
  --live-evidence-dir runs\provider_market_data_live_evidence\arrow_ws_nse_2026_06_23 `
  --out runs\provider_market_data_imbalance_research\arrow_ws_nse_2026_06_23 `
  --entry-imbalance 0.55 0.65 0.75 `
  --min-microprice-edge-ticks 0.25 0.50 1.00 `
  --forward-horizon-ns 100000000 500000000 1000000000 `
  --min-tick-folds 2 `
  --tick-size 0.05 `
  --instrument-kind FUT `
  --instrument-id NIFTY-I `
  --fail-on-blocked-actions `
  --fail-on-breach
```

This writes a nested `research_handoff` plus `imbalance_research` folder under
the output root. If the evidence gate passes, it runs the existing imbalance
edge walk-forward, replay-proof, and promotion pipeline against the provider
tick folds, then writes
`provider_market_data_imbalance_research_summary.csv`,
`provider_market_data_imbalance_research_action_queue.csv`, config/runbook
artifacts, and a manifest. When available, those wrapper artifacts also retain
the approved capture bundle, blank credential env-template, adapter handoff
paths, upstream source credential env-template proof, exchange/session metadata,
`live_fetch_contract`, provider-profile contract/SHA, and credential-safe
`adapter_execution_contract` carried by the nested research handoff. They also
carry nested `synthetic_sidecar_proof`, so explicit synthetic-smoke runs remain
blocked if rehearsal sidecar proof is missing, stale, or does not cover every
synthetic fold. The wrapper now also requires the nested handoff's sealed
`adapter_receipt_proof`, verifies its receipt and capture hash counts against
live evidence, fingerprints every required receipt and capture in its own
manifest, and carries the proof into summary/config/runbook and manifest
artifacts. If the provider profile, adapter contract, or adapter receipt proof
is missing, unsafe, incomplete, or no longer matches live evidence, the
strategy pipeline is blocked before imbalance research runs. If the live
evidence is synthetic smoke evidence, not research-ready, or too thin, the
strategy pipeline is not run and the action queue points back to the provider
evidence or imbalance research gate.

Review the provider imbalance research evidence before building broker launch
artifacts:

```powershell
python -m hft_cli review-provider-market-data-imbalance-evidence `
  --provider-research-dir runs\provider_market_data_imbalance_research\arrow_ws_nse_2026_06_23 `
  --out runs\provider_market_data_imbalance_evidence\arrow_ws_nse_2026_06_23 `
  --fail-on-blocked-actions `
  --fail-on-breach
```

This writes a nested experiment `catalog` and `strategy_evidence` review using
the `provider_imbalance_research` profile. That profile requires the provider
research handoff, imbalance edge walk-forward, replay walk-forward, promotion,
the root imbalance research pipeline, and the provider imbalance research
manifest. The evidence summary/config/runbook and manifest also retain the
approved capture bundle, blank credential env-template, adapter handoff paths,
upstream source credential env-template proof, exchange/session metadata,
capture-bundle session match proof, `live_fetch_contract`, and the
provider-profile contract/SHA plus credential-safe
`adapter_execution_contract` when they were present in the upstream provider
research wrapper. It also carries nested `synthetic_sidecar_proof` and flattened
sidecar counts from provider imbalance research, so synthetic provider folds
remain blocked from launch packaging if rehearsal sidecar proof is missing or no
longer covers every synthetic fold. The review reads the provider research
manifest, requires its sealed `adapter_receipt_proof` to exactly match the
research config, rechecks the receipt/capture fingerprint counts, and carries
that proof into the evidence manifest. If the provider profile, adapter
contract, adapter receipt proof, or synthetic sidecar proof is missing, unsafe,
or no longer matched to live evidence, the review blocks launch packaging. A
ready review points to `pipeline-imbalance-launch`; it does not weaken the full
`imbalance` profile, which still requires order-plan and launch pipeline proof
before shadow scale-up.

Build the provider imbalance launch packet directly from the ready evidence
review:

```powershell
python -m hft_cli pipeline-provider-market-data-imbalance-launch `
  --provider-evidence-dir runs\provider_market_data_imbalance_evidence\arrow_ws_nse_2026_06_23 `
  --out runs\provider_market_data_imbalance_launch\arrow_ws_nse_2026_06_23 `
  --adapter arrow_money `
  --route-tag imbalance_shadow `
  --instrument-id NIFTY-I `
  --reference-price 24500 `
  --max-order-qty 75 `
  --max-notional 2000000 `
  --max-orders 2 `
  --fail-on-blocked-actions `
  --fail-on-breach
```

The provider launch packet infers the promoted imbalance candidate from the
provider research root and runs the standard imbalance order-plan, staging,
launch, export, upload-pack, and broker-readiness pipeline. When ready, the next
gate is `review-strategy-evidence --profile imbalance`, which verifies the full
launch-ready profile rather than only the provider-data research profile. The
provider launch summary/config/runbook and manifest retain the upstream capture
bundle, blank credential env-template, adapter handoff paths, source credential
env-template proof, exchange/session metadata, capture-bundle session match
proof, `live_fetch_contract`, provider-profile contract/SHA, and credential-safe
`adapter_execution_contract` when present in the provider evidence review. They
also retain nested `synthetic_sidecar_proof` plus flattened sidecar counts, and
block the downstream launch pipeline when synthetic provider folds are missing
ready rehearsal sidecar proof. The launch wrapper now reads the evidence
manifest, requires its sealed `adapter_receipt_proof` to exactly match evidence
config, re-hashes every required receipt and provider capture, and fingerprints
those files again in the launch manifest. If the provider profile, adapter
contract, adapter receipt proof, or synthetic sidecar proof is missing, unsafe,
or no longer matched to live evidence, the downstream launch pipeline is not
run, keeping broker-facing artifacts tied to the live data source contract.

Review the full launch-ready imbalance profile from the provider launch packet:

```powershell
python -m hft_cli review-provider-market-data-imbalance-launch-evidence `
  --provider-launch-dir runs\provider_market_data_imbalance_launch\arrow_ws_nse_2026_06_23 `
  --out runs\provider_market_data_imbalance_launch_evidence\arrow_ws_nse_2026_06_23 `
  --fail-on-blocked-actions `
  --fail-on-breach
```

This catalogs both the original provider imbalance research root and the
provider launch packet root before running the full `imbalance` evidence profile.
A ready review proves that edge walk-forward, replay walk-forward, promotion,
research pipeline, order plan, and launch pipeline evidence all share the same
imbalance/market identity. The launch-evidence summary/config/runbook and
manifest retain the upstream capture bundle, blank credential env-template,
adapter handoff paths, source credential env-template proof, exchange/session
metadata, capture-bundle session match proof, `live_fetch_contract`, and the
provider-profile contract/SHA plus credential-safe `adapter_execution_contract`
from the provider launch packet. They also retain nested
`synthetic_sidecar_proof` plus flattened sidecar counts, and block scorecard
readiness when synthetic provider folds are missing ready rehearsal sidecar
proof. The review now reads the launch manifest, requires its sealed
`adapter_receipt_proof` to exactly match launch config, re-hashes every required
receipt and provider capture, and fingerprints those files in its own manifest.
If the provider profile, adapter contract, adapter receipt proof, or synthetic
sidecar proof is missing, unsafe, or no longer matched to live evidence,
scorecard readiness is blocked before later broker handoffs can drift from the
provider-data source contract. Its next gate is
`score-strategy-readiness --profile imbalance`.

Score the provider-data imbalance launch evidence for shadow scale-up planning:

```powershell
python -m hft_cli score-provider-market-data-imbalance-readiness `
  --provider-launch-evidence-dir runs\provider_market_data_imbalance_launch_evidence\arrow_ws_nse_2026_06_23 `
  --out runs\provider_market_data_imbalance_scorecards\arrow_ws_nse_2026_06_23 `
  --fail-on-blocked-actions `
  --fail-on-breach
```

This runs the standard strategy readiness scorecard on only the full `imbalance`
profile from the launch-evidence catalog. A ready scorecard has readiness score
`1.0` and points to `plan-provider-market-data-imbalance-scaleup` for
paper/shadow capital and runtime sizing. The provider scorecard
summary/config/runbook and manifest also retain the upstream capture bundle,
blank credential env-template, adapter handoff paths, source credential
env-template proof, exchange/session metadata, capture-bundle session match
proof, `live_fetch_contract`, provider-profile contract/SHA, and credential-safe
`adapter_execution_contract` before scale-up planning begins. It also carries
nested `synthetic_sidecar_proof` plus flattened sidecar counts, and blocks
scale-up readiness when synthetic provider folds are missing ready rehearsal
sidecar proof. The provider scorecard now reads the launch-evidence manifest,
requires exact `adapter_receipt_proof` agreement with launch-evidence config,
re-hashes every required receipt and provider capture, and fingerprints those
files in its own manifest. If the provider profile, adapter contract, adapter
receipt proof, or synthetic sidecar proof is missing, unsafe, or no longer
matched to live evidence, the nested readiness scorer is not run; the wrapper
blocks scale-up readiness and sends the packet back through launch-evidence
review.

Build provider route-readiness proof from the same launch evidence:

```powershell
python -m hft_cli review-provider-market-data-imbalance-route-readiness `
  --provider-launch-evidence-dir runs\provider_market_data_imbalance_launch_evidence\arrow_ws_nse_2026_06_23 `
  --ops-evidence runs\strategy_evidence\provider_imbalance_ops_launch_arrow_ws_nse_2026_06_23 `
  --out runs\provider_market_data_imbalance_route_readiness\arrow_ws_nse_2026_06_23 `
  --fail-on-blocked-actions `
  --fail-on-breach
```

When no market-portability packet is supplied, the provider wrapper builds an
India `microprice_imbalance` portability packet and joins it with the full
imbalance strategy evidence plus ops-launch evidence. Missing ops-launch
controls stay blocked at `review-strategy-evidence --profile
provider_market_data_imbalance_ops_launch --require-file-inputs`, using a
provider-specific portability config copy for the nested generic route review;
a ready wrapper writes nested `route_readiness` outputs and can be passed to
`plan-provider-market-data-imbalance-scaleup --route-readiness`. Provider
route-readiness also inherits the generic route sidecar gate, so stale or
breached provider broker round-trip synthetic sidecar proof is sent back to
`review-strategy-evidence --profile provider_market_data_imbalance_ops_launch --require-file-inputs`.

Create the provider-data imbalance scale-up plan from that ready scorecard and
an accepted shadow-session comparison:

```powershell
python -m hft_cli plan-provider-market-data-imbalance-scaleup `
  --scorecard runs\provider_market_data_imbalance_scorecards\arrow_ws_nse_2026_06_23 `
  --shadow-comparison runs\shadow_comparisons\provider_imbalance_arrow_ws_nse_2026_06_23 `
  --route-readiness runs\provider_market_data_imbalance_route_readiness\arrow_ws_nse_2026_06_23 `
  --out runs\provider_market_data_imbalance_scaleup\arrow_ws_nse_2026_06_23 `
  --allowed-adapter arrow_money `
  --max-scale-multiplier 1.0 `
  --max-orders-per-session 2 `
  --max-session-notional 2000000 `
  --fail-on-blocked-actions `
  --fail-on-breach
```

The provider wrapper infers the full imbalance `strategy_evidence` and nested
`imbalance_launch_pipeline` paths from the scorecard and launch-evidence
artifacts, but it still requires a real `shadow_session_comparison_summary.csv`.
Supplying the provider route-readiness wrapper root lets the provider scale-up
wrapper resolve its nested generic `route_readiness` proof automatically, then
the generic scale-up gate revalidates ops-launch route controls before runtime
sizing, including provider broker round-trip synthetic sidecar breach counts
from the Arrow.money/iRage-ready route packet. Breached sidecar proof blocks the
provider scale-up action queue back at
`review-provider-market-data-imbalance-route-readiness`. It writes provider
wrapper checks/summary/action/config/runbook artifacts plus a nested generic
`scaleup` folder with `scaleup_plan.csv`,
`scaleup_checks.csv`, `scaleup_summary.csv`, and `scaleup_config.json`, while
retaining the upstream capture bundle, blank credential env-template, and
adapter handoff paths, source credential env-template proof, exchange/session
metadata, capture-bundle session match proof, `live_fetch_contract`, and the
provider-profile contract/SHA plus credential-safe `adapter_execution_contract`
from the provider scorecard in the provider wrapper summary/config/runbook and
manifest. It also retains nested `synthetic_sidecar_proof` plus flattened
sidecar counts from the provider scorecard and blocks runtime telemetry when
synthetic provider folds are missing ready rehearsal sidecar proof. Missing,
unsafe, or mismatched provider-profile, adapter-contract, or synthetic sidecar
proof keeps scale-up blocked at provider scorecard readiness before runtime
telemetry begins. The scale-up wrapper also reads the provider scorecard
manifest, requires exact `adapter_receipt_proof` agreement with scorecard
config, re-hashes every required receipt and provider capture, and fingerprints
those files in its own manifest. Receipt or capture drift prevents the generic
scale-up planner from running and routes remediation back to provider scorecard
generation. A ready wrapper points to
`build-provider-market-data-imbalance-runtime-telemetry`; missing or rejected
shadow evidence stays blocked at `compare-shadow-sessions`.

Build guard-ready runtime telemetry from that provider scale-up wrapper:

```powershell
python -m hft_cli build-provider-market-data-imbalance-runtime-telemetry `
  --scaleup runs\provider_market_data_imbalance_scaleup\arrow_ws_nse_2026_06_23 `
  --out runs\provider_market_data_imbalance_runtime_telemetry\arrow_ws_nse_2026_06_23 `
  --pnl runs\runtime_snapshots\provider_imbalance_pnl.csv `
  --open-orders runs\runtime_snapshots\provider_imbalance_open_orders.csv `
  --positions runs\runtime_snapshots\provider_imbalance_positions.csv `
  --snapshot-ts-ns 1782198900000000000 `
  --fail-on-blocked-actions `
  --fail-on-breach
```

By default the provider telemetry wrapper infers broker export and upload-pack
inputs from the provider imbalance launch pipeline carried by the scale-up
wrapper, then writes provider checks/summary/action/config/runbook artifacts
plus a nested `runtime_telemetry` folder with `runtime_telemetry.csv`,
`runtime_telemetry_sources.csv`, `runtime_telemetry_checks.csv`, and
`runtime_telemetry_summary.csv`. The provider wrapper also retains the upstream
capture bundle, blank credential env-template, adapter handoff paths, source
credential env-template proof, exchange/session metadata, capture-bundle session
match proof, `live_fetch_contract`, provider-profile contract/SHA, and
credential-safe `adapter_execution_contract` from scale-up in its
summary/config/runbook and manifest. It also retains nested
`synthetic_sidecar_proof` plus flattened sidecar counts from scale-up and
blocks guard monitoring when synthetic provider folds are missing ready
rehearsal sidecar proof. Before invoking the generic telemetry builder, the
wrapper reads the provider scale-up manifest, requires exact
`adapter_receipt_proof` agreement with scale-up config, and re-hashes every
required adapter receipt and provider capture. Receipt or capture drift keeps
telemetry blocked, leaves the nested generic telemetry absent, and routes
remediation back to provider scale-up planning; accepted files are
fingerprinted again in the runtime telemetry manifest. It also carries the
provider route-readiness broker
round-trip synthetic sidecar breach counter from scale-up, and stale packets
with nonzero route sidecar breaches are routed back to
`review-provider-market-data-imbalance-route-readiness`. Missing, unsafe, or
mismatched provider-profile, adapter-contract, or synthetic sidecar proof blocks
guard monitoring and sends the packet back through provider scale-up planning. Supply
live PnL, open-order, and position CSVs when they are available from
Arrow.money/iRage; omit them for a dry guard-input snapshot based on scale-up
and launch-pipeline metadata. A ready wrapper points to
`monitor-provider-market-data-imbalance-runtime-guard`.

Run the provider-specific runtime guard wrapper:

```powershell
python -m hft_cli monitor-provider-market-data-imbalance-runtime-guard `
  --runtime-telemetry runs\provider_market_data_imbalance_runtime_telemetry\arrow_ws_nse_2026_06_23 `
  --out runs\provider_market_data_imbalance_runtime_guard\arrow_ws_nse_2026_06_23 `
  --as-of-ts-ns 1782198900000000000 `
  --max-telemetry-age-ns 1000000000 `
  --fail-on-blocked-actions `
  --fail-on-breach `
  --fail-on-halt
```

The wrapper reads the provider telemetry summary, resolves the nested
`scaleup_config.json` and `runtime_telemetry.csv`, writes provider
checks/summary/action/config/runbook artifacts plus nested generic
`runtime_guard` outputs, and retains the upstream capture bundle, blank
credential env-template, adapter handoff paths, source credential env-template
proof, exchange/session metadata, capture-bundle session match proof, and
`live_fetch_contract` plus provider-profile contract/SHA and credential-safe
`adapter_execution_contract` in its provider wrapper summary/config/runbook and
manifest. It also retains nested `synthetic_sidecar_proof` plus flattened
sidecar counts from runtime telemetry. Missing, unsafe, or mismatched
provider-profile, adapter-contract, or synthetic sidecar proof blocks
runtime-session monitoring and sends the packet back through provider runtime
telemetry. Before invoking the generic guard, the wrapper reads the runtime
telemetry manifest, requires exact `adapter_receipt_proof` agreement with the
telemetry config, and re-hashes every required adapter receipt and provider
capture. Receipt or capture drift leaves the nested generic guard absent,
routes remediation back to runtime telemetry generation, and only accepted
files are fingerprinted again in the guard manifest. Runtime guard also carries
the provider route-readiness broker
round-trip synthetic sidecar breach counter from runtime telemetry; stale
nonzero breach packets are routed back to
`review-provider-market-data-imbalance-route-readiness`. It converts guard
halts into a ready `plan-halt-response` action. A clean guard points to
`monitor-provider-market-data-imbalance-runtime-session`.

Run the provider-specific runtime session wrapper:

```powershell
python -m hft_cli monitor-provider-market-data-imbalance-runtime-session `
  --runtime-guard runs\provider_market_data_imbalance_runtime_guard\arrow_ws_nse_2026_06_23 `
  --out runs\provider_market_data_imbalance_runtime_session\arrow_ws_nse_2026_06_23 `
  --as-of-ts-ns 1782198900000000000 `
  --max-telemetry-age-ns 1000000000 `
  --fail-on-blocked-actions `
  --fail-on-breach `
  --fail-on-halt
```

The session wrapper reads the provider guard summary/config, infers the provider
runtime telemetry directory, reuses the telemetry wrapper's broker export,
upload-pack, reconciliation, metadata, PnL, open-order, and position inputs when
available, writes provider session checks/summary/action/config/runbook
artifacts plus a nested generic `runtime_session`, and retains the upstream
capture bundle, blank credential env-template, adapter handoff paths, source
credential env-template proof, exchange/session metadata, capture-bundle session
match proof, `live_fetch_contract`, provider-profile contract/SHA, and
credential-safe `adapter_execution_contract` in its provider wrapper
summary/config/runbook and manifest. It also retains nested
`synthetic_sidecar_proof` plus flattened sidecar counts from runtime guard.
Missing, unsafe, or mismatched provider-profile, adapter-contract, or
synthetic sidecar proof blocks broker readiness review and sends the packet
back through provider runtime guard. Before invoking the generic session
monitor, the wrapper reads the runtime-guard manifest, requires exact
`adapter_receipt_proof` agreement with guard config, and re-hashes every
required adapter receipt and provider capture. Receipt or capture drift leaves
the nested generic session absent, routes remediation back to runtime guard,
and only accepted files are fingerprinted again in the session manifest.
Runtime session also carries the provider
route-readiness broker round-trip synthetic sidecar breach counter from runtime
guard; stale nonzero breach packets are routed back to
`review-provider-market-data-imbalance-route-readiness`.
Clean sessions route to
`review-provider-market-data-imbalance-broker-readiness`. If the session guard
halts and a halt response is ready, it emits a ready `export-halt-response`
action.

Run the provider-specific broker readiness wrapper:

```powershell
python -m hft_cli review-provider-market-data-imbalance-broker-readiness `
  --runtime-session runs\provider_market_data_imbalance_runtime_session\arrow_ws_nse_2026_06_23 `
  --dispatch-roundtrip runs\provider_market_data_imbalance_broker_dispatch_roundtrip\arrow_ws_nse_2026_06_23 `
  --require-dispatch-roundtrip `
  --out runs\provider_market_data_imbalance_broker_readiness\arrow_ws_nse_2026_06_23 `
  --fail-on-blocked-actions `
  --fail-on-breach
```

The provider broker-readiness wrapper reads the provider runtime-session
summary/config, infers the nested generic `runtime_session` plus provider launch
order export/upload-pack artifacts, accepts either the provider broker-dispatch
round-trip wrapper root or its nested generic `broker_dispatch_roundtrip`
folder, preserves any upstream round-trip lineage carried by the provider
wrapper, preserves inherited upstream vendor-market-data batch evidence under
`upstream_*_vendor_market_data_batch_*` fields, runs the generic
`broker_readiness` gate under a nested folder, and writes provider
checks/summary/action/config/runbook artifacts. It also retains the upstream
capture bundle, blank credential env-template, adapter handoff paths, source
credential env-template proof, exchange/session metadata, capture-bundle session
match proof, `live_fetch_contract`, provider-profile contract/SHA, and
credential-safe `adapter_execution_contract` in the provider
summary/config/runbook plus manifest, so broker integration reviewers can trace
the live data source without opening nested runtime-session folders. It also
retains nested `synthetic_sidecar_proof` plus flattened sidecar counts from the
runtime-session wrapper. Missing, unsafe, or mismatched provider-profile,
adapter-contract, or synthetic sidecar proof blocks cutover review and sends
the packet back through provider runtime session. Before invoking the generic
broker-readiness scorer, the wrapper reads the runtime-session manifest,
requires exact `adapter_receipt_proof` agreement with session config, and
re-hashes every required adapter receipt and provider capture. Receipt or
capture drift leaves the nested generic broker-readiness report absent, routes
remediation back to runtime session, and only accepted files are fingerprinted
again in the broker-readiness manifest.
Broker readiness also carries the provider route-readiness broker round-trip
synthetic sidecar breach counter from runtime session; stale nonzero breach
packets are routed back to
`review-provider-market-data-imbalance-route-readiness`.
When a provider round-trip proof carries its own `dispatch_roundtrip_*` capture
bundle/env-template, adapter handoff path, source credential env-template
proof, `live_fetch_contract`, provider-profile contract/SHA, or
credential-safe `adapter_execution_contract`, plus exchange/session metadata
and capture-bundle session proof,
broker-readiness records those exact fields as `dispatch_roundtrip_*`
provenance, falls back to older top-level wrapper fields for legacy artifacts,
adds manifest inputs/metadata for every proof root including the round-trip
source credential env-template, carries any round-trip
`synthetic_sidecar_proof` plus flattened `dispatch_roundtrip_synthetic_*`
counts, and fails closed back to
`review-provider-market-data-imbalance-broker-dispatch-roundtrip` if they are
missing, unsafe, stale, or conflict with the runtime-session provenance,
exchange/session/live-fetch identity, runtime-session provider profile, or
runtime-session adapter contract. If the supplied provider round-trip has
synthetic provider folds but no ready rehearsal sidecar proof, broker-readiness
also blocks cutover and routes the packet back to broker-dispatch round-trip
review. If that final provider round-trip carries a route-readiness provider
broker round-trip synthetic sidecar breach counter, broker-readiness exposes it
as `dispatch_roundtrip_route_readiness_*` summary/config/manifest fields and
routes nonzero final dry-run sidecar breaches back to
`review-provider-market-data-imbalance-route-readiness`.
When `--dispatch-roundtrip` points to the provider wrapper root,
broker-readiness also reads its summary, config, and manifest before invoking
the generic scorer. It requires the provider run type, exact
`adapter_receipt_proof` agreement between round-trip config and manifest, exact
agreement with the runtime-session receipt proof, and current SHA-256 values for
every required receipt and capture. Accepted files are fingerprinted again as
`dispatch_roundtrip_adapter_receipts` and
`dispatch_roundtrip_provider_captures`; proof or byte drift leaves nested
generic broker-readiness absent and routes repair to
`review-provider-market-data-imbalance-broker-dispatch-roundtrip`. Passing the
nested generic `broker_dispatch_roundtrip` folder directly remains supported;
provider-wrapper-only receipt checks are inactive and the generic round-trip
checks remain authoritative on that compatibility path.
If the final provider round-trip CSV is sparse but its config sidecar carries
`dispatch_roundtrip_provenance`, broker-readiness hydrates missing or blank
`dispatch_roundtrip_route_readiness_*` fields from that sidecar while keeping
explicit CSV `False` and `0` values authoritative, so mixed-version final
round-trip artifacts still preserve route-sidecar proof.
When the final round-trip proof carries Arrow.money/iRage vendor-market-data
batch evidence, the wrapper
promotes both generic dispatch and broker-dispatch vendor batch readiness fields
into the provider summary/config/runbook plus manifest metadata, so cutover
reviewers do not need to inspect nested generic folders.
By default it is suitable for initial Arrow.money/iRage dry-run testing: it
requires the provider runtime session, order export, upload pack, and
broker-readiness pass, while leaving reviewed schema, reconciliation, route
readiness, and dispatch roundtrip as explicit promotion flags. A ready wrapper
points to
`review-provider-market-data-imbalance-cutover`.

Run the provider-specific cutover wrapper:

```powershell
python -m hft_cli review-provider-market-data-imbalance-cutover `
  --broker-readiness runs\provider_market_data_imbalance_broker_readiness\arrow_ws_nse_2026_06_23 `
  --out runs\provider_market_data_imbalance_cutover\arrow_ws_nse_2026_06_23 `
  --fail-on-blocked-actions `
  --fail-on-breach
```

The provider cutover wrapper reads the provider broker-readiness summary/config,
infers nested generic scale-up, broker-readiness, runtime-session evidence, and
any provider broker-dispatch round-trip proof carried by broker-readiness. It
runs `review-cutover-gate` under a nested `cutover` folder, writes provider
checks/summary/action/config/runbook artifacts, and preserves the provider
round-trip wrapper root, nested generic `broker_dispatch_roundtrip` folder, and
any upstream proof lineage in the cutover summary/config/manifest. It also
preserves the capture bundle, blank credential env-template, adapter handoff
paths, source credential env-template proof, exchange/session metadata,
capture-bundle session match proof, `live_fetch_contract`, provider-profile
contract/SHA, and credential-safe `adapter_execution_contract` inherited from
broker-readiness, plus any nested `synthetic_sidecar_proof` and flattened
sidecar counts produced for synthetic provider folds, so route-enable reviewers
can trace the live data source from the cutover artifact set without exposing
credential values. If the provider-profile, adapter contract, or required
synthetic sidecar proof is missing, unsafe, unready, or no longer matched to
live evidence, cutover blocks route-enable and routes the packet back to
`review-provider-market-data-imbalance-broker-readiness`. Before invoking the
generic cutover gate, the wrapper reads the broker-readiness manifest, requires
exact `adapter_receipt_proof` agreement with broker-readiness config, and
re-hashes every required adapter receipt and provider capture. Receipt or
capture drift leaves the nested generic cutover absent, routes remediation
back to broker readiness, and only accepted files are fingerprinted again in
the cutover manifest. If
broker-readiness carried a provider route-readiness broker round-trip synthetic
sidecar breach counter, cutover preserves it too; stale nonzero breach packets
are routed back to
`review-provider-market-data-imbalance-route-readiness`.
If broker-readiness validated round-trip capture bundle/env-template/adapter
handoff provenance, cutover also carries those `dispatch_roundtrip_*`
provenance fields plus the validated round-trip source credential env-template,
exchange/session metadata, capture-bundle session proof, live-fetch
exchange/session identity, `live_fetch_contract` snapshot, provider-profile
contract/SHA, and credential-safe round-trip `adapter_execution_contract`
forward for route-enable and dispatch reviewers. It also carries the final
round-trip `synthetic_sidecar_proof` plus flattened
`dispatch_roundtrip_synthetic_*` counts from broker-readiness and fails closed
when synthetic final dry-run folds are missing ready rehearsal sidecars. It
also carries `dispatch_roundtrip_route_readiness_*` sidecar breach proof and
routes nonzero final dry-run sidecar breaches back to
`review-provider-market-data-imbalance-route-readiness`. If that final dry-run
provider profile, adapter proof, or sidecar proof is missing, unsafe, stale,
unready, or no longer
matched to runtime-session evidence, cutover blocks route-enable and routes
back to `review-provider-market-data-imbalance-broker-readiness`.
When broker-readiness used a provider round-trip wrapper with required adapter
receipts, cutover additionally requires its `dispatch_roundtrip_provenance`
receipt proof to match both the broker-readiness manifest copy and the root
runtime receipt proof exactly. It re-hashes every final round-trip receipt and
capture before invoking the generic cutover gate and fingerprints accepted
files as `dispatch_roundtrip_adapter_receipts` and
`dispatch_roundtrip_provider_captures`. Proof or byte drift leaves nested
generic cutover absent and routes repair to
`review-provider-market-data-imbalance-broker-readiness`. A provider wrapper
with no required receipts and a broker-readiness packet with no provider-wrapper
proof remain supported; the runbook marks the final receipt seal not applicable
instead of blocked on those compatibility paths.
When a
broker-readiness CSV is from an
older or thinner wrapper but its config sidecar has
`dispatch_roundtrip_provenance`, cutover hydrates missing or blank
`dispatch_roundtrip_*` fields from that config while preserving explicit CSV
`False` and `0` values as authoritative. If provider
broker-readiness carried vendor-market-data batch evidence, cutover also
retains the generic dispatch, broker-dispatch, and inherited upstream vendor
batch readiness fields plus config snapshots, including
`upstream_*_vendor_market_data_batch_*` fields for route-enable and dispatch
reviewers. It keeps the generic cutover safety model intact: if route-readiness
or broker route proof is missing, the wrapper blocks with
`review-route-readiness`; once cutover is fully clean, it points to
`review-route-enable`. Use
`--allow-missing-route-readiness` only for diagnostic dry-runs that are not
allowed to proceed into route-enable.

Run the provider-specific route-enable wrapper:

```powershell
python -m hft_cli review-provider-market-data-imbalance-route-enable `
  --provider-cutover runs\provider_market_data_imbalance_cutover\arrow_ws_nse_2026_06_23 `
  --out runs\provider_market_data_imbalance_route_enable\arrow_ws_nse_2026_06_23 `
  --fail-on-blocked-actions `
  --fail-on-breach
```

The provider route-enable wrapper reads the provider cutover summary/config,
infers the nested generic `cutover` plus broker upload-pack/order-export inputs
from the provider broker-readiness config, carries any cutover-retained provider
broker-dispatch round-trip wrapper, nested generic `broker_dispatch_roundtrip`
paths, cutover-retained vendor-market-data batch readiness fields/config, and
upstream proof lineage. It also preserves inherited
`upstream_*_vendor_market_data_batch_*` readiness fields/config so dispatch
planners can see the full Arrow.money/iRage vendor-data chain from the
route-enable artifact. It also preserves the capture bundle, blank credential
env-template, adapter handoff paths, source credential env-template proof, and
exchange/session metadata, capture-bundle session match proof, and
`live_fetch_contract`, the provider-profile contract/SHA, plus the
credential-safe `adapter_execution_contract` inherited from cutover so dispatch
planners can trace the live data source before packaging broker orders without
exposing credential values. Before invoking generic `review-route-enable`, the
wrapper reads the cutover manifest, requires its `adapter_receipt_proof` to
match the cutover config exactly, and re-hashes every required adapter receipt
and provider capture. Accepted receipt/capture files are fingerprinted in the
route-enable manifest; any drift leaves the nested generic `route_enable`
absent and routes repair back to
`review-provider-market-data-imbalance-cutover`. It also carries any nested
`synthetic_sidecar_proof` and flattened sidecar counts inherited from cutover.
If that provider profile, adapter contract, or required synthetic sidecar proof
is missing, unsafe, unready, or no longer matched to live evidence,
route-enable blocks broker-dispatch planning and routes the packet back to
`review-provider-market-data-imbalance-cutover`. Route-enable also preserves
the cutover-carried provider route-readiness broker round-trip synthetic
sidecar breach counter; stale nonzero breach packets are routed back to
`review-provider-market-data-imbalance-route-readiness`.
If cutover retained
broker-readiness validated round-trip capture
bundle/env-template/adapter handoff provenance, route-enable carries those
`dispatch_roundtrip_*` fields plus the validated round-trip source credential
env-template, round-trip exchange/session metadata, capture-bundle session
proof, live-fetch exchange/session identity, `live_fetch_contract` snapshot,
round-trip provider-profile proof, credential-safe round-trip
`adapter_execution_contract`, manifest inputs, and consistency flags forward
for broker-dispatch planning. If that final dry-run provider profile or adapter
proof is missing, unsafe, stale, or no longer matched to runtime-session
evidence, route-enable blocks broker-dispatch planning and routes the packet
back to
`review-provider-market-data-imbalance-cutover`. Route-enable also carries the
cutover-retained final round-trip `synthetic_sidecar_proof` plus flattened
`dispatch_roundtrip_synthetic_*` counters; if synthetic final dry-run folds are
present without ready rehearsal sidecars, broker-dispatch planning is blocked
and routed back to `review-provider-market-data-imbalance-cutover`. It also
carries `dispatch_roundtrip_route_readiness_*` sidecar breach proof from
cutover and routes nonzero final dry-run sidecar breaches back to
`review-provider-market-data-imbalance-route-readiness`. When a
cutover packet carries a provider-wrapper final receipt proof with required
adapter receipts, route-enable also requires exact
`dispatch_roundtrip_provenance` agreement with the cutover manifest and root
runtime receipt proof, re-hashes every final receipt and capture before generic
route authorization, and fingerprints accepted files as
`dispatch_roundtrip_adapter_receipts` and
`dispatch_roundtrip_provider_captures`. Proof or byte drift leaves nested
generic route-enable absent and routes repair to
`review-provider-market-data-imbalance-cutover`. No-provider-wrapper packets
and provider wrappers without required receipts remain supported and are marked
not applicable rather than blocked in the runbook.
When a
cutover CSV is sparse
but its config sidecar has
`dispatch_roundtrip_provenance`, route-enable hydrates missing or blank
`dispatch_roundtrip_*` fields, including the final round-trip sidecar counters,
from that config before falling back to the broker-readiness config sidecar,
while keeping explicit summary `False` and `0` values authoritative. The
wrapper runs `review-route-enable` under a nested
`route_enable` folder and writes provider checks/summary/action/config/runbook
artifacts. Fully clean wrappers emit a ready
`plan_provider_imbalance_broker_dispatch` action and point to
`plan-broker-dispatch`; blocked wrappers route back to the exact repair gate,
such as `review-route-readiness`, `pack-broker-upload`, or the provider cutover
wrapper.

Run the provider-specific broker-dispatch wrapper:

```powershell
python -m hft_cli plan-provider-market-data-imbalance-broker-dispatch `
  --provider-route-enable runs\provider_market_data_imbalance_route_enable\arrow_ws_nse_2026_06_23 `
  --out runs\provider_market_data_imbalance_broker_dispatch\arrow_ws_nse_2026_06_23 `
  --fail-on-blocked-actions `
  --fail-on-breach
```

The provider broker-dispatch wrapper reads the provider route-enable
summary/config, infers the nested generic `route_enable` plus broker upload-pack
inputs, preserves any route-enable-carried provider broker-dispatch round-trip
wrapper, nested generic `broker_dispatch_roundtrip` paths, vendor-market-data
batch readiness fields/config, upstream proof lineage, and inherited
`upstream_*_vendor_market_data_batch_*` readiness fields/config. It also
preserves the capture bundle, blank credential env-template, and adapter
handoff paths, source credential env-template proof, exchange/session metadata,
capture-bundle session match proof, and `live_fetch_contract` inherited from
route-enable. It also carries the credential-safe `adapter_execution_contract`
from route-enable plus the provider-profile contract/SHA so send preparation can
trace the live data adapter without exposing credential values. Before invoking
generic `plan-broker-dispatch`, the wrapper reads the route-enable manifest,
requires its `adapter_receipt_proof` to match route-enable config exactly, and
re-hashes every required adapter receipt and provider capture. Accepted files
are fingerprinted again in the broker-dispatch manifest; any drift leaves the
nested generic `broker_dispatch` absent and routes repair back to
`review-provider-market-data-imbalance-route-enable`. If that
provider profile or adapter contract is missing, unsafe, or no longer matched
to live evidence, broker-dispatch blocks send preparation and routes back to
`review-provider-market-data-imbalance-route-enable`. It also carries nested
`synthetic_sidecar_proof` plus flattened sidecar counts from route-enable and
blocks send preparation when synthetic provider folds are missing ready
rehearsal sidecar proof. It also carries the route-enable-carried
route-readiness provider broker round-trip synthetic sidecar breach counter; if
that inherited counter is nonzero, send preparation is blocked and routed back
to `review-provider-market-data-imbalance-route-readiness`. It also carries the
route-enable-retained final round-trip `dispatch_roundtrip_route_readiness_*`
sidecar breach proof; if the final dry-run route sidecar breach counter is
nonzero, send preparation is blocked and routed back to
`review-provider-market-data-imbalance-route-readiness`. It also carries the
route-enable-retained
validated dispatch round-trip source credential env-template,
round-trip exchange/session metadata, capture-bundle session proof, live-fetch
exchange/session identity, `live_fetch_contract`, final round-trip
provider-profile proof, credential-safe `adapter_execution_contract`, and
source-provenance consistency flags so broker dispatch reviewers can trace the
exact live data source before generating non-submitting dry-run orders. If the
route-enable-retained round-trip provider profile or adapter contract is
missing, unsafe, stale, or mismatched against runtime-session evidence,
broker-dispatch blocks send preparation and routes back to
`review-provider-market-data-imbalance-route-enable`. Broker-dispatch also
carries the route-enable-retained final round-trip `synthetic_sidecar_proof`
plus flattened `dispatch_roundtrip_synthetic_*` counters; if synthetic final
dry-run folds are present without ready rehearsal sidecars, send preparation is
blocked and routed back to `review-provider-market-data-imbalance-route-enable`.
When a route-enable packet carries a provider-wrapper final receipt proof with
required adapter receipts, broker-dispatch also requires exact
`dispatch_roundtrip_provenance` agreement with the route-enable manifest and
root runtime receipt proof, re-hashes every final receipt and capture before
generic dispatch planning, and fingerprints accepted files as
`dispatch_roundtrip_adapter_receipts` and
`dispatch_roundtrip_provider_captures`. Proof or byte drift leaves nested
generic `broker_dispatch` absent and routes repair to
`review-provider-market-data-imbalance-route-enable`. No-provider-wrapper
packets and provider wrappers without required receipts remain supported and
are marked not applicable rather than blocked in the runbook.
When a route-enable CSV is
sparse but its config sidecar has `dispatch_roundtrip_provenance`,
broker-dispatch hydrates missing or blank `dispatch_roundtrip_*` fields,
including the round-trip provider profile, adapter contract, and sidecar
counters, from that config while keeping explicit summary `False` and `0` values
authoritative. The
wrapper runs `plan-broker-dispatch` under a nested `broker_dispatch` folder,
and writes provider checks/summary/action/config/runbook artifacts. Fully clean
wrappers emit a ready `prepare_provider_imbalance_broker_dispatch_send` action
and point to `prepare-broker-dispatch-send`; blocked wrappers route back to the
provider route-enable repair gate, `pack-broker-upload`, or the generic dispatch
planner depending on the first failing proof.

Run the provider-specific broker-dispatch send wrapper:

```powershell
python -m hft_cli prepare-provider-market-data-imbalance-broker-dispatch-send `
  --provider-broker-dispatch runs\provider_market_data_imbalance_broker_dispatch\arrow_ws_nse_2026_06_23 `
  --out runs\provider_market_data_imbalance_broker_dispatch_send\arrow_ws_nse_2026_06_23 `
  --fail-on-blocked-actions `
  --fail-on-breach
```

The provider broker-dispatch-send wrapper reads the provider dispatch
summary/config, infers the nested generic `broker_dispatch` artifact, preserves
any provider/nested broker-dispatch round-trip paths, broker-dispatch
vendor-market-data batch readiness/config, upstream proof lineage, and inherited
`upstream_*_vendor_market_data_batch_*` readiness/config from the dispatch
wrapper. It also preserves the capture bundle, blank credential env-template,
adapter handoff paths, source credential env-template proof, exchange/session
metadata, capture-bundle session match proof, and `live_fetch_contract`
inherited from dispatch. It also carries the credential-safe
`adapter_execution_contract` from broker-dispatch plus the provider-profile
contract/SHA so ack reconciliation can trace the live data adapter without
exposing credential values. Before invoking generic
`prepare-broker-dispatch-send`, the wrapper reads the broker-dispatch manifest,
requires its `adapter_receipt_proof` to match broker-dispatch config exactly,
and re-hashes every required adapter receipt and provider capture. Accepted
files are fingerprinted again in the send-packet manifest; any drift leaves the
nested generic `broker_dispatch_send` absent and routes repair back to
`plan-provider-market-data-imbalance-broker-dispatch`. If that provider profile
or adapter contract is missing, unsafe, or no longer matched to live evidence,
broker-dispatch-send
blocks acknowledgement reconciliation and routes back to
`plan-provider-market-data-imbalance-broker-dispatch`. It also carries nested
`synthetic_sidecar_proof` plus flattened sidecar counts from broker-dispatch and
blocks acknowledgement reconciliation when synthetic provider folds are missing
ready rehearsal sidecar proof. It also carries the broker-dispatch-carried
route-readiness provider broker round-trip synthetic sidecar breach counter; if
that inherited counter is nonzero, acknowledgement reconciliation is blocked
and routed back to `review-provider-market-data-imbalance-route-readiness`. It
also carries the broker-dispatch-retained final round-trip
`dispatch_roundtrip_route_readiness_*` sidecar breach proof; if the final
dry-run route sidecar breach counter is nonzero, acknowledgement reconciliation
is blocked and routed back to
`review-provider-market-data-imbalance-route-readiness`. It
also carries the broker-dispatch-retained validated dispatch round-trip source credential
env-template, round-trip exchange/session metadata, capture-bundle session
proof, live-fetch exchange/session identity, `live_fetch_contract`, final
round-trip provider profile, round-trip `adapter_execution_contract`, and
source-provenance consistency flags, so operators can trace the exact live data
source beside the dry-run request envelopes. If the broker-dispatch-retained
round-trip provider profile or adapter contract is missing, unsafe, stale, or
mismatched against the runtime-session proof, broker-dispatch-send blocks
acknowledgement reconciliation and routes back to
`plan-provider-market-data-imbalance-broker-dispatch`. The same send-prep gate
also carries the broker-dispatch-retained final round-trip
`synthetic_sidecar_proof` plus flattened `dispatch_roundtrip_synthetic_*`
counters; if synthetic final dry-run folds are present without ready rehearsal
sidecars, acknowledgement reconciliation is blocked at that broker-dispatch
repair gate. When a broker-dispatch packet carries a provider-wrapper final
receipt proof with required adapter receipts, send preparation also requires
exact `dispatch_roundtrip_provenance` agreement with the broker-dispatch
manifest and root runtime receipt proof, re-hashes every final receipt and
capture before generating request envelopes, and fingerprints accepted files
as `dispatch_roundtrip_adapter_receipts` and
`dispatch_roundtrip_provider_captures`. Proof or byte drift leaves nested
generic `broker_dispatch_send` absent and routes repair to
`plan-provider-market-data-imbalance-broker-dispatch`. No-provider-wrapper
packets and provider wrappers without required receipts remain supported and
are marked not applicable rather than blocked in the runbook.
When a broker-dispatch CSV is sparse but its config sidecar has
`dispatch_roundtrip_provenance`,
broker-dispatch-send hydrates missing or blank `dispatch_roundtrip_*` fields,
including the round-trip provider profile, adapter contract, and sidecar
counters, from that config while keeping explicit summary `False` and `0` values
authoritative.
The wrapper runs
`prepare-broker-dispatch-send` under a nested `broker_dispatch_send` folder,
and writes provider checks, summary, action, config, and runbook artifacts. It
still does not submit orders: the nested packet writes request envelopes and
expected ack templates with
`submission_enabled=false`.
Fully clean wrappers emit a ready
`capture_provider_imbalance_broker_acknowledgements` action and point to
`reconcile-broker-dispatch` for the later dry-run acknowledgement file.

Run the provider-specific acknowledgement reconciliation wrapper once a dry-run
ack CSV is available:

```powershell
python -m hft_cli reconcile-provider-market-data-imbalance-broker-dispatch `
  --provider-broker-dispatch-send runs\provider_market_data_imbalance_broker_dispatch_send\arrow_ws_nse_2026_06_23 `
  --acks logs\arrow_ws_nse_dry_run_acks.csv `
  --out runs\provider_market_data_imbalance_broker_dispatch_ack\arrow_ws_nse_2026_06_23 `
  --fail-on-blocked-actions `
  --fail-on-breach
```

The provider acknowledgement wrapper reads the provider send-packet
summary/config, requires an explicit broker/dry-run ack CSV, infers the nested
generic `broker_dispatch` plan, preserves any provider/nested broker-dispatch
round-trip paths, broker-dispatch vendor-market-data batch readiness/config,
upstream proof lineage, and inherited
`upstream_*_vendor_market_data_batch_*` readiness/config from the send packet.
It also preserves the capture bundle, blank credential env-template, and
adapter handoff paths, source credential env-template proof, exchange/session
metadata, capture-bundle session match proof, and `live_fetch_contract`
inherited from the send packet. It also carries the credential-safe
`adapter_execution_contract` from the send packet plus the provider-profile
contract/SHA so round-trip review can trace the live data adapter without
exposing credential values. Before invoking generic `reconcile-broker-dispatch`,
the wrapper reads the send-packet manifest, requires its
`adapter_receipt_proof` to match send-packet config exactly, and re-hashes every
required adapter receipt and provider capture. Accepted files are fingerprinted
again in the acknowledgement manifest; any drift leaves the nested generic
`broker_dispatch_ack` absent and routes repair back to
`prepare-provider-market-data-imbalance-broker-dispatch-send`. If that provider
profile or adapter contract is missing, unsafe, or no longer matched to live
evidence, acknowledgement
reconciliation blocks round-trip review and routes back to
`prepare-provider-market-data-imbalance-broker-dispatch-send`. It also carries
nested `synthetic_sidecar_proof` plus flattened sidecar counts from the send
packet. If the required synthetic sidecar proof is missing or unready,
acknowledgement reconciliation blocks round-trip review and routes back to
`prepare-provider-market-data-imbalance-broker-dispatch-send`. It also carries
the send-carried route-readiness provider broker round-trip synthetic sidecar
breach counter; if that inherited counter is nonzero, round-trip review is
blocked and routed back to
`review-provider-market-data-imbalance-route-readiness`. It also carries the
send-retained validated dispatch round-trip source credential env-template,
round-trip exchange/session metadata, capture-bundle session proof, live-fetch
exchange/session identity, `live_fetch_contract`, final round-trip provider
profile, round-trip `adapter_execution_contract`, and source-provenance
consistency flags beside the acknowledgement proof. If the send-retained
round-trip provider profile or adapter contract is missing, unsafe, stale, or
mismatched against the runtime-session proof, acknowledgement reconciliation
blocks round-trip review and routes back to
`prepare-provider-market-data-imbalance-broker-dispatch-send`. The same
acknowledgement gate also carries the send-retained final round-trip
`synthetic_sidecar_proof` plus flattened `dispatch_roundtrip_synthetic_*`
counters; if synthetic final dry-run folds are present without ready rehearsal
sidecars, round-trip review is blocked at that send-packet repair gate. It also
carries the send-retained final `dispatch_roundtrip_route_readiness_*`
sidecar breach proof; if nonzero final dry-run route sidecar breaches remain,
acknowledgement reconciliation routes directly back to
`review-provider-market-data-imbalance-route-readiness`. When a send packet
carries a provider-wrapper final receipt proof with required adapter receipts,
acknowledgement reconciliation also requires exact
`dispatch_roundtrip_provenance` agreement with the send manifest and root
runtime receipt proof, re-hashes every final receipt and capture before
accepting broker acknowledgements, and fingerprints accepted files as
`dispatch_roundtrip_adapter_receipts` and
`dispatch_roundtrip_provider_captures`. Proof or byte drift leaves nested
generic `broker_dispatch_ack` absent and routes repair to
`prepare-provider-market-data-imbalance-broker-dispatch-send`.
No-provider-wrapper packets and provider wrappers without required receipts
remain supported and are marked not applicable rather than blocked in the
runbook. When a send-packet CSV is sparse but its config sidecar has
`dispatch_roundtrip_provenance`, acknowledgement hydrates missing or blank
`dispatch_roundtrip_*` fields, including the round-trip provider profile and
adapter contract and sidecar counters, from that config while keeping explicit
summary `False` and `0` values authoritative. The
wrapper runs `reconcile-broker-dispatch` under a nested
`broker_dispatch_ack` folder, and writes provider checks, summary, action,
config, and runbook artifacts. Clean
acknowledgement proof emits a ready
`review_provider_imbalance_broker_dispatch_roundtrip` action and points to
`review-provider-market-data-imbalance-broker-dispatch-roundtrip`; missing ack
files, unready send packets, and rejected/duplicate/unmatched acknowledgements
fail closed before round-trip proof is trusted.
Provider acknowledgement reconciliation resolves the wrapper's nested generic
`broker_dispatch_send` bundle and activates the complete generic send-lineage
gate by default. The explicit `--require-send-packet` option remains accepted
for readable scripts. The exact request/envelope/template/dispatch proof is
then carried into the nested acknowledgement manifest; missing, stale,
relabeled, authorizing, or source-detached packets block the provider wrapper
before final review. `--allow-legacy-send-lineage` is limited to historical
acknowledgement inputs already classified by the lineage migration audit and
must be paired with `--lineage-migration-audit <audit_dir>`. The CLI verifies
that the sealed audit has 100% coverage, zero blockers, and a
`covered_by_strict` acknowledgement row for the exact provider-send source
before creating output. The generated acknowledgement adds a
`lineage_migration_audit_ready` check; exposes audit identity, manifest hash,
policy/coverage status, exact source status, and strict replacement identity in
its summary and runbook; and retains the same evidence in config and manifest
metadata. The catalog automatically exposes those summary fields. The manifest
also fingerprints the audit, its manifest, and its transitive dependencies.
Supplying an audit on the strict path is rejected; new reconciliations should
retain the strict default.

Review the provider-specific dispatch/send/ack round-trip proof:

```powershell
python -m hft_cli review-provider-market-data-imbalance-broker-dispatch-roundtrip `
  --provider-broker-dispatch-ack runs\provider_market_data_imbalance_broker_dispatch_ack\arrow_ws_nse_2026_06_23 `
  --out runs\provider_market_data_imbalance_broker_dispatch_roundtrip\arrow_ws_nse_2026_06_23 `
  --require-ack-lineage `
  --fail-on-blocked-actions `
  --fail-on-breach
```

The provider round-trip wrapper reads the provider acknowledgement
summary/config, infers the nested generic `broker_dispatch`,
`broker_dispatch_send`, and `broker_dispatch_ack` folders, runs
`review-broker-dispatch-roundtrip` under a nested `broker_dispatch_roundtrip`
folder, preserves any acknowledgement-carried upstream provider/nested
round-trip proof as `upstream_*_roundtrip` lineage, preserves inherited
vendor-market-data batch evidence under `upstream_*_vendor_market_data_batch_*`
fields, carries the acknowledgement-inherited capture bundle, blank credential
env-template, adapter handoff paths, source credential env-template proof,
exchange/session metadata, capture-bundle session match proof, and
`live_fetch_contract`, plus the credential-safe `adapter_execution_contract`
from acknowledgement reconciliation plus the provider-profile contract/SHA, so
broker-readiness feed can trace the live data adapter without exposing
credential values. Before invoking the generic round-trip review, the wrapper
reads the provider acknowledgement manifest and requires its
`adapter_receipt_proof` to match the acknowledgement config exactly. It then
re-hashes every required adapter receipt and provider capture and fingerprints
the accepted files in the provider round-trip manifest. Manifest-proof drift or
changed receipt/capture bytes leave the nested generic
`broker_dispatch_roundtrip` artifact absent and route repair back to
`reconcile-provider-market-data-imbalance-broker-dispatch`. If that provider
profile or adapter contract is missing,
unsafe, or no longer matched to live evidence, round-trip review blocks
broker-readiness feed and routes back to
`reconcile-provider-market-data-imbalance-broker-dispatch`. It also carries
nested `synthetic_sidecar_proof` plus flattened sidecar counts from
acknowledgement reconciliation. If the required synthetic sidecar proof is
missing or unready, round-trip review blocks broker-readiness feed and routes
back to `reconcile-provider-market-data-imbalance-broker-dispatch`. It also
carries the acknowledgement-carried route-readiness provider broker round-trip
synthetic sidecar breach counter; if that inherited counter is nonzero,
broker-readiness feed is blocked and routed back to
`review-provider-market-data-imbalance-route-readiness`. It also carries the
ack-retained validated dispatch round-trip
source credential env-template, round-trip exchange/session metadata,
capture-bundle session proof, live-fetch exchange/session identity,
`live_fetch_contract`, final round-trip `adapter_execution_contract`, and
source-provenance consistency flags, into summary/config/runbook artifacts plus
manifest inputs/extra metadata. If the ack-retained round-trip adapter contract
is missing, unsafe, stale, or mismatched against the runtime-session contract,
round-trip review blocks broker-readiness feed and routes back to
`reconcile-provider-market-data-imbalance-broker-dispatch`; the runbook also
prints the ack-retained round-trip exchange/session and live-fetch availability
before writing provider checks/action artifacts.
The same round-trip review gate also carries the ack-retained final round-trip
`synthetic_sidecar_proof` plus flattened `dispatch_roundtrip_synthetic_*`
counters; if synthetic final dry-run folds are present without ready rehearsal
sidecars, broker-readiness feed is blocked at the acknowledgement repair gate.
It also carries the ack-retained final `dispatch_roundtrip_route_readiness_*`
sidecar breach proof; if nonzero final dry-run route sidecar breaches remain,
broker-readiness feed routes directly back to
`review-provider-market-data-imbalance-route-readiness`.
When an acknowledgement packet carries a provider-wrapper final receipt proof
with required adapter receipts, round-trip review also requires exact
`dispatch_roundtrip_provenance` agreement with the acknowledgement manifest and
root runtime receipt proof, re-hashes every final receipt and capture before
creating the fresh round-trip artifact, and fingerprints accepted files as
`dispatch_roundtrip_adapter_receipts` and
`dispatch_roundtrip_provider_captures`. Proof or byte drift leaves nested
generic `broker_dispatch_roundtrip` absent and routes repair to
`reconcile-provider-market-data-imbalance-broker-dispatch`.
No-provider-wrapper packets and provider wrappers without required receipts
remain supported and are marked not applicable rather than blocked in the
runbook.
When an acknowledgement CSV is sparse but its config sidecar has
`dispatch_roundtrip_provenance`, the provider round-trip wrapper hydrates
missing or blank `dispatch_roundtrip_*` fields, including the round-trip
adapter contract and sidecar counters, from that config while keeping explicit
summary `False` and `0` values authoritative.
When the nested generic round-trip carries broker vendor-market-data batch
evidence, the provider wrapper also exposes that fresh proof in its own
summary/config under both
`roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_*` and
`broker_dispatch_roundtrip_vendor_market_data_batch_*` fields. Clean proof emits
a ready `feed_provider_imbalance_broker_dispatch_roundtrip_into_broker_readiness`
action and points to `review-provider-market-data-imbalance-broker-readiness`
so either the provider wrapper root or its nested `broker_dispatch_roundtrip`
folder can be supplied through `--dispatch-roundtrip` before any provider
cutover promotion.
Provider final round-trip review now activates the acknowledgement-lineage gate
by default against the exact nested dispatch/send/ack directories inferred from
provider acknowledgement output. The explicit `--require-ack-lineage` flag
remains accepted for readable scripts. The provider summary carries the full
`broker_dispatch_ack_*` record, the config and manifest bind it under
`broker_dispatch_ack_lineage`, and the runbook reports whether the source is
current. Post-ack artifact drift or a different send source blocks provider
broker-readiness feed and routes back to provider acknowledgement reconciliation.
`--allow-legacy-ack-lineage` is limited to historical acknowledgement bundles
already classified by the lineage migration audit and must be paired with
`--lineage-migration-audit <audit_dir>`. The audit must cover that exact
provider acknowledgement with a current policy-equivalent strict sibling. The
generated round-trip checks, summary, runbook, config, manifest metadata, and
catalog row expose the accepted audit and exact source coverage; the manifest
also retains its sealed dependency graph. Supplying an audit without the legacy
override is rejected; new reviews should retain the strict default.

Issue a compact, content-addressed integrity certificate for the completed
rehearsal:

```powershell
python -m hft_cli certify-provider-market-data-imbalance-broker-rehearsal `
  --provider-broker-dispatch-roundtrip runs\provider_market_data_imbalance_broker_dispatch_roundtrip\arrow_ws_nse_2026_06_23 `
  --out runs\provider_market_data_imbalance_broker_rehearsal_certificate\arrow_ws_nse_2026_06_23 `
  --require-sealed-provider-receipts `
  --require-ack-lineage `
  --fail-on-blocked-actions `
  --fail-on-breach
```

Certification re-reads the final provider summary/config/checks, enforces the
nested dispatch/send/ack invariants with strict zero-anomaly thresholds, and
rejects enabled submission even when an upstream round-trip was intentionally
run with a relaxed threshold. It recursively walks reachable manifests,
re-hashes every recorded artifact and input directory/file fingerprint, checks
recorded git provenance, and emits a deterministic rehearsal cycle id plus a
certificate SHA-256. `--require-sealed-provider-receipts` raises the assurance
level from generic broker dry-run proof to sealed provider receipt proof and
blocks providers that have not yet produced receipt/capture evidence. Use
`--allow-recorded-dirty-git` only for development fixtures; operator sign-off
should retain the default clean-provenance requirement.
Rehearsal certification requires acknowledgement lineage by default. The
explicit `--require-ack-lineage` shown above remains accepted for readable and
forward-compatible scripts. The gate requires the provider summary, nested
generic round-trip summary, provider config, provider manifest, and nested
manifest to carry the same complete current acknowledgement-lineage record.
That record is content-addressed inside the certificate payload and output
manifest, so acknowledgement relabeling or drift requires certificate reissue.
`--allow-legacy-ack-lineage` is the deliberate compatibility escape hatch for
an archived rehearsal already assessed by the lineage migration audit. It
requires `--lineage-migration-audit <audit_dir>`, and the audit must cover the
exact provider round-trip source before certificate generation. The certificate
checks, summary, runbook, payload, manifest metadata, and catalog row expose
the accepted audit and exact source coverage. The certificate SHA-256
content-addresses that payload, while its manifest fingerprints the audit and
all sealed dependencies. It must not be used for new broker rehearsals or
production-readiness certification.

Outputs:

```text
provider_market_data_imbalance_broker_rehearsal_certificate.json
provider_market_data_imbalance_broker_rehearsal_certificate_summary.csv
provider_market_data_imbalance_broker_rehearsal_certificate_checks.csv
provider_market_data_imbalance_broker_rehearsal_certificate_fingerprints.csv
provider_market_data_imbalance_broker_rehearsal_certificate_manifest_graph.csv
provider_market_data_imbalance_broker_rehearsal_certificate_action_queue.csv
provider_market_data_imbalance_broker_rehearsal_certificate_runbook.md
manifest.json
```

The certificate is deliberately non-authorizing: both JSON and manifest set
`authorizes_submission=false` and `digitally_signed=false`. The SHA-256 binds
the recorded content but is not a broker, compliance, or cryptographic signer
approval. It proves an offline rehearsal and cannot enable, approve, or submit
a broker order. Any source, acknowledgement, receipt, manifest, or artifact
change requires a new certificate.

Before using a legacy lineage override under the strict CLI defaults, audit all
retained provider acknowledgement, final round-trip, and rehearsal-certificate
bundles:

```powershell
python -m hft_cli audit-provider-market-data-imbalance-broker-lineage-migration `
  --roots runs\provider_market_data_imbalance_broker_dispatch_ack `
          runs\provider_market_data_imbalance_broker_dispatch_roundtrip `
          runs\provider_market_data_imbalance_broker_rehearsal_certificate `
  --out runs\provider_broker_lineage_migration_audit\2026_07_12 `
  --max-blocked-bundles 0 `
  --min-strict-ready-coverage 1.0 `
  --fail-on-blocked-actions `
  --fail-on-breach
```

The read-only audit recursively verifies each bundle and its manifested input
chain, then classifies it as `strict_ready`, `covered_by_strict`,
`regenerate_strict`, or `blocked`. A legacy bundle is only
`covered_by_strict` when its exact `_strict` sibling is current and passed, its
non-lineage policy fingerprint is unchanged, its normalized source-evidence
identity matches, and the upstream legacy dependency is itself strict or
covered. A similarly named but policy-mismatched replacement does not count.
Regeneration commands preserve the archived policy thresholds, target new
sibling directories without overwriting existing proof, and are ordered
acknowledgement -> round-trip -> certificate so downstream commands consume the
newly strict dependency. The audit output itself is excluded when it lives below
a scanned archive root, but it cannot be written inside an audited bundle.
`--no-recursive` limits discovery to manifests supplied directly through
`--roots`.

Schema version 2 audit manifests separately fingerprint every audited bundle,
each audited root manifest, and every recursively discovered source dependency.
Changing a provider-send proof, acknowledgement file, nested manifest, or other
upstream input after audit generation therefore invalidates the audit itself.
The shared `verify_provider_broker_lineage_migration_audit` Python contract is
the fail-closed gate used by all three legacy CLI overrides. It requires 100%
strict-ready coverage, zero blocked bundles/actions, all audit checks passing, consistent
summary/config/manifest counts, non-authorizing claims, and exactly one
`covered_by_strict` inventory row for the supplied `provider_send`,
`provider_ack`, or `provider_roundtrip` source. A current but unrelated audit,
a relaxed-threshold audit, or post-audit source drift does not qualify.

Outputs:

```text
provider_broker_lineage_migration_inventory.csv
provider_broker_lineage_migration_checks.csv
provider_broker_lineage_migration_summary.csv
provider_broker_lineage_migration_action_queue.csv
provider_broker_lineage_migration_config.json
provider_broker_lineage_migration_runbook.md
manifest.json
```

Every migration artifact sets `authorizes_submission=false`; the generated
commands only rebuild offline proof bundles and cannot enable broker routing.

After legacy overrides have produced retained acknowledgement, round-trip, or
certificate proofs, review the accepted audit usage as an independent aggregate
policy gate:

```powershell
python -m hft_cli review-provider-market-data-imbalance-broker-lineage-audit-usage `
  --roots runs\provider_market_data_imbalance_broker_dispatch_ack `
          runs\provider_market_data_imbalance_broker_dispatch_roundtrip `
          runs\provider_market_data_imbalance_broker_rehearsal_certificate `
  --out runs\provider_broker_lineage_audit_usage\2026_07_12 `
  --max-unaudited-legacy-bundles 0 `
  --max-drifted-audit-bundles 0 `
  --max-strict-with-audit-bundles 0 `
  --fail-on-blocked-actions `
  --fail-on-breach
```

The review distinguishes `strict_ready`, `audited_legacy_ready`,
`unaudited_legacy`, `audited_legacy_drifted`, `proof_manifest_drifted`, and
`strict_with_audit`. For every accepted legacy proof it requires the summary,
config or certificate payload, and manifest metadata to contain identical audit
evidence, then reruns the exact-source migration-audit verifier against the
current audit, source, and strict replacement. An operationally blocked proof
can still have current lineage evidence; this report deliberately evaluates the
lineage retention policy rather than replacing the proof's own readiness gate.
The defaults permit no unaudited legacy proof, no drift, and no migration audit
attached to an already-strict proof. `--no-recursive` limits discovery to roots
that directly contain a target manifest.

Every non-ready proof also receives a provider-specific refresh assessment. If
the recorded proof artifacts are byte-current, the action queue emits a strict
CLI regeneration command with the original policy thresholds and target mode,
omits the legacy audit option, and selects a new `_strict`,
`_strict_rebuilt`, or numbered sibling without creating or overwriting it.
Actions are ordered acknowledgement -> round-trip -> certificate, and
downstream commands predict the fresh strict dependency path selected by the
earlier action. Input-only drift can therefore be repaired from intact recorded
policy. Missing or changed proof artifacts, unreadable policy, missing source
paths, unsealed summary/config files, missing input fingerprints, unsupported
run types, and absent or authorizing non-submission metadata remain `blocked`
and do not receive a command. `--fail-on-breach` enforces the lineage policy;
`--fail-on-blocked-actions` separately enforces refresh-plan executability.

Outputs:

```text
provider_broker_lineage_audit_usage_inventory.csv
provider_broker_lineage_audit_usage_checks.csv
provider_broker_lineage_audit_usage_summary.csv
provider_broker_lineage_audit_usage_action_queue.csv
provider_broker_lineage_audit_usage_config.json
provider_broker_lineage_audit_usage_runbook.md
manifest.json
```

The aggregate manifest fingerprints every reviewed bundle, proof manifest, and
recursively manifested dependency. Later provider-source, accepted-audit, or
strict-replacement drift invalidates the review artifact. The report and all of
its actions remain non-authorizing.

After executing the ready strict-refresh commands, prove that their generated
siblings close the sealed audit-usage plan:

```powershell
python -m hft_cli verify-provider-market-data-imbalance-broker-lineage-refresh `
  --audit-usage runs\provider_broker_lineage_audit_usage\2026_07_13 `
  --out runs\provider_broker_lineage_refresh_convergence\2026_07_13 `
  --fail-on-blocked-actions `
  --fail-on-actions `
  --fail-on-breach
```

The convergence gate first verifies the complete audit-usage review and rejects
cross-artifact disagreement, drift, or any authorizing claim before trusting a
recorded command. For each planned action, the generated output must occupy the
exact sealed sibling path; have a current, passed, non-authorizing manifest;
require current strict acknowledgement lineage; omit migration-audit evidence;
preserve the original non-lineage policy and normalized source identity; consume
the source path named by the command; include the correct strict flag; and omit
all legacy override options. Zero unresolved actions is fixed policy and cannot
be relaxed.

A missing output remains a ready action carrying the original sealed command.
An occupied but invalid output is blocked with no command because refresh proof
is never overwritten; rerun the audit-usage review to allocate the next fresh
`_strict_rebuilt*` sibling. If the source review is stale or inconsistent, all
recorded commands are suppressed. A source review with no refresh actions is a
valid no-op convergence.

Outputs:

```text
provider_broker_lineage_refresh_convergence_inventory.csv
provider_broker_lineage_refresh_convergence_checks.csv
provider_broker_lineage_refresh_convergence_summary.csv
provider_broker_lineage_refresh_convergence_action_queue.csv
provider_broker_lineage_refresh_convergence_config.json
provider_broker_lineage_refresh_convergence_runbook.md
manifest.json
```

The convergence manifest seals the audit-usage review, every existing refreshed
bundle and manifest, and all recursive dependencies. Any later refreshed-proof
or source-review drift invalidates the convergence artifact. It remains
non-authorizing and cannot enable or submit broker orders.

Once convergence passes, publish the active selection and retirement contract:

```powershell
python -m hft_cli index-provider-market-data-imbalance-broker-active-lineage `
  --convergence runs\provider_broker_lineage_refresh_convergence\2026_07_13 `
  --out runs\provider_broker_active_lineage\2026_07_13 `
  --fail-on-blocked-actions `
  --fail-on-actions `
  --fail-on-breach
```

The index independently revalidates every convergence pair. Each pair must
still contain a current, passed, non-authorizing original and a current,
passed, strict, audit-free, non-authorizing sibling with identical non-lineage
policy and normalized source-evidence identity. Exactly one `active_strict`
entry is marked `selectable`; exactly one `legacy_original` entry is marked
`retained_only`. Retirement is logical and non-destructive: the legacy bundle
stays available for audit and reproducibility but the verified resolver and
index-aware catalog never treat it as a selectable proof.

The resolver requires an original path when more than one archive has a
selectable bundle of the same type, preventing path-order or newest-directory
heuristics from silently choosing a different lineage family. An unready,
stale, edited, ambiguous, or inconsistent index is rejected. A successful
strict no-op convergence produces a valid empty index.

Outputs:

```text
provider_broker_active_lineage_index.csv
provider_broker_active_lineage_checks.csv
provider_broker_active_lineage_summary.csv
provider_broker_active_lineage_action_queue.csv
provider_broker_active_lineage_config.json
provider_broker_active_lineage_runbook.md
manifest.json
```

The manifest seals the convergence proof, both members of every lineage pair,
their manifests, and recursive dependencies. Any later source or sibling drift
invalidates both direct resolution and index-aware catalog construction. The
index explicitly sets `authorizes_submission=false`.

Use the verified index when building a provider-proof candidate catalog:

```powershell
python -m hft_cli catalog-runs `
  --roots runs\provider_broker_archive `
  --provider-broker-active-lineage-index `
    runs\provider_broker_active_lineage\2026_07_13 `
  --out runs\catalog\provider_broker_active `
  --fail-on-provider-lineage-selection-blocks
```

After a credentialed provider client writes a normalized CSV, review that capture
against the packet before feeding it into the market-data pipeline:

```powershell
python -m hft_cli review-provider-market-data-capture `
  --client-packet runs\provider_market_data_clients\arrow_ws_nse\provider_market_data_client_packet.json `
  --capture captures\arrow_ws_nse_day1.csv `
  --out runs\provider_market_data_capture\arrow_ws_nse_day1 `
  --min-rows 100000 `
  --expected-market india_nse_index_derivatives `
  --expected-kind ticks `
  --pipeline-output-dir runs\provider_market_data_pipeline\arrow_ws_nse_day1 `
  --fail-on-blocked-actions `
  --fail-on-breach
```

The review validates the packet, normalized required columns, parseable and
monotonic timestamps, row threshold, market/kind identity, capture fingerprint,
and null counts. A ready review emits the exact `pipeline-vendor-market-data`
handoff using `--adapter normalized`.

To run that capture review and the normalized market-data pipeline as one root
artifact, use:

```powershell
python -m hft_cli pipeline-provider-market-data `
  --client-packet runs\provider_market_data_clients\arrow_ws_nse\provider_market_data_client_packet.json `
  --capture captures\arrow_ws_nse_day1.csv `
  --out runs\provider_market_data_roots\arrow_ws_nse_day1 `
  --min-capture-rows 100000 `
  --pipeline-min-rows 100000 `
  --tick-size 0.05 `
  --max-p99-gap-ns 1000000000 `
  --max-median-spread-ticks 2 `
  --fail-on-blocked-actions `
  --fail-on-breach
```

This writes `provider_market_data_pipeline_summary.csv`,
`provider_market_data_pipeline_components.csv`,
`provider_market_data_pipeline_action_queue.csv`,
`provider_market_data_pipeline_config.json`, a runbook, and a root manifest.
The root folder nests `01_capture_review` and
`02_vendor_market_data_pipeline`; when both are ready, the next gate is
`review-data-readiness` using the nested
`04_data_readiness\data_readiness_summary.csv`.

For multiple live capture sessions, run the provider batch root:

```powershell
python -m hft_cli pipeline-provider-market-data-batch `
  --client-packet runs\provider_market_data_clients\arrow_ws_nse\provider_market_data_client_packet.json `
  --capture captures\arrow_ws_nse_open_2026_06_23.csv captures\arrow_ws_nse_close_2026_06_23.csv `
  --label open_window `
  --label close_window `
  --out runs\provider_market_data_batches\arrow_ws_nse_2026_06_23 `
  --min-capture-rows 100000 `
  --pipeline-min-rows 100000 `
  --tick-size 0.05 `
  --max-p99-gap-ns 1000000000 `
  --max-median-spread-ticks 2 `
  --min-datasets 2 `
  --min-ready-datasets 2 `
  --min-unique-source-files 2 `
  --fail-on-blocked-actions `
  --fail-on-breach
```

This runs one `pipeline-provider-market-data` root per capture under
`captures\<label>`, compares the nested `04_data_readiness` outputs, rejects
reused capture files by source fingerprint, and writes
`provider_market_data_batch_summary.csv`,
`provider_market_data_batch_datasets.csv`,
`provider_market_data_batch_action_queue.csv`,
`provider_market_data_batch_config.json`, a runbook, and a root manifest.

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

For an exact source that already has a verified approved mapping review, use
the review-bound path instead of `--mapping`:

```powershell
python -m hft_cli pipeline-vendor-market-data `
  --input vendor\arrow_ticks_2026_06_10.csv `
  --mapping-review mappings\arrow_ticks_review `
  --out runs\vendor_data\arrow_ticks_2026_06_10_reviewed `
  --adapter arrow_money `
  --kind ticks `
  --timestamp-unit datetime `
  --tick-size 0.05 `
  --min-rows 100000 `
  --fail-on-blocked-actions `
  --fail-on-breach
```

For a different file covered by an approved exact-header scope, first create its
verified target mapping application with `apply-vendor-mapping-scope`, then run
the target-bound path:

```powershell
python -m hft_cli pipeline-vendor-market-data `
  --input vendor\arrow_ticks_2026_06_11.csv `
  --mapping-application mappings\arrow_ticks_2026_06_11_application `
  --out runs\vendor_data\arrow_ticks_2026_06_11_applied `
  --adapter arrow_money `
  --kind ticks `
  --timestamp-unit datetime `
  --tick-size 0.05 `
  --min-rows 100000 `
  --fail-on-blocked-actions `
  --fail-on-breach
```

`--mapping`, `--mapping-review`, and `--mapping-application` are mutually
exclusive. Review mode verifies approval before creating pipeline output,
requires `--input` to be the exact source retained by the review, derives the
canonical mapping from that review, and forces review-bound data readiness.
Application mode reconstructs the verified scope-review, target-intake, exact
target-source, and applied-mapping graph before creating output. It derives all
normalization inputs from that application and forces the stricter
target-application readiness contract. The root summary, config, and manifest
retain the relevant review or application IDs, fingerprints, and evidence
paths.

An exact-source review cannot be reused for another file, and an application
cannot be reused for another target. In target-application batch mode, every
input must carry its own distinct application as described below.

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
hash, mapping hash, mapping source, mapping-review or target-application
lineage, and component manifest paths. The root manifest fingerprints the
intake, mapped-data, and data-readiness manifests and, in application mode, the
application, scope-review, target-intake, exact source, and applied mapping.
Reruns can therefore prove whether a changed Arrow.money/iRage file, header,
mapping, or approval graph is the reason readiness changed.
`vendor_market_data_pipeline_config.json` is the machine-readable handoff for
strategy research or future vendor adapters.
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

To batch files covered by approved exact-header scopes, repeat
`--mapping-application` once per input in the same order:

```powershell
python -m hft_cli pipeline-vendor-market-data-batch `
  --input vendor\arrow_ticks_2026_06_10.csv vendor\arrow_ticks_2026_06_11.csv `
  --mapping-application mappings\arrow_ticks_2026_06_10_application `
  --mapping-application mappings\arrow_ticks_2026_06_11_application `
  --label day1 `
  --label day2 `
  --out runs\vendor_data\arrow_ticks_applied_batch `
  --adapter arrow_money `
  --kind ticks `
  --timestamp-unit datetime `
  --tick-size 0.05 `
  --min-datasets 2 `
  --min-ready-rate 1 `
  --fail-on-blocked-actions `
  --fail-on-breach
```

`--mapping` and batch `--mapping-application` are mutually exclusive. The
application count must exactly match the input count; applications must be
distinct and bound to their corresponding exact sources. The batch validates
every application, source, adapter/kind identity, sanitized dataset label, and
root evidence/output path before creating the output directory. A swapped,
missing, duplicate, stale, or colliding application therefore cannot leave a
partially authorized batch root.

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
`unique_header_fingerprints`, `mapping_sources`, `mapping_application_count`,
`unique_mapping_applications`, and `target_application_coverage`. The batch
manifest fingerprints each dataset pipeline manifest plus the comparison
manifest. In application mode it also fingerprints every application,
application manifest/receipt, scope review, target intake, exact source, and
applied mapping, then re-verifies every application graph before sealing the
root manifest.
`vendor_market_data_batch_config.json` keeps the accepted dataset list,
comparison thresholds, per-dataset fingerprints, and application lineage
together for walk-forward research handoff. The batch action queue promotes
per-dataset pipeline blockers and comparison blockers to the batch root,
including the exact
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

For files covered by approved exact-header scopes, the combined broker handoff
accepts the same ordered per-dataset applications as the batch command:

```powershell
python -m hft_cli pipeline-broker-vendor-readiness `
  --input vendor\arrow_ticks_2026_06_10.csv vendor\arrow_ticks_2026_06_11.csv `
  --mapping-application mappings\arrow_ticks_2026_06_10_application `
  --mapping-application mappings\arrow_ticks_2026_06_11_application `
  --label day1 `
  --label day2 `
  --out runs\broker_vendor_data\arrow_target_bound `
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

Combined `--mapping` and repeated `--mapping-application` inputs are mutually
exclusive. Application arguments must align one for one with the input order.
The wrapper does not create its root until the nested batch has verified every
application, exact target source, adapter/kind binding, distinct application,
sanitized label, and evidence/output path. Count mismatches, swapped targets,
duplicates, stale evidence, and path collisions therefore fail before either
the vendor batch or broker proof root is created.

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
ready. In application mode, the batch, broker-readiness, and wrapper
summary/config artifacts all preserve `mapping_source_mode`,
`mapping_application_count`, `unique_mapping_applications`, and
`target_application_coverage`; broker readiness additionally requires one
complete application-lineage record per dataset. When final round-trip target
proof is available, the wrapper also exposes its cross-stage consistency flag,
the current/final lineage match decision, and both lineage SHA-256 digests in
the root summary/config/checks/runbook. A fresh current batch cannot replace the
final broker proof or pass when it refers to different target applications.
The wrapper manifest directly
fingerprints every application directory, application manifest and receipt,
plus the nested batch manifest/config, while the nested batch manifest retains
the scope-review, target-intake, exact-source, and applied-mapping graph.
The wrapper summary/config/runbook also surfaces `adapter_schema_status`,
`schema_review_required`, `schema_reviewed`, `schema_review_mode`,
`placeholder_schema_active`, `placeholder_schema_allowed`, and
`placeholder_schema_warning`, so dry-run placeholder schema overrides remain
visible in catalogs until real Arrow.money/iRage mappings are reviewed.
The wrapper summary/config also carries broker-readiness route-control proof as
`broker_readiness_route_readiness_*` and
`broker_readiness_route_broker_route_readiness_*` summary fields plus nested
`broker_readiness.dispatch_roundtrip.route_readiness` and
`broker_readiness.dispatch_roundtrip.route_broker_route_readiness` JSON blocks,
so launch schedulers can prove direct launch-control evidence and
allocation/concentration-safe broker route runs without opening nested broker
readiness artifacts.
When broker readiness consumed post-halt resume evidence, the wrapper also
preserves `broker_readiness_resume_broker_route_readiness_*` and
`broker_readiness_resume_incident_broker_route_readiness_*` summary fields plus
nested `broker_readiness.resume_gate.broker_route_readiness` and
`broker_readiness.resume_gate.incident_broker_route_readiness` JSON blocks, so
the data-proof root retains the route controls that authorized resume after a
halt.
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
  --mapped-data runs\data\arrow_ticks_reviewed `
  --tick-diagnostics runs\diagnostics\futures `
  --chain-diagnostics runs\diagnostics\chain `
  --market-profile runs\market_profiles\india_us `
  --market-portability runs\market_profiles\portability `
  --instrument-metadata runs\risk\leadlag_shadow_instruments `
  --out runs\data_readiness\india_nse_2026_06_10 `
  --require-vendor-intake `
  --require-schema-audit `
  --require-mapped-data `
  --require-reviewed-mapping-normalization `
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
`--require-reviewed-mapping-normalization` also makes mapped data mandatory and
fails closed unless its summary explicitly retains a verified approved mapping
review, exact source and reviewed-mapping fingerprints, normalization-only
safety, and non-research/non-routing/non-submission claims. Failed checks route
operators to `normalize-reviewed-mapped-data`.
For a different target file covered by an approved exact-header scope, use
`--require-target-application-normalization` instead. It requires the target
application ID/hash, scope-review ID/hash, target-intake receipt, exact source
and ordered-header fingerprints, target-applied mapping fingerprint, explicit
normalization execution, and the application's preserved non-authorizing
state. Failed checks route to `normalize-applied-vendor-mapping`. The reviewed
and target-application strict modes are mutually exclusive because they prove
different source-binding contracts.
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
