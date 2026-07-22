# Versioned Market Calendars

Use a market-calendar JSON input whenever research or capture evidence spans
dates whose exchange status matters. The platform fingerprints the source file
and fails closed outside its declared coverage. It does not ship guessed NSE
holiday dates.

## Contract

The JSON schema version is `1`:

```json
{
  "schema_version": 1,
  "calendar_id": "publisher-calendar-version",
  "market": "india_nse_index_derivatives",
  "timezone": "Asia/Kolkata",
  "valid_from": "YYYY-MM-DD",
  "valid_to": "YYYY-MM-DD",
  "provenance": {
    "publisher": "authoritative publisher",
    "source_url": "https://authoritative.example/calendar",
    "published_date": "YYYY-MM-DD"
  },
  "sessions": [
    {
      "date": "YYYY-MM-DD",
      "status": "closed",
      "label": "exchange holiday"
    },
    {
      "date": "YYYY-MM-DD",
      "status": "open",
      "open_time": "18:00:00",
      "close_time": "19:00:00",
      "label": "special session"
    }
  ]
}
```

Dates omitted from `sessions` use the market profile's regular weekday and
session hours. A `closed` override cannot carry times. An `open` override must
carry explicit `HH:MM:SS` open and close times, including for weekend or
special sessions. Duplicate overrides and overrides outside the coverage range
are rejected.

## Evidence Rules

- A supplied calendar must match the selected market and timezone.
- Dates before `valid_from` or after `valid_to` are rejected as
  `calendar_out_of_range`.
- Explicit closures are reported as `calendar_closed`.
- Ordinary weekends and intraday session violations remain separate reasons.
- The calendar path and SHA-256 are retained in manifests, summaries, configs,
  and runbooks.
- Calendar reports and all downstream artifacts remain non-authorizing.

Validate and fingerprint a calendar before use:

```powershell
python -m hft_cli market-calendar-report `
  --calendar path/to/market_calendar.json `
  --market india_nse_index_derivatives `
  --out runs/market_calendar
```

Pass the same file to normalization, diagnostics, vendor/provider batch, broker
readiness, or live-session commands with `--market-calendar`. The live-session
planner carries that argument into its generated post-capture batch command.
