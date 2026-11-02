"""Daily briefing, today's schedule and tech headlines (see jarvis/briefing.py)."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from jarvis import briefing
from jarvis.actions.base import ActionError, ActionResult, ActionSpec, Params, PermissionLevel
from jarvis.actions.system import telemetry


class _NoParams(Params):
    pass


class NewsParams(Params):
    count: int = Field(default=5, ge=1, le=10)


def _store(ctx):
    if ctx.store is None:
        raise ActionError("STORAGE_UNAVAILABLE", "Storage isn't available.")
    return ctx.store


def daily_briefing(params: _NoParams, ctx, prepared) -> ActionResult:
    b = briefing.build_briefing(_store(ctx), ctx.news, telemetry(ctx), ctx.connectivity.online(), datetime.now())
    return ActionResult(True, b["reply"], data={"speech": b["speech"], "speech_exact": True, "briefing": b["data"]})


def schedule_today(params: _NoParams, ctx, prepared) -> ActionResult:
    sched = briefing.schedule_today(_store(ctx))
    md, spoken = briefing.schedule_text(sched)
    return ActionResult(True, f"**Today**\n{md}", data={"speech": spoken, "speech_exact": True, "schedule": sched})


def news_headlines(params: NewsParams, ctx, prepared) -> ActionResult:
    if ctx.news is None:
        raise ActionError("NEWS_UNAVAILABLE", "News isn't set up.")
    items = ctx.news.headlines(params.count)
    md, spoken = briefing.news_text(items)
    return ActionResult(
        True,
        f"**Latest tech news**\n{md}",
        data={
            "speech": f"Here's the latest in tech. {spoken}",
            "speech_exact": True,
            "news": [h.as_dict() for h in items],
        },
    )


SPECS = [
    ActionSpec(
        "daily_briefing",
        "Give the daily briefing: greeting, today's events and tasks, top tech headlines, battery and system state.",
        _NoParams,
        PermissionLevel.READ_ONLY,
        daily_briefing,
        timeout_s=30,
        examples=("brief me", "good morning, what's my day like"),
    ),
    ActionSpec(
        "schedule_today",
        "Say today's calendar events plus tasks due today and overdue tasks.",
        _NoParams,
        PermissionLevel.READ_ONLY,
        schedule_today,
        examples=("what's my schedule today", "what's scheduled today"),
    ),
    ActionSpec(
        "news_headlines",
        "Read the latest technology news headlines from public news feeds.",
        NewsParams,
        PermissionLevel.READ_ONLY,
        news_headlines,
        online=True,
        timeout_s=30,
        examples=("latest tech news", "what's new in tech"),
    ),
]
