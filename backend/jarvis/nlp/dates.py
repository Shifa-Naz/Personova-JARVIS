"""Deterministic date/time extraction for tasks, reminders and calendar events.

``extract_when(text)`` finds a date and/or time phrase, removes it from the text, and
reports ambiguity instead of guessing (e.g. "12/10" or "at 5" without am/pm).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONTHS = {
    m: i + 1
    for i, m in enumerate(
        [
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        ]
    )
}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTHS["sept"] = 9
_MONTH_RE = "|".join(sorted(MONTHS, key=len, reverse=True))
PARTS_OF_DAY = {
    "morning": time(9, 0),
    "afternoon": time(14, 0),
    "evening": time(18, 0),
    "tonight": time(20, 0),
    "night": time(20, 0),
    "noon": time(12, 0),
    "midday": time(12, 0),
    "midnight": time(0, 0),
}


@dataclass
class When:
    date: date | None = None
    time: time | None = None
    rest: str = ""
    ambiguous: str | None = None  # a clarifying question when the phrase can't be resolved safely

    @property
    def found(self) -> bool:
        return self.date is not None or self.time is not None

    def date_str(self) -> str | None:
        return self.date.isoformat() if self.date else None

    def time_str(self) -> str | None:
        return self.time.strftime("%H:%M") if self.time else None


def _cut(text: str, match: re.Match) -> str:
    return (text[: match.start()] + " " + text[match.end() :]).strip()


def _tidy(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip(" ,.")
    return re.sub(r"\b(?:on|at|by|for|due|before)$", "", text).strip(" ,.")


def _next_weekday(today: date, weekday: int, force_next: bool) -> date:
    """'friday'/'this friday' = the coming Friday (today if it is Friday); 'next friday' never means today."""
    days = (weekday - today.weekday()) % 7
    if force_next and days == 0:
        days = 7
    return today + timedelta(days=days)


def extract_when(text: str, now: datetime | None = None) -> When:
    now = now or datetime.now()
    today = now.date()
    t = f" {text.lower()} "
    result = When()

    # ---- dates --------------------------------------------------------
    patterns = [
        (r"\b(?:on |by |for |due )?the day after tomorrow\b", lambda m: today + timedelta(days=2)),
        (r"\b(?:on |by |for |due )?day after tomorrow\b", lambda m: today + timedelta(days=2)),
        (r"\b(?:by |for |due )?tomorrow\b", lambda m: today + timedelta(days=1)),
        (r"\b(?:by |for |due )?today\b", lambda m: today),  # "tonight" is handled with times
        (r"\bin (\d{1,2}) days?\b", lambda m: today + timedelta(days=int(m.group(1)))),
        (r"\bin (?:a|one) week\b|\bnext week\b", lambda m: today + timedelta(days=7)),
        (
            rf"\b(?:on |by |for |due )?(?:this |next |coming )?({'|'.join(WEEKDAYS)})\b",
            lambda m: _next_weekday(today, WEEKDAYS.index(m.group(1)), "next" in m.group(0)),
        ),
        (r"\b(?:on |by )?(\d{4})-(\d{2})-(\d{2})\b", lambda m: date(int(m.group(1)), int(m.group(2)), int(m.group(3)))),
        (
            rf"\b(?:on |by )?(?:the )?(\d{{1,2}})(?:st|nd|rd|th)?(?: of)? ({_MONTH_RE})\b(?:,? (\d{{4}}))?",
            lambda m: _future(today, int(m.group(1)), MONTHS[m.group(2)], m.group(3)),
        ),
        (
            rf"\b(?:on |by )?({_MONTH_RE}) (\d{{1,2}})(?:st|nd|rd|th)?\b(?:,? (\d{{4}}))?",
            lambda m: _future(today, int(m.group(2)), MONTHS[m.group(1)], m.group(3)),
        ),
        (r"\b(?:on |by )?(?:the )?(\d{1,2})(?:st|nd|rd|th)\b", lambda m: _day_of_month(today, int(m.group(1)))),
    ]
    numeric = re.search(r"\b(?:on |by )?(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?\b", t)
    for pattern, resolve in patterns:
        m = re.search(pattern, t)
        if m:
            try:
                result.date = resolve(m)
            except ValueError:
                result.ambiguous = "That date doesn't exist. Which date did you mean?"
                return result
            t = f" {_cut(t, m)} "
            break
    else:
        if numeric:
            a, b = int(numeric.group(1)), int(numeric.group(2))
            if a <= 12 and b <= 12 and a != b:
                result.ambiguous = (
                    f"Did you mean {a} {_month_name(b)} or {b} {_month_name(a)}? Please say the month name."
                )
                return result
            day, month = (a, b) if a > 12 or a == b else (b, a)
            try:
                result.date = _future(today, day, month, numeric.group(3))
            except ValueError:
                result.ambiguous = "That date doesn't exist. Which date did you mean?"
                return result
            t = f" {_cut(t, numeric)} "

    # ---- times --------------------------------------------------------
    m = re.search(r"\b(?:at |by |around )?(\d{1,2})(?::(\d{2}))? ?(a\.?m\.?|p\.?m\.?)(?=\W|$)", t)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2) or 0)
        if not 1 <= hour <= 12 or minute > 59:
            result.ambiguous = "That time doesn't look right. What time did you mean?"
            return result
        pm = m.group(3).startswith("p")
        result.time = time((hour % 12) + (12 if pm else 0), minute)
        t = f" {_cut(t, m)} "
    else:
        m = re.search(r"\b(?:at |by |around )?([01]?\d|2[0-3]):([0-5]\d)\b", t)
        if m:
            hour, minute = int(m.group(1)), int(m.group(2))
            if 1 <= hour <= 11 and not re.search(r"\b(?:morning|evening|afternoon|night|tonight)\b", t):
                # "at 5:30" — 5:30 am or pm? 13:00-23:59 and 00:xx are unambiguous.
                result.ambiguous = f"Is that {hour}:{minute:02d} in the morning or the evening?"
                return result
            result.time = time(hour, minute)
            t = f" {_cut(t, m)} "
        else:
            m = re.search(r"\bat (\d{1,2})(?: o'?clock)?\b(?! ?(?:days?|weeks?|%|percent))", t)
            if m:
                hour = int(m.group(1))
                if hour > 23:
                    result.ambiguous = "That time doesn't look right. What time did you mean?"
                    return result
                if 1 <= hour <= 12 and not re.search(r"\b(?:morning|evening|afternoon|night|tonight)\b", t):
                    result.ambiguous = f"Do you mean {hour} AM or {hour} PM?"
                    return result
                result.time = time(hour % 24, 0)
                t = f" {_cut(t, m)} "
    pod = re.search(r"\b(?:in the |this |at )?(morning|afternoon|evening|tonight|night|noon|midday|midnight)\b", t)
    if pod:
        part = PARTS_OF_DAY[pod.group(1)]
        if result.time is None:
            result.time = part
        elif part.hour >= 12 > result.time.hour:  # "at 5 in the evening" -> 17:00
            result.time = time(result.time.hour + 12, result.time.minute)
        if pod.group(1) == "tonight" and result.date is None:
            result.date = today
        t = f" {_cut(t, pod)} "

    result.rest = _tidy(t)
    return result


def _future(today: date, day: int, month: int, year: str | None) -> date:
    if year:
        y = int(year)
        y = y + 2000 if y < 100 else y
        return date(y, month, day)
    candidate = date(today.year, month, day)
    return candidate if candidate >= today else date(today.year + 1, month, day)


def _day_of_month(today: date, day: int) -> date:
    candidate = date(today.year, today.month, day)
    if candidate >= today:
        return candidate
    month, year = (today.month % 12) + 1, today.year + (1 if today.month == 12 else 0)
    return date(year, month, day)


def _month_name(n: int) -> str:
    return datetime(2000, n, 1).strftime("%B")


def describe(d: str | None, t: str | None, now: datetime | None = None) -> str:
    """Human phrase for a stored date/time, e.g. 'tomorrow at 5:00 PM'."""
    now = now or datetime.now()
    parts = []
    if d:
        day = date.fromisoformat(d)
        delta = (day - now.date()).days
        if delta == 0:
            parts.append("today")
        elif delta == 1:
            parts.append("tomorrow")
        elif delta == -1:
            parts.append("yesterday")
        elif 1 < delta < 7:
            parts.append(day.strftime("%A"))
        else:
            parts.append(f"{day.strftime('%A')}, {day.day} {day.strftime('%B')}")
    if t:
        hh, mm = (int(x) for x in t.split(":"))
        parts.append("at " + time(hh, mm).strftime("%I:%M %p").lstrip("0"))
    return " ".join(parts)
