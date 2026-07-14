# Pure Infinite Buying V4 + DB Securities

**Pure Infinite Buying V4 + DB Securities** is a deterministic Windows CLI (Python 3.12) that computes the `순수 무한매수 V4` strategy for TQQQ/SOXL and safely prepares, records, and reconciles orders through the DB Securities (DB증권) Open API. Real orders are fail-closed behind multiple gates. Package `infinite_buying_dbapi`; CLI entry `app` (`uv run app ...`); app version 0.1.0; strategy version `pure-v4-ruleset-1`.

## Prime directives (safety-critical)

Always-on. This handles real money on leveraged ETFs — when in doubt, fail closed.

- **Pure strategy core.** `src/infinite_buying_dbapi/strategy.py` and `src/infinite_buying_dbapi/models.py` must have **no broker, DB, clock, env-var, or network dependency**; same input → same output. Golden vectors in `tests/golden/` guard this.
- **No live path on unverified capability.** Never build a real `live` order path on an unverified DB Securities capability. Verified vs unverified is tracked in `docs/dbsec-capability-matrix.md` (확인됨 vs 확인 필요).
- **Live mode fails closed.** `RECONCILIATION_REQUIRED` blocks new orders; never resend an ambiguous/timed-out order; never hand-edit the SQLite state file.
- **Immutable-versioned ruleset.** To change strategy rules, create a NEW ruleset version + NEW golden vectors — never overwrite `pure-v4-ruleset-1`.
- **Secrets never leak.** APP_KEY / APP_SECRET / access token / account number never appear in committed `.env`, README, logs, or command output. Storage is Windows Credential Manager via `keyring`; `security.py` redacts; diagnostics stay `--redacted`.

## Project map

Source — `src/infinite_buying_dbapi/`:

| Path | Role |
| --- | --- |
| `src/infinite_buying_dbapi/models.py` | Immutable domain contracts & pure types; constants `RULESET_VERSION`, `SUPPORTED_SYMBOLS={TQQQ,SOXL}`, `SUPPORTED_DIVISIONS={20,30,40}`. |
| `src/infinite_buying_dbapi/strategy.py` | Pure V4 transitions (no I/O). |
| `src/infinite_buying_dbapi/store.py` | SQLite migrations, optimistic state locking, outbox, fill ledger, audit log. |
| `src/infinite_buying_dbapi/broker.py` | Preview / paper / DB Securities broker boundaries. |
| `src/infinite_buying_dbapi/auth.py` | DB Securities OAuth token issue + cache. |
| `src/infinite_buying_dbapi/execution.py` | Holdings/notional preflight checks and live gates. |
| `src/infinite_buying_dbapi/reconciliation.py` | Broker-vs-local compare; sets `reconciliation_required` on mismatch. |
| `src/infinite_buying_dbapi/market_calendar.py` | XNYS sessions, DST, holidays, early closes. |
| `src/infinite_buying_dbapi/rate_limit.py` | Cross-process DB Securities request interval. |
| `src/infinite_buying_dbapi/replay.py` | Deterministic synthetic fill replay via the production core. |
| `src/infinite_buying_dbapi/service.py` | Two-phase (sell/buy) planning. |
| `src/infinite_buying_dbapi/cli.py` | Typer operator commands. |
| `src/infinite_buying_dbapi/config.py` | pydantic-settings (`IB_*` env), keyring-backed secrets. |
| `src/infinite_buying_dbapi/security.py` | Keyring secret storage + sensitive-key redaction. |

Docs — read the relevant one before changing related code:

| Path | Role |
| --- | --- |
| `docs/implementation-plan.md` | Architecture & delivery-stage contract (developer reference). |
| `docs/dbsec-capability-matrix.md` | Verified vs unverified DB Securities capabilities. |
| `docs/ruleset-1.md` | V4 formula & partial-fill rules (strategy source of truth). |
| `docs/testbed-protocol.md` | Opposing-LOC test that must pass before live enablement. |
| `docs/operations.md` | Operator runbook. |
| `docs/manuals/README.md` + `docs/manuals/01`..`07` | Korean beginner manuals. |
| `README.md` | Korean user guide; §1 lists what the program does NOT do. |

## Rules & conventions

- Python ≥3.12, `uv`-managed. Install deps with `uv sync --python 3.12` (add `--extra dev` for tests).
- Lint: ruff, select `E4,E7,E9,F,I`, line-length 160, target py312.
- Tests: pytest; coverage source `infinite_buying_dbapi`, `fail_under = 80`; golden vectors in `tests/golden/`.
- Windows quirks, Korean/English reply mirroring, and Karpathy coding principles live in `~/.claude/CLAUDE.md` and apply here — don't restate them.

## Capability boundaries

- **What the system does NOT do** (recommend tickers, predict markets, make LLM/Hermes trade decisions, guarantee/limit losses, change strategy without approval, invent unverified broker behavior) → see `README.md` §1.
- **Verified vs unverified DB Securities capabilities** → `docs/dbsec-capability-matrix.md`. Do not code a real-order path on a `확인 필요` capability.
- **Hermes/LLM is data-only in v1.** Advisory proposals are stored rejected-by-default and cannot mutate strategy state or broker payloads.
- **CLI surface:** `setup`, `profile`, `preview`, `capability verify`, `run sell-phase|buy-phase`, `reconcile`, `orders`, `live`, `emergency-stop`, `backup`, `scheduler`, `dbsec` (read-only), `diagnostics`.

## Lessons learned / guardrails

- **OAuth style.** Two official DB Securities docs disagree. Verified default `IB_DBSEC_OAUTH_STYLE=form` (`x-www-form-urlencoded`; fields `appkey`, `appsecretkey`, `grant_type=client_credentials`, `scope=oob`). `json` is explicit compatibility only; never auto-retry the other style (issuance limited to 1/min).
- **Balance code `2679`** = "no rows" → normalize to empty holdings/transactions. Every other non-`00000` code stays a fail-closed error (never silently treat as an empty account).
- **Credential bundle ≠ app `.env`.** DB-issued `appkey`/`appsecret`/`env`/`expire_date` differ from the app schema. Only key+secret go to Credential Manager; `expire_date` is APP-KEY expiry (not token expiry); `DB_ENV=real` is metadata, not the app's `IB_ENVIRONMENT`.
- **Accounting limits.** KRW settlement is not live-eligible in v1 (USD-only accounting). Division 30 is experimental (preview/paper only).

## Commands

```powershell
uv sync --python 3.12 --extra dev            # install (with tests)
uv run app --help                            # CLI surface
uv run ruff check .                          # lint
uv run pytest --cov=infinite_buying_dbapi    # tests + coverage
uv build                                     # build package
```

## Execution model

**Execution model (Advisor/Worker): see `.claude/rules/execution-model.md`.**
