from __future__ import annotations

from datetime import date, datetime, time

import pytest

from jarvis.nlp.dates import describe, extract_when

NOW = datetime(2026, 10, 11, 10, 0)  # a Sunday


@pytest.mark.parametrize(
    ("text", "d", "t", "rest"),
    [
        ("call mom tomorrow", date(2026, 10, 12), None, "call mom"),
        ("submit report by friday", date(2026, 10, 16), None, "submit report"),
        ("team meeting next sunday at 4 pm", date(2026, 10, 18), time(16, 0), "team meeting"),
        ("dentist on 3rd november at 10:30 am", date(2026, 11, 3), time(10, 30), "dentist"),
        ("project demo oct 20", date(2026, 10, 20), None, "project demo"),
        ("pay rent on 5 october", date(2027, 10, 5), None, "pay rent"),  # past date -> next year
        ("standup at 17:00", None, time(17, 0), "standup"),
        ("dinner tonight", date(2026, 10, 11), time(20, 0), "dinner"),
        ("gym in 3 days", date(2026, 10, 14), None, "gym"),
        ("review at 5 in the evening", None, time(17, 0), "review"),
        ("buy groceries", None, None, "buy groceries"),
        ("meeting on 25/10", date(2026, 10, 25), None, "meeting"),
        ("JARVIS tomorrow", date(2026, 10, 12), None, "jarvis"),
    ],
)
def test_extract(text, d, t, rest):
    w = extract_when(text, NOW)
    assert (w.date, w.time, w.rest, w.ambiguous) == (d, t, rest, None)


@pytest.mark.parametrize(
    ("text", "question"),
    [
        ("meeting on 10/11", "Did you mean 10 November or 11 October"),
        ("call at 5", "Do you mean 5 AM or 5 PM?"),
        ("sync at 5:30", "in the morning or the evening"),
        ("party on 31 february", "doesn't exist"),
    ],
)
def test_ambiguous_asks(text, question):
    w = extract_when(text, NOW)
    assert w.ambiguous and question in w.ambiguous


def test_describe():
    assert describe("2026-10-12", "17:00", NOW) == "tomorrow at 5:00 PM"
    assert describe("2026-10-11", None, NOW) == "today"
    assert describe("2026-10-14", None, NOW) == "Wednesday"
