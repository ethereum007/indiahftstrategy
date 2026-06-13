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
  --out runs\catalog\latest
```

Outputs:

```text
experiment_catalog.csv
experiment_catalog_summary.csv
manifest.json
```

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

Outputs:

```text
strategy_evidence_items.csv
strategy_evidence_checks.csv
strategy_evidence_summary.csv
manifest.json
```

The catalog recognizes research, proof, promotion, data-readiness, market
portability, calibration, launch, broker export/upload, broker-readiness,
shadow-session, scale-up, quote-lifecycle, runtime guard, runtime-session,
cutover, route-enable, broker-dispatch, halt-response, and resume summaries,
so those run types can be promoted into explicit `--required-run-type`
evidence gates.

Use `--require-same-strategy` and `--require-same-market` before scale-up to
fail closed when required proof, stress, promotion, broker, or shadow artifacts
come from different strategy or market identities. Pair them with
`--expected-strategy` and `--expected-market` when the scale-up target is known.
The identity check also recognizes runtime identity aliases retained by
broker-readiness, shadow-session, and runtime-session summaries.

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
  --out runs\market_profiles\portability
```

Outputs:

```text
market_portability_matrix.csv
market_portability_gaps.csv
market_portability_summary.csv
manifest.json
```

US rows are marked `needs_fee_model` unless explicit fees are acknowledged.
India-specific settlement convergence remains blocked for US profiles until a
separate US settlement/microstructure model is implemented.

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
  --delta 0.5 `
  --trigger-ticks 3 `
  --qty 75 `
  --fill-model runs\fill_model\leadlag_shadow_latest
```

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

## Microprice Imbalance Research Pipeline

Run the full imbalance research proof path in one command: edge walk-forward,
replay-proof walk-forward, and promotion into launch-compatible candidate
artifacts.

```powershell
python -m hft_cli pipeline-imbalance-research `
  --ticks data\atm_option_ticks_2026_06_10.csv data\atm_option_ticks_2026_06_11.csv `
  --label day1 `
  --label day2 `
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
```

## Surface Quotes

Fit per-snapshot option surfaces and generate market-making quotes:

```powershell
python -m hft_cli quote-surface `
  --chain data\chain.csv `
  --futures data\futures.csv `
  --out runs\surface_quotes_2026_06_10 `
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

## Surface Quote Review

Gate generated market-making quotes before replay or live routing:

```powershell
python -m hft_cli review-quotes `
  --quotes runs\surface_quotes_2026_06_10\surface_quotes.csv `
  --out runs\surface_quotes_2026_06_10\quote_review `
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
unproven vendor market data.

## Surface Quote Lifecycle Plan

Convert generated surface quote snapshots into a submit/replace/cancel plan
with exchange-message and outstanding-quote limits before paper routing:

```powershell
python -m hft_cli plan-quote-lifecycle `
  --quotes runs\surface_quotes_2026_06_10\surface_quotes.csv `
  --quote-risk-review runs\surface_quotes_2026_06_10\quote_review `
  --require-quote-risk-review `
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

## Surface Market-Making Research Pipeline

Run the complete surface market-making research path from option-chain/futures
data through quote generation, quote review, replay sweep proof, scenario
selection, and promotion:

```powershell
python -m hft_cli pipeline-surface-mm-research `
  --chain data\chain.csv `
  --futures data\futures.csv `
  --out runs\surface_mm_pipeline_2026_06_10 `
  --data-readiness-comparison runs\vendor_data\arrow_ticks_batch\comparison `
  --require-data-readiness-comparison `
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
02_quote_review\quote_risk_summary.csv
03_sweep\sweep_summary.csv
04_selection\selection_summary.csv
05_promotion\promotion_summary.csv
surface_mm_pipeline_stages.csv
surface_mm_pipeline_summary.csv
candidate_config.json
manifest.json
```

## Surface Market-Making Launch Pipeline

Turn a passed surface market-making research pipeline into broker-prep artifacts
for paper or shadow trading:

```powershell
python -m hft_cli pipeline-surface-mm-launch `
  --surface-pipeline runs\surface_mm_pipeline_2026_06_10 `
  --out runs\surface_mm_launch_2026_06_10 `
  --mode shadow `
  --adapter arrow_money `
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
  --fail-on-breach
```

Outputs:

```text
broker_upload_orders.csv
broker_upload_mapping.csv
broker_upload_checks.csv
broker_upload_summary.csv
broker_upload_schema.csv
manifest.json
```

The mapping file is emitted beside the upload-shaped orders so the final
Arrow.money/iRage column semantics can be reviewed before any live route is
enabled.

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
  --fail-on-breach
```

