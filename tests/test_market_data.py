from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from infinite_buying_dbapi import market_data as market_data_module
from infinite_buying_dbapi.market_data import MarketDataError, collect_market_data, latest_completed_session


class FakeSource:
    def __init__(self, closes: dict[str, dict[date, Decimal]]) -> None:
        self.closes = closes
        self.calls: list[tuple[str, date, date]] = []

    def daily_candles(self, symbol: str, start: date, end: date, market_code: str = "FN") -> list[dict[str, object]]:
        self.calls.append((symbol, start, end))
        return [
            {"date": day, "open": close, "high": close, "low": close, "close": close, "volume": 100}
            for day, close in self.closes[symbol].items()
            if start <= day <= end
        ]


def test_latest_completed_session_respects_new_york_close() -> None:
    eastern = ZoneInfo("America/New_York")
    assert latest_completed_session(datetime(2026, 7, 13, 15, 59, tzinfo=eastern)) == date(2026, 7, 10)
    assert latest_completed_session(datetime(2026, 7, 13, 16, 1, tzinfo=eastern)) == date(2026, 7, 13)


def test_collect_appends_through_latest_completed_session_and_updates_metadata(tmp_path: Path, monkeypatch) -> None:
    _use_short_fixture_bootstrap(monkeypatch)
    _seed(tmp_path, "TQQQ", "10")
    _seed(tmp_path, "SOXL", "15")
    _seed(tmp_path, "QQQ", "20")
    _seed(tmp_path, "SMH", "25")
    _seed(tmp_path, "SPY", "30")
    source = FakeSource(
        {
            "TQQQ": {date(2026, 7, 10): Decimal("10"), date(2026, 7, 13): Decimal("10")},
            "SOXL": {date(2026, 7, 10): Decimal("15"), date(2026, 7, 13): Decimal("16")},
            "QQQ": {date(2026, 7, 10): Decimal("20"), date(2026, 7, 13): Decimal("21")},
            "SMH": {date(2026, 7, 10): Decimal("25"), date(2026, 7, 13): Decimal("26")},
            "SPY": {date(2026, 7, 10): Decimal("30"), date(2026, 7, 13): Decimal("31")},
        }
    )

    result = collect_market_data(source, tmp_path, datetime(2026, 7, 13, 16, 1, tzinfo=ZoneInfo("America/New_York")))

    assert result["updated"] is True
    assert result["added"] == 5
    assert (tmp_path / "tqqq_adjusted_daily.csv").read_text(encoding="utf-8").splitlines()[-1] == "2026-07-13,TQQQ,10,10,10,10,100"
    metadata = json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["files"]["qqq_adjusted_daily.csv"]["last_date"] == "2026-07-13"


def test_collect_refuses_mismatched_price_basis_without_writing(tmp_path: Path, monkeypatch) -> None:
    _use_short_fixture_bootstrap(monkeypatch)
    _seed(tmp_path, "TQQQ", "10")
    _seed(tmp_path, "SOXL", "15")
    _seed(tmp_path, "QQQ", "20")
    _seed(tmp_path, "SMH", "25")
    _seed(tmp_path, "SPY", "30")
    before = (tmp_path / "tqqq_adjusted_daily.csv").read_bytes()
    source = FakeSource(
        {
            "TQQQ": {date(2026, 7, 10): Decimal("99"), date(2026, 7, 13): Decimal("11")},
            "SOXL": {date(2026, 7, 10): Decimal("15"), date(2026, 7, 13): Decimal("16")},
            "QQQ": {date(2026, 7, 10): Decimal("20"), date(2026, 7, 13): Decimal("21")},
            "SMH": {date(2026, 7, 10): Decimal("25"), date(2026, 7, 13): Decimal("26")},
            "SPY": {date(2026, 7, 10): Decimal("30"), date(2026, 7, 13): Decimal("31")},
        }
    )

    with pytest.raises(MarketDataError, match="refusing to mix price bases"):
        collect_market_data(source, tmp_path, datetime(2026, 7, 13, 16, 1, tzinfo=ZoneInfo("America/New_York")))
    assert (tmp_path / "tqqq_adjusted_daily.csv").read_bytes() == before


def test_collect_backfills_a_truncated_history(tmp_path: Path, monkeypatch) -> None:
    _use_short_fixture_bootstrap(monkeypatch)
    for symbol, close in (("TQQQ", "10"), ("SOXL", "15"), ("QQQ", "20"), ("SMH", "25"), ("SPY", "30")):
        _seed(tmp_path, symbol, close)
    (tmp_path / "spy_adjusted_daily.csv").write_text(
        "date,symbol,open,high,low,close,volume\n2026-07-13,SPY,31,31,31,31,100\n",
        encoding="utf-8",
    )
    source = FakeSource(
        {
            "TQQQ": {date(2026, 7, 10): Decimal("10"), date(2026, 7, 13): Decimal("10")},
            "SOXL": {date(2026, 7, 10): Decimal("15"), date(2026, 7, 13): Decimal("16")},
            "QQQ": {date(2026, 7, 10): Decimal("20"), date(2026, 7, 13): Decimal("21")},
            "SMH": {date(2026, 7, 10): Decimal("25"), date(2026, 7, 13): Decimal("26")},
            "SPY": {date(2026, 7, 10): Decimal("30"), date(2026, 7, 13): Decimal("31")},
        }
    )

    collect_market_data(source, tmp_path, datetime(2026, 7, 13, 16, 1, tzinfo=ZoneInfo("America/New_York")))

    assert ("SPY", date(2026, 7, 10), date(2026, 7, 13)) in source.calls
    assert (tmp_path / "spy_adjusted_daily.csv").read_text(encoding="utf-8").splitlines()[1].startswith("2026-07-10,SPY,")


def _seed(directory: Path, symbol: str, close: str) -> None:
    filename = f"{symbol.lower()}_adjusted_daily.csv"
    content = f"date,symbol,open,high,low,close,volume\n2026-07-10,{symbol},{close},{close},{close},{close},100\n"
    (directory / filename).write_text(content, encoding="utf-8")
    metadata_path = directory / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {"files": {}}
    metadata["files"][filename] = {"symbol": symbol, "rows": 1, "first_date": "2026-07-10", "last_date": "2026-07-10", "sha256": "unused"}
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")


def _use_short_fixture_bootstrap(monkeypatch) -> None:
    monkeypatch.setattr(market_data_module, "BOOTSTRAP_START_DATES", {symbol: date(2026, 7, 10) for symbol in market_data_module.COLLECTED_SYMBOLS})
