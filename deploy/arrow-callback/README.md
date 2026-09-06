# Arrow Callback VPS Bundle

This bundle serves the two URLs registered in Arrow while production order routing remains disabled:

- `GET https://arrow.alphabullacademy.com/auth/callback`
- `POST https://arrow.alphabullacademy.com/order/postback`

It requires a Linux VPS with Docker, inbound TCP 80/443, and the Cloudflare `arrow` DNS record
pointing at the VPS in **DNS only** mode while the origin and certificate are first verified.
Export `ARROW_APP_ID`, `ARROW_APP_SECRET`, and the operator-verified Arrow
user ID as `ARROW_EXPECTED_USER_ID` in the VPS shell or secret manager. Never commit them.

Start from the repository root:

```bash
docker compose -f deploy/arrow-callback/compose.yml up -d --build
curl --fail https://arrow.alphabullacademy.com/healthz
```

The health response must show `routing_enabled: false`. Caddy obtains and renews HTTPS
certificates. The postback journal is stored in the private `arrow-evidence` Docker volume.
HTTP access logging is disabled because Arrow places the temporary request token in the callback
query string.
