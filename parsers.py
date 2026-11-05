"""Regex and keyword parsing for reminders and expenses.

No LLM API is used. The rules are intentionally small and easy to explain:
- Reminders need "remind me to ... at <time>", with optional daily/weekly words.
- Expenses start with spent/paid/bought, followed by an amount and optional note.
"""

import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import config


class ParseError(ValueError):
    """A short, user-friendly explanation of what was missing."""


@dataclass(frozen=True)
class ParsedReminder:
    title: str
    when: datetime
    recurrence: str  # "none", "daily", or "weekly"


@dataclass(frozen=True)
class ParsedExpense:
    amount: float
    category: str
    note: str


REMIND_PREFIX_RE = re.compile(r"^remind\s+me\s+(?:to\s+)?", re.IGNORECASE)
TIME_RE = re.compile(r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)?", re.IGNORECASE)
DAILY_RE = re.compile(r"\b(?:every\s*day|daily)\b", re.IGNORECASE)
WEEKLY_DAY_RE = re.compile(
    r"\b(?:every|each)\s+"
    r"(monday|mon|tuesday|tue|wednesday|wed|thursday|thu|"
    r"friday|fri|saturday|sat|sunday|sun)\b",
    re.IGNORECASE,
)
WEEKLY_RE = re.compile(r"\bweekly\b", re.IGNORECASE)
MONTHLY_RE = re.compile(r"\b(?:every\s+month|monthly)\b", re.IGNORECASE)
TOMORROW_RE = re.compile(r"\btomorrow\b", re.IGNORECASE)
TODAY_RE = re.compile(r"\btoday\b", re.IGNORECASE)

WEEKDAYS = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}

EXPENSE_RE = re.compile(
    r"^\s*(?:i\s+)?(?:spent|paid|bought)\s+"
    r"(?:₹|rs\.?|inr)?\s*"
    r"(?P<amount>\d+(?:,\d{2,3})*(?:\.\d{1,2})?)"
    r"\s*(?:(?:on|for|at)\s+)?"
    r"(?P<note>.*?)\s*$",
    re.IGNORECASE,
)

# Order matters: the first matching category wins.
CATEGORY_WORDS: dict[str, set[str]] = {
    "Food": {
        "food", "lunch", "dinner", "breakfast", "snack", "snacks", "meal",
        "canteen", "cafeteria", "mess", "restaurant", "coffee", "tea", "milk",
        "pizza", "burger", "sandwich", "biryani", "samosa", "chocolate",
        "fruits", "groceries", "grocery", "chicken",
    },
    "Travel": {
        "bus", "auto", "cab", "taxi", "train", "metro", "uber", "ola",
        "fuel", "petrol", "diesel", "travel", "ticket", "flight", "railway",
        "parking",
    },
    "Study": {
        "book", "books", "notebook", "pen", "pens", "stationery", "print",
        "printing", "xerox", "exam", "course", "lab", "tuition", "assignment",
        "project", "college",
    },
    "Bills": {
        "bill", "bills", "electricity", "internet", "wifi", "recharge",
        "rent", "gas", "phone", "mobile", "maintenance", "subscription",
    },
    "Shopping": {
        "shirt", "shoes", "clothes", "dress", "amazon", "flipkart", "shopping",
        "headphones", "bag", "watch", "gift", "order",
    },
}


