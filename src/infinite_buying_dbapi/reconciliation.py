from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from .broker import DbSecBroker
from .models import FillEvent, IntentRole, Side, StrategyProfile, StrategyState
from .positions import apply_fills_with_cycles
from .store import StateStore


def reconcile_dbsec(store: StateStore, broker: DbSecBroker, profile: StrategyProfile, session_date: date) -> StrategyState:
    state = store.get_state(profile.profile_id)
    unresolved = store.unresolved_orders(profile.profile_id)
    start_date = min((date.fromisoformat(row["order_date"]) for row in unresolved), default=session_date)
    records = broker.transaction_history(start_date, session_date, profile.symbol)
    unresolved_broker_order = False
    for row in records:
        order_no = str(row.get("OrdNo", ""))
        if not order_no:
            continue
        try:
            raw_order_date = str(row.get("OrdDt") or "")
            order_date = datetime.strptime(raw_order_date, "%Y%m%d").date() if len(raw_order_date) == 8 else None
            local_order = store.get_order(order_no, profile.account_alias, order_date)
        except KeyError:
            state = _flag_mismatch(store, state, f"unknown broker order {order_no}")
            unresolved_broker_order = True
            continue
        intent = store.get_intent(local_order["intent_id"])
        executed = _int_qty(row.get("AstkExecQty"))
        remaining = _int_qty(row.get("AstkOrdRmqty"))
        rejected = str(row.get("AstkRjtCode", "")).strip() not in {"", "0", "00000"}
        cancelled = str(row.get("OrdCnclYn") or row.get("AstkCnclYn") or "").upper() in {"Y", "1", "TRUE"}
        status = (
            "REJECTED"
            if rejected
            else "CANCELLED_PARTIAL"
            if cancelled and executed
            else "CANCELLED"
            if cancelled
            else "FILLED"
            if executed and not remaining
            else "PARTIAL"
            if executed
            else "OPEN"
            if remaining
            else "UNKNOWN"
        )
        store.update_order_status(order_no, status, executed, remaining, profile.account_alias, order_date)
        exec_no = str(row.get("ExecNo", "0"))
        if executed <= 0 or exec_no in {"", "0"}:
            continue
        fill = FillEvent(
            broker_order_no=order_no,
            fill_id=exec_no,
            intent_id=intent.intent_id,
            side=Side.BUY if str(row.get("AstkBnsTpCode")) == "2" else Side.SELL,
            role=IntentRole(intent.role),
            requested_qty=intent.quantity,
            filled_qty=min(executed, intent.quantity),
            fill_price=Decimal(str(row.get("AstkExecPrc") or "0")),
            fee=Decimal(str(row.get("CmsnAmt") or row.get("AstkCmsn") or "0")),
            settlement_status=str(row.get("StlmYn") or row.get("SettlementStatus") or "unknown"),
            filled_at=_parse_datetime(row),
        )
        store.add_fill(fill)

    pending = store.pending_fills(profile.profile_id)
    if pending:
        pairs = [(store.get_intent(fill.intent_id), fill) for fill in pending]
        updated = apply_fills_with_cycles(store, profile, state, pairs)
        store.save_reconciled_state(updated, state.version, pending)
        state = updated

    holding = broker.holding(profile.symbol)
    broker_quantity = _int_qty(holding.get("AstkExecBaseQty")) if holding else 0
    if broker_quantity != state.quantity:
        return _flag_mismatch(store, state, f"quantity local={state.quantity} broker={broker_quantity}")
    if unresolved_broker_order or store.has_unknown_intents(profile.profile_id):
        return state
    if state.reconciliation_required:
        cleared = state.evolved(reconciliation_required=False)
        store.save_state(cleared, state.version)
        state = cleared
    store.audit("DBSEC_RECONCILIATION", {"profile_id": profile.profile_id, "status": "OK", "quantity": state.quantity})
    return state


def _flag_mismatch(store: StateStore, state: StrategyState, reason: str) -> StrategyState:
    if not state.reconciliation_required:
        flagged = state.evolved(reconciliation_required=True)
        store.save_state(flagged, state.version)
        state = flagged
    store.audit("DBSEC_RECONCILIATION", {"profile_id": state.profile_id, "status": "MISMATCH", "reason": reason})
    store.set_profile_status(state.profile_id, "LOCKED")
    return state


def _int_qty(value: Any) -> int:
    return int(Decimal(str(value or "0")))


def _parse_datetime(row: dict[str, Any]) -> datetime:
    raw = str(row.get("AstkExecDttm") or row.get("AstkLclExecDttm") or "").strip()
    digits = "".join(character for character in raw if character.isdigit())
    for pattern, length in (("%Y%m%d%H%M%S%f", 17), ("%Y%m%d%H%M%S", 14)):
        if len(digits) == length:
            return datetime.strptime(digits, pattern).replace(tzinfo=timezone.utc)
    order_date = str(row.get("OrdDt") or "")
    if len(order_date) == 8:
        return datetime.strptime(order_date, "%Y%m%d").replace(tzinfo=timezone.utc)
    raise ValueError("DB Securities fill has no parseable execution timestamp")
