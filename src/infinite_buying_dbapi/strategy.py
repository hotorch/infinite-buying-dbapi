from __future__ import annotations

from dataclasses import asdict
from decimal import ROUND_FLOOR, Decimal
from typing import Iterable

from .models import (
    ZERO,
    FillEvent,
    IntentRole,
    MarketSnapshot,
    Mode,
    OrderIntent,
    OrderType,
    Phase,
    Side,
    StrategyProfile,
    StrategyState,
    stable_hash,
)


def floor_quantity(budget: Decimal, price: Decimal) -> int:
    if budget <= ZERO or price <= ZERO:
        return 0
    return int((budget / price).to_integral_value(rounding=ROUND_FLOOR))


def star_pct(profile: StrategyProfile, t: Decimal) -> Decimal:
    return profile.target_pct - (profile.target_pct * Decimal(2) / Decimal(profile.division_count)) * t


def star_price(profile: StrategyProfile, state: StrategyState, tick_size: Decimal = Decimal("0.01")) -> Decimal:
    if state.quantity <= 0:
        raise ValueError("star price requires a position")
    raw = state.avg_cost * (Decimal(1) + star_pct(profile, state.t))
    return max(tick_size, raw.quantize(tick_size))


def one_buy_amount(profile: StrategyProfile, state: StrategyState) -> Decimal:
    denominator = Decimal(profile.division_count) - state.t
    if denominator <= Decimal(1):
        return ZERO
    return state.cash / denominator


def prepare_state(profile: StrategyProfile, state: StrategyState, snapshot: MarketSnapshot) -> StrategyState:
    entered_new_reverse_session = state.mode == Mode.REVERSE and snapshot.session_date > state.session_date
    closes = tuple(snapshot.completed_closes[-5:]) if snapshot.completed_closes else state.last_5_closes
    changes: dict[str, object] = {}
    if closes != state.last_5_closes:
        changes["last_5_closes"] = closes
    if snapshot.session_date > state.session_date:
        changes["session_date"] = snapshot.session_date
        if state.mode == Mode.REVERSE:
            changes["reverse_days"] = state.reverse_days + 1
    prepared = state.evolved(**changes) if changes else state
    if prepared.quantity and prepared.mode == Mode.NORMAL and prepared.t > Decimal(profile.division_count - 1):
        prepared = prepared.evolved(
            mode=Mode.REVERSE,
            reverse_cash_pool=prepared.cash,
            reverse_cash_used=ZERO,
            reverse_days=0,
        )
    if entered_new_reverse_session and prepared.mode == Mode.REVERSE and prepared.quantity:
        recovery_ratio = Decimal("0.80") if profile.symbol == "SOXL" else Decimal("0.85")
        if snapshot.previous_close > prepared.avg_cost * recovery_ratio:
            prepared = prepared.evolved(mode=Mode.NORMAL, reverse_days=0)
    return prepared


def generate_intents(
    profile: StrategyProfile,
    state: StrategyState,
    snapshot: MarketSnapshot,
    phase: Phase,
) -> tuple[StrategyState, list[OrderIntent]]:
    state = prepare_state(profile, state, snapshot)
    if state.reconciliation_required:
        return state, []
    input_hash = stable_hash({"profile": asdict(profile), "state": asdict(state), "snapshot": asdict(snapshot), "phase": phase})
    specs = _sell_specs(profile, state, snapshot) if phase == Phase.SELL else _buy_specs(profile, state, snapshot)
    intents: list[OrderIntent] = []
    for side, order_type, role, quantity, price, budget, t_effect, reason in specs:
        if quantity <= 0:
            continue
        identity = {
            "ruleset": profile.ruleset_version,
            "account": profile.account_alias,
            "session": snapshot.session_date,
            "phase": phase,
            "cycle": state.cycle_id,
            "symbol": profile.symbol,
            "side": side,
            "role": role,
        }
        intents.append(
            OrderIntent(
                intent_id=stable_hash(identity),
                input_hash=input_hash,
                cycle_id=state.cycle_id,
                profile_id=profile.profile_id,
                strategy_version=profile.ruleset_version,
                session_date=snapshot.session_date,
                phase=phase,
                side=side,
                order_type=order_type,
                role=role,
                quantity=quantity,
                limit_price=price,
                budget=budget,
                planned_t_effect=t_effect,
                reason_code=reason,
            )
        )
    return state, intents


IntentSpec = tuple[Side, OrderType, IntentRole, int, Decimal | None, Decimal, Decimal, str]


