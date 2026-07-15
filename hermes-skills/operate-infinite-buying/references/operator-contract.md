# Operator contract

## Non-negotiable boundary

- Version: app `0.2.x`; strategy `pure-v4-ruleset-1`; weather `regime-weather-1`.
- Weather may explain or allocate new settled USD. It never changes V4 price, quantity, `T`, reverse mode, or an open cycle.
- `T` is strategy progress, not trading-day count. A cycle starts on its first BUY fill and ends when a SELL fill makes quantity zero. Same-time fills apply SELL before BUY.
- Profiles are `OFF`, `ON`, or `LOCKED`. Use `LOCKED` only for mechanical uncertainty or mismatch.
- Do not add an approval step or a fixed daily/order dollar cap. The CLI enforces allocated cash, holdings, broker orderable amount, settled USD, and optional operator limits.
- Do not expose credentials, tokens, account numbers, raw broker responses, or Slack secrets.

## Natural-language mapping

| User intent | Required sequence |
| --- | --- |
| `TQQQ 실주문 시작` | Ensure cron jobs exist and are verified → `automation readiness --profile TQQQ_PROFILE` → show blockers or `automation on --profile ... --cron-verified` |
| `SOXL 꺼줘` | `automation off --profile SOXL_PROFILE`; OFF blocks first, then cancels and reconciles |
| `이번 입금은 다음 회차` | `capital status` → identify the exact settled USD event/amount → `capital apply --profile ... --amount ... --timing next_cycle` |
| `현재 회차와 오늘 날씨 보고` | `position status PROFILE --json` + `weather current --symbol SYMBOL --json` |
| `미체결 전부 정리` | Run `automation off` for each requested profile; do not loop direct cancel commands |

For an open-cycle deposit, ask exactly: (1) add cash now while preserving current `T` and cost, or (2) wait unallocated until the next cycle. With no response, leave it unallocated and include it in the daily report.

## Stable JSON commands

```text
uv run app automation readiness --profile PROFILE
uv run app automation on --profile PROFILE --cron-verified
uv run app automation off --profile PROFILE
uv run app automation status [PROFILE] --json
uv run app automation tick --all --quiet-when-idle
uv run app capital scan
uv run app capital status
uv run app capital propose --profile PROFILE --amount USD
uv run app capital apply --profile PROFILE --amount USD --timing current_cycle|next_cycle
uv run app reconcile --profile PROFILE --json
uv run app report daily --session-date latest --json
uv run app position status [PROFILE] --json
uv run app position cycles [PROFILE] --json
uv run app position sessions PROFILE --cycle N --json
uv run app orders list --profile PROFILE --json
uv run app weather update|current|history --symbol TQQQ|SOXL --json
```

Every public response has `schema_version`, `ok`, `data`, `warnings`, `errors`, and `generated_at`. An empty stdout from the live runner means idle success. A nonzero exit is an alert and must not be retried automatically.

## Hermes cron setup

Create with the unified `cronjob` tool, set an absolute project `workdir`, and deliver to `slack` (the configured Slack home channel).

1. `live-runner`: schedule `every 5m`, `no_agent=true`, script `infinite_buying_runner.py`, argument/mode `live`. Empty stdout suppresses delivery.
2. `capital-watch`: schedule `every 30m`, `no_agent=true`, same script, mode `capital`. Wake an agent only when the command returns a new event; never invent a capital event.
3. `morning-report`: schedule `0 8 * * *` in Asia/Seoul, attach this skill, and prompt: `Run app report daily --session-date latest --json. If ok, write a concise Korean Slack report using only returned fields. If not ok, report the errors without retrying.`

List and verify all three jobs before ON. Pause `live-runner` when every profile is OFF. Cron executions cannot create other cron jobs.

Slack must have allowed Member IDs, an allowed channel list, and a home channel configured in Hermes. Keep tokens in Hermes storage/OS keychain; never in this repository.
