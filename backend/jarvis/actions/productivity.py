"""Notes, tasks and calendar events — the same data the Notes/Tasks/Calendar pages show.

Targets are found by name ("complete the groceries task"). When two items match
equally well JARVIS asks which one; it never guesses. Deleting asks for confirmation.
Dates and times go through ``jarvis.nlp.dates`` and ambiguous ones trigger a question.
"""

from __future__ import annotations

import re
import time
from datetime import date, datetime, timedelta

from pydantic import Field

from jarvis.actions.base import ActionError, ActionResult, ActionSpec, Params, PermissionLevel, Prepared
from jarvis.nlp.dates import describe, extract_when

_WORD = re.compile(r"[a-z0-9]+")
_FILLER = {"the", "a", "an", "my", "task", "note", "event", "meeting", "to", "for", "about", "called", "named"}


def _store(ctx):
    if ctx.store is None:
        raise ActionError("STORAGE_UNAVAILABLE", "Storage isn't available.")
    return ctx.store


def _score(query: str, *fields: str) -> float:
    q = query.lower().strip()
    hay = " ".join(f for f in fields if f).lower()
    if not q:
        return 0.0
    title = (fields[0] or "").lower()
    if title == q:
        return 100.0
    if title.startswith(q) or q in title:
        return 80.0
    terms = {w for w in _WORD.findall(q) if w not in _FILLER}
    if not terms:
        return 0.0
    hits = sum(1 for w in terms if w in _WORD.findall(hay))
    return 60.0 * hits / len(terms) if hits else 0.0


def find_one(items: list[dict], query: str, kind: str, extra_fields: tuple[str, ...] = ()) -> dict:
    scored = sorted(
        ((_score(query, it.get("title", ""), *(str(it.get(f, "")) for f in extra_fields)), it) for it in items),
        key=lambda s: s[0],
        reverse=True,
    )
    scored = [s for s in scored if s[0] > 0]
    if not scored:
        raise ActionError(f"{kind.upper()}_NOT_FOUND", f"I couldn't find a {kind} matching “{query}”.")
    if len(scored) > 1 and scored[0][0] == scored[1][0] and scored[0][0] < 100:
        names = ", ".join(f"“{s[1]['title']}”" for s in scored[:3])
        raise ActionError("AMBIGUOUS", f"Which {kind} do you mean: {names}?")
    return scored[0][1]


def _parse_date(raw: str | None, field: str) -> tuple[str | None, str | None]:
    """Accepts ISO dates or phrases like 'tomorrow at 5 pm'. Returns (date, time)."""
    if not raw:
        return None, None
    raw = raw.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        try:
            return date.fromisoformat(raw).isoformat(), None
        except ValueError as exc:
            raise ActionError("AMBIGUOUS", "That date doesn't exist. Which date did you mean?") from exc
    w = extract_when(raw)
    if w.ambiguous:
        raise ActionError("AMBIGUOUS", w.ambiguous)
    if not w.found:
        raise ActionError("AMBIGUOUS", f"I couldn't understand the {field} “{raw}”. Could you say it differently?")
    return w.date_str(), w.time_str()


def _parse_time(raw: str | None) -> str | None:
    if not raw:
        return None
    if re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", raw.strip()):
        return raw.strip()
    w = extract_when(raw)
    if w.ambiguous:
        raise ActionError("AMBIGUOUS", w.ambiguous)
    if w.time is None:
        raise ActionError("AMBIGUOUS", f"I couldn't understand the time “{raw}”.")
    return w.time_str()


def _changed(kind: str):
    """Marks results so the UI refreshes the matching page."""
    return {"changed": kind}


# ============================================================== notes
class NoteCreateParams(Params):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(default="", max_length=5000)


def note_create(params: NoteCreateParams, ctx, prepared) -> ActionResult:
    item = _store(ctx).add(
        "notes", {"title": params.title, "content": params.content, "date": datetime.now().strftime("%d %b %Y, %H:%M")}
    )
    return ActionResult(True, f"Noted: {params.title}.", data={"note": item, **_changed("notes")})


class _NoParams(Params):
    pass


def note_list(params: Params, ctx, prepared) -> ActionResult:
    notes = _store(ctx).load("notes")
    if not notes:
        return ActionResult(True, "You don't have any notes yet.", data={"notes": []})
    titles = ", ".join(n["title"] for n in notes[:5])
    more = f", and {len(notes) - 5} more" if len(notes) > 5 else ""
    return ActionResult(
        True, f"You have {len(notes)} {'note' if len(notes) == 1 else 'notes'}: {titles}{more}.", data={"notes": notes}
    )


