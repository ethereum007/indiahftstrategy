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
  --required-run-type stress_report `
  --required-run-type promotion_report `
  --required-run-type shadow_session_comparison `
  --require-same-git-commit `
  --fail-on-breach
```

Outputs:

```text
strategy_evidence_items.csv
strategy_evidence_checks.csv
strategy_evidence_summary.csv
manifest.json
```

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
  --order-latency-us 250
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
  --qty 75
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

## Surface Market-Making Replay

Replay passive surface quotes against later option-chain snapshots. A bid quote
fills when a later best ask is at or below the quote; an ask quote fills when a
later best bid is at or above the quote.

```powershell
python -m hft_cli replay-surface-mm `
  --quotes runs\surface_quotes_2026_06_10\surface_quotes.csv `
  --chain data\chain.csv `
  --out runs\surface_mm_replay_2026_06_10 `
  --quote-ttl-ns 1000000000 `
  --markout-horizon-ns 1000000000 `
  --fill-depth-fraction 0.25 `
  --order-latency-us 250
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

## Surface Market-Making Sweep

Run passive surface quote replay across TTL, latency, fill-depth, and markout
horizon assumptions, then evaluate every replay folder with the proof gate:

```powershell
python -m hft_cli sweep-surface-mm `
  --quotes runs\surface_quotes_2026_06_10\surface_quotes.csv `
  --chain data\chain.csv `
  --out runs\surface_mm_sweep_2026_06_10 `
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

Gate a full paper/shadow loop by combining launch, export, and reconciliation
artifacts:

```powershell
python -m hft_cli shadow-session-report `
  --launch runs\launch\leadlag_shadow `
  --export runs\exports\leadlag_shadow_arrow `
  --reconciliation runs\reconciliation\leadlag_shadow_arrow `
  --out runs\sessions\leadlag_shadow_2026_06_10 `
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

## Controlled Scale-Up Plan

Convert accepted evidence and shadow sessions into explicit size limits and
kill switches:

```powershell
python -m hft_cli plan-scaleup `
  --evidence runs\evidence\leadlag_shadow `
  --shadow-comparison runs\sessions\leadlag_shadow_comparison `
  --launch runs\launch\leadlag_shadow `
  --order-exposure runs\risk\leadlag_shadow_exposure `
  --out runs\scaleup\leadlag_shadow `
  --target-mode shadow `
  --allowed-adapter arrow_money `
  --min-shadow-sessions 2 `
  --min-shadow-acceptance-rate 1 `
  --min-worst-order-fill-rate 0.8 `
  --max-worst-adverse-slippage 0.05 `
  --max-scale-multiplier 1 `
  --max-orders-per-session 100 `
  --max-session-notional 100000 `
  --stop-loss 5000 `
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

## Runtime Scale-Up Guard

Evaluate live or paper telemetry snapshots against the scale-up limits and kill
switches:

```powershell
python -m hft_cli monitor-scaleup-guard `
  --scaleup runs\scaleup\leadlag_shadow `
  --telemetry logs\leadlag_shadow_telemetry.csv `
  --out runs\guards\leadlag_shadow_latest `
  --fail-on-halt
```

Telemetry CSV columns:

```text
scenario_key,adapter,orders_sent,session_notional,realized_pnl,total_failed_component_checks,unmatched_fills,mismatched_orders,overfilled_orders,worst_adverse_slippage
```

Outputs:

```text
runtime_guard_metrics.csv
runtime_guard_checks.csv
runtime_guard_summary.csv
manifest.json
```

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

## Order Staging

Stage generated quote or order candidates into a broker-neutral pre-trade file
before any Arrow.money/iRage-specific routing adapter is wired in:

```powershell
python -m hft_cli stage-orders `
  --orders runs\surface_quotes_2026_06_10\surface_quotes.csv `
  --source surface_quotes `
  --out runs\surface_quotes_2026_06_10\staged_orders `
  --max-order-qty 75 `
  --max-notional 10000 `
  --price-band-pct 0.02 `
  --max-orders 100 `
  --fail-on-reject
```

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