Outputs:

```text
vendor_intake_columns.csv
vendor_intake_kind_scores.csv
vendor_intake_mapping_candidates.csv
vendor_mapping_draft.csv
vendor_intake_summary.csv
manifest.json
```

The generated `vendor_mapping_draft.csv` uses `normalized_column`,
`source_column`, `default_value`, `required`, and `transform` columns so it can
be reviewed and then passed to `normalize-mapped-data`.

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
  --fail-on-unmapped
```

Outputs:

```text
order_mapping_draft.csv
order_mapping_draft_checks.csv
order_mapping_draft_summary.csv
manifest.json
```

The draft marks suggested mappings, manual defaults, optional gaps, and
unmapped required vendor columns before any broker-specific upload file is
generated.

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
mapped_order_summary.csv
mapped_order_schema.csv
manifest.json
```

## Broker Integration Readiness

Combine adapter schema review, broker-neutral export, mapped/upload files,
optional halt-export, optional reconciliation, optional runtime-session, and
optional resume-gate evidence into one go/no-go record before Arrow.money/iRage
paper or shadow routing:

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
  --out runs\broker_readiness\leadlag_shadow_arrow `
  --require-mapping-draft `
  --require-mapped-orders `
  --require-runtime-session `
  --require-resume-gate `
  --fail-on-breach
```

Use `--allow-placeholder-schema` only for dry-run review while Arrow.money/iRage
schemas are still placeholders. Without it, placeholder schemas fail closed.
When broker-neutral exports contain quote lifecycle fields, the built-in
normalized, Arrow.money, and iRage review templates carry `lifecycle_action`,
`lifecycle_action_id`, `lifecycle_reason`, `lifecycle_message_count`,
`quote_age_ns`, and `replaces_order_id` into the upload-shaped CSV for broker
schema review.
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

Outputs:

```text
broker_readiness_items.csv
broker_readiness_checks.csv
broker_readiness_summary.csv
manifest.json
```

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
  --fail-on-breach
```

Outputs:

```text
order_reconciliation.csv
unmatched_fills.csv
reconciliation_checks.csv
reconciliation_summary.csv
manifest.json
```

## Shadow Session Report

Gate a full paper/shadow loop by combining launch, export, reconciliation, and
optional runtime-session monitor artifacts:

```powershell
python -m hft_cli shadow-session-report `
  --launch runs\launch\leadlag_shadow `
  --export runs\exports\leadlag_shadow_arrow `
  --reconciliation runs\reconciliation\leadlag_shadow_arrow `
  --runtime-session runs\runtime_sessions\leadlag_shadow_latest `
  --out runs\sessions\leadlag_shadow_2026_06_10 `
  --require-runtime-session `
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
identity.

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
broker resume strategy/market/proof identity across the comparison set.

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
  --require-broker-readiness `
  --require-resume-gate `
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

For settlement convergence or surface market-making handoffs, `--launch` may
point at the launch-pipeline root. In that case scale-up reads the nested
launch summary and automatically includes nested broker-readiness evidence when
present, so `--require-broker-readiness` can gate the pipeline folder directly.
If broker readiness included runtime-session evidence, `scaleup_summary.csv`
and `scaleup_config.json` retain the runtime guard action/halt status plus the
runtime target mode, strategy, and market for the session that fed the broker
gate.
If broker readiness included resume-gate evidence, scale-up also retains the
resume authorization identity, prior incident identity, and resume
`proof_refresh_*` context. `--require-resume-gate` fails closed unless broker
readiness supplied a ready resume gate with strategy/market and proof-refresh
identity matching the scale-up identity.
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
broker readiness plus broker runtime-session evidence with a continuing runtime
guard, and fails closed unless that runtime-session strategy and market match
the scale-up identity.

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

For settlement convergence or surface market-making handoffs, `--export` and
`--upload-pack` may point at the launch-pipeline root; telemetry will read the
nested broker export and upload-pack summaries from that folder. Upload-pack
summaries carry `lifecycle_orders` and `replace_orders` into runtime guardrails.
Telemetry carries the scale-up `strategy` and `market` identities from
`scaleup_config.json`; missing identity fails closed before guard evaluation.
When scale-up required proof-refresh evidence, telemetry also carries
`proof_refresh_*` fields from the scale-up config and fails closed if the proof
is missing, unready, mixed, or for a different strategy/market.
When scale-up required broker resume-gate evidence, telemetry also carries
`broker_resume_*` fields from the scale-up config and fails closed if the
resume authorization, its strategy/market identity, or its proof-refresh
identity is missing or stale.
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
  --fail-on-halt
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

Outputs:

```text
runtime_guard_metrics.csv
runtime_guard_checks.csv
runtime_guard_summary.csv
manifest.json
```

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
  --fail-on-breach
```

