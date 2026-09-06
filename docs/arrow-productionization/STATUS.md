# Arrow Productionization Status

Last updated: 2026-09-06

## Sprint outcome

The broker-neutral production boundary, Arrow authentication/configuration skeleton, official Data Stream decoder, exact instrument resolver, configurable rate limiter, append-only recorder, latency observatory, independent risk engine, kill switch, restartable OMS, liquidity universe, opportunity ranker, execution policy, causal feature engine, and broker-contained shadow runtime are implemented and tested with fakes.

Live routing remains fail-closed. No Arrow credentials are required by tests or CI.

## Baseline

- Source: `master` at `7fe42d6`.
- Feature branch: `feat/arrow-productionization`.
- Existing CI: none.
- Existing editable install: failed because setuptools package discovery was not configured; fixed in this branch.
- Baseline collection: 2,872 preserved tests. Current collection: 2,909 tests (37 added).
- Deterministic production boundary: 37 passed, 0 failed, 89% statement coverage.
- Full legacy run: not completed locally. The first attempt ended with 80 failed, 2,061 passed,
  and 757 errors caused predominantly by a full system temporary drive; that result is invalid.
  A clean rerun on a secondary drive progressed beyond 96% without infrastructure errors but
  was interrupted by the host session before pytest emitted its aggregate. This is an open
  internal regression/CI-runtime gate, not `BLOCKED_EXTERNAL`.

## Implemented now

- Strongly typed broker-neutral contracts with distinct event timestamps and trace IDs.
- `BrokerAdapter` protocol; strategy packages have no Arrow import.
- Isolated `brokers/arrow` package with environment-only config, redaction, authentication state, checksum helpers, dependency-injected transports, subscriptions, reconnect policy, rate limits, decoder, portfolio/margin boundaries, reconciliation, and disabled order routing.
- Official Arrow Data Stream packet support: LTP, LTPC, quote, full L5 depth, and CAS trailers.
- Order-update gateway with injected handshake, heartbeat, timeout, bounded reconnect, parser,
  event bus, and independent health reporting.
- Feed diagnostics for duplicates, out-of-order timestamps, malformed frames, and publish counts.
- Independent pre-trade limits and non-auto-resuming kill switch.
- Rate-limit pressure circuit breaker connected to the kill switch.
- Append-only OMS journal with recovery and submission reservation idempotency.
- Raw and normalized append-only capture with partition-ready paths and quality checks.
- Synthetic latency percentiles (p50/p90/p95/p99/p99.9/max/jitter).
- Causal online features calculate RVOL, signed flow, VWAP slope, OFI, depth changes, spread
  z-score, opening range, volatility shock, and benchmark residuals without forward data.
- Shadow runtime supports forecast → portfolio → risk → OMS, records hypothetical fills, P&L,
  slippage, markout, and latency, and contains execution in the simulator.
- Broker state queries fail closed unless a typed query provider is injected; empty broker state
  is never fabricated.
- GitHub Actions test, coverage, lint, format, typing, dependency audit, security audit, and secret scan.

## Verification

- `pytest` production boundary: **37 passed, 0 failed**.
- Coverage over new production packages: **89%** (1,565 statements; 175 missed).
- Ruff lint: passed. Ruff format check: passed after formatting.
- Mypy: passed across 35 production source files.
- Bandit: passed. Pip-audit: no known vulnerabilities; the local package is not on PyPI.
- Full 2,909-test result: **INCOMPLETE_INTERNAL** pending the GitHub Actions legacy lane.

## BLOCKED_EXTERNAL

- Static-IP registration and network allow-list confirmation.
- Real authentication/account-identity response validation.
- Live instrument-master comparison and expiry-day validation.
- WebSocket handshake, heartbeat behavior, packet captures, sequence/gap semantics, and HFT-stream variants.
- Real order/update schemas and broker order lifecycle certification.
- Real latency, data quality, fill, slippage, markout, and reconciliation evidence.

These are external evidence gaps, not missing architecture. Follow `STATIC_IP_CUTOVER.md` when access is supplied.
