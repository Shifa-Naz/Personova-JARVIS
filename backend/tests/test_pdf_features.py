"""Features from the Personova/JARVIS completion spec: memory, productivity, files, web, API contract."""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from jarvis.storage.store import JsonStore

TOMORROW = (date.today() + timedelta(days=1)).isoformat()


# ---------------------------------------------------------------- store
def test_store_recovers_from_corrupt_json(tmp_path):
    (tmp_path / "tasks.json").write_text("{not json", encoding="utf-8")
    store = JsonStore(tmp_path)
    assert store.load("tasks") == []
    assert store.recovered == ["tasks"]
    assert list(tmp_path.glob("tasks.corrupt-*.json"))  # bad file kept aside, not deleted
    store.add("tasks", {"title": "fresh"})
    assert json.loads((tmp_path / "tasks.json").read_text())[0]["title"] == "fresh"


def test_store_rejects_wrong_shape(tmp_path):
    (tmp_path / "notes.json").write_text('{"a": 1}', encoding="utf-8")
    assert JsonStore(tmp_path).load("notes") == []


# ---------------------------------------------------------------- memory
def test_remember_and_recall(pipeline):
    saved = pipeline.command("Remember that I prefer C++")
    assert saved.status == "done" and "you prefer C++" in saved.reply
    recalled = pipeline.command("What language do I prefer?")
    assert recalled.reply == "From memory: I prefer C++"


def test_recall_without_llm_reads_memory(pipeline, fake_ai):
    pipeline.command("remember that my favourite colour is teal")
    fake_ai.is_available = False
    assert "your favourite colour is teal" in pipeline.command("what is my favourite colour").reply


def test_memory_not_saved_automatically(pipeline, services):
    pipeline.command("I really like pizza")
    pipeline.command("what is polymorphism")
    assert services.store.load("memory") == []


def test_memory_refuses_secrets(pipeline, services):
    resp = pipeline.command("remember that my password is hunter2")
    assert resp.error_code == "SENSITIVE_DATA"
    assert services.store.load("memory") == []


def test_forget_requires_confirmation(pipeline, services):
    pipeline.command("remember that I prefer C++")
    resp = pipeline.command("forget that I prefer C++")
    assert resp.status == "needs_confirmation"
    assert pipeline.command("yes").reply == "Forgotten."
    assert services.store.load("memory") == []


def test_memories_are_context_for_answers(pipeline, fake_ai):
    pipeline.command("remember that I prefer C++")
    pipeline.command("how do I write a loop in my preferred language?")
    assert fake_ai.last_memories == ["I prefer C++"]


def test_memory_list(pipeline):
    pipeline.command("remember that I study at KLE")
    assert "you study at KLE" in pipeline.command("what do you remember about me").reply


# ---------------------------------------------------------------- tasks
def test_task_with_date_and_case(pipeline, services):
    resp = pipeline.command("Add a JARVIS task tomorrow")
    assert resp.status == "done" and "JARVIS" in resp.reply and "tomorrow" in resp.reply
    task = services.store.load("tasks")[0]
    assert (task["title"], task["due"], task["completed"]) == ("JARVIS", TOMORROW, False)
    assert resp.results[0].data["changed"] == "tasks"


def test_task_lifecycle(pipeline, services):
    pipeline.command("remind me to call mom tomorrow at 6 pm")
    assert services.store.load("tasks")[0]["due_time"] == "18:00"
    assert "call mom" in pipeline.command("what are my tasks").reply
    assert pipeline.command("mark call mom as done").reply == "Marked “call mom” as done."
    assert services.store.load("tasks")[0]["completed"] is True
    assert pipeline.command("reopen call mom").reply == "Reopened “call mom”."
    resp = pipeline.command("delete the call mom task")
    assert resp.status == "needs_confirmation"
    pipeline.command("yes")
    assert services.store.load("tasks") == []


def test_ambiguous_time_asks(pipeline, services):
    resp = pipeline.command("remind me to call mom at 5")
    assert resp.status == "needs_clarification" and "5 AM or 5 PM" in resp.reply
    assert services.store.load("tasks") == []