class QueryParams(Params):
    query: str = Field(min_length=2, max_length=200)


def note_search(params: QueryParams, ctx, prepared) -> ActionResult:
    notes = _store(ctx).load("notes")
    hits = [n for n in notes if _score(params.query, n["title"], n.get("content", "")) > 0]
    if not hits:
        return ActionResult.fail("NOTE_NOT_FOUND", f"No notes mention “{params.query}”.")
    titles = ", ".join(n["title"] for n in hits[:5])
    return ActionResult(True, f"I found {len(hits)}: {titles}.", data={"notes": hits})


def note_read(params: QueryParams, ctx, prepared) -> ActionResult:
    note = find_one(_store(ctx).load("notes"), params.query, "note", ("content",))
    body = note.get("content") or "It has no text."
    return ActionResult(True, f"{note['title']}. {body}", data={"note": note})


class NoteUpdateParams(Params):
    query: str = Field(min_length=2, max_length=200)
    content: str = Field(min_length=1, max_length=5000)
    mode: str = Field(default="append", pattern="^(append|replace)$")


def note_update(params: NoteUpdateParams, ctx, prepared) -> ActionResult:
    store = _store(ctx)
    note = find_one(store.load("notes"), params.query, "note", ("content",))
    old = note.get("content", "")
    new = f"{old}\n{params.content}".strip() if params.mode == "append" else params.content
    # The previous text is kept so a replace can be undone from the Notes page.
    item = store.update("notes", note["id"], {"content": new, "previous": old})
    verb = "Added that to" if params.mode == "append" else "Updated"
    return ActionResult(True, f"{verb} “{note['title']}”.", data={"note": item, **_changed("notes")})


def prepare_note_delete(params: QueryParams, ctx) -> Prepared:
    note = find_one(_store(ctx).load("notes"), params.query, "note", ("content",))
    return Prepared(summary=f"This will delete the note “{note['title']}”.", data={"id": note["id"]})


def note_delete(params: QueryParams, ctx, prepared: Prepared | None) -> ActionResult:
    if prepared is None or not _store(ctx).delete("notes", prepared.data["id"]):
        return ActionResult.fail("NOTE_NOT_FOUND", "That note no longer exists.")
    return ActionResult(True, "Note deleted.", data=_changed("notes"))


# ============================================================== tasks
class TaskCreateParams(Params):
    title: str = Field(min_length=1, max_length=200)
    due: str | None = Field(default=None, max_length=80, description="Date (YYYY-MM-DD) or phrase like 'tomorrow'")
    due_time: str | None = Field(default=None, max_length=40)
    priority: str = Field(default="medium", pattern="^(high|medium|low)$")


def task_create(params: TaskCreateParams, ctx, prepared) -> ActionResult:
    due, t = _parse_date(params.due, "due date")
    t = _parse_time(params.due_time) or t
    item = _store(ctx).add(
        "tasks", {"title": params.title, "completed": False, "priority": params.priority, "due": due, "due_time": t}
    )
    when = f" for {describe(due, t)}" if due or t else ""
    pri = " as high priority" if params.priority == "high" else ""
    return ActionResult(True, f"Added “{params.title}”{when}{pri}.", data={"task": item, **_changed("tasks")})


class TaskListParams(Params):
    filter: str = Field(default="pending", pattern="^(pending|today|overdue|completed|all)$")


def task_list(params: TaskListParams, ctx, prepared) -> ActionResult:
    tasks = _store(ctx).load("tasks")
    today = date.today().isoformat()
    selected = {
        "pending": [t for t in tasks if not t.get("completed")],
        "today": [t for t in tasks if not t.get("completed") and t.get("due") == today],
        "overdue": [t for t in tasks if not t.get("completed") and t.get("due") and t["due"] < today],
        "completed": [t for t in tasks if t.get("completed")],
        "all": tasks,
    }[params.filter]
    label = {"pending": "pending", "today": "due today", "overdue": "overdue", "completed": "completed", "all": ""}[
        params.filter
    ]
    if not selected:
        return ActionResult(True, f"You have no {label + ' ' if label else ''}tasks.", data={"tasks": []})
    selected.sort(key=lambda t: (t.get("due") or "9999", {"high": 0, "medium": 1, "low": 2}.get(t.get("priority"), 1)))
    parts = [t["title"] + (f" ({describe(t['due'], None)})" if t.get("due") else "") for t in selected[:6]]
    more = f", and {len(selected) - 6} more" if len(selected) > 6 else ""
    noun = "task" if len(selected) == 1 else "tasks"
    return ActionResult(
        True,
        f"You have {len(selected)} {label + ' ' if label else ''}{noun}: {', '.join(parts)}{more}.",
        data={"tasks": selected},
    )


