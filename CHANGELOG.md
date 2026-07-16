# Changelog

## Unreleased

- Updated the Hermes handoff, README, agent guidance, and beginner manuals to match the 0.2.0 CLI and safety contract.
- Clarified that weather is reporting-only, Hermes is read-only by default, `automation tick` can place real orders, and UNKNOWN handling starts with the emergency stop.

## 0.2.0 - 2026-07-15

- Replaced local paper, daily approvals, Task Scheduler, and repository Slack delivery with OFF/ON/LOCKED profiles and a Hermes-owned JSON automation contract.
- Added SQLite v1→v2 migration, composite broker order identity, cross-day UNKNOWN tracking, cycle/session ledgers, weather snapshots, capital events, and automation claims.
- Added the embedded `regime-weather-1` engine for TQQQ/QQQ/SPY and SOXL/SMH/SPY, shared backtesting, and five-symbol DB Securities market-data collection.
- Added settled-USD allocation choices, stable position/order/report JSON commands, dashboard updates, and one relative-path-based Hermes project handoff document.
- Kept real ordering fail-closed until instructor-account LOC/LIMIT/MOC, cancellation, partial-fill, and timeout-reconciliation evidence is recorded.

- Replaced the conflicting MIT notice with consistent all-rights-reserved terms that prohibit recipient redistribution without prior written permission.
- Changed the DB Securities OAuth default to the form contract verified by the downloadable specification, official testbed sample, and a real-key read-only call.
- Added one-time import of DB-issued `DB_APPKEY`, `DB_APPSECRET`, `DB_ENV`, and `DB_EXPIRE_DATE` values into Windows Credential Manager.
- Treat DB Securities balance code `2679` as an empty overseas-stock balance while preserving fail-closed handling for every other error code.
- Documented the distinction between broker credential metadata and application execution settings.
- Added read-only `dbsec` CLI commands for auth status, balances, holdings, transaction history, current price, and daily candles with minimal redacted output.
- Added paginated holdings validation, sanitized HTTP failures, credential-expiry preflight, token retry timestamps, and fail-closed live reconciliation coverage.

## 0.1.0 - 2026-07-12

- Added deterministic `pure-v4-ruleset-1` for TQQQ and SOXL.
- Added 20/40 live-candidate and 30 experimental profile validation.
- Added SQLite outbox, fill ledger, reconciliation, backup, audit, and crash-safe idempotency.
- Added DB Securities OAuth, order, orderable amount, transaction, balance, price, and daily-chart contracts.
- Added session-relative Windows scheduler, live gates, emergency stop, and redacted diagnostics.
- Added replay, golden vectors, testbed protocol, and operator documentation.
- Added a Korean beginner README and seven indexed step-by-step manuals.
- Added explicit JSON/form OAuth selection because two official DB Securities documents differ; form is now the verified default.
