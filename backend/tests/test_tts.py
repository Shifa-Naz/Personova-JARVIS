from __future__ import annotations

import os
import wave
from io import BytesIO
from pathlib import Path

import pytest

from jarvis.voice.tts import Synthesizer

H = {"Origin": "http://localhost:8080", "X-Jarvis-Token": "test-token"}


def test_speak_returns_wav(client, fake_synth):
    resp = client.post("/api/v1/speak", json={"text": "All systems online."}, headers=H)
    assert resp.status_code == 200
    assert resp.mimetype == "audio/wav"
    assert fake_synth.spoken == ["All systems online."]


def test_speak_requires_token(client):
    assert client.post("/api/v1/speak", json={"text": "hi"}, headers={"Origin": H["Origin"]}).status_code == 401


def test_speak_unavailable_is_503(client, fake_synth):
    fake_synth.ready = False
    resp = client.post("/api/v1/speak", json={"text": "hi"}, headers=H)
    assert resp.status_code == 503 and resp.json["error_code"] == "TTS_UNAVAILABLE"


def test_speak_empty_text_is_422(client):
    assert client.post("/api/v1/speak", json={"text": "   "}, headers=H).status_code == 422


def test_capabilities_report_tts(client):
    caps = client.get("/api/v1/status", headers=H).json["capabilities"]
    assert caps["tts"] is True and caps["tts_voice"]


def test_missing_voice_is_reported_not_downloaded(tmp_path):
    synth = Synthesizer("en_GB-alan-medium", tmp_path)
    assert not synth.voice_downloaded()
    assert not synth.available()


VOICE_DIR = os.environ.get("JARVIS_TEST_VOICE_DIR")


@pytest.mark.skipif(not VOICE_DIR, reason="set JARVIS_TEST_VOICE_DIR to a folder containing en_GB-alan-medium.onnx")
def test_real_piper_synthesis():
    synth = Synthesizer("en_GB-alan-medium", Path(VOICE_DIR))
    audio = synth.synthesize("Hello, I am JARVIS.")
    with wave.open(BytesIO(audio)) as wav:
        assert wav.getnframes() / wav.getframerate() > 0.5


class FakeTranscriber:
    def __init__(self):
        self.prompts = []

    @staticmethod
    def installed():
        return True

    def transcribe_detailed(self, audio, suffix=".webm", prompt=None):
        self.prompts.append(prompt)
        return "Jarvis, are you up?", 0.9


def test_wake_hint_biases_whisper(settings, fake_platform, fake_ai, connectivity, fake_synth, fake_ocr):
    from jarvis.app import build_services, create_app
    from jarvis.files.search import FileSearchService

    stt = FakeTranscriber()
    services = build_services(
        settings,
        platform=fake_platform,
        ai=fake_ai,
        files=FileSearchService(settings.search_roots),
        connectivity=connectivity,
        synthesizer=fake_synth,
        ocr=fake_ocr,
        transcriber=stt,
    )
    client = create_app(services).test_client()
    h = {**H, "Content-Type": "audio/webm"}
    assert client.post("/api/v1/transcribe?hint=wake", data=b"x", headers=h).json["text"] == "Jarvis, are you up?"
    client.post("/api/v1/transcribe", data=b"x", headers=h)
    assert stt.prompts[0] == "Jarvis, are you up?" and "write me a program" in stt.prompts[1]


def test_wake_phrase_reply(pipeline):
    for text in ("Jarvis are you up??", "jarvis, are you up?", "Hey Jarvis, are you awake?"):
        assert pipeline.command(text).reply == "For you, always ma'am."
    resp = pipeline.command("Jarvis are you up? what time is it")
    assert resp.reply.startswith("For you, always ma'am. It's")


def test_name_alone_and_name_with_command(pipeline, fake_platform):
    assert pipeline.command("Jarvis").reply == "Yes?"
    assert pipeline.command("Hey Jarvis!").reply == "Yes?"
    assert pipeline.command("Jarvis, open chrome").reply == "Chrome is open."


def test_homophones_and_note_of(pipeline, services):
    assert pipeline.plan("Right me a C program to add two numbers").steps[0].action == "answer_question"
    pipeline.command("made a note of baking cookies")
    assert services.store.load("notes")[0]["title"].lower() == "baking cookies"
