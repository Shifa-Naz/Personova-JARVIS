"""Deterministic intent matcher: utterance -> intent + validated-shape PlanSteps.

Replaces the old parser/step_splitter/planner trio. Rules:
- match on whole words / anchored regexes, never `str.replace` on substrings;
- never "correct" user arguments (file names, queries, titles);
- compound commands split only on conjunctions followed by a command verb;
- anything not recognised is UNKNOWN and goes to the LLM planner (if available).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

from jarvis.actions.base import PlanStep
from jarvis.actions.browser import KNOWN_SITES
from jarvis.core import personal
from jarvis.platform.apps import AppRegistry


class Intent(StrEnum):
    EMPTY = "EMPTY"
    COMMAND = "COMMAND"
    COMPOUND = "COMPOUND"
    QUESTION = "QUESTION"
    REALTIME_QUERY = "REALTIME_QUERY"
    SMALL_TALK = "SMALL_TALK"
    AMBIGUOUS = "AMBIGUOUS"
    CONFIRM_YES = "CONFIRM_YES"
    CONFIRM_NO = "CONFIRM_NO"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


@dataclass
class IntentResult:
    intent: Intent
    steps: list[PlanStep] = field(default_factory=list)
    text: str = ""
    clarification: str | None = None
    source: str = "rules"
    confidence: float | None = None


def step(action: str, **params) -> PlanStep:
    return PlanStep(action=action, params={k: v for k, v in params.items() if v is not None})


# ---------------------------------------------------------------- normalize
# "hey jarvis, open chrome" -> "open chrome"; "hello jarvis" -> "hello" (a greeting, not an empty command).
_WAKE = re.compile(r"^(?:(hey|ok|okay)\s+)?jarvis\b[\s,!.:;-]*")
_GREETING_WAKE = re.compile(r"^(hi|hello|good (?:morning|afternoon|evening))[\s,]+jarvis[\s,!.:;-]*$")
_PREFIX = re.compile(
    r"^(?:please|kindly|can you|could you|would you|will you|go ahead and|i want you to|"
    r"i'd like you to|i would like you to|i want to|i'd like to)\s+"
)
_SUFFIX = re.compile(r"[\s,]+(?:please|for me|thanks|thank you|jarvis)$")


def normalize(text: str) -> tuple[str, bool]:
    """Return (normalized text, was_question)."""
    t = text.strip().lower()
    t = t.replace("’", "'").replace("‘", "'").replace("“", "").replace("”", "")
    t = re.sub(r'["`]', "", t)
    t = re.sub(r"\s+", " ", t).strip()
    was_question = t.endswith("?")
    t = _GREETING_WAKE.sub(lambda m: m.group(1), t)
    # Common speech-recognition homophones at the start of a request.
    t = re.sub(r"^(?:right|rite|wright)(?= (?:me|a|an|the|down|some|code|program|python|java|c)\b)", "write", t)
    t = re.sub(r"^made a note\b", "make a note", t)
    t = _WAKE.sub("", t)
    t = re.sub(r"[.!?]+$", "", t).strip().strip(",").strip()
    for _ in range(3):
        new = _PREFIX.sub("", t)
        new = _SUFFIX.sub("", new).strip()
        if new == t:
            break
        t = new
    return t, was_question


# ---------------------------------------------------------------- splitting
_VERBS = (
    r"open|launch|start|run|close|quit|exit|search|google|look up|find|play|pause|resume|next|previous|skip|"
    r"go to|visit|navigate to|take|show|read|copy|delete|move|type|press|scroll|click|mute|unmute|increase|"
    r"decrease|raise|lower|turn|set|volume|tell me|remind me|remember|schedule|book|add|create|make|"
    r"mark|complete|finish|rename|forget|cancel|note down|jot down|what's|what is|describe"
)
_SPLIT = re.compile(
    rf"\s*(?:,\s*(?:and\s+|then\s+|and then\s+)?|\s+and then\s+|\s+then\s+|\s+and\s+)(?=(?:{_VERBS})\b)"
)


def split_segments(text: str) -> list[str]:
    return [p.strip() for p in _SPLIT.split(text) if p and p.strip()]


# ---------------------------------------------------------------- vocab
YES = re.compile(
    r"^(?:yes|yeah|yep|yup|sure|ok|okay|do it|go ahead|proceed|confirm|confirmed|yes please|"
    r"please do|of course|absolutely|play it|open it|sure thing)$"
)
NO = re.compile(r"^(?:no|nope|nah|cancel|don't|do not|never mind|nevermind|no thanks|no thank you|abort|forget it)$")

WAKE_REPLY = "For you, always ma'am."
NAME_REPLY = "Yes?"
_WAKE_LEAD = re.compile(r"^(are you up|you up|are you awake|you awake|are you there|you there)[?!.,;:\s]+")

_SMALL_TALK = [
    # The wake phrase "Jarvis, are you up?" ("jarvis" is stripped by normalize()).
    (re.compile(r"^(?:are you up|you up|are you awake|you awake|are you there|you there)$"), WAKE_REPLY),
    (re.compile(r"^(?:hi|hello|hey|hey there|hello there|hi there|yo)$"), "Hello! How can I help you?"),
    (re.compile(r"^good (?:morning|afternoon|evening)$"), "Hello! What can I do for you?"),
    (re.compile(r"^(?:good night|bye|goodbye|see you|see you later)$"), "Goodbye. I'll be here when you need me."),
    (re.compile(r"^how are you(?: doing)?(?: today)?$"), "All systems are running smoothly. How can I help?"),
    (
        re.compile(r"^(?:who are you|what is your name|what's your name|what are you|introduce yourself)$"),
        "I'm JARVIS, your offline desktop assistant. I can open apps, find files, control media and answer questions.",
    ),
    (re.compile(r"^(?:thanks|thank you|thank you so much|thanks a lot|cheers)$"), "You're welcome."),
    (
        re.compile(r"^(?:help|what can you do|what can i say|commands)$"),
        "Try: open Chrome, search YouTube for lo-fi music, play Believer, open my resume, volume up, "
        "what's the battery, take a screenshot, or ask me a question.",
    ),
    (re.compile(r"^(?:ok|okay|cool|nice|great|alright)$"), "Okay."),
]

_BLOCKED = [
    (
        re.compile(
            r"\b(?:sudo|rm -rf|powershell|cmd\.exe|shell command|terminal command|run (?:a |the |this )?(?:command|script)|"
            r"execute (?:a |the |this )?(?:command|script|code|file)|chmod|regedit|registry)\b"
        ),
        "I don't run commands or scripts. I can only use my built-in actions.",
    ),
    (re.compile(r"\b(?:install|uninstall|reinstall)\b"), "I can't install or remove software."),
    (
        re.compile(
            r"\b(?:format (?:my |the )?(?:drive|disk|computer|laptop)|wipe (?:my |the )?(?:drive|disk|computer))\b"
        ),
        "I won't format or wipe drives.",
    ),
    (
        re.compile(
            r"\b(?:make (?:a |the )?payment|transfer money|send money|wire money|pay (?:rs|inr|\$|₹|\d)"
            r"|pay (?:someone|him|her|them|my (?:bill|bills|friend))|(?:buy|purchase|order) .*\b(?:online|on amazon|"
            r"on flipkart|for me)\b|place an? order|order food|checkout|check out my cart)"
        ),
        "I can't make payments or purchases.",
    ),
    (
        re.compile(r"\bsend (?:an? )?(?:email|e-mail|mail|message|text|whatsapp|sms)\b"),
        "I can't send messages on your behalf yet.",
    ),
    (
        re.compile(
            r"\b(?:shut ?down|restart|reboot) (?:the |my )?(?:computer|laptop|pc|system)\b|^(?:shut ?down|reboot)$"
        ),
        "I won't shut down or restart the computer.",
    ),
]

_WORD_OPS = [
    (r"\bmultiplied by\b|\btimes\b|\binto\b|\bx\b", "*"),
    (r"\bdivided by\b|\bover\b", "/"),
    (r"\bplus\b|\badded to\b", "+"),
    (r"\bminus\b|\bless\b", "-"),
    (r"\bto the power of\b|\bpower\b", "**"),
    (r"\bmod(?:ulo)?\b", "%"),
]

_REALTIME = re.compile(
    r"\b(?:weather|forecast|temperature outside|news|headlines?|today's|tonight|tomorrow|yesterday|current(?:ly)?|"
    r"latest|right now|live|score|stock|share price|price of|exchange rate|president|prime minister|chief minister|"
    r"ceo of|this week|this year|trending|release date|near me|restaurants?|open now)\b"
)
# Requests for written content — code, text, translations — are answered by the model directly,
# not planned as computer actions ("write a hello world program in C", "draft an email asking for leave").
_GENERATIVE = re.compile(
    r"^(?:write|generate|draft|compose|translate|summari[sz]e|paraphrase|rewrite|proofread|implement|debug|refactor)\b"
    r"|^(?:create|make|build|give me|show me|suggest|recommend|tell me|come up with|help me (?:write|with))\b.*"
    r"\b(?:program|code|function|script|class|method|algorithm|query|regex|example|snippet|poem|story|essay|email|"
    r"letter|joke|summary|plan|idea|ideas|recipe|outline|quiz|questions|explanation|template|paragraph|bio|caption)s?\b"
)
# What an actual computer command starts with. Anything else that no rule matched is conversation:
# it goes to the model as a question instead of the (slow) action planner.
_ACTION_START = re.compile(
    r"^(?:open|close|launch|start|run|quit|exit|kill|play|pause|resume|stop|skip|delete|remove|trash|move|copy|rename|"
    r"send|click|type|press|scroll|search|find|locate|show|turn|set|change|increase|decrease|raise|lower|mute|unmute|"
    r"take|schedule|remind|add|mark|complete|install|download|upload|go|visit|navigate|make|put|save|create|book|"
    r"cancel|enable|disable|switch|connect|disconnect|lock|minimi[sz]e|maximi[sz]e|close)\b"
)

_QUESTION_START = re.compile(
    r"^(?:what|what's|whats|who|who's|whom|whose|when|where|where's|why|how|which|is|are|was|were|can|could|does|"
    r"do|did|will|would|should|explain|tell me|define|describe|give me|list|summarize|compare)\b"
)

KNOWN_FOLDER_RE = r"(downloads|documents|desktop|pictures|photos|music|videos|home)"
_FOLDER_ALIAS = {"photos": "pictures"}
KIND_WORDS = {
    "pdf": "pdf",
    "pdfs": "pdf",
    "document": "document",
    "documents": "document",
    "doc": "document",
    "image": "image",
    "images": "image",
    "photo": "image",
    "photos": "image",
    "picture": "image",
    "pictures": "image",
    "video": "video",
    "videos": "video",
    "movie": "video",
    "song": "audio",
    "songs": "audio",
    "music": "audio",
    "audio": "audio",
    "track": "audio",
    "file": None,
    "files": None,
}
PRONOUNS = re.compile(
    r"^(?:(?:it|that|this|that song|this song|that one|this one|the song|that video|the same)(?: again| once more)?|again)$"
)


def _folder(word: str) -> str:
    return _FOLDER_ALIAS.get(word, word)


def _clean_arg(text: str) -> str:
    text = re.sub(r"^(?:the|a|an|my|some)\s+", "", text.strip())
    return text.strip(" ,.")


def _math_expression(s: str) -> str | None:
    body = re.sub(r"^(?:what is|what's|whats|calculate|compute|how much is|evaluate|solve)\s+", "", s)
    if not re.search(r"\d", body):
        return None
    expr = body
    for pattern, op in _WORD_OPS:
        expr = re.sub(pattern, f" {op} ", expr)
    expr = expr.replace("^", "**").replace("×", "*").replace("÷", "/")
    expr = re.sub(r"\s+", " ", expr).strip()
    if not re.fullmatch(r"[\d\s.+\-*/()%]+", expr) or not re.search(r"[+\-*/%]", expr):
        return None
    if not re.search(r"\d\s*(?:\*\*|[+\-*/%])\s*[\d(]", expr):
        return None
    return expr


# ---------------------------------------------------------------- matcher
class IntentMatcher:
    def __init__(self, apps: AppRegistry) -> None:
        self.apps = apps
        alias_alt = "|".join(re.escape(a) for a in apps.aliases())
        self._app_re = re.compile(rf"(?:the )?({alias_alt})(?: app| application| browser)?")
        site_alt = "|".join(re.escape(s) for s in sorted(KNOWN_SITES, key=len, reverse=True))
        self._site_re = re.compile(rf"(?:the )?({site_alt})(?: website| site| page|\.com)?")

    def parse(self, raw: str, session=None, confirmations: bool = True) -> IntentResult:
        """`confirmations=False` re-parses "yes"/"open it" etc. as normal commands when nothing is pending."""
        text, was_question = normalize(raw)
        if not text:
            if re.search(r"\bjarvis\b", raw, re.IGNORECASE):  # just the name: JARVIS answers and listens
                return IntentResult(Intent.SMALL_TALK, [step("reply", text=NAME_REPLY)], "jarvis")
            return IntentResult(Intent.EMPTY, text=text)
        if confirmations and YES.fullmatch(text):
            return IntentResult(Intent.CONFIRM_YES, text=text)
        if confirmations and NO.fullmatch(text):
            return IntentResult(Intent.CONFIRM_NO, text=text)

        segments = split_segments(text)
        # "jarvis are you up? open chrome": answer the wake phrase, then run the rest.
        lead = _WAKE_LEAD.match(text)
        if lead and lead.end() < len(text):
            segments = [lead.group(1), *split_segments(text[lead.end() :].strip())]
        results = [self._segment(seg, was_question and len(segments) == 1, session) for seg in segments]
        for r in results:
            r.steps = [restore_case(st, raw) for st in r.steps]

        for r in results:
            if r.intent in (Intent.BLOCKED, Intent.AMBIGUOUS):
                r.text = text
                return r
        if any(r.intent is Intent.UNKNOWN for r in results):
            return IntentResult(Intent.UNKNOWN, text=text)
        if len(results) == 1:
            results[0].text = text
            return self._finalize(results[0], session)
        steps = [st for r in results for st in r.steps]
        final = self._finalize(IntentResult(Intent.COMPOUND, steps, text), session)
        if final.intent is Intent.COMPOUND and len(final.steps) == 1:
            final.intent = Intent.COMMAND
        return final

    @staticmethod
    def _personal(s: str, matchers) -> IntentResult | None:
        for matcher in matchers:
            hit = matcher(s)
            if hit is not None:
                if hit.clarification:
                    return IntentResult(Intent.AMBIGUOUS, clarification=hit.clarification)
                return IntentResult(Intent.QUESTION if hit.intent == "QUESTION" else Intent.COMMAND, hit.steps)
        return None

    def _finalize(self, result: IntentResult, session) -> IntentResult:
        """Fill "play the first result" from the preceding search, or from session memory."""
        last_query = session.last_search_query if session is not None else None
        last_kind = getattr(session, "last_search_kind", None) if session is not None else None
        previous_title = None
        for i, st in enumerate(result.steps):
            # "take a note buy bread and add it to my tasks": "it" is the previous step's title.
            title = st.params.get("title")
            if isinstance(title, str) and title.lower() in ("it", "that", "this", "them") and previous_title:
                result.steps[i] = st = PlanStep(action=st.action, params={**st.params, "title": previous_title})
            if isinstance(st.params.get("title"), str):
                previous_title = st.params["title"]
            if st.action in ("search_youtube", "search_web", "web_answer"):
                last_query = st.params.get("query")
                last_kind = "youtube" if st.action == "search_youtube" else "web"
            if st.action == "open_first_result" and not st.params.get("query"):
                if not last_query:
                    return IntentResult(
                        Intent.AMBIGUOUS,
                        text=result.text,
                        clarification="What should I search for? Then I can open the first result.",
                    )
                action = "play_youtube" if last_kind == "youtube" else "open_first_result"
                result.steps[i] = PlanStep(action=action, params={"query": last_query})
                continue
            if st.action == "play_youtube" and not st.params.get("query"):
                if not last_query:
                    return IntentResult(
                        Intent.AMBIGUOUS,
                        text=result.text,
                        clarification="What would you like me to play? Please search for something first.",
                    )
                result.steps[i] = PlanStep(action="play_youtube", params={**st.params, "query": last_query})
        result.steps = merge_steps(result.steps)
        return result

    # ------------------------------------------------------------------
    def _segment(self, s: str, was_question: bool, session) -> IntentResult:  # noqa: C901 - flat rule table
        fm = re.fullmatch

        stored = self._personal(s, personal.STORAGE_MATCHERS)
        if stored is not None:
            return stored

        for pattern, reason in _BLOCKED:
            if pattern.search(s):
                return IntentResult(Intent.BLOCKED, [step("blocked_request", reason=reason)])

        for pattern, reply in _SMALL_TALK:
            if pattern.fullmatch(s):
                return IntentResult(Intent.SMALL_TALK, [step("reply", text=reply)])

        expr = _math_expression(s)
        if expr:
            return IntentResult(Intent.QUESTION, [step("calculate", expression=expr)])

        # ---- time / date / system information
        if fm(
            r"(?:what time is it|what's the time|whats the time|what is the time|tell me the time|current time|time)(?: now)?",
            s,
        ):
            return _cmd(step("system_information", topic="time"))
        if fm(
            r"(?:what's|what is|whats|tell me) (?:the |today's )?date(?: today)?|what day is (?:it|today)|today's date|date",
            s,
        ):
            return _cmd(step("system_information", topic="date"))
        topic = _system_topic(s)
        if topic:
            return _cmd(step("system_information", topic=topic))

        # ---- media transport + volume
        media = _media(s)
        if media:
            return _cmd(media)

        # ---- screen understanding (OCR)
        screen = _screen_request(s)
        if screen:
            return IntentResult(Intent.QUESTION, [screen])

        # ---- create / copy / rename files (jarvis/core/personal.py)
        files_hit = self._personal(s, (personal.file_ops_intent,))
        if files_hit is not None:
            return files_hit

        # ---- "open/play the first result" after a search (resolved in _finalize)
        if fm(
            r"(?:play|open|click)(?: on)? (?:the )?(?:first|top) (?:result|one|video|link|website|site)"
            r"(?: on youtube)?",
            s,
        ):
            return _cmd(step("youtube" in s and "play_youtube" or "open_first_result"))

        # ---- screenshot / clipboard
        if fm(
            r"(?:take|grab|capture|save)(?: a| an| the)? (?:screenshot|screen ?shot|screen capture|snapshot of (?:the|my) screen)|screenshot",
            s,
        ):
            return _cmd(step("screenshot"))
        if fm(
            r"(?:read|show|what's in|what is in|whats in|what's on|what is on|paste)(?: me)?(?: my| the)? clipboard", s
        ):
            return _cmd(step("clipboard_read"))
        m = fm(r"copy (.+?) to(?: the| my)? clipboard", s)
        if m:
            return _cmd(step("clipboard_write", text=m.group(1)))

        # ---- YouTube
        m = fm(r"play (.+?) on youtube", s) or fm(r"(?:open )?youtube (?:and )?play (.+)", s)
        if m:
            return _cmd(step("play_youtube", query=_clean_arg(m.group(1))))
        m = (
            fm(r"(?:search|look up|find)(?: on)? youtube(?: for)? (.+)", s)
            or fm(r"(?:search|look up|find)(?: for)? (.+?) on youtube", s)
            or fm(r"youtube(?: search)?(?: for)? (.+)", s)
        )
        if m:
            return _cmd(step("search_youtube", query=_clean_arg(m.group(1))))

        # ---- web search
        m = fm(
            r"(?:search|look up|google)(?: on)?(?: google| the web| the internet| online| web)?(?: for)? (.+)", s
        ) or fm(r"(?:search|look up)(?: for)? (.+?) (?:on|in) (?:google|the web|the internet)", s)
        if m and not re.match(r"^(?:my |for my )?(?:files?|folders?|computer|laptop|pc)\b", m.group(1)):
            query = re.sub(r"\s+(?:on|in) (?:google|the web|the internet)$", "", m.group(1))
            return _cmd(step("search_web", query=_clean_arg(query)))

        # ---- websites
        m = fm(r"(?:open|go to|visit|navigate to|show me) " + self._site_re.pattern, s)
        if m:
            return _cmd(step("open_url", url=KNOWN_SITES[m.group(1)]))
        m = fm(r"(?:open|go to|visit|navigate to) ((?:https?://)?(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/\S*)?)", s)
        if m and not re.search(r"\.(?:pdf|docx?|txt|mp3|mp4|jpg|jpeg|png|zip|xlsx?|pptx?|md|csv)$", m.group(1)):
            return _cmd(step("open_url", url=m.group(1)))

        # ---- close app
        m = fm(r"(?:close|quit|exit|kill|shut) (?:down )?(.+)", s)
        if m:
            app = self.apps.resolve(_clean_arg(m.group(1)))
            if app:
                return _cmd(step("close_application", app=app.name))
            return _cmd(step("close_application", app=_clean_arg(m.group(1))))

        # ---- folders
        m = fm(rf"(?:open|show|go to)(?: me)?(?: my| the)? {KNOWN_FOLDER_RE}(?: folder| directory)?", s)
        if m:
            return _cmd(step("open_folder", known=_folder(m.group(1))))
        m = fm(r"open (?:the |my )?(?:folder|directory)(?: called| named)? (.+)", s) or fm(
            r"open (?:the |my )?(.+?) (?:folder|directory)", s
        )
        if m:
            return _cmd(step("open_folder", query=_clean_arg(m.group(1))))

        # ---- open: app, latest-of-kind, file
        m = fm(r"(?:open|launch|start|run|fire up|bring up)(?: up)? (.+)", s)
        if m:
            target = m.group(1).strip()
            app = self.apps.resolve(_clean_arg(target))
            if app:
                return _cmd(step("open_application", app=app.name))
            lm = fm(r"(?:the |my )?(?:latest|newest|most recent|last) (\w+)", target)
            if lm and lm.group(1) in KIND_WORDS:
                return _cmd(step("open_file", latest=True, kind=KIND_WORDS[lm.group(1)]))
            if PRONOUNS.fullmatch(target):
                return self._pronoun(session, "open")
            fm_file = fm(r"(?:the )?(?:file|document)(?: called| named)? (.+)", target)
            return _cmd(step("open_file", query=_clean_arg(fm_file.group(1) if fm_file else target)))

        # ---- find files
        m = fm(r"(?:find|show|list|search for|locate)(?: me)?(?: all)?(?: my| the)? (\w+?)s? files", s)
        if m and (m.group(1) in KIND_WORDS or re.fullmatch(r"[a-z0-9]{2,5}", m.group(1))):
            word = m.group(1)
            if word in KIND_WORDS and KIND_WORDS[word]:
                return _cmd(step("find_file", kind=KIND_WORDS[word]))
            return _cmd(step("find_file", ext=word))
        if fm(
            r"(?:show|list|find)(?: me)?(?: the| my)? files (?:i )?(?:modified|changed|edited|created|downloaded) today",
            s,
        ):
            return _cmd(step("find_file", modified_today=True))
        m = fm(
            r"(?:find|locate|where is|where's)(?: my| the)? (?:(folder|project|directory) |file )?(?:called |named )?(.+)",
            s,
        )
        if m:
            target, folders = _clean_arg(m.group(2)), bool(m.group(1))
            sm = re.fullmatch(r"(.+?) (?:project|folder|directory|repo|repository)", target)
            if sm:
                target, folders = sm.group(1), True
            return _cmd(step("find_file", query=target, folders=folders or None))

        # ---- play local media
        if fm(r"play(?: some| my)? (?:music|songs|tunes)", s):
            return _cmd(step("play_media", kind="audio"))
        m = fm(
            rf"play(?: (?:the|some|my))? (?:music|songs|videos?) (?:from|in) (?:my |the )?{KNOWN_FOLDER_RE}(?: folder)?",
            s,
        )
        if m:
            kind = "video" if "video" in s else "audio"
            return _cmd(step("play_media", kind=kind, folder=_folder(m.group(1))))
        m = fm(r"play(?: the| my)?(?: (song|track|video|movie|music))?(?: called| named| titled)? (.+)", s)
        if m:
            target = _clean_arg(m.group(2))
            if PRONOUNS.fullmatch(m.group(2).strip()) or PRONOUNS.fullmatch(target):
                return self._pronoun(session, "play")
            kind = {"video": "video", "movie": "video"}.get(m.group(1) or "", "media")
            return _cmd(step("play_media", query=target, kind=kind))

        # ---- destructive file operations
        m = fm(
            rf"(?:delete|remove|trash|erase|clear)(?: all)?(?: the| my)?(?: (\w+?)s?)? files? (?:in|from|inside) (?:my |the )?{KNOWN_FOLDER_RE}(?: folder)?",
            s,
        )
        if m:
            kind = KIND_WORDS.get(m.group(1) or "") if m.group(1) else None
            return _cmd(step("delete_files", folder=_folder(m.group(2)), all_in_folder=True, kind=kind))
        m = fm(r"(?:delete|remove|trash|erase)(?: the| my)?(?: file| document)?(?: called| named)? (.+)", s)
        if m:
            return _cmd(step("delete_files", query=_clean_arg(m.group(1))))
        m = fm(r"move(?: the| my)?(?: file)? (.+) to (?:the |my )?(.+?)(?: folder| directory)?", s)
        if m:
            return _cmd(step("move_file", query=_clean_arg(m.group(1)), destination=_clean_arg(m.group(2))))

        # ---- keyboard / mouse
        m = fm(r"type (.+)", s)
        if m:
            return _cmd(step("type_text", text=m.group(1)))
        if fm(r"(?:press|hit) enter|send(?: it)?|submit", s):
            return _cmd(step("press_key", key="enter"))
        m = fm(r"(?:press|hit) (tab|escape|space|backspace|up|down|left|right|page ?up|page ?down)(?: key)?", s)
        if m:
            return _cmd(step("press_key", key=m.group(1).replace(" ", "")))
        m = fm(r"scroll (up|down)(?: a bit| more)?", s) or fm(r"go (up|down)", s)
        if m:
            return _cmd(step("scroll", direction=m.group(1)))
        m = fm(r"click(?: on)?(?: the)? (.+?)(?: button| link| tab)?", s)
        if m:
            return _cmd(step("click_text", text=m.group(1)))

        # ---- questions
        if _GENERATIVE.match(s):
            return IntentResult(Intent.QUESTION, [step("answer_question", question=s)])
        if was_question or _QUESTION_START.match(s):
            if _REALTIME.search(s):
                return IntentResult(Intent.REALTIME_QUERY, [step("web_answer", query=s)])
            return IntentResult(Intent.QUESTION, [step("answer_question", question=s)])
        if not _ACTION_START.match(s):
            # Statements and chat ("I think I'll go with Python", "that was helpful") are conversation.
            return IntentResult(Intent.QUESTION, [step("answer_question", question=s)])

        return IntentResult(Intent.UNKNOWN)

    def _pronoun(self, session, verb: str) -> IntentResult:
        if session is not None:
            if verb == "play" and session.last_media_path:
                return _cmd(step("open_file", path=session.last_media_path))
            if verb == "play" and session.last_media_query:
                return _cmd(step("play_media", query=session.last_media_query))
            if verb == "open" and session.last_file_path:
                return _cmd(step("open_file", path=session.last_file_path))
            if verb == "open" and session.last_results:
                return _cmd(step("open_file", path=session.last_results[0]))
        what = "song" if verb == "play" else "file"
        return IntentResult(Intent.AMBIGUOUS, clarification=f"Which {what} do you mean? Please tell me its name.")


# Matching runs on lowercased text; these user-supplied values keep the user's own capitalisation.
_CASED_PARAMS = ("title", "text", "name", "new_name", "content", "question")


def restore_case(st: PlanStep, raw: str) -> PlanStep:
    params = dict(st.params)
    changed = False
    for key in _CASED_PARAMS:
        value = params.get(key)
        if not isinstance(value, str) or not value:
            continue
        m = re.search(re.escape(value).replace("\\ ", r"\s+"), raw, re.IGNORECASE)
        if m:
            params[key] = m.group(0)
        elif key in ("title", "text") and value[:1].islower():
            params[key] = value[:1].upper() + value[1:]
        else:
            continue
        changed = True
    return PlanStep(action=st.action, params=params) if changed else st


def _cmd(*steps: PlanStep) -> IntentResult:
    return IntentResult(Intent.COMMAND, list(steps))


def _system_topic(s: str) -> str | None:
    if re.search(
        r"^(?:what's|what is|whats|how much|check|show)(?: my| the)? battery|\bbattery(?: level| status| percentage| life| left)?$|\bam i (?:charging|plugged in)\b",
        s,
    ):
        return "battery"
    if re.search(
        r"\b(?:cpu|processor) (?:usage|load|use|status|utili[sz]ation)\b|^(?:cpu|processor)$|how busy is (?:my|the) (?:cpu|processor|computer)",
        s,
    ):
        return "cpu"
    if re.search(r"\b(?:ram|memory) (?:usage|used|use|status|left|free)\b|^(?:ram|memory)$|how much (?:ram|memory)", s):
        return "memory"
    if re.search(
        r"\b(?:disk|storage|drive) (?:space|usage|left|status|free)\b|^storage$|how much (?:disk |storage |free )?space|free space",
        s,
    ):
        return "storage"
    if re.fullmatch(
        r"(?:am i (?:online|connected)|(?:is the |is my )?internet (?:working|connected|status|on)|network status|"
        r"(?:check )?(?:my )?(?:internet|network|wifi|wi-fi)(?: connection| status)?)",
        s,
    ):
        return "network"
    if re.fullmatch(
        r"(?:system|computer|laptop|pc) (?:status|info|information|stats|health)|how is my (?:system|computer|laptop) doing|status report",
        s,
    ):
        return "summary"
    return None


_SCREEN = r"(?:my|the|this) (?:screen|display|monitor)"


def _screen_request(s: str) -> PlanStep | None:
    fm = re.fullmatch
    if fm(
        rf"read(?: out| me)?(?: aloud)? {_SCREEN}(?: to me| for me| aloud| out loud)?|"
        rf"read (?:me )?(?:what's|what is|whats|the text|everything|all the text) (?:on|in) {_SCREEN}(?: aloud)?|"
        rf"what does {_SCREEN} say",
        s,
    ):
        return step("describe_screen", mode="read")
    if fm(
        rf"(?:what's|what is|whats|what's showing|what is showing|what's open|what is open) (?:on|in) {_SCREEN}"
        rf"(?: right now| now| at the moment)?|"
        rf"(?:describe|explain|summari[sz]e|analy[sz]e|scan|look at|check) {_SCREEN}|"
        rf"(?:describe|explain|summari[sz]e) (?:what's|what is) (?:on|in) {_SCREEN}|"
        rf"tell me (?:about|what's on|what is on) {_SCREEN}|"
        r"what am i (?:looking at|seeing)(?: right now| now)?|"
        rf"what do you see(?: on {_SCREEN})?|can you see {_SCREEN}",
        s,
    ):
        return step("describe_screen", mode="describe")
    if re.search(rf"\b(?:on|in) {_SCREEN}\b", s) and _QUESTION_START.match(s):
        return step("describe_screen", mode="ask", question=s)
    return None


def _media(s: str) -> PlanStep | None:
    fm = re.fullmatch
    if fm(r"(?:pause|stop)(?: the| my)?(?: music| song| video| playback| it| media| track)?", s):
        return step("media_control", command="pause")
    if fm(r"(?:resume|continue|unpause)(?: the| my)?(?: music| song| video| playback| it| media)?|play", s):
        return step("media_control", command="play")
    if fm(r"(?:next|skip)(?: the)?(?: song| track| video| one)?|play (?:the )?next(?: song| track)?", s):
        return step("media_control", command="next")
    if fm(
        r"(?:previous|prev|last|go back)(?: to the)?(?: song| track| video| one)?|play (?:the )?previous(?: song| track)?",
        s,
    ):
        return step("media_control", command="previous")
    if fm(r"(?:un ?mute)(?: the)?(?: sound| volume| audio)?|turn (?:the )?sound (?:back )?on", s):
        return step("volume_control", command="unmute")
    if fm(r"mute(?: the)?(?: sound| volume| audio)?|turn (?:the )?sound off", s):
        return step("volume_control", command="mute")
    m = fm(r"(?:set|change|put)(?: the)? volume to (\d{1,3})(?: percent|%)?|volume (\d{1,3})(?: percent|%)?", s)
    if m:
        value = int(m.group(1) or m.group(2))
        return step("volume_control", command="set", value=min(value, 100))
    if fm(r"(?:increase|raise|turn up|boost)(?: the)? (?:volume|sound)(?: up)?|volume up|louder|turn it up", s):
        return step("volume_control", command="up")
    if fm(
        r"(?:decrease|lower|reduce|turn down)(?: the)? (?:volume|sound)(?: down)?|volume down|quieter|softer|turn it down",
        s,
    ):
        return step("volume_control", command="down")
    return None


_BROWSER_STEP_ACTIONS = {"search_youtube", "search_web", "open_url", "play_youtube"}


def merge_steps(steps: list[PlanStep]) -> list[PlanStep]:
    """Fold "open <browser>" / "open youtube" into the browser step that follows."""
    out: list[PlanStep] = []
    for st in steps:
        prev = out[-1] if out else None
        if (
            prev
            and prev.action == "open_application"
            and st.action in _BROWSER_STEP_ACTIONS
            and "browser" not in st.params
        ):
            if prev.params.get("app") in ("chrome", "firefox", "edge"):
                out[-1] = PlanStep(action=st.action, params={**st.params, "browser": prev.params["app"]})
                continue
        if prev and prev.action == "open_url" and prev.params.get("url") == KNOWN_SITES["youtube"]:
            browser = {"browser": prev.params["browser"]} if prev.params.get("browser") else {}
            if st.action == "search_web":
                out[-1] = PlanStep(action="search_youtube", params={"query": st.params["query"], **browser})
                continue
            if st.action == "play_media" and st.params.get("query"):
                out[-1] = PlanStep(action="play_youtube", params={"query": st.params["query"], **browser})
                continue
        if (
            prev
            and prev.action == "search_web"
            and st.action == "open_first_result"
            and prev.params.get("query") == st.params.get("query")
        ):
            out[-1] = PlanStep(action="open_first_result", params={"query": st.params["query"]})
            continue
        if (
            prev
            and prev.action == "search_youtube"
            and st.action == "play_youtube"
            and prev.params.get("query") == st.params.get("query")
        ):
            out[-1] = PlanStep(action="play_youtube", params={**prev.params, **st.params})
            continue
        if (
            prev
            and prev.action == "open_url"
            and prev.params.get("url") == KNOWN_SITES["google"]
            and st.action == "search_web"
        ):
            out[-1] = st
            continue
        out.append(st)
    return out
