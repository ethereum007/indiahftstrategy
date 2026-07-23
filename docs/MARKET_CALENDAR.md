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

## Compile An Authoritative Session File

`build-market-calendar` converts an operator-normalized session CSV into the
canonical JSON contract, validates it before writing any output, and emits the
usual governed calendar report. It does not scrape an exchange webpage or
claim to understand arbitrary NSE, Arrow.money, iRage, or broker exports.
Obtain the authoritative source separately and normalize its exceptional
sessions into these exact ordered columns:

```csv
date,status,open_time,close_time,label
2026-01-26,closed,,,exchange holiday
2026-02-01,open,09:15:00,15:30:00,special session
```

The compiler requires:

- `date` in `YYYY-MM-DD` form within the declared coverage period.
- `status` equal to `closed` or `open`.
- Blank times for a closed date and explicit `HH:MM:SS` times for an open
  override.
- Exactly one row per exceptional date.
- Publisher, source URL, publication date, calendar ID, and market supplied
  explicitly by the operator.

The timezone is derived from the selected market profile, not accepted as a
free-form CLI value. The untouched CSV is retained as a manifest-fingerprinted
input, while its schema version, filename, and SHA-256 are embedded in the
generated JSON provenance:

```powershell
python -m hft_cli build-market-calendar `
  --sessions data\calendars\nse_fo_2026_sessions.csv `
  --calendar-id nse-fo-2026-v1 `
  --market india_nse_index_derivatives `
  --valid-from 2026-01-01 `
  --valid-to 2026-12-31 `
  --publisher "authoritative publisher" `
  --source-url "https://authoritative.example/calendar" `
  --published-date 2025-12-15 `
  --out runs\market_calendar\nse_fo_2026
```

The output includes `market_calendar.json`, report CSVs, a runbook, and a
manifest. No exchange dates are bundled by the platform, and the resulting
evidence remains non-authorizing.

## Verify Retained Evidence

Reconstruct a retained report from its manifest-bound source before using it
downstream:

```powershell
python -m hft_cli verify-market-calendar-report `
  --report runs\market_calendar\nse_fo_2026 `
  --fail-on-breach
```

The verifier supports both `market-calendar-report` outputs and calendars
compiled by `build-market-calendar`. It requires a current source fingerprint,
the complete manifest-tracked artifact set, exact manifest parameters and
metadata, deterministic report CSVs and runbook, and the explicit
non-authorizing claim. For a compiled calendar it also regenerates the
canonical JSON from the retained session CSV and compares it byte for byte.
Editing an artifact and writing a fresh manifest does not make the report
semantically valid.

`review-data-readiness` invokes this verifier automatically whenever
`--market-calendar-report` is supplied. Its own manifest separately
fingerprints the calendar report directory, report manifest, and external
calendar source, so later source, manifest, or artifact drift invalidates the
readiness lineage.

## Evidence Rules

- A supplied calendar must match the selected market and timezone.
- Dates before `valid_from` or after `valid_to` are rejected as
  `calendar_out_of_range`.
- Explicit closures are reported as `calendar_closed`.
- Ordinary weekends and intraday session violations remain separate reasons.
- The calendar path and SHA-256 are retained in manifests, summaries, configs,
  and runbooks.
- Tick and chain diagnostic summaries retain the same calendar ID, coverage,
  and SHA-256 used to classify their timestamps.
- A data-readiness run can require a validated calendar report and fails if
  mapped data or diagnostics use a different ID, fingerprint, or coverage.
- A directory-backed data-readiness run fails closed unless the retained
  calendar report reconstructs from its current manifest-bound source.
- A multi-dataset comparison can require complete calendar evidence and one
  consistent calendar source across every daily readiness run.
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
Vendor and provider pipelines that receive this argument automatically write a
`00_market_calendar` report and make it mandatory in nested data readiness.

For a direct readiness assembly, bind the validated report explicitly:

```powershell
python -m hft_cli review-data-readiness `
  --market-calendar-report runs/market_calendar `
  --mapped-data runs/normalized `
  --tick-diagnostics runs/diagnostics `
  --require-market-calendar `
  --out runs/data_readiness `
  --fail-on-breach
```

For multi-day or walk-forward evidence, require both complete coverage and a
single source fingerprint:

```powershell
python -m hft_cli compare-data-readiness `
  --readiness runs/day_1/readiness runs/day_2/readiness `
  --require-market-calendar `
  --require-consistent-market-calendar `
  --out runs/calendar_bound_comparison `
  --fail-on-breach
```
