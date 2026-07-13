# Operator runbook

## Installation and setup

```powershell
uv sync --python 3.12 --extra dev
uv run app setup --account-alias student-001 --save-api-credentials
uv run app profile create p1 --symbol TQQQ --division 40 --capital 10000
uv run app capability verify
```

Capital is USD. Do not enter a KRW amount. Credentials are prompted and stored
through Windows Credential Manager. The verified OAuth setting is
`IB_DBSEC_OAUTH_STYLE=form`.

If a DB Securities credential JSON was temporarily copied into `.env`, migrate
it once and then remove the `DB_APPKEY` and `DB_APPSECRET` lines:

```powershell
uv run app setup --account-alias student-001 --import-env-credentials
```

`DB_ENV=real` describes the broker credential bundle; it is separate from the
application's `IB_ENVIRONMENT=preview|paper|live` execution mode.
Set `IB_DBSEC_REQUESTS_PER_SECOND` only after recording the lowest official
limit among every TR used by this installation. Live mode rejects a missing
value.

The read-only balance endpoint may return business code `2679` when there are
no overseas-stock rows. The adapter normalizes that code to an empty holdings
or transaction-history list. Any other non-success business code stops reconciliation and must not be
silently converted to an empty account.

## Read-only DB Securities checks

```powershell
uv run app dbsec auth-status
uv run app dbsec balance
uv run app dbsec holdings
uv run app dbsec transaction-history --start 2026-07-01 --end 2026-07-13
uv run app dbsec current-price --symbol TQQQ
uv run app dbsec daily-chart --symbol TQQQ --start 2026-07-01 --end 2026-07-13
```

These commands have no raw-JSON mode and never call the order path. Reconcile
an existing profile with `uv run app reconcile p1 --environment live`; a
quantity mismatch persists `RECONCILIATION_REQUIRED` and blocks execution.
When no verified rate is configured, read-only commands use a conservative
one-request-per-second local limit. Live reconciliation and orders still
require the verified `IB_DBSEC_REQUESTS_PER_SECOND` setting.

## Daily preview

```powershell
uv run app preview p1 --previous-close 100 --completed-closes 96,97,98,99,100
uv run app scheduler show --session-date 2026-07-13
uv run app scheduler install p1 --confirm
```

Run sell phase after the session-relative premarket time, reconcile, then run
buy phase after the regular open. Preview is the default environment.

## Live controls

Live requires successful testbed evidence plus external legal/risk review:

```powershell
uv run app capability verify --opposing-loc-confirmed --rate-limits-confirmed --evidence "..."
uv run app live enable --legal-review-ack --risk-disclosure-ack
uv run app emergency-stop off
uv run app live approve-today --session-date 2026-07-13
```

Any mismatch must be resolved through `app reconcile`; do not edit SQLite by
hand. An ambiguous order result must be queried at the broker and must never be
blindly resubmitted.

## Recovery

```powershell
uv run app emergency-stop on
uv run app backup create backups/state-20260713.sqlite3
uv run app diagnostics --output diagnostics/report.json --redacted
```

Restore requires `--confirm` and validates SQLite integrity first.
