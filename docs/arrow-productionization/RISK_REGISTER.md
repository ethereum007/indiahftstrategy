# Risk Register

| Risk | Control | Status |
| --- | --- | --- |
| Accidental live order | Arrow order service defaults disabled and fails closed; shadow has no broker reference | Controlled |
| Secret exposure | Environment/secret-provider input, empty example, structured redaction, CI secret scan | Controlled |
| Duplicate submission after timeout/restart | Durable client ID and append-only submission reservation | Tested |
| Stale/disconnected feed | Feed-age risk limit plus kill-switch triggers | Tested synthetically |
| Unknown/ambiguous instrument | Exact token/identity resolver rejects duplicates, missing, expired, and ambiguous identities | Tested |
| Bad/changed binary layout | Versioned decoder rejects unknown lengths | Tested; live capture BLOCKED_EXTERNAL |
| Rate-limit breach | Per-endpoint configurable budget, burst/minute/daily tracking, Retry-After, pressure signal | Tested |
| Order/update race | OMS explicit UNKNOWN/reconciliation path | State machine implemented; live lifecycle BLOCKED_EXTERNAL |
| Position mismatch/unexpected fill | Halt reasons and reconciliation boundary | Implemented; live proof BLOCKED_EXTERNAL |
| Forward leakage | Online feature state rejects timestamp regression | Tested interface |
| Tail latency | Stage-specific percentile observatory | Synthetic proof; network measurement BLOCKED_EXTERNAL |
| Legacy suite exceeds practical local runtime and uses substantial temporary storage | Separate fast production, quality/security, and six-hour full-regression CI lanes | INCOMPLETE_INTERNAL until CI aggregate is available |
| Empty broker query response mistaken for zero exposure | Query methods fail closed without an injected typed provider | Implemented and tested |
| Approaching configured Arrow quota | Pressure circuit breaker triggers non-auto-resuming kill switch | Implemented and tested |
| Auto-resume after halt | Resume requires reconciliation state and named operator | Tested |