def _sell_specs(profile: StrategyProfile, state: StrategyState, snapshot: MarketSnapshot) -> list[IntentSpec]:
    if state.quantity <= 0:
        return []
    if state.mode == Mode.REVERSE:
        quantity = max(1, (state.quantity * 2) // profile.division_count)
        if state.reverse_days == 0:
            return [(Side.SELL, OrderType.MOC, IntentRole.REVERSE_FIRST_SELL, quantity, None, ZERO, Decimal(2) / profile.division_count, "reverse-first-moc")]
        reverse_star = _reverse_star(state)
        return [(Side.SELL, OrderType.LOC, IntentRole.REVERSE_SELL, quantity, reverse_star, ZERO, Decimal(2) / profile.division_count, "reverse-star-loc-sell")]

    quarter = max(1, state.quantity // 4)
    target_quantity = state.quantity - quarter
    star = star_price(profile, state, snapshot.tick_size)
    target = (state.avg_cost * (Decimal(1) + profile.target_pct)).quantize(snapshot.tick_size)
    specs: list[IntentSpec] = [(Side.SELL, OrderType.LOC, IntentRole.STAR_QUARTER_SELL, quarter, star, ZERO, Decimal("0.25"), "normal-star-quarter-loc-sell")]
    if target_quantity:
        specs.append((Side.SELL, OrderType.LIMIT, IntentRole.TARGET_SELL, target_quantity, target, ZERO, Decimal("0.75"), "normal-target-limit-sell"))
    return specs


def _buy_specs(profile: StrategyProfile, state: StrategyState, snapshot: MarketSnapshot) -> list[IntentSpec]:
    if state.mode == Mode.REVERSE:
        if state.reverse_days == 0 or state.quantity <= 0:
            return []
        tranche = state.reverse_cash_pool / Decimal(4)
        budget = min(state.cash, state.reverse_cash_remaining, tranche)
        limit = max(snapshot.tick_size, _reverse_star(state) - snapshot.tick_size)
        quantity = floor_quantity(budget, limit)
        return [(Side.BUY, OrderType.LOC, IntentRole.REVERSE_BUY, quantity, limit, budget, Decimal("0.25"), "reverse-quarter-loc-buy")]

    if state.quantity == 0:
        budget = state.cash / Decimal(profile.division_count)
        limit = (snapshot.previous_close * Decimal("1.20")).quantize(snapshot.tick_size)
        quantity = floor_quantity(budget, limit)
        return [(Side.BUY, OrderType.LOC, IntentRole.INITIAL_BUY, quantity, limit, budget, Decimal(1), "initial-prev-close-120pct-loc")]

    amount = one_buy_amount(profile, state)
    if amount <= ZERO:
        return []
    star_limit = max(snapshot.tick_size, star_price(profile, state, snapshot.tick_size) - snapshot.tick_size)
    if state.t < Decimal(profile.division_count) / Decimal(2):
        half = amount / Decimal(2)
        return [
            (
                Side.BUY,
                OrderType.LOC,
                IntentRole.AVG_HALF_BUY,
                floor_quantity(half, state.avg_cost),
                state.avg_cost.quantize(snapshot.tick_size),
                half,
                Decimal("0.5"),
                "normal-avg-half-loc-buy",
            ),
            (Side.BUY, OrderType.LOC, IntentRole.STAR_HALF_BUY, floor_quantity(half, star_limit), star_limit, half, Decimal("0.5"), "normal-star-half-loc-buy"),
        ]
    return [(Side.BUY, OrderType.LOC, IntentRole.STAR_FULL_BUY, floor_quantity(amount, star_limit), star_limit, amount, Decimal(1), "normal-star-full-loc-buy")]


def _reverse_star(state: StrategyState) -> Decimal:
    if not state.last_5_closes:
        raise ValueError("reverse mode needs completed closes")
    return sum(state.last_5_closes, ZERO) / Decimal(len(state.last_5_closes))


def apply_fill(profile: StrategyProfile, state: StrategyState, intent: OrderIntent, fill: FillEvent) -> StrategyState:
    if fill.intent_id != intent.intent_id or fill.side != intent.side or fill.role != intent.role:
        raise ValueError("fill does not match intent")
    ratio = fill.fill_ratio
    value = fill.fill_price * fill.filled_qty
    if fill.side == Side.BUY:
        if value > state.cash:
            raise ValueError("fill exceeds available cash")
        new_quantity = state.quantity + fill.filled_qty
        new_cost = state.cost_basis + value
        if fill.role == IntentRole.REVERSE_BUY:
            delta = (Decimal(profile.division_count) - state.t) * Decimal("0.25") * ratio
            return state.evolved(
                cash=state.cash - value,
                quantity=new_quantity,
                cost_basis=new_cost,
                t=state.t + delta,
                reverse_cash_used=state.reverse_cash_used + value,
            )
        return state.evolved(cash=state.cash - value, quantity=new_quantity, cost_basis=new_cost, t=state.t + intent.planned_t_effect * ratio)

    if fill.filled_qty > state.quantity:
        raise ValueError("sell fill exceeds holdings")
    cost_reduction = state.cost_basis * Decimal(fill.filled_qty) / Decimal(state.quantity)
    remaining_quantity = state.quantity - fill.filled_qty
    remaining_cost = state.cost_basis - cost_reduction if remaining_quantity else ZERO
    factor = Decimal(1) - intent.planned_t_effect * ratio
    evolved = state.evolved(
        cash=state.cash + value,
        quantity=remaining_quantity,
        cost_basis=remaining_cost,
        t=state.t * factor,
    )
    if remaining_quantity == 0:
        return evolved.evolved(mode=Mode.NORMAL, t=ZERO, reverse_cash_pool=ZERO, reverse_cash_used=ZERO, reverse_days=0)
    return evolved


def apply_fills_in_order(
    profile: StrategyProfile,
    state: StrategyState,
    pairs: Iterable[tuple[OrderIntent, FillEvent]],
) -> StrategyState:
    ordered = sorted(pairs, key=lambda item: (item[1].filled_at, 0 if item[1].side == Side.SELL else 1, item[1].fill_id))
    for intent, fill in ordered:
        state = apply_fill(profile, state, intent, fill)
    return state
