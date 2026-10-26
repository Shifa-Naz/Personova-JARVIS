from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from jarvis.ai.provider import AiProvider, AiUnavailable
from jarvis.app import build_services, create_app
from jarvis.config import Settings
from jarvis.core.context import Connectivity
from jarvis.files.search import FileSearchService
from jarvis.platform.fake import FakeAdapter


class FakeAI(AiProvider):
    name = "fake"

    def __init__(self) -> None:
        self.is_available = True
        self.plans: list[dict] = []
        self.answers: list[str] = ["New Delhi is the capital of India."]
        self.plan_calls = 0
        self.screen_calls: list[dict] = []

    def available(self) -> bool:
        return self.is_available

    def answer(self, question, history, memories=None):
        if not self.is_available:
            raise AiUnavailable("offline model down")
        self.last_memories = memories
        return self.answers[0]

    def answer_with_memory(self, question, facts):
        if not self.is_available:
            raise AiUnavailable("offline model down")
        return f"From memory: {facts[0]}"

    def answer_from_sources(self, question, results):
        if not self.is_available:
            raise AiUnavailable("offline model down")
        return f"Per {results[0]['title']}: {results[0]['snippet']}"

    def describe_screen(self, screen_text, request, history, image_b64=None):
        if not self.is_available:
            raise AiUnavailable("offline model down")
        self.screen_calls.append({"text": screen_text, "request": request, "image": image_b64 is not None})
        return "You're looking at a mail app with a quarterly report open."

    def plan(self, utterance, catalog, action_names, history):
        if not self.is_available:
            raise AiUnavailable("offline model down")
        self.plan_calls += 1
        return self.plans.pop(0) if self.plans else {"kind": "unsupported", "steps": [], "text": "Not supported."}


def _touch(path: Path, mtime: float | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    if mtime:
        os.utime(path, (mtime, mtime))
    return path


@pytest.fixture
def home(tmp_path: Path) -> Path:
    root = tmp_path / "home"
    old = time.time() - 10 * 86400
    _touch(root / "Downloads" / "Believer - Imagine Dragons.mp3", old)
    _touch(root / "Downloads" / "setup_installer.zip", old)
    _touch(root / "Downloads" / "lecture notes.pdf")
    _touch(root / "Documents" / "Resume_2026.pdf", old)
    _touch(root / "Documents" / "report draft.docx", old)
    _touch(root / "Documents" / "projects" / "react-app" / "package.json", old)
    _touch(root / "Music" / "Thunder.mp3", old)
    _touch(root / "Pictures" / "holiday.jpg", old)
    _touch(root / "Desktop" / "important.docx", old)
    (root / "Videos").mkdir(parents=True)
    return root


@pytest.fixture
def settings(home: Path, tmp_path: Path) -> Settings:
    roots = tuple(home / n for n in ("Desktop", "Downloads", "Documents", "Music", "Pictures", "Videos"))
    return Settings(token="test-token", data_dir=tmp_path / "data", search_roots=roots)


@pytest.fixture
def fake_platform() -> FakeAdapter:
    return FakeAdapter()


@pytest.fixture
def fake_ai() -> FakeAI:
    return FakeAI()


@pytest.fixture
def connectivity() -> Connectivity:
    c = Connectivity()
    c.override = True
    return c


class FakeSynth:
    def __init__(self) -> None:
        self.ready = True
        self.spoken: list[str] = []

    def available(self) -> bool:
        return self.ready

    def synthesize(self, text: str) -> bytes:
        from jarvis.actions.base import ActionError

        if not self.ready:
            raise ActionError("TTS_UNAVAILABLE", "voice not downloaded")
        if not text.strip():
            raise ActionError("NO_TEXT", "There's nothing to say.")
        self.spoken.append(text)
        return b"RIFF....WAVEfake"


# Built at runtime so no key-shaped literal sits in the repo (GitHub push protection flags it).
FAKE_STRIPE_KEY = "sk_" + "live_" + "x1Y2z3" * 4


class FakeOcr:
    """Returns canned lines; records which image paths it was asked to read."""

    def __init__(self) -> None:
        from jarvis.vision.ocr import OcrLine

        self.lines = [
            OcrLine("Inbox - Mail", 0.9, 20, 8, 200, 20),
            OcrLine("Quarterly Report: Revenue grew 12% in Q3", 0.9, 80, 120, 700, 32),
            OcrLine("api key " + FAKE_STRIPE_KEY, 0.9, 80, 220, 600, 20),
            OcrLine("Meeting with the design team at 4:30 PM", 0.9, 80, 270, 600, 20),
        ]
        self.paths: list[str] = []
        self.ready = True

    def engine_name(self):
        return "fake" if self.ready else None

    def available(self) -> bool:
        return self.ready

    def read(self, image_path):
        self.paths.append(str(image_path))
        assert image_path.exists(), "screenshot must exist while OCR runs"
        return list(self.lines), (1920, 1080)


@pytest.fixture
def fake_ocr() -> FakeOcr:
    return FakeOcr()


@pytest.fixture
def fake_synth() -> FakeSynth:
    return FakeSynth()


@pytest.fixture
def services(settings, fake_platform, fake_ai, connectivity, fake_synth, fake_ocr):
    files = FileSearchService(settings.search_roots)
    return build_services(
        settings,
        platform=fake_platform,
        ai=fake_ai,
        files=files,
        connectivity=connectivity,
        synthesizer=fake_synth,
        ocr=fake_ocr,
    )


@pytest.fixture
def pipeline(services):
    return services.pipeline


@pytest.fixture
def client(services):
    app = create_app(services)
    app.testing = True
    return app.test_client()


@pytest.fixture
def trash(monkeypatch):
    """Replace send2trash so tests never touch the real trash."""
    import send2trash

    trashed: list[str] = []

    def fake_send2trash(path):
        trashed.append(path)
        os.remove(path)

    monkeypatch.setattr(send2trash, "send2trash", fake_send2trash)
    return trashed


@pytest.fixture
def no_youtube_network(monkeypatch):
    from jarvis.actions import browser

    monkeypatch.setattr(browser, "first_youtube_video", lambda query, timeout=8.0: "abcdefghijk")
