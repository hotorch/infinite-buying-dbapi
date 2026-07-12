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
