from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .broker import AmbiguousOrderError, Broker, DbSecBroker
from .models import Environment, OrderIntent, Side, StrategyProfile, StrategyState
from .store import StateStore


class PreflightError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ExecutionLimits:
    max_order_notional: Decimal
    max_daily_notional: Decimal


def assert_live_gates(store: StateStore, profile: StrategyProfile, state: StrategyState, session_date: date) -> None:
    failures: list[str] = []
    if not profile.live_eligible:
        failures.append("PROFILE_NOT_LIVE_ELIGIBLE")
    if store.setting("live_enabled", "false") != "true":
        failures.append("LIVE_NOT_ENABLED")
    if not store.is_live_approved(profile.account_alias, session_date):
        failures.append("DAILY_APPROVAL_MISSING")
    if store.capability("supports_opposing_loc") != "확인됨":
        failures.append("OPPOSING_LOC_NOT_VERIFIED")
    if store.capability("oauth_client_credentials") != "확인됨":
        failures.append("OAUTH_NOT_VERIFIED")
    if store.capability("rate_limits") != "확인됨":
        failures.append("RATE_LIMITS_NOT_VERIFIED")
    if store.setting("legal_review_ack", "false") != "true":
        failures.append("LEGAL_REVIEW_NOT_ACKNOWLEDGED")
    if store.setting("risk_disclosure_ack", "false") != "true":
        failures.append("RISK_DISCLOSURE_NOT_ACKNOWLEDGED")
    if store.setting("emergency_stop", "true") == "true":
        failures.append("EMERGENCY_STOP_ACTIVE")
    if state.reconciliation_required:
        failures.append("RECONCILIATION_REQUIRED")
    if failures:
        raise PreflightError(",".join(failures))


def preflight_intents(intents: list[OrderIntent], state: StrategyState, limits: ExecutionLimits, daily_submitted: Decimal = Decimal(0)) -> None:
    sell_total = sum((intent.quantity for intent in intents if intent.side == Side.SELL), 0)
    if sell_total > state.quantity:
        raise PreflightError("SELL_QUANTITY_EXCEEDS_HOLDINGS")
    total = daily_submitted
    for intent in intents:
        reference_price = intent.limit_price if intent.limit_price is not None else state.avg_cost
        notional = reference_price * intent.quantity
        if notional > limits.max_order_notional:
            raise PreflightError("ORDER_NOTIONAL_LIMIT_EXCEEDED")
        total += notional
    if total > limits.max_daily_notional:
        raise PreflightError("DAILY_NOTIONAL_LIMIT_EXCEEDED")


def execute_intents(
    store: StateStore,
    broker: Broker,
    profile: StrategyProfile,
    state: StrategyState,
    intents: list[OrderIntent],
    environment: Environment,
    limits: ExecutionLimits,
) -> list[str]:
    if environment == Environment.LIVE:
        assert_live_gates(store, profile, state, intents[0].session_date if intents else state.session_date)
    session_date = intents[0].session_date if intents else state.session_date
    preflight_intents(intents, state, limits, store.daily_submitted_notional(session_date))
    submitted: list[str] = []
    for intent in intents:
        if store.has_order_for_intent(intent.intent_id):
            continue
        try:
            if isinstance(broker, DbSecBroker):
                if intent.side == Side.BUY:
                    if intent.limit_price is None:
                        raise PreflightError("LIVE_BUY_REQUIRES_LIMIT_PRICE")
                    available_amount, available_quantity = broker.orderable_amount(profile.symbol, intent.side, intent.limit_price, "2")
                    if intent.quantity > available_quantity or intent.limit_price * intent.quantity > available_amount:
                        raise PreflightError("BROKER_ORDERABLE_AMOUNT_EXCEEDED")
                order = broker.place_order_for_symbol(profile.symbol, intent)
            else:
                order = broker.place_order(intent)
        except AmbiguousOrderError:
            store.mark_intent_unknown(intent.intent_id)
            store.audit("ORDER_AMBIGUOUS", {"intent_id": intent.intent_id})
            raise
        store.record_broker_order(order)
        submitted.append(order.broker_order_no)
    return submitted
