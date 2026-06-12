# Project: India HFT Strategy Research & Backtesting Platform

## What this is
Backtesting and research platform for HFT strategies on Indian index
derivatives (NSE Nifty complex, BSE Sensex complex). The strategy spec is
docs/india_hft_strategy_research.md. The single-instrument reference engine is
engine/hft_backtest.py; its fill, latency, and cost semantics are the ground
truth to preserve.

## Non-negotiable domain rules
- Costs: post-April-2026 Indian regime. Futures STT 0.05% sell-side notional;
  options STT 0.15% of premium sell-side. All charges parameterized, never
  hardcoded inline. Options are the trading instrument; futures are hedges.
- Latency honesty: every order acts on the book as of arrival time
  (decision_ts + order latency), never decision time. Every strategy sees ticks
  at exchange_ts + feed latency.
- Queue conservatism: maker fills only after estimated queue ahead is consumed;
  default conservatism multiplier is 1.5.
- Executable prices only: all arbitrage/signal detection at touch prices
  (buy at ask, sell at bid), sized to a configurable fraction of displayed
  depth. Mid-price edge is a bug.
- Regime breaks: Nov-2024 weekly consolidation, Sep-2025 expiry swap
  (Nifty Tuesday, Sensex Thursday), Apr-2026 STT hike. Every backtest report
  must support per-regime breakdown.
- Compliance: track order-to-trade ratio in every run. No strategy logic whose
  P&L depends on own impact moving the index.

## Engineering conventions
- Python 3.11+, pandas + numpy, pytest, type hints where practical, dataclasses
  for messages/configs.
- Determinism: every simulation seeded; same inputs produce identical outputs.
- No lookahead: any function joining timestamps must take an explicit latency
  parameter.
- Tests first for engine semantics: every fill-model behavior gets a
  hand-constructed tick fixture with a hand-computed expected outcome.
- Keep engine/ free of strategy logic; strategies/ free of fill logic.
- Run `pytest -q` after every change.

## Current architecture
- engine/hft_backtest.py: single-instrument event engine reference.
- engine/: multi-instrument engine evolves here.
- strategies/: Strategy subclasses only.
- scanners/: Layer-1 vectorized research tools.
- data/: loaders, schema normalization, synthetic generators.
- tests/: pytest suites and fixtures.
