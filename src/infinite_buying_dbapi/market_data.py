from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import tempfile
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

import exchange_calendars as xcals
import pandas as pd

from .market_calendar import NEW_YORK

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "market"
COLLECTED_SYMBOLS = ("TQQQ", "SOXL", "QQQ")
MARKET_CODES = {"TQQQ": "FN", "SOXL": "FA", "QQQ": "FN"}
CSV_COLUMNS = ("date", "symbol", "open", "high", "low", "close", "volume")


class CandleSource(Protocol):
    def daily_candles(self, symbol: str, start: date, end: date, market_code: str = "FN") -> list[dict[str, Any]]: ...


class MarketDataError(RuntimeError):
    pass


def latest_completed_session(now: datetime | None = None) -> date:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must include a timezone")
    current_utc = current.astimezone(timezone.utc)
    new_york_day = current_utc.astimezone(NEW_YORK).date()
    calendar = xcals.get_calendar("XNYS")
    session = calendar.date_to_session(pd.Timestamp(new_york_day), direction="previous")
    if session.date() == new_york_day and current_utc < calendar.session_close(session).to_pydatetime():
        session = calendar.previous_session(session)
    return session.date()


def market_data_status(data_dir: Path = DATA_DIR, now: datetime | None = None) -> dict[str, Any]:
    target = latest_completed_session(now)
    symbols = []
    for symbol in COLLECTED_SYMBOLS:
        rows = _read_rows(data_dir / _filename(symbol), symbol)
        last_date = date.fromisoformat(rows[-1]["date"])
        symbols.append({"symbol": symbol, "last_date": last_date.isoformat(), "needs_update": last_date < target})
    return {
        "latest_completed_session": target.isoformat(),
        "needs_update": any(item["needs_update"] for item in symbols),
        "symbols": symbols,
    }


def collect_market_data(source: CandleSource, data_dir: Path = DATA_DIR, now: datetime | None = None) -> dict[str, Any]:
    target = latest_completed_session(now)
    prepared: dict[str, bytes] = {}
    summaries: list[dict[str, Any]] = []

    for symbol in COLLECTED_SYMBOLS:
        path = data_dir / _filename(symbol)
        rows = _read_rows(path, symbol)
        previous_last = date.fromisoformat(rows[-1]["date"])
        if previous_last >= target:
            summaries.append(
                {"symbol": symbol, "previous_last_date": previous_last.isoformat(), "last_date": previous_last.isoformat(), "added": 0}
            )
            continue

        fetched = source.daily_candles(symbol, previous_last, target, market_code=MARKET_CODES[symbol])
        fetched_by_date = {item["date"]: item for item in fetched if previous_last <= item["date"] <= target}
        expected = {stamp.date() for stamp in xcals.get_calendar("XNYS").sessions_in_range(previous_last, target)}
        missing = sorted(expected - set(fetched_by_date))
        if missing:
            raise MarketDataError(f"{symbol}: DB Securities did not return completed sessions: {', '.join(day.isoformat() for day in missing[:5])}")

        _assert_overlap_matches(symbol, rows[-1], fetched_by_date[previous_last])
        additions = [_row_from_candle(symbol, fetched_by_date[day]) for day in sorted(fetched_by_date) if day > previous_last]
        merged = rows + additions
        _validate_rows(symbol, merged)
        prepared[symbol] = _csv_bytes(merged)
        summaries.append(
            {
                "symbol": symbol,
                "previous_last_date": previous_last.isoformat(),
                "last_date": merged[-1]["date"],
                "added": len(additions),
            }
        )

    if prepared:
        _commit_files(data_dir, prepared, target)

    return {
        "latest_completed_session": target.isoformat(),
        "updated": bool(prepared),
        "added": sum(item["added"] for item in summaries),
        "symbols": summaries,
    }


def _filename(symbol: str) -> str:
    return f"{symbol.lower()}_adjusted_daily.csv"


