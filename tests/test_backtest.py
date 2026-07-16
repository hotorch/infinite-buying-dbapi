from __future__ import annotations

import pytest

from infinite_buying_dbapi.backtest import BacktestError, run_backtest


def request(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "symbol": "TQQQ",
        "division_count": 40,
        "capital": 3000,
        "start_date": "2025-01-02",
        "end_date": "2025-03-31",
    }
    values.update(changes)
    return values


def test_backtest_contract_is_complete_and_deterministic() -> None:
    first = run_backtest(request())
    second = run_backtest(request())

    assert first == second
    assert first["request"]["symbol"] == "TQQQ"
    assert first["summary"]["trading_days"] > 0
    assert first["daily"] and first["events"]
    assert first["weather_daily"]
    assert len(first["assumptions"]["digest"]) == 64
    assert {"total_return", "cagr", "mdd", "final_equity", "benchmarks", "cycle_count"} <= first["summary"].keys()
    assert {item["symbol"] for item in first["summary"]["benchmarks"]} == {"TQQQ", "QQQ", "SPY"}
    assert {"date", "open", "high", "low", "close", "avg_cost", "star_price", "target_price", "t", "quantity", "cash", "equity", "benchmark_equities", "drawdown", "cycle_id"} <= first["daily"][0].keys()
    assert set(first["daily"][0]["benchmark_equities"]) == {"TQQQ", "QQQ", "SPY"}
    assert {"date", "side", "role", "quantity", "price", "fee", "reason_code", "cycle_id"} <= first["events"][0].keys()
    assert {
        "date",
        "signal_date",
        "regime",
        "weather_state",
        "score",
        "signal_return_3m",
        "signal_return_6m",
        "signal_rs",
        "signal_distance_50",
    } <= first["weather_daily"][0].keys()
    assert first["weather_research"]
    assert {row["symbol"] for row in first["weather_research"]} == {"TQQQ"}
    assert {row["horizon_sessions"] for row in first["weather_research"]} == {60}


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"capital": 0}, "CAPITAL_TOO_LOW"),
        ({"start_date": "2025-03-01", "end_date": "2025-01-01"}, "REVERSED_DATES"),
        ({"symbol": "QQQ"}, "UNSUPPORTED_SYMBOL"),
        ({"division_count": 25}, "UNSUPPORTED_DIVISION"),
    ],
)
def test_backtest_rejects_invalid_input(changes: dict[str, object], code: str) -> None:
    with pytest.raises(BacktestError) as caught:
        run_backtest(request(**changes))
    assert caught.value.code == code


def test_non_session_dates_are_mapped_to_effective_sessions() -> None:
    result = run_backtest(request(start_date="2025-01-04", end_date="2025-01-12"))
    assert result["assumptions"]["effective_dates"] == {"start": "2025-01-06", "end": "2025-01-10"}


def test_backtest_accepts_explicit_capital_above_old_dashboard_cap() -> None:
    result = run_backtest(request(capital=10000))
    assert result["request"]["capital"] == 10000


def test_soxl_backtest_uses_smh_weather_engine() -> None:
    result = run_backtest(request(symbol="SOXL"))
    assert result["request"]["symbol"] == "SOXL"
    assert result["daily"]
    assert result["weather_daily"]
    assert {row["symbol"] for row in result["weather_daily"]} == {"SOXL"}
    assert {row["signal_symbol"] for row in result["weather_daily"]} == {"SMH"}
    assert {row["benchmark_symbol"] for row in result["weather_daily"]} == {"SPY"}
    assert {row["ruleset_version"] for row in result["weather_daily"]} == {"regime-weather-1"}
    assert {item["symbol"] for item in result["summary"]["benchmarks"]} == {"SOXL", "SMH", "SPY"}
    assert set(result["daily"][0]["benchmark_equities"]) == {"SOXL", "SMH", "SPY"}
    assert {row["symbol"] for row in result["weather_research"]} == {"SOXL"}
