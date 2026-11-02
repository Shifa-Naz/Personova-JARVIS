"""Launcher helpers (no processes are started, no real autostart entry is written)."""

from __future__ import annotations

import json
import sys

import pytest

import launch


def test_profile_pre_approves_the_microphone_for_jarvis_only(tmp_path):
    launch.prepare_profile(tmp_path)
    prefs = json.loads((tmp_path / "Default" / "Preferences").read_text())
    mic = prefs["profile"]["content_settings"]["exceptions"]["media_stream_mic"]
    assert set(mic) == {f"{launch.FRONTEND_URL},*", f"http://127.0.0.1:{launch.FRONTEND_PORT},*"}
    assert all(v == {"setting": 1} for v in mic.values())


def test_existing_profile_is_left_alone(tmp_path):
    prefs = tmp_path / "Default" / "Preferences"
    prefs.parent.mkdir(parents=True)
    prefs.write_text('{"mine": true}')
    launch.prepare_profile(tmp_path)
    assert json.loads(prefs.read_text()) == {"mine": True}


@pytest.mark.skipif(sys.platform == "win32", reason="Linux autostart entry")
def test_autostart_install_and_remove(tmp_path, monkeypatch):
    monkeypatch.setattr(launch.Path, "home", classmethod(lambda cls: tmp_path))
    entry = launch.install_autostart()
    text = entry.read_text()
    assert entry == tmp_path / ".config" / "autostart" / "jarvis.desktop"
    assert "--at-login" in text and sys.executable in text
    assert launch.remove_autostart() and not entry.exists()


def test_browser_flags_allow_hands_free_audio():
    assert "--autoplay-policy=no-user-gesture-required" in launch.BROWSER_FLAGS
