from __future__ import annotations

import pytest

from jarvis.actions import build_registry
from jarvis.actions.base import ActionError, PermissionLevel, PlanStep
from jarvis.actions.conversation import safe_eval


def test_registry_rejects_unknown_actions_and_fields():
    reg = build_registry()
    with pytest.raises(ActionError) as exc:
        reg.validate(PlanStep(action="exec", params={}))
    assert exc.value.code == "UNKNOWN_ACTION"
    with pytest.raises(ActionError) as exc:
        reg.validate(PlanStep(action="open_application", params={"app": "chrome", "shell": "rm -rf /"}))
    assert exc.value.code == "INVALID_PARAMS"


def test_open_url_only_allows_http():
    reg = build_registry()
    for bad in ("file:///etc/passwd", "javascript:alert(1)", "ftp://x.org"):
        with pytest.raises(ActionError):
            reg.validate(PlanStep(action="open_url", params={"url": bad}))
    _, params = reg.validate(PlanStep(action="open_url", params={"url": "github.com"}))
    assert params.url == "https://github.com"


def test_permission_levels_match_policy():
    reg = build_registry()
    expected = {
        "delete_files": PermissionLevel.DESTRUCTIVE,
        "move_file": PermissionLevel.DESTRUCTIVE,
        "close_application": PermissionLevel.SENSITIVE,
        "type_text": PermissionLevel.SENSITIVE,
        "clipboard_write": PermissionLevel.SENSITIVE,
        "open_application": PermissionLevel.SAFE,
        "find_file": PermissionLevel.READ_ONLY,
        "blocked_request": PermissionLevel.BLOCKED,
    }
    for name, level in expected.items():
        assert reg.get(name).permission is level


def test_catalog_excludes_blocked_actions():
    names = {c["action"] for c in build_registry().catalog()}
    assert "blocked_request" not in names and "open_application" in names


def test_delete_everything_in_home_is_invalid():
    with pytest.raises(ActionError):
        build_registry().validate(PlanStep(action="delete_files", params={"folder": "home", "all_in_folder": True}))


@pytest.mark.parametrize(("expr", "value"), [("25 * 18", 450), ("2 ** 10", 1024), ("(1 + 2) * 3", 9), ("7 / 2", 3.5)])
def test_safe_eval(expr, value):
    assert safe_eval(expr) == value


@pytest.mark.parametrize("expr", ["__import__('os')", "2 ** 1000000", "1 / 0", "open('x')"])
def test_safe_eval_rejects(expr):
    with pytest.raises(ActionError):
        safe_eval(expr)


def test_ollama_memory_error_is_explained(monkeypatch):
    import io
    import urllib.error

    from jarvis.ai.provider import AiUnavailable, OllamaProvider

    body = b'{"error":"model requires more system memory (4.9 GiB) than is available (4.5 GiB)"}'

    def fake_urlopen(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 500, "Internal Server Error", {}, io.BytesIO(body))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    with pytest.raises(AiUnavailable, match="enough free memory.*4.9 GiB"):
        OllamaProvider("http://127.0.0.1:11434", "qwen2.5vl:3b").answer("hi", [])


def test_ollama_timeout_is_not_reported_as_not_running(monkeypatch):
    from jarvis.ai.provider import AiUnavailable, OllamaProvider

    def slow(req, timeout):
        raise TimeoutError("timed out")

    monkeypatch.setattr("urllib.request.urlopen", slow)
    with pytest.raises(AiUnavailable, match="took longer than"):
        OllamaProvider("http://127.0.0.1:11434", "llama3.2:3b", timeout_s=5).answer("hi", [])


def test_ollama_requests_use_configured_threads(monkeypatch):
    import io
    import json as _json

    from jarvis.ai.provider import OllamaProvider

    sent = {}

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout):
        sent.update(_json.loads(req.data))
        return Resp(b'{"message": {"content": "ok"}}')

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    OllamaProvider("http://127.0.0.1:11434", "llama3.2:3b", threads=8).answer("hi", [])
    assert sent["options"]["num_thread"] == 8 and sent["keep_alive"] == "30m"