def _read_rows(path: Path, symbol: str) -> list[dict[str, str]]:
    if not path.exists():
        raise MarketDataError(f"{symbol}: market data file is missing")
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != CSV_COLUMNS:
            raise MarketDataError(f"{symbol}: market data columns are invalid")
        rows = [dict(row) for row in reader]
    if not rows:
        raise MarketDataError(f"{symbol}: market data file is empty")
    _validate_rows(symbol, rows)
    return rows


def _validate_rows(symbol: str, rows: list[dict[str, str]]) -> None:
    parsed_dates: list[date] = []
    for row in rows:
        if row["symbol"] != symbol:
            raise MarketDataError(f"{symbol}: market data contains another symbol")
        row_date = date.fromisoformat(row["date"])
        parsed_dates.append(row_date)
        open_price, high, low, close = (Decimal(row[key]) for key in ("open", "high", "low", "close"))
        volume = Decimal(row["volume"])
        if min(open_price, high, low, close) <= 0 or volume < 0 or high < max(open_price, low, close) or low > min(open_price, high, close):
            raise MarketDataError(f"{symbol}: invalid OHLCV row on {row_date.isoformat()}")
    if parsed_dates != sorted(parsed_dates) or len(parsed_dates) != len(set(parsed_dates)):
        raise MarketDataError(f"{symbol}: dates must be unique and ascending")


def _assert_overlap_matches(symbol: str, stored: dict[str, str], fetched: dict[str, Any]) -> None:
    for key in ("open", "high", "low", "close", "volume"):
        if Decimal(stored[key]) != Decimal(str(fetched[key])):
            raise MarketDataError(f"{symbol}: stored and DB Securities {key} differ on {stored['date']}; refusing to mix price bases")


def _row_from_candle(symbol: str, candle: dict[str, Any]) -> dict[str, str]:
    return {
        "date": candle["date"].isoformat(),
        "symbol": symbol,
        "open": _decimal_text(candle["open"]),
        "high": _decimal_text(candle["high"]),
        "low": _decimal_text(candle["low"]),
        "close": _decimal_text(candle["close"]),
        "volume": str(int(candle["volume"])),
    }


def _decimal_text(value: Any) -> str:
    text = format(Decimal(str(value)), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _csv_bytes(rows: list[dict[str, str]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def _commit_files(data_dir: Path, prepared: dict[str, bytes], target: date) -> None:
    metadata_path = data_dir / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["generated_on"] = date.today().isoformat()
    metadata["incremental_updates"] = {
        "source": "DB Securities Open API",
        "endpoint": "/api/v1/quote/overseas-stock/chart/day",
        "adjusted_price_request": "InputOrgAdjPrc=1",
        "latest_completed_session": target.isoformat(),
    }

    for symbol, content in prepared.items():
        rows = list(csv.DictReader(io.StringIO(content.decode("utf-8"))))
        metadata["files"][_filename(symbol)] = {
            "symbol": symbol,
            "rows": len(rows),
            "first_date": rows[0]["date"],
            "last_date": rows[-1]["date"],
            "sha256": hashlib.sha256(content).hexdigest(),
        }

    temporary: list[tuple[Path, Path]] = []
    try:
        for symbol, content in prepared.items():
            target_path = data_dir / _filename(symbol)
            temporary.append((_write_temp(data_dir, target_path.name, content), target_path))
        metadata_bytes = (json.dumps(metadata, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        temporary.append((_write_temp(data_dir, metadata_path.name, metadata_bytes), metadata_path))
        for temp_path, target_path in temporary:
            os.replace(temp_path, target_path)
    finally:
        for temp_path, _ in temporary:
            temp_path.unlink(missing_ok=True)


def _write_temp(directory: Path, filename: str, content: bytes) -> Path:
    descriptor, raw_path = tempfile.mkstemp(prefix=f".{filename}.", suffix=".tmp", dir=directory)
    path = Path(raw_path)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    return path