Outputs:

```text
01_telemetry\runtime_telemetry.csv
02_guard\runtime_guard_summary.csv
03_halt_response\halt_response_summary.csv
runtime_session_steps.csv
runtime_session_summary.csv
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
evaluation.

## Halt Response Plan

Convert a runtime guard halt into broker-neutral cancel and flatten action files:

```powershell
python -m hft_cli plan-halt-response `
  --guard runs\guards\leadlag_shadow_latest `
  --open-orders logs\open_orders.csv `
  --positions logs\positions.csv `
  --out runs\halt_response\leadlag_shadow_latest `
  --fail-on-breach
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
halt_response_config.json
manifest.json
```

`halt_response_summary.csv`, `halt_cancel_orders.csv`, and
`halt_flatten_orders.csv` include the guard failed check names, first halt
reason, strategy, and market so emergency action files show why the
cancel/flatten packet exists and which scaled strategy produced it. They also
retain `proof_refresh_*` and `proof_source` fields from the runtime guard so a
halt packet can be tied back to the fresh proof state that authorized the
runtime session.

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
  --fail-on-breach
```

Both mapping files use:

```text
target_column,source_column,default_value,required,transform
```

If no mapping is supplied for an action type, the broker-neutral action file is
passed through unchanged. This keeps the halt workflow usable before the real
Arrow.money/iRage emergency action schemas arrive.

Outputs:

```text
broker_cancel_orders.csv
broker_flatten_orders.csv
halt_response_export_checks.csv
halt_response_export_summary.csv
halt_response_export_schema.csv
manifest.json
```

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
  --fail-on-breach
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
manifest.json
```

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
  --fail-on-breach
```

Outputs:

```text
halt_incident_timeline.csv
halt_incident_checks.csv
halt_incident_summary.csv
manifest.json
```

The timeline and summary retain guard-trigger, strategy, market, and
`proof_refresh_*` fields so the incident closure record shows both the failed
guard checks that caused the halt and the proof-freshness context that fed the
scaled runtime.

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
  --fail-on-breach
```

Outputs:

```text
resume_authorization.csv
resume_checks.csv
resume_summary.csv
resume_config.json
manifest.json
```

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
`acknowledged_guard_failed_check_names` value.

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
  --fail-on-breach
```

Outputs:

```text
cutover_authorization.csv
cutover_checks.csv
cutover_summary.csv
cutover_config.json
manifest.json
```

For `live_dryrun`, the cutover gate automatically requires operator approval,
operator acknowledgement of the strategy/market identity, and acknowledgement
of the scale-up order/notional limits. It also requires the runtime guard to be
continuing, validates runtime strategy/market/target-mode identity against the
scale-up plan, carries proof-refresh state, and validates any supplied broker
resume-gate proof identity before broker routing is allowed.

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
  --fail-on-breach
```

Outputs:

```text
route_enable_packet.csv
route_enable_checks.csv
route_enable_summary.csv
route_enable_config.json
manifest.json
```

The packet does not submit orders. It carries the approved target mode,
strategy, market, scenario, adapter, order limit, notional limit, upload file,
and proof/resume context into one machine-readable artifact. It fails closed if
cutover is not ready, the upload pack is not ready, the adapter or target mode
does not match, the upload order count exceeds the cutover limit, or the
optional order-export notional exceeds the cutover notional cap.

## Broker Dispatch Plan

Bind the enabled route to the exact broker upload rows and create a dry-run
dispatch batch with deterministic idempotency keys:

```powershell
python -m hft_cli plan-broker-dispatch `
  --route-enable runs\route_enable\leadlag_shadow_live_dryrun `
  --upload-pack runs\uploads\leadlag_shadow_arrow `
  --out runs\dispatch\leadlag_shadow_live_dryrun `
  --target-mode live_dryrun `
  --fail-on-breach
```

Outputs:

```text
broker_dispatch_orders.csv
broker_dispatch_checks.csv
broker_dispatch_summary.csv
broker_dispatch_config.json
manifest.json
```

This command still does not submit orders. It hashes the route-enable
authorization and upload file, creates one dry-run dispatch row per upload
order, and requires unique source order IDs, unique dispatch IDs, route-enabled
state, matching target mode, and order counts within the approved route limits.
The resulting `broker_dispatch_config.json` is the artifact a future
Arrow.money/iRage sender can consume.

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
  --fail-on-breach
```