def _clean_title(value: str) -> str:
    """Remove leftover joining words and extra spaces from a reminder title."""
    title = re.sub(r"\s+", " ", value).strip(" .,-")
    title = re.sub(r"^to\s+", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s+(?:at|on|by)\s*$", "", title, flags=re.IGNORECASE)
    return title.strip(" .,-")


def parse_reminder(text: str, now: datetime | None = None) -> ParsedReminder:
    """Parse 'remind me to <title> [daily] at <time>' into a datetime.

    Raises ParseError with a one-line question when the message is ambiguous.
    """
    tz = ZoneInfo(config.TIMEZONE)
    if now is None:
        current = datetime.now(tz)
    elif now.tzinfo is None:
        current = now.replace(tzinfo=tz)
    else:
        current = now.astimezone(tz)

    prefix = REMIND_PREFIX_RE.match(text.strip())
    if not prefix:
        raise ParseError("Start with: remind me to ... at 5pm.")

    working = text.strip()[prefix.end():].strip()
    if not working:
        raise ParseError("What should I remind you about?")

    recurrence = "none"
    weekday: int | None = None

    if DAILY_RE.search(working):
        recurrence = "daily"
        working = DAILY_RE.sub(" ", working)
    elif match := WEEKLY_DAY_RE.search(working):
        recurrence = "weekly"
        weekday = WEEKDAYS[match.group(1).lower()]
        working = working[:match.start()] + " " + working[match.end():]
    elif WEEKLY_RE.search(working):
        recurrence = "weekly"
        working = WEEKLY_RE.sub(" ", working)
    elif MONTHLY_RE.search(working) or re.search(
        r"\bevery\s+\d+\s+(?:day|week|month)s?\b", working, re.IGNORECASE
    ):
        raise ParseError("I can repeat reminders daily or weekly.")

    day_offset: int | None = None
    if TOMORROW_RE.search(working):
        day_offset = 1
        working = TOMORROW_RE.sub(" ", working)
    elif TODAY_RE.search(working):
        day_offset = 0
        working = TODAY_RE.sub(" ", working)

    time_match = TIME_RE.search(working)
    if not time_match:
        raise ParseError("What time? Add it like 'at 5pm' or 'at 17:00'.")

    hour = int(time_match.group(1))
    minute = int(time_match.group(2) or "0")
    meridiem = (time_match.group(3) or "").replace(".", "").lower()

    if hour > 23 or minute > 59:
        raise ParseError("That time looks invalid. Try 'at 5pm' or 'at 17:30'.")

    if meridiem:
        if not 1 <= hour <= 12:
            raise ParseError("Use 5pm or 17:00, not 13pm.")
        if meridiem == "am":
            hour = hour % 12
        else:
            hour = (hour % 12) + 12
    elif 1 <= hour <= 12:
        raise ParseError("AM or PM? Add it like '5pm' or use 17:00.")

    working = working[:time_match.start()] + " " + working[time_match.end():]
    title = _clean_title(working)
    if not title:
        raise ParseError("What should I remind you about?")

    local_time = time(hour, minute, tzinfo=tz)
    today = current.date()
    candidate = datetime.combine(today, local_time)

    if recurrence == "daily":
        if candidate <= current:
            candidate += timedelta(days=1)
    elif recurrence == "weekly":
        if weekday is not None:
            days_ahead = (weekday - today.weekday()) % 7
            candidate = datetime.combine(
                today + timedelta(days=days_ahead), local_time
            )
            if candidate <= current:
                candidate += timedelta(days=7)
        elif candidate <= current:
            candidate += timedelta(days=7)
    else:
        if day_offset == 1:
            candidate = datetime.combine(today + timedelta(days=1), local_time)
        elif day_offset == 0:
            if candidate <= current:
                raise ParseError(
                    "That time has already passed today. Try 'tomorrow at ...'."
                )
        elif candidate <= current:
            candidate += timedelta(days=1)

    return ParsedReminder(title=title, when=candidate, recurrence=recurrence)


def looks_like_expense(text: str) -> bool:
    return bool(
        re.match(
            r"^\s*(?:i\s+)?(?:spent|paid|bought)\b", text, re.IGNORECASE
        )
    )


def categorize(note: str) -> str:
    """Pick a category using simple keyword rules, defaulting to Other."""
    words = set(re.findall(r"[a-z]+", note.lower()))
    for category, keywords in CATEGORY_WORDS.items():
        if words & keywords:
            return category
    return "Other"


def parse_expense(text: str) -> ParsedExpense:
    """Parse 'spent 120 on lunch' into amount, category, and note."""
    match = EXPENSE_RE.match(text.strip())
    if not match:
        raise ParseError("How much? Example: spent 120 on lunch.")

    amount = float(match.group("amount").replace(",", ""))
    if amount <= 0:
        raise ParseError("The amount must be more than zero.")

    note = re.sub(r"\s+", " ", match.group("note") or "").strip(" .")
    return ParsedExpense(amount=amount, category=categorize(note), note=note)
