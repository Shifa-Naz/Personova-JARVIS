"""Today's schedule and the daily briefing (schedule + tech news + a machine check).

Used by the `daily_briefing` / `schedule_today` actions and by the lid-open briefing, so the voice, the
dashboard and the wake-up greeting always say the same thing.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime

from jarvis.actions.base import ActionError

log = logging.getLogger(__name__)

NEWS_SPOKEN = 3
NEWS_SHOWN = 5


def time_label(hhmm: str | None) -> str:
    """'16:30' -> '4:30 PM', '09:00' -> '9 AM'."""
    if not hhmm:
        return ""
    try:
        t = datetime.strptime(hhmm[:5], "%H:%M")
    except ValueError:
        return hhmm
    label = t.strftime("%I:%M %p").lstrip("0")
    return label.replace(":00 ", " ")


def greeting(now: datetime) -> str:
    if now.hour < 5:
        return "You're up late"
    if now.hour < 12:
        return "Good morning"
    if now.hour < 17:
        return "Good afternoon"
    return "Good evening"


def _md_escape(text: str) -> str:
    return re.sub(r"([\\`*_\[\]<>#|])", r"\\\1", text)


def _join(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def schedule_today(store, today: date | None = None) -> dict:
    today_iso = (today or date.today()).isoformat()
    events = sorted(
        (e for e in store.load("events") if e.get("date") == today_iso), key=lambda e: e.get("time") or "99:99"
    )
    open_tasks = [t for t in store.load("tasks") if not t.get("completed")]
    due = sorted((t for t in open_tasks if t.get("due") == today_iso), key=lambda t: t.get("due_time") or "99:99")
    overdue = [t for t in open_tasks if t.get("due") and t["due"] < today_iso]
    return {"date": today_iso, "events": events, "due_today": due, "overdue": overdue}


def schedule_text(s: dict) -> tuple[str, str]:
    """(Markdown for the page, sentence for the voice)."""
    md: list[str] = []
    spoken: list[str] = []
    events, due, overdue = s["events"], s["due_today"], s["overdue"]
    for e in events:
        at = time_label(e.get("time"))
        md.append(f"- {at + ', ' if at else ''}{_md_escape(e['title'])}")
    if events:
        names = [f"{e['title']}{' at ' + time_label(e.get('time')) if e.get('time') else ''}" for e in events[:4]]
        more = f", plus {len(events) - 4} more" if len(events) > 4 else ""
        noun = "event" if len(events) == 1 else "events"
        spoken.append(f"You have {len(events)} {noun} today: {_join(names)}{more}.")
    else:
        spoken.append("Your calendar is clear today.")
    if due:
        md.append(f"- Due today: {', '.join(_md_escape(t['title']) for t in due)}")
        noun = "task is" if len(due) == 1 else "tasks are"
        spoken.append(f"{len(due)} {noun} due today: {_join([t['title'] for t in due[:4]])}.")
    if overdue:
        md.append(f"- Overdue: {', '.join(_md_escape(t['title']) for t in overdue)}")
        spoken.append(f"{len(overdue)} {'task is' if len(overdue) == 1 else 'tasks are'} overdue.")
    if not md:
        md.append("- Nothing scheduled and no tasks due.")
    return "\n".join(md), " ".join(spoken)


def news_text(headlines) -> tuple[str, str]:
    md = "\n".join(
        f"{i}. [{_md_escape(h.title)}]({h.url}) ({_md_escape(h.source)})" for i, h in enumerate(headlines, 1)
    )
    spoken = " ".join(f"{h.title.rstrip('.')}." for h in headlines[:NEWS_SPOKEN])
    return md, spoken


def machine_text(t: dict) -> tuple[str, str]:
    parts = [f"CPU {t['cpu_percent']:.0f}%", f"memory {t['memory']['percent']:.0f}%"]
    spoken = ""
    b = t.get("battery")
    if b:
        parts.insert(0, f"battery {b['percent']}%{' (charging)' if b['plugged'] else ''}")
        if b["percent"] < 25 and not b["plugged"]:
            spoken = f"Your battery is at {b['percent']} percent, so you may want to plug in."
    parts.append("online" if t.get("online") else "offline")
    return ", ".join(parts).capitalize() + ".", spoken


def build_briefing(store, news, telemetry: dict | None, online: bool, now: datetime | None = None) -> dict:
    """Returns {"reply": Markdown, "speech": short spoken text, "data": {...}}. Never raises for missing news."""
    now = now or datetime.now()
    sched = schedule_today(store, now.date())
    sched_md, sched_spoken = schedule_text(sched)
    hello = greeting(now)
    when = f"{time_label(now.strftime('%H:%M'))} on {now.strftime('%A')}, {now.day} {now.strftime('%B')}"
    reply = [f"**{hello}.** It's {when}.", "", "**Today**", sched_md]
    speech = [f"{hello}. It's {time_label(now.strftime('%H:%M'))}.", sched_spoken]

    headlines = []
    if news is not None and online:
        try:
            headlines = news.headlines(NEWS_SHOWN)
        except ActionError as exc:
            log.info("Briefing without news: %s", exc.message)
    if headlines:
        news_md, news_spoken = news_text(headlines)
        reply += ["", "**Tech news**", news_md]
        speech.append(f"In tech news: {news_spoken}")
    elif news is not None:
        reply += ["", "**Tech news**", "I couldn't get the news right now" + ("." if online else ", you're offline.")]

    if telemetry:
        machine_md, machine_spoken = machine_text(telemetry)
        reply += ["", f"**This computer:** {machine_md}"]
        if machine_spoken:
            speech.append(machine_spoken)
    return {
        "reply": "\n".join(reply),
        "speech": " ".join(s for s in speech if s),
        "data": {"schedule": sched, "news": [h.as_dict() for h in headlines]},
    }