def _set_done(ctx, query: str, done: bool) -> ActionResult:
    store = _store(ctx)
    candidates = [t for t in store.load("tasks") if bool(t.get("completed")) != done] or store.load("tasks")
    task = find_one(candidates, query, "task")
    if bool(task.get("completed")) == done:
        state = "already done" if done else "already open"
        return ActionResult(True, f"“{task['title']}” is {state}.", data={"task": task})
    item = store.update("tasks", task["id"], {"completed": done, "completed_at": time.time() if done else None})
    msg = f"Marked “{task['title']}” as done." if done else f"Reopened “{task['title']}”."
    return ActionResult(True, msg, data={"task": item, **_changed("tasks")})


def task_complete(params: QueryParams, ctx, prepared) -> ActionResult:
    return _set_done(ctx, params.query, True)


def task_reopen(params: QueryParams, ctx, prepared) -> ActionResult:
    return _set_done(ctx, params.query, False)


class TaskUpdateParams(Params):
    query: str = Field(min_length=2, max_length=200)
    title: str | None = Field(default=None, max_length=200)
    due: str | None = Field(default=None, max_length=80)
    priority: str | None = Field(default=None, pattern="^(high|medium|low)$")


def task_update(params: TaskUpdateParams, ctx, prepared) -> ActionResult:
    store = _store(ctx)
    task = find_one(store.load("tasks"), params.query, "task")
    patch: dict = {}
    if params.title:
        patch["title"] = params.title
    if params.priority:
        patch["priority"] = params.priority
    if params.due:
        patch["due"], t = _parse_date(params.due, "due date")
        if t:
            patch["due_time"] = t
    if not patch:
        raise ActionError("AMBIGUOUS", "What should I change about that task?")
    item = store.update("tasks", task["id"], patch)
    return ActionResult(True, f"Updated “{item['title']}”.", data={"task": item, **_changed("tasks")})


def prepare_task_delete(params: QueryParams, ctx) -> Prepared:
    task = find_one(_store(ctx).load("tasks"), params.query, "task")
    return Prepared(summary=f"This will delete the task “{task['title']}”.", data={"id": task["id"]})


def task_delete(params: QueryParams, ctx, prepared: Prepared | None) -> ActionResult:
    if prepared is None or not _store(ctx).delete("tasks", prepared.data["id"]):
        return ActionResult.fail("TASK_NOT_FOUND", "That task no longer exists.")
    return ActionResult(True, "Task deleted.", data=_changed("tasks"))


# ============================================================== calendar
class EventCreateParams(Params):
    title: str = Field(min_length=1, max_length=200)
    date: str | None = Field(default=None, max_length=80, description="Date (YYYY-MM-DD) or phrase like 'next friday'")
    time: str | None = Field(default=None, max_length=40, description="HH:MM (24h) or phrase like '5 pm'")


def event_create(params: EventCreateParams, ctx, prepared) -> ActionResult:
    if not params.date:
        raise ActionError("AMBIGUOUS", f"When is “{params.title}”? Tell me the day.")
    d, t = _parse_date(params.date, "date")
    t = _parse_time(params.time) or t
    if d is None:
        raise ActionError("AMBIGUOUS", f"Which day is “{params.title}”?")
    item = _store(ctx).add("events", {"title": params.title, "date": d, "time": t or ""})
    return ActionResult(
        True, f"Scheduled “{params.title}” for {describe(d, t)}.", data={"event": item, **_changed("events")}
    )


class EventListParams(Params):
    range: str = Field(default="upcoming", pattern="^(today|tomorrow|week|upcoming|date)$")
    date: str | None = Field(default=None, max_length=80)


def event_list(params: EventListParams, ctx, prepared) -> ActionResult:
    events = _store(ctx).load("events")
    today = date.today()
    if params.range == "date":
        d, _ = _parse_date(params.date, "date")
        lo = hi = d
    else:
        span = {"today": 0, "tomorrow": 1, "week": 6, "upcoming": 365}[params.range]
        start = today + timedelta(days=1) if params.range == "tomorrow" else today
        lo, hi = start.isoformat(), (today + timedelta(days=span)).isoformat()
    selected = sorted(
        (e for e in events if lo <= e.get("date", "") <= hi), key=lambda e: (e["date"], e.get("time") or "99")
    )
    when = {
        "today": "today",
        "tomorrow": "tomorrow",
        "week": "this week",
        "upcoming": "coming up",
        "date": describe(lo, None) if lo else "",
    }[params.range]
    if not selected:
        return ActionResult(True, f"Nothing on your calendar {when}.", data={"events": []})
    parts = [f"{e['title']} {describe(e['date'], e.get('time') or None)}" for e in selected[:6]]
    more = f", and {len(selected) - 6} more" if len(selected) > 6 else ""
    return ActionResult(True, f"{when.capitalize()}: {', '.join(parts)}{more}.", data={"events": selected})


