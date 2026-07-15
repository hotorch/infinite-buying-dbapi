---
name: operate-infinite-buying
description: Operate Pure Infinite Buying V4 profiles for TQQQ and SOXL through the version-pinned infinite-buying-dbapi 0.2 JSON CLI. Use for Slack requests to check readiness or weather, turn real trading ON/OFF, cancel and reconcile orders, allocate settled USD, report cycle/day/T state, or create and manage the three Hermes cron jobs.
---

# Operate Infinite Buying

Use only `uv run app` from the installed project directory. Parse the common JSON envelope and stop whenever `ok` is false. Never edit source, `.env`, environment variables, SQLite, order payloads, or strategy state. Never call a broker endpoint directly.

Read [references/operator-contract.md](references/operator-contract.md) before any mutating request. It contains the safety sequence, command contract, and natural-language mappings.

## Workflow

1. Run `uv run app automation status --json` and the relevant read-only status command.
2. For ON, verify the three cron jobs first, then run `uv run app automation readiness --profile PROFILE`. Continue only when every check passes.
3. Run exactly one requested mutating command. Do not retry `UNKNOWN`, timeout, network, 5xx, or malformed-response outcomes.
4. Run `uv run app reconcile --profile PROFILE --json` after order or cancellation changes.
5. Report only fields returned by the JSON commands. Never infer fills, cash, weather, or broker state.

For cron creation, copy the packaged no-agent script to `~/.hermes/scripts/infinite_buying_runner.py`; do not modify its command list. Use Hermes `cronjob` lifecycle operations and Slack delivery, not Task Scheduler or repository webhook code.

If code changes are needed, turn every profile OFF successfully first. If any profile becomes `LOCKED`, stop and ask the operator to reconcile; do not patch around the lock.
