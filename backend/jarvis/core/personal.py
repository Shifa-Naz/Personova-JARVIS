"""Intent rules for memory, notes, tasks, calendar and file create/copy/rename.

Each matcher returns ``(intent_name, steps)`` / a clarification, or None. Date phrases are
extracted with ``jarvis.nlp.dates``; ambiguous ones become a clarifying question.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from jarvis.actions.base import PlanStep
from jarvis.nlp.dates import extract_when


@dataclass
class Match:
    steps: list[PlanStep]
    intent: str = "COMMAND"  # COMMAND | QUESTION
    clarification: str | None = None


def step(action: str, **params) -> PlanStep:
    return PlanStep(action=action, params={k: v for k, v in params.items() if v not in (None, "")})


def _clean(text: str) -> str:
    text = re.sub(r"^(?:the|a|an|my)\s+", "", text.strip())
    return text.strip(" ,.:;\"'")


def _ask(question: str) -> Match:
    return Match(steps=[], clarification=question)


fm = re.fullmatch

# ================================================================= memory
# Questions about the user themselves (answered from saved memories), e.g. "what language do I prefer",
# "what's my name", "do you remember where I live". General questions that merely mention "my" are not.
_PERSONAL_Q = re.compile(
    r"^(?:what|which|who|where|when)\b(?:(?! how ).)*\b(?:do|did|am|was|have) i\b.*"
    r"\b(?:prefer|like|love|live|study|work|use|enjoy|hate|support|want)\b"
    r"|^(?:what|which|who|when|where)(?:'s| is| are| was| were)? my\b"
    r"|^do you (?:remember|know) (?:my|what|where|who|which|if|that|when)\b"
    r"|^who am i\b"
)


# "what's my battery / what are my tasks / what's on my screen" belong to other features.
_OWNED_ELSEWHERE = re.compile(
    r"\bmy (?:tasks?|to-?dos?|todo list|notes?|calendar|schedule|agenda|events?|meetings?|appointments?|battery|"
    r"cpu|ram|memory usage|storage|disk|ip|wifi|internet|screen|clipboard|files?|folders?|downloads|documents|"
    r"music|volume)\b"
)


def memory_intent(s: str) -> Match | None:
    if fm(
        r"what do you (?:remember|know) about me|what have you remembered|what do you remember|"
        r"(?:show|list|read)(?: me)?(?: all)?(?: my| your)? (?:memories|saved memories)",
        s,
    ):
        return Match([step("memory_list")], "QUESTION")
    m = fm(r"(?:forget|delete|remove|erase)(?: the memory| my memory)?(?: that| about)? (.+)", s)
    if m and not fm(r"it|that|this|about it", m.group(1)) and re.match(r"^forget\b", s):
        return Match([step("memory_forget", query=_clean(m.group(1)))])
    m = fm(r"(?:update|change) (?:my )?memory (?:about |that )?(.+?) to (.+)", s)
    if m:
        return Match([step("memory_update", query=_clean(m.group(1)), text=m.group(2).strip())])
    m = fm(
        r"(?:please )?(?:remember|don't forget|do not forget|keep in mind|note that i|make a note that i)(?: that)? (.+)",
        s,
    )
    if m and not re.match(r"^to\b", m.group(1)):
        text = m.group(1)
        if s.startswith(("note that i", "make a note that i")):
            text = "I " + text
        return Match([step("memory_save", text=text)])
    if _PERSONAL_Q.search(s) and not _OWNED_ELSEWHERE.search(s):
        return Match([step("memory_recall", query=s)], "QUESTION")
    return None


# ================================================================= tasks
_PRIORITY = [
    (re.compile(r"\b(?:with |as |at )?(?:high|top|urgent) priority\b|\b(?:urgent|important|asap)\b"), "high"),
    (re.compile(r"\b(?:with |as |at )?low priority\b|\bwhen i have time\b"), "low"),
    (re.compile(r"\b(?:with |as |at )?(?:medium|normal) priority\b"), "medium"),
]


def _task_from_text(text: str) -> Match:
    priority = None
    for pattern, level in _PRIORITY:
        if pattern.search(text):
            priority = level
            text = pattern.sub(" ", text)
            break
    when = extract_when(text)
    if when.ambiguous:
        return _ask(when.ambiguous)
    title = _clean(when.rest)
    if not title:
        return _ask("What should the task be called?")
    return Match([step("task_create", title=title, due=when.date_str(), due_time=when.time_str(), priority=priority)])


def task_intent(s: str) -> Match | None:
    m = fm(r"remind me to (.+)", s) or fm(r"remember to (.+)", s)
    if m:
        return _task_from_text(m.group(1))
    m = fm(r"add (.+) to (?:my |the )?(?:tasks?|task list|to-?do(?: list)?|todo list)", s)
    if m:
        return _task_from_text(m.group(1))
    m = fm(
        r"(?:add|create|make|new|set)(?: a| an)?(?: new)?(?: (.+?))? (?:task|to-?do|todo)(?: item)?"
        r"(?:(?: to| called| named| for|:)? (.+))?",
        s,
    )
    if m and (m.group(1) or m.group(2)):
        return _task_from_text(f"{m.group(1) or ''} {m.group(2) or ''}")

    m = fm(
        r"(?:show|list|read|tell me|what are|what's on|whats on)(?: me)?(?: all)?(?: my| the)?"
        r"(?: (pending|open|completed|done|finished|overdue))? (?:tasks|to-?dos|todos|to-?do list|todo list|task list)"
        r"(?: (?:for |due )?(today))?",
        s,
    ) or fm(r"what (?:do i have to do|tasks do i have|is pending)( today)?", s)
    if m:
        groups = [g for g in m.groups() if g]
        word = groups[0] if groups else ""
        filt = {
            "completed": "completed",
            "done": "completed",
            "finished": "completed",
            "overdue": "overdue",
            "today": "today",
            " today": "today",
        }.get(word.strip() if word else "", "pending")
        if "today" in s:
            filt = "today"
        return Match([step("task_list", filter=filt)], "QUESTION")

    m = fm(r"(?:mark|set) (?:the )?(.+?)(?: task)? (?:as )?(?:not done|incomplete|undone|pending|open)", s) or fm(
        r"(?:reopen|undo|unmark|uncheck) (?:the )?(?:task )?(.+)", s
    )
    if m:
        return Match([step("task_reopen", query=_clean(m.group(1)))])
    m = (
        fm(r"(?:mark|set) (?:the )?(.+?)(?: task)? (?:as )?(?:done|complete|completed|finished)", s)
        or fm(r"(?:complete|finish|tick off|check off) (?:the )?(?:task )?(.+)", s)
        or fm(r"i(?: have| 've|'ve)? (?:finished|completed|done) (?:the )?(?:task )?(.+)", s)
    )
    if m:
        return Match([step("task_complete", query=_clean(m.group(1)))])
    m = fm(r"(?:delete|remove|cancel|drop) (?:the )?(?:task|to-?do) (?:called |named )?(.+)", s) or fm(
        r"(?:delete|remove|cancel|drop) (?:the )?(.+?) (?:task|to-?do)", s
    )
    if m:
        return Match([step("task_delete", query=_clean(m.group(1)))])
    m = fm(r"(?:move|reschedule|postpone|push|change) (?:the )?(?:task )?(.+?) task to (.+)", s) or fm(
        r"(?:move|reschedule|postpone|push) (?:the )?task (.+?) to (.+)", s
    )
    if m:
        target = m.group(2)
        level = re.fullmatch(r"(high|medium|low)(?: priority)?", target)
        if level:
            return Match([step("task_update", query=_clean(m.group(1)), priority=level.group(1))])
        return Match([step("task_update", query=_clean(m.group(1)), due=target)])
    m = fm(r"(?:make|set|change) (?:the )?(?:task )?(.+?)(?: task)? (?:to |as )?(high|medium|low) priority", s)
    if m:
        return Match([step("task_update", query=_clean(m.group(1)), priority=m.group(2))])
    return None


# ================================================================= notes
def note_intent(s: str) -> Match | None:
    m = fm(
        r"(?:take|make|made|create|add|write|new)(?: a| an)?(?: new)? note(?: of| that| saying| called| to say| about|:)? (.+)",
        s,
    ) or fm(r"(?:note down|jot down|write down) (.+)", s)
    if m and not re.match(r"^(?:that )?i\b", m.group(1)):
        text = m.group(1).strip()
        title = text if len(text) <= 60 else text[:57].rsplit(" ", 1)[0] + "…"
        return Match([step("note_create", title=title[:1].upper() + title[1:], content=text if len(text) > 60 else "")])
    if fm(r"(?:show|list|read|what are|open)(?: me)?(?: all)?(?: my| the)? notes", s):
        return Match([step("note_list")], "QUESTION")
    m = fm(r"(?:search|find|look)(?: in| through| for)?(?: my)? notes? (?:for |about |mentioning )?(.+)", s) or fm(
        r"(?:which|what) notes? (?:mention|talk about|are about) (.+)", s
    )
    if m:
        return Match([step("note_search", query=_clean(m.group(1)))], "QUESTION")
    m = fm(r"add (.+) to (?:the |my )?(.+?) note", s)
    if m:
        return Match([step("note_update", query=_clean(m.group(2)), content=m.group(1), mode="append")])
    m = fm(r"(?:update|change|replace|rewrite) (?:the |my )?(.+?) note (?:to|with) (.+)", s)
    if m:
        return Match([step("note_update", query=_clean(m.group(1)), content=m.group(2), mode="replace")])
    m = fm(r"(?:delete|remove|erase) (?:the |my )?note (?:about |called |named |on )?(.+)", s) or fm(
        r"(?:delete|remove|erase) (?:the |my )?(.+?) note", s
    )
    if m:
        return Match([step("note_delete", query=_clean(m.group(1)))])
    m = fm(r"(?:read|open|show)(?: me)? (?:the |my )?note (?:about |called |named |on )?(.+)", s) or fm(
        r"(?:read|show)(?: me)? (?:the |my )?(.+?) note", s
    )
    if m:
        return Match([step("note_read", query=_clean(m.group(1)))], "QUESTION")
    return None


# ================================================================= calendar
_EVENT_WORDS = r"(?:event|meeting|appointment|call|class|exam|interview|session)"


def _event_from_text(text: str) -> Match:
    when = extract_when(text)
    if when.ambiguous:
        return _ask(when.ambiguous)
    title = _clean(re.sub(rf"^(?:an? )?(?:new )?{_EVENT_WORDS}s? (?:for|called|named|about)\s+", "", when.rest))
    if not title:
        return _ask("What should I call the event?")
    if when.date is None:
        return _ask(f"When is “{title}”? Tell me the day.")
    return Match([step("event_create", title=title, date=when.date_str(), time=when.time_str())])


def event_intent(s: str) -> Match | None:
    m = fm(r"(?:add|put|schedule|create|set up)(?: an?)? (.+?) (?:to|on|in) (?:my |the )?calendar(?: (.+))?", s)
    if m:
        return _event_from_text(f"{m.group(1)} {m.group(2) or ''}")
    m = fm(r"(?:schedule|book|set up|arrange|plan)(?: an?| my)? (.+)", s) or fm(
        rf"(?:add|create)(?: an?)? (?:new )?((?:{_EVENT_WORDS}) .+)", s
    )
    if m:
        return _event_from_text(m.group(1))

    m = (
        fm(
            r"what(?:'s| is| do i have)(?: on| in)?(?: my| the)?(?: calendar| schedule| agenda)?(?: for)? "
            r"(today|tomorrow|this week|next week)",
            s,
        )
        or fm(
            r"(?:show|list|read|what's on|whats on|what is on)(?: me)?(?: my| the)? (?:calendar|events|schedule|agenda)"
            r"(?: for)?(?: (today|tomorrow|this week))?",
            s,
        )
        or fm(
            r"(?:do i have|are there) (?:any )?(?:events|meetings|appointments|plans)(?: for| on)? "
            r"(today|tomorrow|this week)",
            s,
        )
    )
    if m:
        word = next((g for g in m.groups() if g), None)
        rng = {"today": "today", "tomorrow": "tomorrow", "this week": "week", "next week": "week"}.get(
            word or "", "upcoming"
        )
        return Match([step("event_list", range=rng)], "QUESTION")
    m = fm(r"what(?:'s| is| do i have) (?:on|planned for) (.+)", s)
    if m:
        when = extract_when(m.group(1))
        if when.date and not when.rest:
            return Match([step("event_list", range="date", date=when.date_str())], "QUESTION")

    m = fm(rf"(?:move|reschedule|postpone|shift|push) (?:the |my )?(.+?) {_EVENT_WORDS} to (.+)", s) or fm(
        rf"(?:move|reschedule|postpone|shift) (?:the |my )?{_EVENT_WORDS} (.+?) to (.+)", s
    )
    if m:
        return Match([step("event_update", query=_clean(m.group(1)), date=m.group(2))])
    m = (
        fm(rf"(?:delete|remove|cancel) (?:the |my )?{_EVENT_WORDS} (?:called |named |for )?(.+)", s)
        or fm(rf"(?:delete|remove|cancel) (?:the |my )?(.+?) {_EVENT_WORDS}", s)
        or fm(r"(?:delete|remove) (.+?) from (?:my |the )?calendar", s)
    )
    if m:
        return Match([step("event_delete", query=_clean(m.group(1)))])
    return None


# ================================================================= briefing, today's schedule, news, machine status
# Full-phrase matches only, so "what's the news about the election" still goes to the web answer.
_TODAY = r"(?: for)?(?: today| this morning| right now)?"
_BRIEFING = re.compile(
    r"brief me|(?:give me |read me |start )?(?:my |the |a )?(?:daily |morning )?briefing|good morning|"
    r"(?:what's|what is|whats|how's|how is) my day(?: looking| look like| like)?|how does my day look"
)
_SCHEDULE = re.compile(
    rf"(?:what's|what is|whats|show me|tell me|read me|give me)? ?(?:my |today's |the )?(?:schedule|agenda|plan|plans)"
    rf"{_TODAY}|what's scheduled{_TODAY}|what is scheduled{_TODAY}|whats scheduled{_TODAY}|"
    rf"what (?:tasks|events|meetings) (?:are|do i have) (?:scheduled|planned|due|on){_TODAY}|"
    rf"what (?:do i have|have i got|is there|is on|'s on)(?: scheduled| planned| going on)?(?: for)? today|"
    r"(?:what's|what is|whats) on (?:my |the )?(?:schedule|agenda|plate) today|anything (?:scheduled |planned )?today"
)
_NEWS = re.compile(
    r"(?:what's|what is|whats|tell me|read me|give me|show me|get me|any)? ?(?:the )?"
    r"(?:latest |today's |top |recent |new )?(?:tech |technology )?(?:news|headlines)(?: today| in tech| for today)?|"
    r"(?:what's|what is|whats) (?:new|happening|the latest) in (?:tech|technology)(?: today)?"
)
_SYSTEM_STATUS = re.compile(
    r"(?:what's|what is|whats|give me|show me|tell me|check)? ?(?:my |the )?(?:system|computer|laptop|pc|machine) "
    r"(?:status|info|information|stats|health|details|report)|how(?:'s| is) my (?:system|computer|laptop|pc|machine)"
    r"(?: doing| running)?|system check"
)
_PROCESSES = re.compile(
    r"(?:what's|what is|whats|what are the) (?:apps |programs )?running(?: on (?:my|the|this) (?:computer|laptop|pc|system))?|"
    r"(?:which|what) (?:apps|programs|processes|applications) are (?:using|eating|taking|hogging)(?: up)?(?: the most| so much| all)?"
    r"(?: of)?(?: my| the)? ?(?:cpu|memory|ram|resources|battery)?|(?:top|running|busiest|heaviest) (?:apps|processes|programs)|"
    r"what's (?:using|eating|slowing down) (?:my|the) (?:cpu|memory|ram|computer|laptop)"
)
_UPTIME = re.compile(
    r"uptime|how long (?:has|have) (?:my |the |this )?(?:computer|laptop|pc|system|i) been (?:on|running|up)"
)


def briefing_intent(s: str) -> Match | None:
    if fm(_BRIEFING, s):
        return Match([step("daily_briefing")], intent="QUESTION")
    if fm(_NEWS, s):
        return Match([step("news_headlines")], intent="QUESTION")
    if fm(_SCHEDULE, s):
        return Match([step("schedule_today")], intent="QUESTION")
    if fm(_SYSTEM_STATUS, s):
        return Match([step("system_information", topic="summary")], intent="QUESTION")
    if fm(_PROCESSES, s):
        return Match([step("system_information", topic="processes")], intent="QUESTION")
    if fm(_UPTIME, s):
        return Match([step("system_information", topic="uptime")], intent="QUESTION")
    return None


# ================================================================= files: create / copy / rename
_TEXT_EXT = r"txt|md|csv|json|log|html|css|js|ts|py|c|h|cpp|java|xml|yaml|yml|ini"
_FILE_CONTENT = re.compile(r" (?:with the text|with text|with content|containing|saying|that says|with) (.+)$")
_FILE_HEAD = re.compile(
    rf"(?:create|make|add|write)(?: me)?(?: a| an)?(?: new)?(?: empty)?"
    rf"(?:(?: text| txt)? file(?: called| named)? (?P<name>[^ ].*?)|(?: the)? (?P<named>\S+\.(?:{_TEXT_EXT}))(?: file)?)"
    r"(?: (?:in|on|inside|under) (?:my |the )?(?P<folder>.+?)(?: folder)?)?"
)


def create_file_intent(s: str) -> Match | None:
    s = re.sub(rf"\s+dot\s+({_TEXT_EXT})\b", r".\1", s)  # speech: "greetings dot txt"
    content = ""
    cm = _FILE_CONTENT.search(s)
    head = s[: cm.start()] if cm else s
    m = fm(_FILE_HEAD, head)
    if not m:
        return None
    if cm:
        content = re.sub(r" in it$", "", cm.group(1)).strip(" \"'")
    name = (m.group("name") or m.group("named") or "").strip(" \"'")
    name = re.sub(r" file$", "", name)
    if len(name) < 1:
        return Match([], clarification="What should I call the file?")
    return Match([step("create_file", name=name, folder=(m.group("folder") or "").strip() or None, content=content)])


def file_ops_intent(s: str) -> Match | None:
    m = fm(
        r"(?:create|make|add)(?: a| an)?(?: new)? (?:folder|directory)(?: called| named)? (.+?)"
        r"(?: (?:in|on|inside|under) (?:my |the )?(.+?))?(?: folder)?",
        s,
    )
    if m:
        return Match([step("create_folder", name=m.group(1).strip(" \"'"), parent=(m.group(2) or "").strip() or None)])
    m = fm(r"copy (?:the |my )?(?:file )?(.+?) (?:to|into) (?:my |the )?(.+?)(?: folder)?", s)
    if m and not re.search(r"\bclipboard\b", m.group(2)):
        return Match([step("copy_file", query=_clean(m.group(1)), destination=m.group(2).strip())])
    m = fm(r"rename (?:the |my )?(?:file )?(.+?) (?:to|as) (.+)", s)
    if m:
        return Match([step("rename_file", query=_clean(m.group(1)), new_name=m.group(2).strip(" \"'"))])
    return None


# Storing text (a task title, a note, a memory) never executes it, so these run before the safety
# filter: "remind me to pay rent" is a reminder, not a payment. File operations run after it.
# create_file only writes text, like a note, and its phrasing is strict ("file" or a text extension).
# briefing_intent only reads (schedule, news, machine status) and matches whole phrases.
STORAGE_MATCHERS = (briefing_intent, create_file_intent, task_intent, event_intent, note_intent, memory_intent)
MATCHERS = (*STORAGE_MATCHERS, file_ops_intent)
