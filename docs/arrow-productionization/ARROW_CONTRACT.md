# Arrow Contract

The implementation is based on Arrow's official documentation as reviewed on 2026-09-05:

- Authentication: <https://docs.arrow.trade/authentication/>
- Symbols/API endpoints: <https://docs.arrow.trade/rest-api/api/>
- Orders: <https://docs.arrow.trade/rest-api/orders/>
- Market Data: <https://docs.arrow.trade/rest-api/market-data/>
- Order Data: <https://docs.arrow.trade/rest-api/order-data/>
- Rate limits: <https://docs.arrow.trade/rate-limits/>

## Confirmed contracts implemented

- Token-exchange checksum: SHA-256 of `appID:appSecret:request-token`.
- Redirect checksum helper: SHA-256 of `request-token:appID`.
- Market WebSocket endpoint and query authentication are configuration-driven.
- Subscription messages use `code`, `mode`, and a token array keyed by mode.
- Big-endian packet sizes: LTP 13, LTPC 17, quote 93, full 249 bytes; the CAS trailer adds 16 bytes.
- Full mode contains five bid and five ask levels, each quantity (8), price (4), order count (2), beginning at byte 109.
- Order updates use `wss://order-updates.arrow.trade`, JSON `ORDER_UPDATE` messages, and a client `PONG` every three seconds with a five-second read timeout.

The general Data Stream decoder has a reviewed version identifier and rejects every unknown length. It does not guess. HFT feed layouts, order-stream messages, heartbeat/sequence semantics, and live REST response variants remain `BLOCKED_EXTERNAL` until captured and certified.

The order-update transport uses an injected handshake so credential placement is not guessed. Its
lifecycle, documented `PONG` heartbeat, five-second read timeout, parser, event bus, and bounded
reconnect policy are testable without network access. Live handshake and captured lifecycle proof
remain `BLOCKED_EXTERNAL`.

## Security boundary

Credentials are accepted only through environment values or a token-provider abstraction. They are never persisted by this package. Order routing is false by default and is intentionally not enabled in this sprint.
