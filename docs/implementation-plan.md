# Pure Infinite Buying V4 + DB Securities implementation contract

This repository implements `pure-v4-ruleset-1` as a deterministic Windows
CLI. Strategy code has no broker, database, clock, environment-variable, or
network dependency. SQLite owns strategy decisions and local state; DB
Securities owns actual orders, fills, and holdings. A mismatch stops new
orders.

## Delivery stages

1. Ruleset, golden vectors, deterministic replay.
2. Read-only DB Securities inquiries and reconciliation.
3. Test-account opposing LOC, correction/cancellation, partial-fill, and
   ambiguous-timeout verification.
4. At least 20 US sessions of shadow operation with zero duplicate or
   unreconciled orders.
5. Per-installation legal/risk acknowledgement and per-session live approval.

Live mode is fail-closed. Division 30 is experimental, KRW settlement is not
live-eligible in v1, and an unverified capability cannot be overridden by an
ordinary run command.

## DB Securities credential and OAuth contract

DB Securities may deliver a credential bundle with `appkey`, `appsecret`,
`env`, and `expire_date`. This bundle is not the application's `.env` schema:

- `appkey` and `appsecret` are long-lived credentials used to issue an access
  token.
- `env=real` identifies a real-account credential bundle. v1 does not infer or
  invent a separate paper domain from this value.
- `expire_date` is the APP KEY/SECRET expiry date in `YYYYMMDD` format, not the
  access-token expiry.
- Only the OAuth fields documented for the selected request style are sent to
  `/oauth2/token`; bundle metadata is never copied into the request body.

The verified default is `IB_DBSEC_OAUTH_STYLE=form`, using
`application/x-www-form-urlencoded`, `appkey`, `appsecretkey`,
`grant_type=client_credentials`, and `scope=oob`. The public how-to page also
shows a JSON contract, so `json` remains an explicit compatibility option but
is never attempted automatically after a form failure. Token issuance is
limited to one request per minute, and a successful token is cached in Windows
Credential Manager until five minutes before expiry.

Secrets must normally be entered with `app setup --save-api-credentials`.
`--import-env-credentials` is a one-time migration path for
`DB_APPKEY`, `DB_APPSECRET`, `DB_ENV`, and `DB_EXPIRE_DATE`; it validates the
environment and expiry, stores only the key and secret in Windows Credential
Manager, and instructs the operator to delete the secret lines from `.env`.

## Read-only verification evidence

On 2026-07-12, a real-account credential completed form OAuth with HTTP 200
and `expires_in=86400`. The production adapter then reached
`/api/v1/trading/overseas-stock/inquiry/balance-margin` with HTTP 200. DB
Securities returned business code `2679` (`조회내역이 없습니다`) for an account
with no overseas-stock rows. `DbSecBroker.holdings()` treats only this explicit
code as an empty result; other non-`00000` codes remain errors.

This evidence verifies credential parsing, form OAuth, token caching, the
balance request schema, and empty-balance handling. It does not verify orders,
opposing LOC, partial fills, correction/cancellation, full reconciliation, or
live eligibility. Those remain gated by delivery stages 3 through 5.

Stage 2 exposes only safe projections through `app dbsec auth-status`,
`balance`, `holdings`, `transaction-history`, `current-price`, and
`daily-chart`. Raw broker JSON is intentionally unavailable. Live
`app reconcile PROFILE --environment live` reads transaction history and
holdings, and persists `reconciliation_required=true` on any quantity or
unknown-order mismatch before execution can proceed.

## Architecture

- `models.py`, `strategy.py`: immutable domain contracts and pure transitions.
- `store.py`: SQLite migrations, optimistic state locking, outbox, audit log.
- `broker.py`: preview, paper, and DB Securities broker boundaries.
- `execution.py`: holdings/notional checks and live gates.
- `market_calendar.py`: XNYS sessions, DST, holidays, and early closes.
- `service.py`, `cli.py`: two-phase planning and operator commands.
- `replay.py`: deterministic synthetic fill replay using the production core.

Hermes integration is intentionally data-only in v1. Future advisory proposals
are stored as rejected by default and cannot mutate strategy state or broker
payloads.
