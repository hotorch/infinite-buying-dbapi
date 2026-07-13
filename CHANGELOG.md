# Changelog

## Unreleased

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
