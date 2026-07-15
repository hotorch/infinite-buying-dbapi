from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import exchange_calendars as xcals
import pandas as pd

from .models import WeatherSnapshot

WEATHER_RULESET_VERSION = "regime-weather-1"
SIGNAL_SYMBOLS = {"TQQQ": "QQQ", "SOXL": "SMH"}
BENCHMARK_SYMBOL = "SPY"
MINIMUM_WEATHER_SESSIONS = 220
ZERO = Decimal("0")


class WeatherDataError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class WeatherCandle:
    session_date: date
    close: Decimal
    volume: Decimal

    def __post_init__(self) -> None:
        if self.close <= 0 or self.volume < 0:
            raise ValueError("weather candles require positive close and non-negative volume")


def compute_weather_history(
    symbol: str,
    candles: Mapping[str, Sequence[WeatherCandle]],
) -> list[WeatherSnapshot]:
    """Compute point-in-time regime snapshots without touching strategy state."""
    symbol = symbol.upper()
    if symbol not in SIGNAL_SYMBOLS:
        raise WeatherDataError(f"unsupported symbol: {symbol}")
    signal_symbol = SIGNAL_SYMBOLS[symbol]
    required = (symbol, signal_symbol, BENCHMARK_SYMBOL)
    missing = [item for item in required if item not in candles]
    if missing:
        raise WeatherDataError(f"missing weather series: {','.join(missing)}")

    aligned: dict[date, tuple[WeatherCandle, WeatherCandle, WeatherCandle]] = {}
    by_symbol = {name: {row.session_date: row for row in candles[name]} for name in required}
    calendar = xcals.get_calendar("XNYS")
    for day in sorted(set(by_symbol[symbol]) & set(by_symbol[signal_symbol]) & set(by_symbol[BENCHMARK_SYMBOL])):
        if not calendar.is_session(pd.Timestamp(day)):
            continue
        aligned[day] = (by_symbol[symbol][day], by_symbol[signal_symbol][day], by_symbol[BENCHMARK_SYMBOL][day])
    days = list(aligned)
    if len(days) < MINIMUM_WEATHER_SESSIONS:
        raise WeatherDataError(f"weather requires at least {MINIMUM_WEATHER_SESSIONS} aligned completed sessions")
    expected = {stamp.date() for stamp in calendar.sessions_in_range(pd.Timestamp(days[0]), pd.Timestamp(days[-1]))}
    missing_sessions = sorted(expected - set(days))
    if missing_sessions:
        raise WeatherDataError(f"weather series are incomplete; first missing session is {missing_sessions[0].isoformat()}")

    signal_close = [aligned[day][1].close for day in days]
    benchmark_close = [aligned[day][2].close for day in days]
    leveraged_close = [aligned[day][0].close for day in days]
    leveraged_volume = [aligned[day][0].volume for day in days]
    history: list[WeatherSnapshot] = []
    previous_regime = ""
    duration = 0
    stress_indices: list[int] = []

    for index in range(MINIMUM_WEATHER_SESSIONS - 1, len(days)):
        close = signal_close[index]
        sma50 = _mean(signal_close[index - 49 : index + 1])
        sma150 = _mean(signal_close[index - 149 : index + 1])
        sma200 = _mean(signal_close[index - 199 : index + 1])
        sma200_20 = _mean(signal_close[index - 219 : index - 19])
        low_52 = min(signal_close[max(0, index - 251) : index + 1])
        high_52 = max(signal_close[max(0, index - 251) : index + 1])
        momentum_3m = close / signal_close[index - 63] - 1
        momentum_6m = close / signal_close[index - 126] - 1
        signal_12m = close / signal_close[max(0, index - 219)] - 1
        benchmark_3m = benchmark_close[index] / benchmark_close[index - 63] - 1
        relative_strength = momentum_3m - benchmark_3m
        distance_50 = close / sma50 - 1
        sma50_rising = sma50 > _mean(signal_close[index - 59 : index - 9])
        dollar_volume = leveraged_close[index] * leveraged_volume[index]
        average_dollar_volume = _mean(
            [leveraged_close[item] * leveraged_volume[item] for item in range(index - 19, index + 1)]
        )
        liquidity_multiple = average_dollar_volume / Decimal("100000000")
        score = (
            Decimal("0.70")
            * (momentum_3m * Decimal("0.50") + momentum_6m * Decimal("0.30") + signal_12m * Decimal("0.20"))
            + relative_strength * Decimal("0.35")
            - max(ZERO, distance_50) * Decimal("0.15")
            + min(Decimal("0.05"), liquidity_multiple * Decimal("0.05"))
        )

        red_reasons: list[str] = []
        if sma50 < sma150:
            red_reasons.append("50ma_below_150ma")
        if sma200 <= sma200_20:
            red_reasons.append("200ma_not_rising")
        if close < sma200:
            red_reasons.append("close_below_200ma")
        if close < sma50 < sma150 < sma200:
            red_reasons.append("stage4_breakdown")

        orange_reasons: list[str] = []
        if not (close > sma50 > sma150 > sma200):
            orange_reasons.append("signal_trend_template_failed")
        if close < low_52 * Decimal("1.30"):
            orange_reasons.append("not_30pct_above_52w_low")
        if close < high_52 * Decimal("0.75"):
            orange_reasons.append("more_than_25pct_below_52w_high")
        if close < sma50:
            orange_reasons.append("close_below_50ma")
        if average_dollar_volume < Decimal("100000000"):
            orange_reasons.append("leveraged_etf_liquidity_below_floor")

        yellow_reasons: list[str] = []
        if distance_50 > Decimal("0.08"):
            yellow_reasons.append("extended_above_50ma")
        if relative_strength <= 0:
            yellow_reasons.append("relative_strength_below_floor")
        if momentum_3m <= 0:
            yellow_reasons.append("three_month_momentum_not_positive")
        if momentum_6m <= 0:
            yellow_reasons.append("six_month_momentum_not_positive")

        if red_reasons:
            regime = "red"
            reasons = red_reasons
        elif orange_reasons:
            regime = "orange"
            reasons = orange_reasons
        elif yellow_reasons:
            regime = "yellow"
            reasons = yellow_reasons
        elif (
            score >= Decimal("0.20")
            and momentum_3m >= Decimal("0.08")
            and momentum_6m >= Decimal("0.12")
            and relative_strength >= Decimal("0.08")
            and distance_50 <= Decimal("0.08")
            and liquidity_multiple >= Decimal("5")
        ):
            regime = "strong_green"
            reasons = ["strong_green_thresholds_met"]
        else:
            regime = "green"
            reasons = ["trend_template_passed"]

        if regime in {"orange", "red"}:
            stress_indices.append(index)
        recent_stress = bool(stress_indices and index - stress_indices[-1] <= 60)
        early_thaw = (
            regime in {"green", "yellow"}
            and recent_stress
            and close > sma50
            and sma50_rising
            and ZERO < momentum_3m < Decimal("0.08")
            and ZERO < relative_strength < Decimal("0.08")
            and ZERO <= distance_50 <= Decimal("0.05")
        )
        weather_state = "early_thaw" if early_thaw else regime
        if weather_state == previous_regime:
            duration += 1
        else:
            duration = 1
            previous_regime = weather_state
        history.append(
            WeatherSnapshot(
                symbol=symbol,
                signal_symbol=signal_symbol,
                benchmark_symbol=BENCHMARK_SYMBOL,
                session_date=_following_session(days[index]),
                signal_date=days[index],
                regime=regime,
                weather_state=weather_state,
                duration=duration,
                momentum_3m=momentum_3m,
                momentum_6m=momentum_6m,
                relative_strength=relative_strength,
                distance_50=distance_50,
                dollar_volume=dollar_volume,
                reason_codes=tuple(reasons),
                score=score,
                sma50_rising_10d=sma50_rising,
                dollar_volume_multiple=liquidity_multiple,
            )
        )
    return history


def candles_from_rows(rows: Iterable[Mapping[str, object]]) -> list[WeatherCandle]:
    candles: list[WeatherCandle] = []
    for row in rows:
        raw_day = row.get("date")
        day = raw_day if isinstance(raw_day, date) else date.fromisoformat(str(raw_day))
        candles.append(WeatherCandle(day, Decimal(str(row["close"])), Decimal(str(row.get("volume", 0)))))
    return sorted(candles, key=lambda item: item.session_date)


def _mean(values: Sequence[Decimal]) -> Decimal:
    if not values:
        raise WeatherDataError("cannot calculate weather from an empty window")
    return sum(values, ZERO) / Decimal(len(values))


def _following_session(day: date) -> date:
    calendar = xcals.get_calendar("XNYS")
    label = calendar.date_to_session(pd.Timestamp(day), direction="previous")
    return calendar.next_session(label).date()
