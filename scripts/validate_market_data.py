from __future__ import annotations

import csv
import hashlib
import json
import math
from datetime import date
from pathlib import Path
from typing import Any

import exchange_calendars as xcals

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "market"
REQUIRED_COLUMNS = ["date", "symbol", "open", "high", "low", "close", "volume"]


def validate_all(data_dir: Path = DATA_DIR) -> list[dict[str, Any]]:
    metadata = json.loads((data_dir / "metadata.json").read_text(encoding="utf-8"))
    summaries = []
    for filename, expected in metadata["files"].items():
        summaries.append(_validate_file(data_dir / filename, expected))
    return summaries


def _validate_file(path: Path, expected: dict[str, Any]) -> dict[str, Any]:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected["sha256"]:
        raise ValueError(f"{path.name}: SHA-256 mismatch")

    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != REQUIRED_COLUMNS:
            raise ValueError(f"{path.name}: unexpected columns {reader.fieldnames}")
        rows = list(reader)

    if len(rows) != expected["rows"]:
        raise ValueError(f"{path.name}: expected {expected['rows']} rows, got {len(rows)}")

    parsed_dates: list[date] = []
    for line_number, row in enumerate(rows, start=2):
        if row["symbol"] != expected["symbol"]:
            raise ValueError(f"{path.name}:{line_number}: unexpected symbol {row['symbol']}")
        parsed_dates.append(date.fromisoformat(row["date"]))
        open_price, high, low, close, volume = _numeric_values(path, line_number, row)
        if min(open_price, high, low, close) <= 0 or volume < 0:
            raise ValueError(f"{path.name}:{line_number}: prices must be positive and volume non-negative")
        if high < max(open_price, low, close) or low > min(open_price, high, close):
            raise ValueError(f"{path.name}:{line_number}: invalid OHLC relationship")

    if parsed_dates != sorted(parsed_dates):
        raise ValueError(f"{path.name}: dates are not ascending")
    if len(parsed_dates) != len(set(parsed_dates)):
        raise ValueError(f"{path.name}: duplicate dates")
    if parsed_dates[0].isoformat() != expected["first_date"] or parsed_dates[-1].isoformat() != expected["last_date"]:
        raise ValueError(f"{path.name}: date range does not match metadata")

    _validate_sessions(path.name, parsed_dates)
    return {
        "file": path.name,
        "rows": len(rows),
        "first_date": parsed_dates[0].isoformat(),
        "last_date": parsed_dates[-1].isoformat(),
        "sha256": digest,
    }


def _numeric_values(path: Path, line_number: int, row: dict[str, str]) -> tuple[float, float, float, float, float]:
    try:
        values = tuple(float(row[key]) for key in ("open", "high", "low", "close", "volume"))
    except (TypeError, ValueError) as error:
        raise ValueError(f"{path.name}:{line_number}: invalid numeric value") from error
    if not all(math.isfinite(value) for value in values):
        raise ValueError(f"{path.name}:{line_number}: non-finite numeric value")
    return values  # type: ignore[return-value]


def _validate_sessions(filename: str, parsed_dates: list[date]) -> None:
    calendar = xcals.get_calendar("XNYS")
    start = max(parsed_dates[0], calendar.first_session.date())
    end = min(parsed_dates[-1], calendar.last_session.date())
    if start > end:
        return
    actual = {value for value in parsed_dates if start <= value <= end}
    expected = {session.date() for session in calendar.sessions_in_range(start, end)}
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        raise ValueError(f"{filename}: calendar mismatch; missing={missing[:5]}, extra={extra[:5]}")


def main() -> None:
    for summary in validate_all():
        print(
            f"{summary['file']}: {summary['rows']} rows, "
            f"{summary['first_date']}..{summary['last_date']}, SHA-256 OK"
        )


if __name__ == "__main__":
    main()
