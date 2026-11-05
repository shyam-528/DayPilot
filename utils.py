"""Small shared helpers for timezone-safe time and money formatting."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import config

TZ = ZoneInfo(config.TIMEZONE)


def now_local() -> datetime:
    """Current time as an aware datetime in Asia/Kolkata."""
    return datetime.now(TZ)


def to_local(value: datetime) -> datetime:
    """Convert any aware datetime to the configured local timezone."""
    return value.astimezone(TZ)


def clock(value: datetime) -> str:
    """Format a time like 5:00 PM (no leading zero)."""
    return to_local(value).strftime("%I:%M %p").lstrip("0")


def describe_when(value: datetime, now: datetime | None = None) -> str:
    """Short human label: '5:00 PM', 'tomorrow, 9:00 AM', etc."""
    local = to_local(value)
    current = to_local(now) if now else now_local()

    if local.date() == current.date():
        return clock(local)
    if local.date() == current.date() + timedelta(days=1):
        return f"tomorrow, {clock(local)}"
    return f"{local.strftime('%a %d %b')}, {clock(local)}"


def task_time_label(iso_value: str) -> str:
    """Format a stored ISO timestamp for the /tasks list."""
    local = datetime.fromisoformat(iso_value).astimezone(TZ)
    current = now_local()

    if local.date() == current.date():
        return clock(local)
    return f"{local.strftime('%a %d %b')}, {clock(local)}"


def money(amount: float) -> str:
    """Render rupees: 1200 -> ₹1,200 and 120.5 -> ₹120.50."""
    if abs(amount - round(amount)) < 0.005:
        return f"₹{round(amount):,}"
    return f"₹{amount:,.2f}"