def test_ambiguous_task_target_asks(pipeline):
    pipeline.command("add submit report to my tasks")
    pipeline.command("add submit form to my tasks")
    resp = pipeline.command("mark submit as done")
    assert resp.status == "needs_clarification" and "Which task" in resp.reply


def test_paying_rent_reminder_is_not_blocked(pipeline):
    assert pipeline.command("remind me to pay rent on friday").status == "done"
    assert pipeline.command("pay ₹500 to ravi").error_code == "BLOCKED"


# ---------------------------------------------------------------- notes / calendar
def test_notes(pipeline, services):
    pipeline.command("take a note Call Ravi about the GitHub repo")
    assert services.store.load("notes")[0]["title"] == "Call Ravi about the GitHub repo"
    assert "GitHub" in pipeline.command("search notes for github").reply
    pipeline.command("add push the fix tonight to the ravi note")
    assert "push the fix tonight" in services.store.load("notes")[0]["content"]
    assert pipeline.command("delete the ravi note").status == "needs_confirmation"


def test_calendar(pipeline, services):
    resp = pipeline.command("schedule team meeting tomorrow at 4 pm")
    assert resp.reply == "Scheduled “team meeting” for tomorrow at 4:00 PM."
    assert services.store.load("events")[0]["date"] == TOMORROW
    assert "team meeting" in pipeline.command("what's on my calendar tomorrow").reply
    assert pipeline.command("move the team meeting to friday").status == "done"
    assert pipeline.command("schedule a call with ravi").status == "needs_clarification"


# ---------------------------------------------------------------- files
def test_create_folder(pipeline, home):
    resp = pipeline.command("Create folder College")
    assert resp.status == "done"
    assert (home / "Documents" / "College").is_dir()
    assert pipeline.command("create folder College").error_code == "FOLDER_EXISTS"


def test_copy_really_copies_and_offers_overwrite(pipeline, home):
    resp = pipeline.command("copy lecture notes.pdf to documents")
    assert resp.status == "done"
    target = home / "Documents" / "lecture notes.pdf"
    assert target.is_file() and (home / "Downloads" / "lecture notes.pdf").is_file()
    again = pipeline.command("copy lecture notes.pdf to documents")
    assert again.status == "needs_confirmation" and "replace it" in again.reply


def test_rename_requires_confirmation_and_keeps_extension(pipeline, home):
    resp = pipeline.command("rename Resume_2026 to Resume Final")
    assert resp.status == "needs_confirmation" and "Resume Final.pdf" in resp.reply
    assert pipeline.command("yes").status == "done"
    assert (home / "Documents" / "Resume Final.pdf").is_file()


def test_ambiguous_open_asks(pipeline, home):
    (home / "Desktop" / "report.txt").write_text("x")
    (home / "Music" / "report.txt").write_text("x")
    pipeline.files.build_index()
    resp = pipeline.command("open my report.txt")
    assert resp.status == "needs_clarification" and "Which one" in resp.reply


# ---------------------------------------------------------------- web
PAGE = """
<a rel="nofollow" class="result__a" href="https://duckduckgo.com/y.js?ad_domain=x.com&u3=1">Sponsored</a>
<a class="result__snippet">ad text</a>
<a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fweather&amp;rut=1">Belgaum
 <b>Weather</b> Today</a><a class="result__snippet" href="#">Sunny, <b>28°C</b> with light wind.</a>
<a rel="nofollow" class="result__a" href="https://docs.python.org/3/">Python docs</a>
"""


def test_parse_results_skips_ads_and_unwraps_redirects():
    from jarvis.actions.web import parse_results

    results = parse_results(PAGE)
    assert [r.url for r in results] == ["https://example.com/weather", "https://docs.python.org/3/"]
    assert results[0].title == "Belgaum Weather Today" and results[0].snippet == "Sunny, 28°C with light wind."


@pytest.fixture
def fake_search(monkeypatch):
    from jarvis.actions import web

    monkeypatch.setattr(web, "search", lambda q, limit=5, timeout=10.0: web.parse_results(PAGE, limit))


