from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Iterable

import exchange_calendars as xcals
import pandas as pd

from .models import FillEvent, OrderIntent, Side, StrategyProfile, StrategyState
from .store import StateStore
from .strategy import apply_fill


def cycle_number(cycle_id: str) -> int:
    try:
        return int(cycle_id.rsplit("-", 1)[-1])
    except ValueError as exc:
        raise ValueError(f"cycle id must end in a number: {cycle_id}") from exc


def apply_fills_with_cycles(
    store: StateStore,
    profile: StrategyProfile,
    state: StrategyState,
    pairs: Iterable[tuple[OrderIntent, FillEvent]],
) -> StrategyState:
    ordered = sorted(pairs, key=lambda item: (item[1].filled_at, 0 if item[1].side == Side.SELL else 1, item[1].fill_id))
    for intent, fill in ordered:
        number = cycle_number(state.cycle_id)
        before = state
        if before.quantity == 0 and fill.side == Side.BUY:
            waiting_capital = store.activate_next_cycle_capital(profile.profile_id)
            if waiting_capital:
                state = state.evolved(cash=state.cash + waiting_capital)
                before = state
            store.open_position_cycle(profile.profile_id, number, fill.filled_at, before.cash)
        state = apply_fill(profile, state, intent, fill)
        if before.quantity > 0 and fill.side == Side.SELL and state.quantity == 0:
            cycle_rows = store.list_position_cycles(profile.profile_id)
            starting = Decimal(next((row["starting_capital"] for row in cycle_rows if row["cycle_no"] == number), profile.capital))
            realized = state.cash - starting
            store.close_position_cycle(profile.profile_id, number, fill.filled_at, realized, state)
            snapshot_cycle_session(store, profile, state, fill.filled_at.date(), fill_count=1)
            state = state.evolved(cycle_id=f"{profile.profile_id}-cycle-{number + 1}")
    if ordered and state.quantity > 0:
        snapshot_cycle_session(store, profile, state, ordered[-1][1].filled_at.date(), fill_count=len(ordered))
    return state


def snapshot_cycle_session(
    store: StateStore,
    profile: StrategyProfile,
    state: StrategyState,
    session_date: date,
    *,
    fill_count: int | None = None,
    market_price: Decimal | None = None,
) -> None:
    number = cycle_number(state.cycle_id)
    cycles = store.list_position_cycles(profile.profile_id)
    current = next((row for row in cycles if row["cycle_no"] == number), None)
    if current is None:
        return
    entry = date.fromisoformat(current["entry_session"])
    sessions = xcals.get_calendar("XNYS").sessions_in_range(pd.Timestamp(entry), pd.Timestamp(session_date))
    with store.connect() as db:
        counts = db.execute(
            """SELECT COUNT(DISTINCT b.id) orders,
                      COALESCE(SUM(CASE WHEN b.status LIKE 'CANCEL%' THEN 1 ELSE 0 END),0) cancels
               FROM order_intents i LEFT JOIN broker_orders b ON b.intent_id=i.intent_id
               WHERE i.profile_id=? AND i.session_date=?""",
            (profile.profile_id, session_date.isoformat()),
        ).fetchone()
        recorded_fills = db.execute(
            """SELECT COUNT(*) FROM fills f JOIN order_intents i ON i.intent_id=f.intent_id
               WHERE i.profile_id=? AND substr(json_extract(f.payload,'$.filled_at'),1,10)=?""",
            (profile.profile_id, session_date.isoformat()),
        ).fetchone()[0]
    weather = next((row for row in store.weather_history(profile.symbol) if row["session_date"] <= session_date.isoformat()), None)
    capital = [dict(row) for row in store.capital_events(profile.account_alias) if str(row["occurred_at"]).startswith(session_date.isoformat())]
    store.upsert_cycle_session(
        {
            "profile_id": profile.profile_id,
            "cycle_no": number,
            "session_date": session_date.isoformat(),
            "trading_day_no": len(sessions),
            "calendar_day_no": (session_date - entry).days + 1,
            "t": str(state.t),
            "division_count": profile.division_count,
            "mode": state.mode.value,
            "quantity": state.quantity,
            "avg_cost": str(state.avg_cost),
            "cash": str(state.cash),
            "invested": str(state.cost_basis),
            "market_value": str(market_price * state.quantity) if market_price is not None else None,
            "order_count": counts["orders"],
            "fill_count": recorded_fills if fill_count is None else max(recorded_fills, fill_count),
            "cancel_count": counts["cancels"],
            "weather_payload": json.dumps(weather, ensure_ascii=False, sort_keys=True) if weather else None,
            "capital_payload": json.dumps(capital, ensure_ascii=False, sort_keys=True) if capital else None,
            "reconciliation_status": "REQUIRED" if state.reconciliation_required else "OK",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
