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
