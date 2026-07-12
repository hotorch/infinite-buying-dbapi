# Operator runbook

## Installation and setup

```powershell
uv sync --python 3.12 --extra dev
uv run app setup --account-alias student-001 --save-api-credentials
uv run app profile create p1 --symbol TQQQ --division 40 --capital 10000
uv run app capability verify
```

Capital is USD. Do not enter a KRW amount. Credentials are prompted and stored
through Windows Credential Manager; never place them in `.env`.
Set `IB_DBSEC_REQUESTS_PER_SECOND` only after recording the lowest official
limit among every TR used by this installation. Live mode rejects a missing
value.

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
