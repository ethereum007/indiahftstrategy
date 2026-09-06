# Arrow Productionization Status

Last updated: 2026-09-06

## Sprint outcome

The broker-neutral production boundary, Arrow authentication/configuration skeleton, official Data Stream decoder, supervised market and order streams, versioned instrument master, configurable rate limiter, automatic data-quality monitor, latency observatory, independent risk engine, unified safety coordinator, restartable OMS, named liquidity universe, opportunity ranker, execution policy, causal feature engine, and tamper-evident shadow runtime are implemented and tested with fakes.

Live routing remains fail-closed. No Arrow credentials are required by tests or CI.

## Baseline

- Source: `master` at `7fe42d6`.
- Feature branch: `feat/arrow-productionization`.
- Existing CI: none.
- Existing editable install: failed because setuptools package discovery was not configured; fixed in this branch.
- Baseline collection: 2,872 preserved tests. Current collection: 2,934 tests (62 added).
- Deterministic production boundary: 62 passed, 0 failed, 89% statement coverage.
- Full legacy run: not completed locally. The first attempt ended with 80 failed, 2,061 passed,
  and 757 errors caused predominantly by a full system temporary drive; that result is invalid.
  A clean rerun on a secondary drive progressed beyond 96% without infrastructure errors but
  was interrupted by the host session before pytest emitted its aggregate. This is an open
  internal regression/CI-runtime gate, not `BLOCKED_EXTERNAL`. The six-hour GitHub lane also
  reached its configured timeout without producing an aggregate; its fast production and
  quality/security sibling lanes passed.

## Implemented now

- Strongly typed broker-neutral contracts with distinct event timestamps and trace IDs.
- `BrokerAdapter` protocol; strategy packages have no Arrow import.
- Isolated `brokers/arrow` package with environment-only config, redaction, authentication state, checksum helpers, dependency-injected transports, subscriptions, reconnect policy, rate limits, decoder, portfolio/margin boundaries, reconciliation, and disabled order routing.
- Official Arrow Data Stream packet support: LTP, LTPC, quote, full L5 depth, and CAS trailers.
- Order-update gateway with injected handshake, heartbeat, timeout, bounded reconnect, parser,
  event bus, independent health reporting, and a reconnect budget that is not reset by a
  connection that immediately flaps.
- Market-data supervisor with stale-feed timeout, close-before-backoff, bounded reconnect,
  subscription restoration, and fail-closed halt callbacks.
- Feed diagnostics for duplicates, out-of-order timestamps, malformed frames, and publish counts.
- Proactive authentication refresh with token-expiry tracking and rotation hooks.
- Credential-free static-IP preflight verifies a public configured address against observed egress,
  probes TLS reachability for all Arrow endpoints, and writes secret-free JSON evidence.
- SHA-256-bound instrument-master snapshots, schema/identity validation, and token-level diffs.
- Independent pre-trade limits, non-auto-resuming kill switch, and a unified safety coordinator
  requiring healthy authentication, market data, order stream, and approved risk.
- Rate-limit pressure circuit breaker connected to the kill switch.
- Append-only OMS journal with recovery and submission reservation idempotency.
- Raw and normalized append-only capture with partition-ready paths and automatic gap, stale,
  regression, and session-boundary quality checks.
- Synthetic latency percentiles (p50/p90/p95/p99/p99.9/max/jitter), filterable and groupable by
  stage, endpoint, strategy, symbol, segment, and hour.
- Causal online features calculate RVOL, signed flow, VWAP slope, OFI, depth changes, spread
  z-score, opening range, volatility shock, and benchmark residuals without forward data.
- Shadow runtime supports forecast → portfolio → risk → OMS, records hypothetical fills, P&L,
  slippage, markout, and latency, and contains execution in the simulator. Session evidence is
  hash-chained, restart-verified, and summarized from its durable journal.
- Named, dated, checksum-bound NIFTY 50/100/200 or custom universe definitions are filtered by
  observed liquidity and ranked under an explicit capacity limit.
- Broker state queries fail closed unless a typed query provider is injected; empty broker state
  is never fabricated.
- GitHub Actions test, coverage, lint, format, typing, dependency audit, security audit, and secret scan.

## Verification

- `pytest` production boundary: **62 passed, 0 failed**.
- Coverage over production packages: **89%** (1,990 statements; 214 missed).
- Ruff lint: passed. Ruff format check: passed after formatting.
- Mypy: passed across 37 production source files.
- Bandit: passed. Pip-audit: no known vulnerabilities; the local package is not on PyPI.
- Full 2,934-test result: **INCOMPLETE_INTERNAL**. The GitHub legacy lane timed out at six hours
  without an aggregate; production and quality/security lanes passed.

## BLOCKED_EXTERNAL

- Static IP is user-reported as acquired; exact egress match, Arrow registration, and network
  allow-list confirmation remain pending certification.
- Arrow app credentials are user-reported as issued and the registered URLs are
  `https://arrow.alphabullacademy.com/auth/callback` and
  `https://arrow.alphabullacademy.com/order/postback`. Credentials have not been shared or
  persisted in the repository. DNS resolves through Cloudflare, but the callback origin did not
  answer the 2026-09-06 reachability check, so authenticated flow remains pending.
- Real authentication/account-identity response validation.
- Live instrument-master comparison and expiry-day validation.
- WebSocket handshake, heartbeat behavior, packet captures, sequence/gap semantics, and HFT-stream variants.
- Real order/update schemas and broker order lifecycle certification.
- Real latency, data quality, fill, slippage, markout, and reconciliation evidence.

These are external evidence gaps, not missing architecture. Follow `STATIC_IP_CUTOVER.md` when access is supplied.