Outputs:

```text
fill_model_metrics.csv
fill_model_recommendations.csv
fill_model_checks.csv
fill_model_summary.csv
fill_model_config.json
manifest.json
```

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
  --fail-on-breach
```

Outputs:

```text
fill_model_drift.csv
fill_model_drift_checks.csv
fill_model_drift_summary.csv
manifest.json
```

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
  --fail-on-breach
```

Outputs:

```text
proof_refresh_decision.csv
proof_refresh_checks.csv
proof_refresh_summary.csv
manifest.json
```

The gate records strategy/market identity from baseline proof, latest proof,
and calibrated replay summaries. Mixed available strategy or market identities
fail closed, and `--strategy`/`--market` enforce the expected target when those
identities are present.

## Adapter Schema Audit

Audit a vendor sample CSV header before wiring a real adapter map:

```powershell
python -m hft_cli audit-adapter-schema `
  --sample vendor\arrow_ticks_sample.csv `
  --adapter arrow_money `
  --kind ticks `
  --out runs\schema_audit\arrow_ticks_sample `
  --fail-on-missing
```

Supported `--kind` values include `ticks`, `chain`, `orders`, and `fills`.
The command reads only the CSV header and writes:

```text
adapter_schema_summary.csv
adapter_schema_columns.csv
adapter_mapping_template.csv
manifest.json
```

For `arrow_money` and `irage`, the summary is marked
`placeholder_normalized_pending_vendor_schema` until real vendor source columns
replace the normalized placeholders.

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
mapped_data_summary.csv
manifest.json
```

The command fails closed when required normalized columns are not mapped, and
tick/chain outputs pass through the same session, timestamp, and data-quality
normalizers used by the strategy backtests.

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
vendor_market_data_pipeline_summary.csv
manifest.json
```

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
  --fail-on-breach
```

Batch outputs:

```text
datasets\<label>\vendor_market_data_pipeline_summary.csv
comparison\data_readiness_comparison_summary.csv
vendor_market_data_batch_datasets.csv
vendor_market_data_batch_summary.csv
manifest.json
```

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
  --max-order-qty 75 `
  --max-notional 10000 `
  --price-band-pct 0.02 `
  --max-orders 100 `
  --fail-on-reject
```

For `--source surface_quotes`, requiring the quote-risk review blocks all
orders unless the supplied `quote_risk_summary.csv` passed. This keeps market
making quotes from moving into broker-neutral staging before the data and quote
hygiene gates are accepted.

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
tick/chain diagnostics, market profile fees, and instrument metadata into one
go/no-go record before edge scans, walk-forwards, or replay pipelines:

```powershell
python -m hft_cli review-data-readiness `
  --vendor-intake mappings\arrow_ticks_intake `
  --schema-audit runs\schema_audit\arrow_ticks `
  --mapped-data data\normalized\arrow_ticks_2026_06_10 `
  --tick-diagnostics runs\diagnostics\futures `
  --chain-diagnostics runs\diagnostics\chain `
  --market-profile runs\market_profiles\india_us `
  --instrument-metadata runs\risk\leadlag_shadow_instruments `
  --out runs\data_readiness\india_nse_2026_06_10 `
  --require-vendor-intake `
  --require-schema-audit `
  --require-mapped-data `
  --require-chain-diagnostics `
  --require-market-profile `
  --require-explicit-fee-model `
  --require-instrument-metadata `
  --max-tick-p99-gap-ns 1000000000 `
  --max-tick-median-spread-ticks 2 `
  --max-chain-median-spread-ticks 20 `
  --fail-on-breach
```

Outputs:

```text
data_readiness_items.csv
data_readiness_checks.csv
data_readiness_summary.csv
manifest.json
```

Compare multiple data-readiness runs before walk-forward research:

```powershell
python -m hft_cli compare-data-readiness `
  --readiness runs\data_readiness\india_nse_2026_06_10 runs\data_readiness\india_nse_2026_06_11 `
  --label 2026-06-10 `
  --label 2026-06-11 `
  --out runs\data_readiness\india_nse_comparison `
  --min-datasets 2 `
  --min-ready-rate 1 `
  --fail-on-breach
```

Outputs:

```text
data_readiness_runs.csv
data_readiness_comparison_checks.csv
data_readiness_comparison_summary.csv
manifest.json
```

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
