from __future__ import annotations

import pytest

from jarvis.config import load_settings

TOKEN = {"X-Jarvis-Token": "test-token"}
FRONTEND = {"Origin": "http://localhost:8080"}


def test_health_is_public(client):
    assert client.get("/api/v1/health").json["ok"] is True


def test_session_hands_token_to_allowed_origin(client):
    resp = client.get("/api/v1/session", headers=FRONTEND)
    assert resp.status_code == 200
    assert resp.json["token"] == "test-token"
    assert resp.headers["Access-Control-Allow-Origin"] == "http://localhost:8080"


def test_foreign_origin_rejected_everywhere(client):
    evil = {"Origin": "https://evil.example"}
    assert client.get("/api/v1/session", headers=evil).status_code == 403
    resp = client.post("/api/v1/command", json={"text": "delete all files in downloads"}, headers={**evil, **TOKEN})
    assert resp.status_code == 403


def test_dns_rebinding_host_rejected(client):
    resp = client.get("/api/v1/health", headers={"Host": "attacker.example:5000"})
    assert resp.status_code == 403


def test_token_required(client):
    assert client.post("/api/v1/command", json={"text": "open chrome"}).status_code == 401
    bad = client.post("/api/v1/command", json={"text": "open chrome"}, headers={"X-Jarvis-Token": "nope"})
    assert bad.status_code == 401


def test_command_flow(client, fake_platform):
    resp = client.post("/api/v1/command", json={"text": "open chrome"}, headers={**FRONTEND, **TOKEN})
    assert resp.status_code == 200
    assert resp.json["status"] == "done"
    assert fake_platform.calls[0][0] == "launch_app"


def test_plan_execute_confirm_flow(client, trash):
    h = {**FRONTEND, **TOKEN}
    plan = client.post(
        "/api/v1/plan", json={"text": "delete the file report draft", "session_id": "ui"}, headers=h
    ).json
    assert plan["status"] == "ready" and plan["steps"][0]["permission"] == "DESTRUCTIVE"
    ex = client.post("/api/v1/execute", json={"plan_id": plan["plan_id"], "session_id": "ui"}, headers=h).json
    assert ex["status"] == "needs_confirmation"
    # a different session cannot use this confirmation
    other = client.post(
        "/api/v1/confirm",
        json={"confirmation_id": ex["confirmation"]["id"], "decision": "confirm", "session_id": "other"},
        headers=h,
    ).json
    assert other["error_code"] == "CONFIRMATION_EXPIRED"
    assert trash == []


def test_confirm_validates_decision(client):
    h = {**FRONTEND, **TOKEN}
    assert (
        client.post("/api/v1/confirm", json={"confirmation_id": "x", "decision": "maybe"}, headers=h).status_code == 400
    )


def test_system_and_status(client):
    h = {**FRONTEND, **TOKEN}
    sys = client.get("/api/v1/system", headers=h).json
    assert "cpu_percent" in sys and "memory" in sys
    caps = client.get("/api/v1/status", headers=h).json["capabilities"]
    assert caps["llm"] is True


def test_transcribe_without_whisper_is_503_or_422(client):
    h = {**FRONTEND, **TOKEN, "Content-Type": "audio/webm"}
    resp = client.post("/api/v1/transcribe", data=b"", headers=h)
    assert resp.status_code in (422, 503)


def test_non_loopback_host_setting_refused():
    with pytest.raises(ValueError):
        load_settings({"JARVIS_HOST": "0.0.0.0"})


def test_unknown_endpoint_is_json(client):
    resp = client.get("/api/v1/nope", headers={**FRONTEND, **TOKEN})
    assert resp.status_code == 404 and resp.json["error_code"] == "NOT_FOUND"


def test_execute_stream_sends_deltas_then_done(client, fake_ai):
    import json as _json

    fake_ai.answer_stream = lambda q, h, m=None: iter(["Hello", ", ", "world."])
    h = {**FRONTEND, **TOKEN}
    plan = client.post("/api/v1/plan", json={"text": "what is polymorphism", "session_id": "s"}, headers=h).json
    resp = client.post("/api/v1/execute/stream", json={"plan_id": plan["plan_id"], "session_id": "s"}, headers=h)
    assert resp.mimetype == "text/event-stream"
    events = [_json.loads(line[6:]) for line in resp.get_data(as_text=True).splitlines() if line.startswith("data: ")]
    assert [e["text"] for e in events if e["type"] == "delta"] == ["Hello", ", ", "world."]
    done = events[-1]
    assert done["type"] == "done" and done["response"]["reply"] == "Hello, world." and done["response"]["success"]


def test_execute_stream_requires_token(client):
    assert client.post("/api/v1/execute/stream", json={"plan_id": "x"}, headers=FRONTEND).status_code == 401