def test_realtime_question_uses_web_with_sources(pipeline, fake_search):
    resp = pipeline.command("what's the weather in belgaum today")
    assert resp.status == "done"
    assert resp.reply.startswith("Per Belgaum Weather Today: Sunny")
    assert "**Sources**" in resp.reply and "example.com" in resp.reply
    assert "Sources" not in resp.speech  # links are shown, not read aloud


def test_search_and_open_first_result(pipeline, fake_platform, fake_search):
    resp = pipeline.command("Search Python tutorials and open the first result")
    assert resp.status == "done"
    assert fake_platform.calls[-1][:2] == ("open_url", "https://example.com/weather")


def test_web_offline(pipeline, connectivity):
    connectivity.override = False
    assert pipeline.command("what's the weather in belgaum today").error_code == "OFFLINE"


# ---------------------------------------------------------------- API contract (§19) and NLP (§9)
def test_exec_response_contract(pipeline):
    resp = pipeline.command("what is polymorphism").model_dump()
    assert {"success", "reply", "response_type", "results", "request_id", "speech"} <= set(resp)
    assert resp["success"] is True and resp["response_type"] == "conversation"
    assert pipeline.command("delete the file report draft").response_type == "confirmation"
    assert pipeline.command("run the command ls").model_dump()["success"] is False


def test_plan_has_confidence_entities_risk(pipeline):
    plan = pipeline.plan("remind me to call mom tomorrow at 6 pm")
    assert plan.confidence >= 0.8
    assert (
        plan.entities == {"title": "call mom", "due": TOMORROW, "due_time": "18:00"}
        or plan.entities["title"] == "call mom"
    )
    assert plan.risk == "SAFE"
    assert pipeline.plan("delete all files in downloads").risk == "DESTRUCTIVE"


def test_low_confidence_llm_plan_asks(pipeline, fake_ai, fake_platform):
    fake_ai.plans = [
        {
            "kind": "plan",
            "confidence": 0.2,
            "text": "open firefox",
            "steps": [{"action": "open_application", "params": {"app": "firefox"}}],
        }
    ]
    resp = pipeline.command("make the fox happen")
    assert resp.status == "needs_clarification" and "Did you mean: open firefox" in resp.reply
    assert fake_platform.calls == []


def test_answer_speech_is_short_and_skips_code(pipeline, fake_ai):
    fake_ai.answers = ["A **loop** repeats code.\n\n```cpp\nfor (int i = 0; i < 3; i++) {}\n```\n\nUse it to iterate."]
    resp = pipeline.command("how do I write a loop in C++?")
    assert "```" in resp.reply  # full Markdown for the page
    assert "for (int" not in resp.speech and "code on screen" in resp.speech


# ---------------------------------------------------------------- items API used by the pages
H = {"Origin": "http://localhost:8080", "X-Jarvis-Token": "test-token"}


def test_items_api_crud_and_import(client):
    created = client.post("/api/v1/items/tasks", json={"title": "Pages task", "priority": "high"}, headers=H)
    assert created.status_code == 201
    tid = created.json["item"]["id"]
    assert client.patch(f"/api/v1/items/tasks/{tid}", json={"completed": True}, headers=H).json["item"]["completed"]
    assert client.get("/api/v1/items/tasks", headers=H).json["items"][0]["id"] == tid
    imported = client.post(
        "/api/v1/items/notes/import",
        json={"items": [{"id": "1", "title": "Old note", "content": "from localStorage"}, {"title": ""}]},
        headers=H,
    ).json
    assert imported["imported"] == 1
    again = client.post(
        "/api/v1/items/notes/import", json={"items": [{"title": "Old note", "content": "from localStorage"}]}, headers=H
    ).json
    assert again["imported"] == 0  # idempotent
    assert client.delete(f"/api/v1/items/tasks/{tid}", headers=H).status_code == 200
    assert client.get("/api/v1/items/secrets", headers=H).status_code == 404
    assert (
        client.post("/api/v1/items/tasks", json={"title": "x", "evil": "field"}, headers=H).json["item"].get("evil")
        is None
    )
