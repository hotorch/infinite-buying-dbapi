from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd

NEW_YORK = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")


@dataclass(frozen=True, slots=True)
class SessionSchedule:
    session_date: date
    premarket_open: datetime
    sell_phase_at: datetime
    regular_open: datetime
    buy_phase_at: datetime
    regular_close: datetime
    loc_cutoff: datetime


def session_schedule(session_date: date, buffer_minutes: int = 5) -> SessionSchedule:
    calendar = xcals.get_calendar("XNYS")
    label = pd.Timestamp(session_date)
    if not calendar.is_session(label):
        raise ValueError(f"not a US trading session: {session_date}")
    regular_open = calendar.session_open(label).to_pydatetime().astimezone(NEW_YORK)
    regular_close = calendar.session_close(label).to_pydatetime().astimezone(NEW_YORK)
    premarket_open = datetime.combine(session_date, time(4, 0), tzinfo=NEW_YORK)
    return SessionSchedule(
        session_date=session_date,
        premarket_open=premarket_open,
        sell_phase_at=premarket_open + timedelta(minutes=buffer_minutes),
        regular_open=regular_open,
        buy_phase_at=regular_open + timedelta(minutes=buffer_minutes),
        regular_close=regular_close,
        loc_cutoff=regular_close - timedelta(minutes=10),
    )


def next_session(day: date) -> date:
    calendar = xcals.get_calendar("XNYS")
    label = calendar.date_to_session(pd.Timestamp(day), direction="next")
    return label.date()
