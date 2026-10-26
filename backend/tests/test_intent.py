"""Table-driven intent tests, including every regression from the original parser/planner (CLAUDE.md §30)."""

from __future__ import annotations

import pytest

from jarvis.core.context import SessionContext
from jarvis.core.intent import Intent, IntentMatcher, normalize, split_segments
from jarvis.platform.apps import AppRegistry


@pytest.fixture(scope="module")
def matcher() -> IntentMatcher:
    return IntentMatcher(AppRegistry())


def plan(matcher, text, session=None):
    r = matcher.parse(text, session)
    return r.intent, [(s.action, s.params) for s in r.steps]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # apps
        ("Open Chrome", [("open_application", {"app": "chrome"})]),
        ("Jarvis, launch the calculator please", [("open_application", {"app": "calculator"})]),
        ("open vs code", [("open_application", {"app": "vscode"})]),
        ("open terminal", [("open_application", {"app": "terminal"})]),
        ("open file manager", [("open_application", {"app": "file_manager"})]),
        ("close chrome", [("close_application", {"app": "chrome"})]),
        # B1: "search" used to become "serch" and never match
        ("search youtube for imagine dragons", [("search_youtube", {"query": "imagine dragons"})]),
        ("Search Google for React hooks", [("search_web", {"query": "react hooks"})]),
        ("search for the best restaurants in belgaum", [("search_web", {"query": "best restaurants in belgaum"})]),
        ("play believer by imagine dragons on youtube", [("play_youtube", {"query": "believer by imagine dragons"})]),
        # B1: "open downloads" used to become "open downlods"
        ("open downloads", [("open_folder", {"known": "downloads"})]),
        ("open my documents folder", [("open_folder", {"known": "documents"})]),
        ("open github", [("open_url", {"url": "https://github.com"})]),
        ("go to example.org", [("open_url", {"url": "example.org"})]),
        # B4: "resume" used to be "corrected" to "result"
        ("open my resume", [("open_file", {"query": "resume"})]),
        ("open the latest pdf", [("open_file", {"latest": True, "kind": "pdf"})]),
        ("find my react project", [("find_file", {"query": "react", "folders": True})]),
        ("find all jpg files", [("find_file", {"ext": "jpg"})]),
        ("show me files modified today", [("find_file", {"modified_today": True})]),
        # media
        ("play believer", [("play_media", {"query": "believer", "kind": "media"})]),
        ("play my music", [("play_media", {"kind": "audio"})]),
        ("play music from downloads", [("play_media", {"kind": "audio", "folder": "downloads"})]),
        ("pause", [("media_control", {"command": "pause"})]),
        ("next song", [("media_control", {"command": "next"})]),
        ("increase volume", [("volume_control", {"command": "up"})]),
        ("set volume to 40 percent", [("volume_control", {"command": "set", "value": 40})]),
        ("mute", [("volume_control", {"command": "mute"})]),
        # system
        ("what time is it", [("system_information", {"topic": "time"})]),
        ("what's the battery", [("system_information", {"topic": "battery"})]),
        ("cpu usage", [("system_information", {"topic": "cpu"})]),
        ("take a screenshot", [("screenshot", {})]),
        ("what's in my clipboard", [("clipboard_read", {})]),
        # math
        ("What is 25 multiplied by 18", [("calculate", {"expression": "25 * 18"})]),
        # B6: "move file X to Y" used to always fail
        ("move file report to documents", [("move_file", {"query": "report", "destination": "documents"})]),
        ("delete all files in downloads", [("delete_files", {"folder": "downloads", "all_in_folder": True})]),
        ("delete the file report draft", [("delete_files", {"query": "report draft"})]),
    ],
)
def test_commands(matcher, text, expected):
    _intent, steps = plan(matcher, text)
    assert steps == expected


@pytest.mark.parametrize(
    ("text", "intent", "action"),
    [
        ("hello", Intent.SMALL_TALK, "reply"),
        # B1: "what is your name" used to become "wht your nme" and be ignored
        ("what is your name", Intent.SMALL_TALK, "reply"),
        ("thanks jarvis", Intent.SMALL_TALK, "reply"),
        ("What is the capital of India?", Intent.QUESTION, "answer_question"),
        ("explain recursion", Intent.QUESTION, "answer_question"),
        ("what is docker", Intent.QUESTION, "answer_question"),
        ("What is the weather today?", Intent.REALTIME_QUERY, "web_answer"),
        ("who is the current president of the united states", Intent.REALTIME_QUERY, "web_answer"),
        ("run the command rm -rf /", Intent.BLOCKED, "blocked_request"),
        ("install vlc", Intent.BLOCKED, "blocked_request"),
        ("send an email to my boss", Intent.BLOCKED, "blocked_request"),
    ],
)
def test_intent_classes(matcher, text, intent, action):
    got_intent, steps = plan(matcher, text)
    assert got_intent is intent
    assert steps[0][0] == action


def test_question_about_cpu_is_not_telemetry(matcher):
    intent, steps = plan(matcher, "what is a cpu")
    assert intent is Intent.QUESTION and steps[0][0] == "answer_question"


def test_compound_open_chrome_and_search_youtube(matcher):
    intent, steps = plan(matcher, "Open Chrome and search YouTube for Java tutorials")
    assert intent is Intent.COMMAND
    assert steps == [("search_youtube", {"query": "java tutorials", "browser": "chrome"})]


