from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from infinite_buying_dbapi.models import (
    FillEvent,
    IntentRole,
    MarketSnapshot,
    Mode,
    Phase,
    Side,
    StrategyProfile,
    StrategyState,
)
from infinite_buying_dbapi.strategy import apply_fill, apply_fills_in_order, generate_intents, star_pct, star_price


def profile(symbol: str = "TQQQ", division: int = 40) -> StrategyProfile:
    return StrategyProfile("p1", symbol, division, Decimal("10000"), effective_from=date(2026, 1, 2))


def state(**changes: object) -> StrategyState:
    values = {
        "profile_id": "p1",
        "cycle_id": "c1",
        "session_date": date(2026, 1, 2),
        "cash": Decimal("30000"),
        "quantity": 50,
        "cost_basis": Decimal("5000"),
        "t": Decimal("10"),
    }
    values.update(changes)
    return StrategyState(**values)


def snapshot(day: date = date(2026, 1, 5)) -> MarketSnapshot:
    return MarketSnapshot(day, Decimal("100"), completed_closes=(Decimal("96"), Decimal("97"), Decimal("98"), Decimal("99"), Decimal("100")))


def test_golden_star_formulas() -> None:
    assert star_pct(profile("TQQQ", 20), Decimal("5")) == Decimal("0.075")
    assert star_pct(profile("TQQQ", 40), Decimal("10")) == Decimal("0.075")
    assert star_pct(profile("SOXL", 20), Decimal("5")) == Decimal("0.10")
    assert star_pct(profile("SOXL", 40), Decimal("10")) == Decimal("0.10")
    assert star_price(profile(), state(), Decimal("0.01")) == Decimal("107.50")


def test_initial_intent_is_deterministic_and_uses_120_percent() -> None:
    flat = state(quantity=0, cost_basis=Decimal(0), t=Decimal(0), cash=Decimal("10000"))
    _, first = generate_intents(profile(), flat, snapshot(), Phase.BUY)
    _, second = generate_intents(profile(), flat, snapshot(), Phase.BUY)
    assert first == second
    assert first[0].limit_price == Decimal("120.00")
    assert first[0].role == IntentRole.INITIAL_BUY
    assert first[0].quantity == 2


def test_normal_front_and_back_half_intents() -> None:
    _, front = generate_intents(profile(), state(t=Decimal("10")), snapshot(), Phase.BUY)
    assert [item.role for item in front] == [IntentRole.AVG_HALF_BUY, IntentRole.STAR_HALF_BUY]
    assert [item.planned_t_effect for item in front] == [Decimal("0.5"), Decimal("0.5")]
    _, back = generate_intents(profile(), state(t=Decimal("20")), snapshot(), Phase.BUY)
    assert [item.role for item in back] == [IntentRole.STAR_FULL_BUY]


@pytest.mark.parametrize("quantity", [1, 2, 3, 4, 5])
def test_sell_intents_never_exceed_holdings(quantity: int) -> None:
    current = state(quantity=quantity, cost_basis=Decimal(100) * quantity)
    _, intents = generate_intents(profile(), current, snapshot(), Phase.SELL)
    assert sum(item.quantity for item in intents) == quantity
    assert intents[0].quantity >= 1


def test_partial_buy_and_sell_t_rules() -> None:
    current = state(t=Decimal("10"))
    _, buys = generate_intents(profile(), current, snapshot(), Phase.BUY)
    intent = buys[0]
    partial = FillEvent("o1", "f1", intent.intent_id, Side.BUY, intent.role, intent.quantity, 1, Decimal("100"))
    after_buy = apply_fill(profile(), current, intent, partial)
    assert after_buy.t == Decimal("10") + Decimal("0.5") * partial.fill_ratio

    _, sells = generate_intents(profile(), current, snapshot(), Phase.SELL)
    quarter = sells[0]
    partial_sell = FillEvent("o2", "f2", quarter.intent_id, Side.SELL, quarter.role, quarter.quantity, 1, Decimal("110"))
    after_sell = apply_fill(profile(), current, quarter, partial_sell)
    assert after_sell.t == Decimal("10") * (Decimal(1) - Decimal("0.25") * partial_sell.fill_ratio)


def test_same_timestamp_sells_are_applied_before_buys() -> None:
    current = state()
    _, sells = generate_intents(profile(), current, snapshot(), Phase.SELL)
    _, buys = generate_intents(profile(), current, snapshot(), Phase.BUY)
    sell, buy = sells[0], buys[0]
    when = datetime(2026, 1, 5, 21, 0, tzinfo=timezone.utc)
    sell_fill = FillEvent("s", "2", sell.intent_id, Side.SELL, sell.role, sell.quantity, 1, Decimal("107.5"), when)
    buy_fill = FillEvent("b", "1", buy.intent_id, Side.BUY, buy.role, buy.quantity, 1, Decimal("100"), when)
    result = apply_fills_in_order(profile(), current, [(buy, buy_fill), (sell, sell_fill)])
    expected_after_sell = apply_fill(profile(), current, sell, sell_fill)
    expected = apply_fill(profile(), expected_after_sell, buy, buy_fill)
    assert result == expected


def test_reverse_entry_first_day_and_next_day() -> None:
    exhausted = state(t=Decimal("39.1"), cash=Decimal("1000"))
    prepared, first = generate_intents(profile(), exhausted, snapshot(), Phase.SELL)
    assert prepared.mode == Mode.REVERSE
    assert prepared.reverse_cash_pool == Decimal("1000")
    assert first[0].role == IntentRole.REVERSE_FIRST_SELL
    next_day = MarketSnapshot(date(2026, 1, 6), Decimal("80"), completed_closes=snapshot().completed_closes)
    prepared2, second = generate_intents(profile(), prepared, next_day, Phase.SELL)
    assert prepared2.reverse_days == 1
    assert second[0].role == IntentRole.REVERSE_SELL


def test_recovery_happens_next_session() -> None:
    reverse = state(mode=Mode.REVERSE, reverse_days=2, t=Decimal("38"), cash=Decimal("1000"))
    recovered, intents = generate_intents(profile(), reverse, MarketSnapshot(date(2026, 1, 6), Decimal("86")), Phase.SELL)
    assert recovered.mode == Mode.NORMAL
    assert intents[0].role == IntentRole.STAR_QUARTER_SELL