class EventUpdateParams(Params):
    query: str = Field(min_length=2, max_length=200)
    date: str | None = Field(default=None, max_length=80)
    time: str | None = Field(default=None, max_length=40)
    title: str | None = Field(default=None, max_length=200)


def event_update(params: EventUpdateParams, ctx, prepared) -> ActionResult:
    store = _store(ctx)
    event = find_one(store.load("events"), params.query, "event")
    patch: dict = {}
    if params.date:
        d, t = _parse_date(params.date, "date")
        if d:
            patch["date"] = d
        if t:
            patch["time"] = t
    if params.time:
        patch["time"] = _parse_time(params.time)
    if params.title:
        patch["title"] = params.title
    if not patch:
        raise ActionError("AMBIGUOUS", "What should I change about that event?")
    item = store.update("events", event["id"], patch)
    return ActionResult(
        True,
        f"Moved “{item['title']}” to {describe(item['date'], item.get('time') or None)}.",
        data={"event": item, **_changed("events")},
    )


def prepare_event_delete(params: QueryParams, ctx) -> Prepared:
    event = find_one(_store(ctx).load("events"), params.query, "event")
    return Prepared(
        summary=f"This will delete “{event['title']}” on {describe(event['date'], event.get('time') or None)}.",
        data={"id": event["id"]},
    )


def event_delete(params: QueryParams, ctx, prepared: Prepared | None) -> ActionResult:
    if prepared is None or not _store(ctx).delete("events", prepared.data["id"]):
        return ActionResult.fail("EVENT_NOT_FOUND", "That event no longer exists.")
    return ActionResult(True, "Event deleted.", data=_changed("events"))


RO, SAFE, DESTRUCTIVE = PermissionLevel.READ_ONLY, PermissionLevel.SAFE, PermissionLevel.DESTRUCTIVE
SPECS = [
    ActionSpec(
        "note_create", "Create a note.", NoteCreateParams, SAFE, note_create, examples=("take a note buy milk",)
    ),
    ActionSpec("note_list", "List the user's notes.", _NoParams, RO, note_list),
    ActionSpec("note_search", "Search notes by words.", QueryParams, RO, note_search),
    ActionSpec("note_read", "Read one note aloud.", QueryParams, RO, note_read),
    ActionSpec("note_update", "Add to (append) or replace a note's text.", NoteUpdateParams, SAFE, note_update),
    ActionSpec("note_delete", "Delete a note.", QueryParams, DESTRUCTIVE, note_delete, prepare=prepare_note_delete),
    ActionSpec(
        "task_create",
        "Create a task with optional due date and priority.",
        TaskCreateParams,
        SAFE,
        task_create,
        examples=("add a task to call the bank tomorrow",),
    ),
    ActionSpec("task_list", "List tasks: pending, today, overdue, completed or all.", TaskListParams, RO, task_list),
    ActionSpec("task_complete", "Mark a task done.", QueryParams, SAFE, task_complete),
    ActionSpec("task_reopen", "Mark a done task as not done.", QueryParams, SAFE, task_reopen),
    ActionSpec("task_update", "Change a task's title, due date or priority.", TaskUpdateParams, SAFE, task_update),
    ActionSpec("task_delete", "Delete a task.", QueryParams, DESTRUCTIVE, task_delete, prepare=prepare_task_delete),
    ActionSpec(
        "event_create",
        "Add a calendar event (date required, time optional).",
        EventCreateParams,
        SAFE,
        event_create,
        examples=("schedule team meeting next friday at 4 pm",),
    ),
    ActionSpec(
        "event_list",
        "List calendar events: today, tomorrow, week, upcoming, or a date.",
        EventListParams,
        RO,
        event_list,
    ),
    ActionSpec("event_update", "Move or rename a calendar event.", EventUpdateParams, SAFE, event_update),
    ActionSpec(
        "event_delete", "Delete a calendar event.", QueryParams, DESTRUCTIVE, event_delete, prepare=prepare_event_delete
    ),
]
