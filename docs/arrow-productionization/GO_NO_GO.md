# Arrow Go / No-Go

Decision: **NO-GO for live routing; READY for static-IP connectivity certification.**

## Internal gates

- [x] Broker-neutral contracts and adapter boundary
- [x] Credential-free CI and deterministic fake tests
- [x] Environment-only configuration and secret redaction
- [x] Official Data Stream L1/L5/CAS decoder contract
- [x] Exact instrument resolver
- [x] Independent risk, kill switch, OMS recovery/idempotency
- [x] Recorder, data-quality checks, and latency observatory
- [x] Shadow/live routing separation
- [x] Configurable rate-limit architecture
- [x] Production boundary: 37 passed, 0 failed, 89% coverage
- [x] Lint, format, type, static-security, and dependency-audit gates
- [ ] `INCOMPLETE_INTERNAL` Full 2,909-test legacy regression aggregate (local clean run was interrupted after 96%)

## External gates

- [ ] `BLOCKED_EXTERNAL` Static IP approved and verified
- [ ] `BLOCKED_EXTERNAL` Authentication and account identity certified
- [ ] `BLOCKED_EXTERNAL` Live instrument master certified
- [ ] `BLOCKED_EXTERNAL` Market and order streams captured and validated
- [ ] `BLOCKED_EXTERNAL` Real data-quality and latency thresholds passed
- [ ] `BLOCKED_EXTERNAL` Shadow sessions and reconciliation passed
- [ ] Separate live-order lifecycle certification and explicit authorization

Passing internal tests does not authorize order submission. Static-IP connectivity and shadow
certification may proceed when access arrives, but production routing remains NO-GO until both the
internal full-regression lane and every external gate pass with explicit operator authorization.
