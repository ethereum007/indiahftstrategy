# Static-IP Cutover Runbook

This is a certification run, not a live-trading launch. Production order routing remains disabled throughout.

1. Register and independently verify the approved static egress IP.
2. Inject secrets through the approved secret provider; do not create a populated `.env` artifact.
3. Validate configuration/redaction, then authenticate.
4. Call the profile/account endpoint and verify user/account identity against an operator-controlled value.
5. Download the instrument master and compare schema, token uniqueness, lot size, tick size, exchange, segment, expiry, strike, and option identity. Fail closed on any mismatch.
6. Connect the market-data WebSocket and subscribe in `full` mode to one liquid NSE cash instrument.
7. Save raw packets and validate token, scale, timestamps, LTP and all five depth levels against an independent Arrow screen/reference.
8. Confirm disconnect/reconnect, heartbeat behavior, subscription restoration, duplicate handling, out-of-order behavior, and any sequence/gap semantics using captured evidence.
9. Expand gradually to a small reviewed liquid universe, then the configured NIFTY universe; monitor queue and rate-limit pressure.
10. Run the data-quality report for duplicates, regressions, staleness, gaps, crossed books, invalid prices, zero depth, session violations, and reconnect windows.
11. Collect latency distributions by symbol, segment, endpoint, strategy, and time of day, including p50/p90/p95/p99/p99.9/max/jitter.
12. Start shadow mode. Confirm signals, risk decisions, hypothetical orders/fills, PnL, costs, slippage, markouts, reason codes, and latency are recorded while broker order-call count remains zero.
13. Connect the order-update stream without submitting orders and validate authentication/reconnect behavior.
14. Reconcile orders, trades, positions, holdings, funds, and margins against the broker UI/account truth.
15. Run GO/NO-GO review and archive signed evidence.
16. End the session with **NO LIVE ORDER ROUTING**. Enabling routing requires a separate broker lifecycle certification, risk sign-off, and explicit operator authorization outside this runbook.
