# Risk Register

| Risk | Control | Status |
| --- | --- | --- |
| Accidental live order | Arrow order service defaults disabled and fails closed; shadow has no broker reference | Controlled |
| Wrong egress IP supplied to Arrow | Public-IP validation, observed/configured exact match, and TLS endpoint evidence | Tooling tested; acquired IP not yet certified |
| Request token leaked through web logs | Callback access logging disabled; browser response and errors never echo tokens | Tested/configured |
| Callback authenticates wrong account | Mandatory operator-pinned Arrow user ID checked before accepting token | Tested |
| Untrusted postback mutates trading state | Postback only writes size-limited hash-chained evidence and has no routing/OMS reference | Tested; live schema/authenticity BLOCKED_EXTERNAL |
| Secret exposure | Environment/secret-provider input, empty example, structured redaction, CI secret scan | Controlled |
| Duplicate submission after timeout/restart | Durable client ID and append-only submission reservation | Tested |
| Stale/disconnected feed | Feed-age risk limit plus stale timeout, close-before-backoff, bounded reconnect, subscription restoration, and halt callbacks | Tested synthetically |
| Infinite reconnect flapping | Retry budget resets only after a successful receive, not after handshake alone | Tested deterministically |
| Unknown/ambiguous instrument | Exact token/identity resolver and checksum-bound master reject schema errors, duplicates, missing, expired, and ambiguous identities | Tested |
| Silent instrument-master change | Versioned snapshot checksum and token-level additions/removals/changes | Tested |
| Bad/changed binary layout | Versioned decoder rejects unknown lengths | Tested; live capture BLOCKED_EXTERNAL |
| Rate-limit breach | Per-endpoint configurable budget, burst/minute/daily tracking, Retry-After, pressure signal | Tested |
| Order/update race | OMS explicit UNKNOWN/reconciliation path | State machine implemented; live lifecycle BLOCKED_EXTERNAL |
| Position mismatch/unexpected fill | Halt reasons and reconciliation boundary | Implemented; live proof BLOCKED_EXTERNAL |
| Forward leakage | Online feature state rejects timestamp regression | Tested interface |
| Tail latency | Stage-specific percentile observatory | Synthetic proof; network measurement BLOCKED_EXTERNAL |
| Corrupt shadow evidence | Hash-chained journal verifies every event on start and fails on tampering | Tested |
| Feed timestamps silently degrade | Automatic regression, gap, stale, and market-session checks | Tested synthetically |
| Legacy suite exceeds practical local runtime and uses substantial temporary storage | Separate fast production, quality/security, and six-hour full-regression CI lanes | INCOMPLETE_INTERNAL; six-hour lane timed out without aggregate |
| Empty broker query response mistaken for zero exposure | Query methods fail closed without an injected typed provider | Implemented and tested |
| Approaching configured Arrow quota | Pressure circuit breaker triggers non-auto-resuming kill switch | Implemented and tested |
| Auto-resume after halt | Resume requires reconciliation state and named operator | Tested |
