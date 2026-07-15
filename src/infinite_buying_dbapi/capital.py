from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Iterable, Mapping

from .models import Side
from .store import StateStore


class CapitalError(RuntimeError):
    pass


EVENT_CODE_MAP = {
    "DEPOSIT": "external_deposit",
    "USD_DEPOSIT": "external_deposit",
    "FX_BUY": "fx_conversion",
    "EXCHANGE": "fx_conversion",
    "SELL_SETTLEMENT": "sale_proceeds",
    "WITHDRAWAL": "withdrawal",
    "USD_WITHDRAWAL": "withdrawal",
}


def normalize_capital_rows(account_alias: str, rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Normalize verified broker fixtures. Unknown event types fail closed."""
    events: list[dict[str, Any]] = []
    for row in rows:
        raw_code = str(row.get("event_code") or row.get("TrxTpCode") or "").upper()
        event_type = EVENT_CODE_MAP.get(raw_code)
        if event_type is None:
            raise CapitalError(f"UNSUPPORTED_CAPITAL_EVENT:{raw_code or 'MISSING'}")
        raw_time = row.get("occurred_at") or row.get("transaction_at")
        try:
            occurred_at = raw_time if isinstance(raw_time, datetime) else datetime.fromisoformat(str(raw_time))
            amount = Decimal(str(row.get("amount")))
        except (ValueError, TypeError, ArithmeticError) as exc:
            raise CapitalError("MALFORMED_CAPITAL_EVENT") from exc
        if not amount.is_finite() or amount == 0:
            raise CapitalError("INVALID_CAPITAL_AMOUNT")
        if event_type == "withdrawal":
            amount = -abs(amount)
        else:
            amount = abs(amount)
        currency = str(row.get("currency") or row.get("CrcyCode") or "").upper()
        if currency not in {"USD", "KRW"}:
            raise CapitalError("UNSUPPORTED_CAPITAL_CURRENCY")
        source_id = str(row.get("transaction_id") or row.get("TrxNo") or "")
        if not source_id:
            raise CapitalError("CAPITAL_EVENT_ID_REQUIRED")
        events.append(
            {
                "event_key": f"{account_alias}:{source_id}",
                "account_alias": account_alias,
                "occurred_at": occurred_at.isoformat(),
                "event_type": event_type,
                "currency": currency,
                "amount": str(amount),
                "settled": bool(row.get("settled", False)),
                "source_id": source_id,
            }
        )
    return events


def available_settled_usd(store: StateStore, account_alias: str) -> Decimal:
    total = Decimal(0)
    with store.connect() as db:
        rows = db.execute(
            """SELECT e.event_key,e.amount
               FROM capital_events e WHERE e.account_alias=? AND e.currency='USD' AND e.settled=1""",
            (account_alias,),
        ).fetchall()
        for row in rows:
            amount = Decimal(row["amount"])
            allocated = sum((Decimal(item["amount"]) for item in db.execute("SELECT amount FROM capital_allocations WHERE event_key=?", (row["event_key"],))), Decimal(0))
            total += amount - allocated if amount > 0 else amount
    return max(Decimal(0), total)


def reserved_buy_notional(store: StateStore, profile_id: str) -> Decimal:
    with store.connect() as db:
        rows = db.execute(
            """SELECT i.budget FROM order_intents i LEFT JOIN broker_orders b ON b.intent_id=i.intent_id
               WHERE i.profile_id=? AND i.side=? AND (i.status='PENDING' OR b.status IN ('ACCEPTED','OPEN','PARTIAL','CANCEL_REQUESTED'))""",
            (profile_id, Side.BUY.value),
        ).fetchall()
    return sum((Decimal(row["budget"]) for row in rows), Decimal(0))


def apply_allocation(store: StateStore, profile_id: str, amount: Decimal, timing: str) -> dict[str, Any]:
    if timing not in {"current_cycle", "next_cycle"}:
        raise CapitalError("timing must be current_cycle or next_cycle")
    if amount <= 0:
        raise CapitalError("allocation amount must be positive")
    profile = store.get_profile(profile_id)
    available = available_settled_usd(store, profile.account_alias)
    if amount > available:
        raise CapitalError("ALLOCATION_EXCEEDS_SETTLED_USD")
    state = store.get_state(profile_id)
    if reserved_buy_notional(store, profile_id) > state.cash:
        raise CapitalError("RESERVED_ORDERS_EXCEED_PROFILE_CASH")

    remaining = amount
    selected: list[str] = []
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        rows = db.execute(
            """SELECT e.event_key,e.amount
               FROM capital_events e WHERE e.account_alias=? AND e.currency='USD' AND e.settled=1
               AND CAST(e.amount AS REAL)>0 ORDER BY e.occurred_at,e.event_key""",
            (profile.account_alias,),
        ).fetchall()
        for row in rows:
            if remaining <= 0:
                break
            allocated = sum((Decimal(item["amount"]) for item in db.execute("SELECT amount FROM capital_allocations WHERE event_key=?", (row["event_key"],))), Decimal(0))
            event_amount = Decimal(row["amount"]) - allocated
            take = min(remaining, event_amount)
            if take <= 0:
                continue
            db.execute(
                "INSERT INTO capital_allocations(event_key,profile_id,amount,timing,status,created_at) VALUES (?,?,?,?,?,CURRENT_TIMESTAMP)",
                (row["event_key"], profile_id, str(take), timing, "applied" if timing == "current_cycle" else "waiting_next_cycle"),
            )
            remaining -= take
            selected.append(row["event_key"])
        if remaining != 0:
            raise CapitalError("ALLOCATION_MUST_MATCH_WHOLE_CAPITAL_EVENTS")
        if timing == "current_cycle":
            state_row = db.execute("SELECT payload,version FROM strategy_states WHERE profile_id=?", (profile_id,)).fetchone()
            if state_row is None:
                raise CapitalError("PROFILE_STATE_NOT_FOUND")
            from .models import canonical_json
            from .store import _now, _state_from_json

            state = _state_from_json(state_row["payload"])
            updated = state.evolved(cash=state.cash + amount)
            db.execute(
                "UPDATE strategy_states SET payload=?,version=?,updated_at=? WHERE profile_id=? AND version=?",
                (canonical_json(updated), updated.version, _now(), profile_id, state.version),
            )
            capital_row = db.execute("SELECT capital FROM profiles WHERE profile_id=?", (profile_id,)).fetchone()
            db.execute("UPDATE profiles SET capital=? WHERE profile_id=?", (str(Decimal(capital_row["capital"]) + amount), profile_id))
            cycle_no = int(state.cycle_id.rsplit("-", 1)[-1])
            cycle_row = db.execute("SELECT capital_added FROM position_cycles WHERE profile_id=? AND cycle_no=?", (profile_id, cycle_no)).fetchone()
            if cycle_row is not None:
                db.execute("UPDATE position_cycles SET capital_added=? WHERE profile_id=? AND cycle_no=?", (str(Decimal(cycle_row["capital_added"]) + amount), profile_id, cycle_no))
    return {"profile_id": profile_id, "amount": str(amount), "timing": timing, "event_keys": selected}
