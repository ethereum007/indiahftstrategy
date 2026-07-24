# NSE Calendar Sources

This directory retains the first authoritative exchange-calendar input used by
the India research path.

## 2026 H1 F&O

`nse_holiday_master_trading_2026-07-23.json` is a byte-for-byte snapshot of
the NSE trading-holiday API:

```text
https://www.nseindia.com/api/holiday-master?type=trading
```

It was retrieved on 2026-07-23 at 15:15:38 UTC. Its SHA-256 is:

```text
798c545acc5351eb9ed84f353c1fcc665a26967426e3761b7097e7f3c7042424
```

The F&O segment is also supported by:

- Annual circular `NSE/FAOP/71777`, dated 2025-12-12:
  `https://nsearchives.nseindia.com/content/circulars/FAOP71777.pdf`
- Amendment `NSE/FAOP/72262`, dated 2026-01-12:
  `https://nsearchives.nseindia.com/content/circulars/FAOP72262.pdf`

The amendment adds the January 15 Maharashtra municipal-election closure.
`nse_fo_2026_h1_sessions.csv` is the deterministic
`nse_holiday_master_fo_json_v1` normalization for 2026-01-01 through
2026-06-30. Weekend holidays are omitted because the market profile already
closes Saturdays and Sundays.

Build and verify the governed calendar:

```powershell
python -m hft_cli build-market-calendar `
  --sessions data\calendars\nse_fo_2026_h1_sessions.csv `
  --authority-source data\calendars\nse_holiday_master_trading_2026-07-23.json `
  --authority-source-schema nse_holiday_master_fo_json_v1 `
  --calendar-id nse-fo-2026-h1-api-20260723-v1 `
  --market india_nse_index_derivatives `
  --valid-from 2026-01-01 `
  --valid-to 2026-06-30 `
  --publisher "National Stock Exchange of India Limited" `
  --source-url "https://www.nseindia.com/api/holiday-master?type=trading" `
  --published-date 2026-01-12 `
  --out runs\market_calendar\nse_fo_2026_h1

python -m hft_cli verify-market-calendar-report `
  --report runs\market_calendar\nse_fo_2026_h1 `
  --fail-on-breach
```

Do not extend this snapshot's coverage through 2026-11-08 without an
authoritative Muhurat Trading timing circular. The NSE snapshot marks that
Sunday with `*` but does not provide open and close times; the normalizer
therefore rejects coverage containing that unresolved special session.
