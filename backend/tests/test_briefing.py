"""Briefing, schedule, news, machine status, lid-open watcher, live speech and OCR result shapes."""

from __future__ import annotations

import json
import random
from datetime import date, datetime, timedelta

import pytest

from jarvis.actions.base import ActionError
from jarvis.briefing import build_briefing, schedule_today, time_label
from jarvis.news import NewsService, parse_feed
from jarvis.nlp.speech import SpeechStreamer, to_speech
from jarvis.vision.ocr import OcrEngine, rapid_lines
from jarvis.wake_watch import COOLDOWN_S, MIN_LOCK_S, EventBus, WakeWatcher

TOKEN = {"X-Jarvis-Token": "test-token", "Origin": "http://localhost:8080"}

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>TechCrunch</title>
<item><title>Chip &amp; AI news - The Verge</title><link>https://example.com/1</link><source>The Verge</source></item>
<item><title>Second story</title><link>https://example.com/2</link></item>
<item><title>Bad link</title><link>javascript:alert(1)</link></item>
<item><title>Third story</title><link>https://example.com/3</link></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>The Verge</title>
<entry><title>Atom one</title><link rel="alternate" href="https://example.com/a"/><updated>2026-11-02</updated></entry>
<entry><title>Atom two</title><link href="https://example.com/b"/></entry>
<entry><title>Atom three</title><link href="https://example.com/c"/></entry>
</feed>"""


# ---------------------------------------------------------------- news
def test_parse_rss_splits_source_and_drops_unsafe_links():
    items = parse_feed(RSS, "https://techcrunch.com/feed/")
    assert [h.title for h in items] == ["Chip & AI news", "Second story", "Third story"]
    assert items[0].source == "The Verge" and items[1].source == "TechCrunch"


def test_parse_atom():
    items = parse_feed(ATOM)
    assert [h.url for h in items] == ["https://example.com/a", "https://example.com/b", "https://example.com/c"]
    assert items[0].source == "The Verge"


def test_feed_with_entities_is_refused():
    bomb = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><rss><channel></channel></rss>'
    with pytest.raises(ValueError):
        parse_feed(bomb)


def test_news_falls_back_to_next_feed_and_caches():
    calls = []

    def fetch(url):
        calls.append(url)
        if "first" in url:
            raise OSError("down")
        return RSS

    news = NewsService(("https://first.example/rss", "https://second.example/rss"), fetch=fetch)
    assert len(news.headlines(5)) == 3
    assert len(news.headlines(5)) == 3  # cached: no new fetches
    assert calls == ["https://first.example/rss", "https://second.example/rss"]


def test_news_unavailable_is_typed():
    news = NewsService(("https://x.example/rss",), fetch=lambda url: (_ for _ in ()).throw(OSError("offline")))
    with pytest.raises(ActionError) as exc:
        news.headlines()
    assert exc.value.code == "NEWS_UNAVAILABLE"


# ---------------------------------------------------------------- schedule + briefing
@pytest.fixture
def day(services):
    store = services.store
    today = date.today()
    store.add("events", {"title": "Dentist", "date": today.isoformat(), "time": "16:30"})
    store.add("events", {"title": "Team sync", "date": today.isoformat(), "time": "10:00"})
    store.add("events", {"title": "Tomorrow thing", "date": (today + timedelta(days=1)).isoformat(), "time": "09:00"})
    store.add("tasks", {"title": "Submit report", "completed": False, "due": today.isoformat()})
    store.add("tasks", {"title": "Pay rent", "completed": False, "due": (today - timedelta(days=2)).isoformat()})
    store.add("tasks", {"title": "Done already", "completed": True, "due": today.isoformat()})
    return store


def test_time_label():
    assert time_label("16:30") == "4:30 PM" and time_label("09:00") == "9 AM" and time_label(None) == ""


def test_schedule_today_sorts_and_splits(day):
    s = schedule_today(day)
    assert [e["title"] for e in s["events"]] == ["Team sync", "Dentist"]
    assert [t["title"] for t in s["due_today"]] == ["Submit report"]
    assert [t["title"] for t in s["overdue"]] == ["Pay rent"]


def test_briefing_has_schedule_news_and_machine(day, fake_news):
    telemetry = {"cpu_percent": 12.0, "memory": {"percent": 40.0}, "battery": {"percent": 15, "plugged": False}}
    b = build_briefing(day, fake_news, {**telemetry, "online": True}, True, datetime(2026, 11, 2, 9, 5))
    assert b["reply"].startswith("**Good morning.** It's 9:05 AM on Monday, 2 November.")
    assert "10 AM, Team sync" in b["reply"] and "Chipmaker unveils" in b["reply"]
    assert "Battery 15%" in b["reply"]
    speech = b["speech"]
    assert "You have 2 events today: Team sync at 10 AM and Dentist at 4:30 PM." in speech
    assert "1 task is overdue." in speech
    assert "Phone makers agree" in speech and "Browser adds" not in speech  # three headlines are read
    assert "plug in" in speech


def test_briefing_offline_says_so_and_skips_news(day, fake_news):
    b = build_briefing(day, fake_news, None, False, datetime(2026, 11, 2, 20, 0))
    assert b["reply"].startswith("**Good evening.**")
    assert "you're offline" in b["reply"] and fake_news.calls == 0


def test_brief_me_reads_the_whole_briefing(pipeline, day):
    resp = pipeline.command("Jarvis, brief me")
    assert resp.status == "done" and resp.response_type == "conversation"
    assert "The rest is on screen" not in resp.speech  # written for speaking; never cut short
    assert "Team sync" in resp.speech and "Chipmaker unveils" in resp.speech


def test_schedule_and_news_commands(pipeline, day, connectivity):
    assert "Team sync at 10 AM" in pipeline.command("what's scheduled today").speech
    assert pipeline.command("latest tech news").reply.startswith("**Latest tech news**")
    connectivity.override = False
    assert pipeline.command("latest tech news").error_code == "OFFLINE"


def test_system_status_and_processes(pipeline, monkeypatch):
    from jarvis.actions import system

    monkeypatch.setattr(
        system,
        "top_processes",
        lambda limit=5, sample_s=0.0: [{"name": "chrome", "cpu_percent": 31.0, "memory": 2 * 1024**3, "count": 9}],
    )
    summary = pipeline.command("what's my system status")
    assert summary.status == "done" and "CPU at" in summary.reply and "has been on for" in summary.reply
    procs = pipeline.command("which apps are using the most cpu")
    assert "**chrome**" in procs.reply and procs.speech.startswith("chrome is the busiest, at 31 percent CPU")


# ---------------------------------------------------------------- lid-open watcher
class Clock:
    def __init__(self) -> None:
        self.wall = 1_000_000.0
        self.mono = 50.0

    def step(self, seconds: float, asleep: bool = False) -> None:
        self.wall += seconds
        if not asleep:
            self.mono += seconds


def make_watcher(clock, locked):
    fired: list[str] = []
    w = WakeWatcher(fired.append, lock_state=lambda: locked[0], wall=lambda: clock.wall, mono=lambda: clock.mono)
    return w, fired


def test_wake_from_sleep_fires_once_after_settling():
    clock, locked = Clock(), [False]
    w, fired = make_watcher(clock, locked)
    clock.step(2)
    w.tick()
    clock.step(600, asleep=True)  # ten minutes asleep: the monotonic clock stood still
    w.tick()
    assert fired == []  # look at the lock screen once more first
    clock.step(2)
    w.tick()
    clock.step(2)
    w.tick()
    assert fired == ["wake"]


def test_wake_waits_for_unlock():
    clock, locked = Clock(), [False]
    w, fired = make_watcher(clock, locked)
    clock.step(300, asleep=True)
    locked[0] = True  # woke up to the lock screen
    for _ in range(10):
        clock.step(2)
        w.tick()
    assert fired == []
    locked[0] = False
    clock.step(2)
    w.tick()
    assert fired == ["wake"]


def advance(w, clock, seconds: float) -> None:
    """Tick every 2 s like the real watcher."""
    for _ in range(int(seconds // 2)):
        clock.step(2)
        w.tick()


def test_long_lock_then_unlock_fires_short_lock_does_not():
    clock, locked = Clock(), [True]
    w, fired = make_watcher(clock, locked)
    w.tick()
    advance(w, clock, MIN_LOCK_S / 2)
    locked[0] = False
    advance(w, clock, 6)
    assert fired == []
    locked[0] = True
    advance(w, clock, MIN_LOCK_S + 2)
    locked[0] = False
    advance(w, clock, 6)
    assert fired == ["unlock"]


def test_busy_cpu_is_not_mistaken_for_sleep():
    clock, locked = Clock(), [None]
    w, fired = make_watcher(clock, locked)
    for _ in range(5):
        clock.step(5)  # late ticks (a busy CPU), but both clocks advanced together
        w.tick()
    assert fired == []


def test_cooldown_between_briefings():
    clock, locked = Clock(), [None]
    w, fired = make_watcher(clock, locked)
    for _ in range(2):
        clock.step(100, asleep=True)
        w.tick()
        clock.step(3)
        w.tick()
    assert len(fired) == (1 if 103 < COOLDOWN_S else 2)


def test_event_bus_long_poll():
    bus = EventBus()
    assert bus.wait(0, timeout=0.05) == []
    e = bus.publish({"type": "briefing", "reply": "hi"})
    assert bus.wait(0, timeout=1)[0]["seq"] == e["seq"]
    assert bus.wait(-1, timeout=0) == [e]  # a page opened right after waking still gets it


def test_api_events_briefing_news_and_processes(client, services):
    first = client.get("/api/v1/events?after=-1&wait=0", headers=TOKEN).json
    assert first["events"] == [] and first["seq"] == 0
    services.events.publish({"type": "briefing", "reply": "Good morning.", "speech": "Good morning."})
    got = client.get("/api/v1/events?after=0&wait=1", headers=TOKEN).json
    assert got["seq"] == 1 and got["events"][0]["type"] == "briefing"
    assert client.get("/api/v1/briefing", headers=TOKEN).json["reply"].startswith("**Good")
    assert len(client.get("/api/v1/news?count=2", headers=TOKEN).json["items"]) == 2
    assert "processes" in client.get("/api/v1/system?processes=1", headers=TOKEN).json
    assert client.get("/api/v1/events", headers={"Origin": "http://localhost:8080"}).status_code == 401
    pushed = client.post("/api/v1/events/briefing", json={"reason": "wake"}, headers=TOKEN).json
    assert (
        client.get(f"/api/v1/events?after={pushed['seq'] - 1}&wait=0", headers=TOKEN).json["events"][0]["reason"]
        == "wake"
    )
    assert client.post("/api/v1/events/briefing", json={"reason": "x"}, headers=TOKEN).status_code == 400


# ---------------------------------------------------------------- live speech
ANSWERS = [
    "Polymorphism lets one interface have many forms. In Java, a `Shape` can be a `Circle`.\n\n```java\n"
    "Shape s = new Circle();\n```\n\nThis keeps code flexible. You can add shapes without changing callers.",
    'Here\'s a C program:\n\n```c\n#include <stdio.h>\nint main(){printf("Hi. There");}\n```\nIt prints Hi There.',
    "1. First item\n2. Second item",
    "The answer is 3.5 meters. Done!",
]


@pytest.mark.parametrize("text", ANSWERS)
def test_live_speech_says_exactly_the_short_version(text):
    rng = random.Random(7)
    for _ in range(50):
        streamer, said, i = SpeechStreamer(), [], 0
        while i < len(text):
            n = rng.randint(1, 9)
            said += streamer.feed(text[i : i + n])
            i += n
        assert " ".join([*said, streamer.finish()]).strip() == to_speech(text)


def test_live_speech_never_reads_code():
    streamer = SpeechStreamer()
    said = []
    for ch in ANSWERS[1]:
        said += streamer.feed(ch)
    assert not any("include" in s or "printf" in s for s in said)


def test_stream_endpoint_sends_spoken_sentences(client, fake_ai):
    fake_ai.answer_stream = lambda q, h, m=None: iter(
        ["Polymorphism means many forms. ", "It is ", "useful. ", "Done."]
    )
    plan = client.post("/api/v1/plan", json={"text": "what is polymorphism", "session_id": "s"}, headers=TOKEN).json
    resp = client.post("/api/v1/execute/stream", json={"plan_id": plan["plan_id"], "session_id": "s"}, headers=TOKEN)
    events = [json.loads(x[6:]) for x in resp.get_data(as_text=True).splitlines() if x.startswith("data: ")]
    said = [e["text"] for e in events if e["type"] == "say"]
    assert said == ["Polymorphism means many forms.", "It is useful.", "Done."]
    done = events[-1]["response"]
    assert done["spoken_live"] is True and done["speech"] == ""  # nothing left to repeat


# ---------------------------------------------------------------- OCR result shapes
def test_rapid_lines_old_and_new_result_shapes():
    box = [[10, 20], [110, 20], [110, 40], [10, 40]]
    old = ([[box, "Hello", 0.9]], [0.1])
    assert rapid_lines(old)[0].text == "Hello" and rapid_lines(old)[0].width == 100

    class NewStyle:
        boxes = [box]
        txts = ("World",)
        scores = (0.8,)

    assert rapid_lines(NewStyle())[0].text == "World"
    assert rapid_lines((None, None)) == []


def test_ocr_start_failure_is_explained(monkeypatch, tmp_path):
    import builtins

    from PIL import Image

    real_import = builtins.__import__

    def broken(name, *args, **kwargs):
        if name.startswith("rapidocr"):
            raise ImportError("DLL load failed while importing onnxruntime_pybind11_state")
        return real_import(name, *args, **kwargs)

    engine = OcrEngine()
    monkeypatch.setattr(OcrEngine, "_rapid_module", staticmethod(lambda: "rapidocr_onnxruntime"))
    monkeypatch.setattr(OcrEngine, "_tesseract_ready", lambda self: False)
    monkeypatch.setattr(builtins, "__import__", broken)
    img = tmp_path / "x.png"
    Image.new("RGB", (10, 10)).save(img)
    with pytest.raises(ActionError) as exc:
        engine.read(img)
    assert exc.value.code == "OCR_UNAVAILABLE" and "Visual C++" in exc.value.message


def test_history_sent_to_the_model_stays_small():
    from jarvis.core.context import HISTORY_CHARS, SessionContext

    s = SessionContext("s")
    for i in range(6):
        s.add_turn(f"question {i}", "x" * 3000)  # long replies: briefings, news, code
    sent = s.history_list()
    assert sum(len(m["content"]) for m in sent) <= HISTORY_CHARS + 400
    assert sent[-1]["role"] == "assistant" and sent[-2]["content"] == "question 5"  # newest kept, in order


def test_timeout_is_reported_as_slow_not_missing(pipeline, fake_ai):
    from jarvis.ai.provider import AiUnavailable

    def slow(*a, **k):
        raise AiUnavailable("The language model took longer than 90 seconds.")

    fake_ai.answer = slow
    resp = pipeline.command("explain recursion")
    assert "took too long" in resp.reply
