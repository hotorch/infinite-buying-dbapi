from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import ROUND_FLOOR, Decimal
from pathlib import Path
from typing import Any

from .models import (
    RULESET_VERSION,
    FillEvent,
    MarketSnapshot,
    OrderIntent,
    OrderType,
    Phase,
    Side,
    StrategyProfile,
    StrategyState,
    stable_hash,
)
from .strategy import apply_fill, generate_intents, star_price

FEE_RATE = Decimal("0.0004")
MINIMUM_CAPITAL = Decimal("1")
MAXIMUM_CAPITAL = Decimal("3000")
WARMUP_SESSIONS = 5
DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "market"


class BacktestError(ValueError):
    """An input or data error that can be shown directly to a dashboard user."""

    def __init__(self, message: str, *, code: str = "INVALID_REQUEST", details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


@dataclass(frozen=True, slots=True)
class PriceRow:
    date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal


def run_backtest(request: dict[str, Any]) -> dict[str, Any]:
    parsed = _validate_request(request)
    symbol = parsed["symbol"]
    division_count = parsed["division_count"]
    capital = parsed["capital"]
    requested_start = parsed["start_date"]
    requested_end = parsed["end_date"]

    symbol_rows = _load_prices(symbol)
    benchmark_rows = {row.date: row for row in _load_prices("QQQ")}
    start_index = next((index for index, row in enumerate(symbol_rows) if row.date >= requested_start), None)
    end_index = next((index for index in range(len(symbol_rows) - 1, -1, -1) if symbol_rows[index].date <= requested_end), None)
    if start_index is None or end_index is None or start_index > end_index:
        raise BacktestError("선택한 기간에 사용할 수 있는 거래일 데이터가 없습니다.", code="NO_TRADING_DAYS")
    if start_index < WARMUP_SESSIONS:
        earliest = symbol_rows[WARMUP_SESSIONS].date.isoformat()
        raise BacktestError(f"시작일은 워밍업 데이터를 위해 {earliest} 이후여야 합니다.", code="INSUFFICIENT_WARMUP", details={"earliest_start_date": earliest})

    effective_rows = symbol_rows[start_index : end_index + 1]
    missing_benchmark = [row.date.isoformat() for row in effective_rows if row.date not in benchmark_rows]
    if missing_benchmark:
        raise BacktestError("같은 기간의 QQQ 비교 데이터가 일부 없습니다.", code="MISSING_BENCHMARK_DATA", details={"dates": missing_benchmark[:5]})

    previous_close = symbol_rows[start_index - 1].close
    first_limit = (previous_close * Decimal("1.20")).quantize(Decimal("0.01"))
    required_capital = first_limit * division_count
    if capital < required_capital:
        required = int(required_capital.to_integral_value(rounding=ROUND_FLOOR)) + 1
        raise BacktestError(
            f"첫 매수 1주를 주문하려면 초기 자본이 최소 ${required:,} 필요합니다.",
            code="INSUFFICIENT_FIRST_ORDER_CAPITAL",
            details={"minimum_capital": required, "first_order_limit": _number(first_limit)},
        )

    profile = StrategyProfile(
        profile_id="dashboard-backtest",
        symbol=symbol,
        division_count=division_count,
        capital=capital,
        effective_from=effective_rows[0].date,
    )
    state = StrategyState(
        profile_id=profile.profile_id,
        cycle_id="cycle-1",
        session_date=effective_rows[0].date,
        cash=capital,
    )

    daily: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    completed_cycles = 0
    buy_count = 0
    sell_count = 0
    peak_equity = capital
    qqq_start = benchmark_rows[effective_rows[0].date].close

    for index, row in enumerate(effective_rows):
        absolute_index = start_index + index
        completed_closes = tuple(item.close for item in symbol_rows[max(0, absolute_index - WARMUP_SESSIONS) : absolute_index])
        snapshot = MarketSnapshot(session_date=row.date, previous_close=symbol_rows[absolute_index - 1].close, completed_closes=completed_closes)

        quantity_before_sell = state.quantity
        state, sell_intents = generate_intents(profile, state, snapshot, Phase.SELL)
        for intent in sorted(sell_intents, key=lambda item: 0 if item.order_type == OrderType.LIMIT else 1):
            fill_price = _fill_price(intent, row)
            if fill_price is None:
                continue
            state, event = _apply_filled_intent(profile, state, intent, fill_price, row.date, len(events))
            if event:
                events.append(event)
                sell_count += 1

        if quantity_before_sell > 0 and state.quantity == 0:
            completed_cycles += 1
            state = state.evolved(cycle_id=f"cycle-{completed_cycles + 1}")

        state, buy_intents = generate_intents(profile, state, snapshot, Phase.BUY)
        for intent in buy_intents:
            fill_price = _fill_price(intent, row)
            if fill_price is None:
                continue
            state, event = _apply_filled_intent(profile, state, intent, fill_price, row.date, len(events))
            if event:
                events.append(event)
                buy_count += 1

        equity = state.cash + Decimal(state.quantity) * row.close
        peak_equity = max(peak_equity, equity)
        drawdown = equity / peak_equity - Decimal(1) if peak_equity else Decimal(0)
        qqq_equity = capital * benchmark_rows[row.date].close / qqq_start
        avg_cost = state.avg_cost if state.quantity else None
        current_star = star_price(profile, state) if state.quantity else None
        target = state.avg_cost * (Decimal(1) + profile.target_pct) if state.quantity else None
        daily.append(
            {
                "date": row.date.isoformat(),
                "open": _number(row.open),
                "high": _number(row.high),
                "low": _number(row.low),
                "close": _number(row.close),
                "avg_cost": _number(avg_cost),
                "star_price": _number(current_star),
                "target_price": _number(target),
                "t": _number(state.t),
                "quantity": state.quantity,
                "cash": _number(state.cash),
                "invested": _number(Decimal(state.quantity) * row.close),
                "equity": _number(equity),
                "qqq_equity": _number(qqq_equity),
                "drawdown": _number(drawdown),
                "cycle_id": state.cycle_id,
            }
        )

    final_equity = Decimal(str(daily[-1]["equity"]))
    total_return = final_equity / capital - Decimal(1)
    benchmark_return = Decimal(str(daily[-1]["qqq_equity"])) / capital - Decimal(1)
    years = Decimal(len(daily)) / Decimal(252)
    cagr = Decimal(str(float(final_equity / capital) ** (1 / float(years)) - 1)) if years > 0 else Decimal(0)
    mdd = min(Decimal(str(row["drawdown"])) for row in daily)
    summary = {
        "total_return": _number(total_return),
        "cagr": _number(cagr),
        "mdd": _number(mdd),
        "final_equity": _number(final_equity),
        "benchmark_return": _number(benchmark_return),
        "excess_return": _number(total_return - benchmark_return),
        "cycle_count": completed_cycles,
        "trading_days": len(daily),
        "buy_count": buy_count,
        "sell_count": sell_count,
    }
    normalized_request = {
        "symbol": symbol,
        "division_count": division_count,
        "capital": _number(capital),
        "start_date": requested_start.isoformat(),
        "end_date": requested_end.isoformat(),
    }
    assumptions: dict[str, Any] = {
        "ruleset_version": RULESET_VERSION,
        "price_basis": "액면분할과 배당을 반영한 수정 OHLC",
        "fee_rate": _number(FEE_RATE),
        "slippage": 0,
        "tax": 0,
        "warmup_sessions": WARMUP_SESSIONS,
        "requested_dates": {"start": requested_start.isoformat(), "end": requested_end.isoformat()},
        "effective_dates": {"start": effective_rows[0].date.isoformat(), "end": effective_rows[-1].date.isoformat()},
    }
    digest_source = {"request": normalized_request, "summary": summary, "assumptions": assumptions, "daily": daily, "events": events}
    assumptions["digest"] = stable_hash(digest_source)
    weather_daily = _load_regime_weather(effective_rows[0].date, effective_rows[-1].date) if symbol == "TQQQ" else []
    return {
        "request": normalized_request,
        "summary": summary,
        "assumptions": assumptions,
        "daily": daily,
        "events": events,
        "weather_daily": weather_daily,
    }


def _validate_request(request: dict[str, Any]) -> dict[str, Any]:
    try:
        symbol = str(request.get("symbol", "TQQQ")).upper()
        division_count = int(request.get("division_count", 40))
        capital = Decimal(str(request.get("capital", "3000")))
        start_date = date.fromisoformat(str(request["start_date"]))
        end_date = date.fromisoformat(str(request["end_date"]))
    except (KeyError, TypeError, ValueError, ArithmeticError) as error:
        raise BacktestError("입력값 형식을 확인해 주세요.") from error
    if symbol not in {"TQQQ", "SOXL"}:
        raise BacktestError("TQQQ 또는 SOXL만 백테스트할 수 있습니다.", code="UNSUPPORTED_SYMBOL")
    if division_count not in {20, 30, 40}:
        raise BacktestError("분할 수는 20, 30, 40 중에서 선택해 주세요.", code="UNSUPPORTED_DIVISION")
    if not capital.is_finite() or capital < MINIMUM_CAPITAL:
        raise BacktestError("초기 자본은 $1 이상 입력해 주세요.", code="CAPITAL_TOO_LOW", details={"minimum_capital": 1})
    if capital > MAXIMUM_CAPITAL:
        raise BacktestError("초기 자본은 최대 $3,000까지 입력할 수 있습니다.", code="CAPITAL_TOO_HIGH", details={"maximum_capital": 3000})
    if start_date > end_date:
        raise BacktestError("시작일은 종료일보다 늦을 수 없습니다.", code="REVERSED_DATES")
    return {"symbol": symbol, "division_count": division_count, "capital": capital, "start_date": start_date, "end_date": end_date}


def _load_prices(symbol: str) -> list[PriceRow]:
    path = DATA_DIR / f"{symbol.lower()}_adjusted_daily.csv"
    if not path.exists():
        raise BacktestError(f"{symbol} 시세 데이터 파일을 찾을 수 없습니다.", code="MISSING_DATA")
    rows: list[PriceRow] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            rows.append(
                PriceRow(
                    date=date.fromisoformat(row["date"]),
                    open=Decimal(row["open"]),
                    high=Decimal(row["high"]),
                    low=Decimal(row["low"]),
                    close=Decimal(row["close"]),
                )
            )
    return rows


def _load_regime_weather(start_date: date, end_date: date) -> list[dict[str, Any]]:
    path = DATA_DIR / "tqqq_regime_weather.csv"
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    numeric_fields = {
        "score",
        "signal_return_3m",
        "signal_return_6m",
        "signal_rs",
        "signal_distance_50",
        "trade_dollar_volume_multiple",
    }
    integer_fields = {"regime_age", "strong_green_age", "sessions_since_stress"}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for raw in csv.DictReader(handle):
            row_date = date.fromisoformat(raw["date"])
            if row_date < start_date or row_date > end_date:
                continue
            row: dict[str, Any] = dict(raw)
            for field in numeric_fields:
                row[field] = float(raw[field]) if raw[field] else None
            for field in integer_fields:
                row[field] = int(raw[field]) if raw[field] else None
            row["signal_sma50_rising_10d"] = raw["signal_sma50_rising_10d"].lower() == "true"
            row["reasons"] = [reason for reason in raw["reasons"].split("|") if reason]
            rows.append(row)
    return rows


def _fill_price(intent: OrderIntent, row: PriceRow) -> Decimal | None:
    if intent.order_type == OrderType.MOC:
        return row.close
    assert intent.limit_price is not None
    if intent.order_type == OrderType.LIMIT:
        if intent.side == Side.BUY and row.low <= intent.limit_price:
            return intent.limit_price
        if intent.side == Side.SELL and row.high >= intent.limit_price:
            return intent.limit_price
        return None
    if intent.side == Side.BUY and row.close <= intent.limit_price:
        return row.close
    if intent.side == Side.SELL and row.close >= intent.limit_price:
        return row.close
    return None


def _apply_filled_intent(
    profile: StrategyProfile,
    state: StrategyState,
    intent: OrderIntent,
    price: Decimal,
    session_date: date,
    sequence: int,
) -> tuple[StrategyState, dict[str, Any] | None]:
    quantity = intent.quantity
    if intent.side == Side.BUY:
        affordable = int((state.cash / (price * (Decimal(1) + FEE_RATE))).to_integral_value(rounding=ROUND_FLOOR))
        quantity = min(quantity, affordable)
    else:
        quantity = min(quantity, state.quantity)
    if quantity <= 0:
        return state, None
    fill = FillEvent(
        broker_order_no=f"BACKTEST-{session_date.isoformat()}-{sequence}",
        fill_id=f"{session_date.isoformat()}-{sequence}-{intent.role.value}",
        intent_id=intent.intent_id,
        side=intent.side,
        role=intent.role,
        requested_qty=intent.quantity,
        filled_qty=quantity,
        fill_price=price,
        filled_at=datetime.combine(session_date, time(21, 0), tzinfo=timezone.utc),
    )
    value = price * quantity
    fee = value * FEE_RATE
    updated = apply_fill(profile, state, intent, fill)
    if intent.side == Side.BUY:
        updated = updated.evolved(cash=updated.cash - fee, cost_basis=updated.cost_basis + fee)
    else:
        updated = updated.evolved(cash=updated.cash - fee)
    return (
        updated,
        {
            "date": session_date.isoformat(),
            "side": intent.side.value,
            "role": intent.role.value,
            "quantity": quantity,
            "price": _number(price),
            "fee": _number(fee),
            "reason_code": intent.reason_code,
            "cycle_id": intent.cycle_id,
        },
    )


def _number(value: Decimal | None, places: str = "0.00000001") -> float | None:
    if value is None:
        return None
    return float(value.quantize(Decimal(places)).normalize())
