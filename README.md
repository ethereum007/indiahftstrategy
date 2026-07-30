# India HFT Strategy Research Platform

An India-first event-driven research, backtesting, and broker-readiness
platform for NSE/BSE index derivatives.

## Where It Stands

The repository has a substantial simulation and evidence stack. It is not a
live-trading system, and it has not yet proven durable alpha on real,
selection-isolated Arrow.money or iRage data.

| Area | Current state |
| --- | --- |
| Event replay | Implemented with causal feed/order latency, queue-aware fills, displayed-liquidity conservation, Indian costs, OTR, and terminal inventory evidence |
| Strategy research | Imbalance, lead-lag, parity, box, settlement convergence, and surface market-making workflows |
| Statistical validation | Walk-forward splits, CSCV-style overfit checks, corrected significance, frozen-candidate holdouts, and promotion gates |
| Indian market rules | NSE/BSE profiles, session calendars, F&O expiry rules, lot-size evidence, and post-April-2026 cost assumptions |
| Reporting | Replay proof, stress, markout, PnL, regime, strategy scorecard, and manifest-backed lineage reports |
| Broker preparation | Broker-neutral orders, mapping review, upload packs, reconciliation, runtime guards, halt plans, and non-authorizing dry-run dispatch evidence |
| Real vendor integration | Framework ready; actual Arrow.money/iRage column maps still require representative exports |
| Live deployment | Blocked pending real data proof, signed broker schemas, credentials, risk limits, shadow calibration, and explicit authorization |

The most important distinction is:

- **Built:** the platform can model, test, reject, and package candidate
  strategies.
- **Not yet proven:** a strategy that survives unseen real Indian-market data,
  realistic latency, costs, and deployable size.
- **Not authorized:** no artifact in this repository permits live order
  submission.

## New Proof Workflow

`prove-imbalance-holdout` takes a frozen promoted imbalance candidate and
replays it on holdout days that must not occur anywhere in the candidate's
manifested development lineage.

It produces:

- `holdout_scenarios.csv`
- `latency_curve.csv`
- `cost_curve.csv`
- `capacity_curve.csv`
- `holdout_checks.csv`
- `holdout_summary.csv`
- `research_proof.json`
- `RESEARCH_PROOF.md`
- `manifest.json`

The sensitivity grid is one-factor-at-a-time:

- **Latency:** total feed-plus-order latency, split by a declared feed fraction.
- **Costs:** an exact multiplier on the complete Indian or generic cash cost.
- **Capacity:** larger venue-valid lot quantities replayed against observed
  displayed liquidity.

Example:

```powershell
python hft_cli.py prove-imbalance-holdout `
  --candidate runs/imbalance_research/promotion `
  --holdout-ticks data/holdout/2026-06-15.csv data/holdout/2026-06-16.csv data/holdout/2026-06-17.csv `
  --label 2026-06-15 --label 2026-06-16 --label 2026-06-17 `
  --out runs/imbalance_holdout_proof `
  --baseline-latency-us 300 `
  --latency-us 100 300 500 1000 `
  --cost-multiplier 1 1.25 1.5 2 `
  --qty-multiplier 1 2 4 8 `
  --fail-on-breach
```

The command exits with code `2` on a failed proof when `--fail-on-breach` is
set. A failed dossier is still useful research evidence; it identifies the
latency, cost, capacity, or holdout condition that broke.

## Evidence Ladder

```text
vendor capture
  -> normalization and data-readiness review
  -> development edge search
  -> frozen candidate
  -> selection-isolated holdout dossier
  -> shadow-session calibration
  -> paper routing review
  -> controlled scale-up
  -> explicit cutover decision
```

Every stage is non-authorizing until the separate operational and human
approval gates are satisfied.

## Strategy Priorities

1. **Executable parity and box spreads** for lower-risk end-to-end validation.
2. **Microprice imbalance and lead-lag** for latency-sensitive alpha research.
3. **Settlement convergence** with strict expiry-day compliance and size caps.
4. **Surface market making** after passive-fill calibration is grounded in
   real shadow data.

The research thesis and Indian microstructure constraints are in
[`docs/india_hft_strategy_research.md`](docs/india_hft_strategy_research.md).

## What Is Needed Next

The next material advances depend on external evidence, not more internal
dispatch plumbing:

1. Representative Arrow.money and/or iRage tick and option-chain exports.
2. At least nine chronologically separated real-market periods for a strict
   development/holdout study.
3. Broker-signed paper/shadow order-upload and acknowledgement schemas.
4. Measured shadow fill, latency, rejection, and slippage samples.
5. Explicit capital, instrument, loss, OTR, and emergency-halt limits before
   any broker-connected trial.

Credentials and live-routing decisions should only be introduced when those
inputs are ready.

## Development

Python 3.11 or newer is required.

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q
```

The unified CLI is:

```powershell
python hft_cli.py --help
```

Detailed command reference and cumulative build history are retained in
[`docs/COMMANDS.md`](docs/COMMANDS.md) and
[`docs/BUILD_STATUS.md`](docs/BUILD_STATUS.md).

## Safety

This software is for research. Backtests can be wrong because of feed gaps,
timestamp mismatch, queue uncertainty, hidden liquidity, cancellation races,
fees, impact, regime shifts, and selection bias. Passing reports are evidence
for the next controlled review, not a claim of expected profit.