def test_compound_open_youtube_and_search(matcher):
    _, steps = plan(matcher, "Open YouTube and search for relaxing music")
    assert steps == [("search_youtube", {"query": "relaxing music"})]


def test_compound_search_and_play_first(matcher):
    _, steps = plan(matcher, "Open Chrome, search YouTube for Java DSA tutorials, and play the first result")
    assert steps == [("play_youtube", {"query": "java dsa tutorials", "browser": "chrome"})]


def test_compound_two_independent_actions(matcher):
    intent, steps = plan(matcher, "open downloads and then take a screenshot")
    assert intent is Intent.COMPOUND
    assert [s[0] for s in steps] == ["open_folder", "screenshot"]


def test_and_inside_query_is_not_split(matcher):
    # B3: the old splitter cut on the substring "and"
    _, steps = plan(matcher, "search for rock and roll")
    assert steps == [("search_web", {"query": "rock and roll"})]
    assert split_segments("open the android studio") == ["open the android studio"]


def test_type_with_hello_is_not_small_talk(matcher):
    # B5: "type hello world" used to be treated as chat
    _, steps = plan(matcher, "type hello world")
    assert steps == [("type_text", {"text": "hello world"})]


def test_filler_words_never_produce_empty_targets(matcher):
    # B2: "delete file link" used to delete the first file on the Desktop
    for text in ("delete file link", "delete file result", "delete the file button", "open file that"):
        intent, steps = plan(matcher, text)
        for _action, params in steps:
            for key in ("query", "path"):
                if key in params:
                    assert len(params[key]) >= 2, (text, params)


def test_pronoun_without_context_asks_for_clarification(matcher):
    result = matcher.parse("play that song")
    assert result.intent is Intent.AMBIGUOUS
    assert "Which song" in result.clarification


def test_pronoun_resolved_from_session(matcher):
    session = SessionContext("s")
    session.last_media_path = "/x/believer.mp3"
    _, steps = plan(matcher, "play it again", session)
    assert steps == [("open_file", {"path": "/x/believer.mp3"})]


def test_play_first_without_search_is_ambiguous(matcher):
    assert matcher.parse("play the first result").intent is Intent.AMBIGUOUS


def test_yes_no(matcher):
    assert matcher.parse("yes").intent is Intent.CONFIRM_YES
    assert matcher.parse("Cancel.").intent is Intent.CONFIRM_NO


def test_unknown(matcher):
    assert matcher.parse("make my wallpaper blue").intent is Intent.UNKNOWN


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Hello JARVIS", "hello"),
        ("hey jarvis, open chrome", "open chrome"),
        ("thanks jarvis", "thanks"),
        ("Jarvis, what time is it?", "what time is it"),
    ],
)
def test_wake_word_handling(text, expected):
    assert normalize(text)[0] == expected


def test_normalize_strips_wake_word_and_politeness():
    assert normalize("Hey Jarvis, could you please open Chrome?")[0] == "open chrome"


def test_compound_productivity_splits_and_resolves_it(matcher):
    _, steps = plan(matcher, "Schedule dentist on friday at 10 am and remind me to carry the insurance card on friday")
    assert [a for a, _ in steps] == ["event_create", "task_create"]
    assert steps[1][1]["title"] == "carry the insurance card"
    _, steps = plan(matcher, "take a note buy bread and add it to my tasks")
    assert steps == [("note_create", {"title": "buy bread"}), ("task_create", {"title": "buy bread"})]
    _, steps = plan(matcher, "add milk and eggs to my tasks")
    assert steps == [("task_create", {"title": "milk and eggs"})]


@pytest.mark.parametrize(
    "text",
    [
        "write a hello world program in C",
        "create a poem about rain",
        "translate good morning to hindi",
        "draft an email asking for leave",
        "can you write a program to sort numbers",
        "make a function in java that adds two numbers",
        "I think I will go with python",
    ],
)
def test_content_requests_and_chat_go_to_the_model_not_the_planner(matcher, text):
    intent, steps = plan(matcher, text)
    assert intent is Intent.QUESTION and steps[0][0] == "answer_question"


def test_compact_catalog_is_small():
    from jarvis.actions import build_registry

    compact = build_registry().catalog_compact()
    assert "create_folder(name, parent?)" in compact and "blocked_request" not in compact
    assert len(compact) < 6000  # the JSON catalog was ~19k chars, ~3 min of prompt reading on CPU


@pytest.mark.parametrize(
    ("text", "params"),
    [
        ("Create greetings.txt", {"name": "greetings.txt"}),
        ("create greetings dot txt on the desktop", {"name": "greetings.txt", "folder": "desktop"}),
        ("create a text file called greetings in downloads", {"name": "greetings", "folder": "downloads"}),
        ("make a new file named todo list", {"name": "todo list"}),
        (
            "Jarvis, create a file greetings.txt saying Hello Sourab, good morning!",
            {"name": "greetings.txt", "content": "Hello Sourab, good morning"},
        ),
    ],
)
def test_create_file_phrasings(matcher, text, params):
    _, steps = plan(matcher, text)
    assert steps == [("create_file", params)]


def test_reply_is_not_offered_to_the_planner():
    from jarvis.actions import build_registry

    reg = build_registry()
    assert "reply(" not in reg.catalog_compact()
    assert "reply" not in {c["action"] for c in reg.catalog()}
