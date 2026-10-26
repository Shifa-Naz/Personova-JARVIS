"""Settings loaded from environment variables (optionally via a .env file)."""

from __future__ import annotations

import json
import os
import secrets
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
DEFAULT_ROOT_NAMES = ("Desktop", "Downloads", "Documents", "Music", "Pictures", "Videos")


def default_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "jarvis"


def default_search_roots() -> tuple[Path, ...]:
    home = Path.home()
    candidates = [home / name for name in DEFAULT_ROOT_NAMES]
    # Windows often redirects Desktop/Documents into OneDrive.
    onedrive = os.environ.get("OneDrive")
    if onedrive:
        candidates += [Path(onedrive) / name for name in ("Desktop", "Documents", "Pictures")]
    return tuple(p for p in candidates if p.is_dir())


def _bool(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(value: str | None, default: int) -> int:
    try:
        return int(value) if value else default
    except ValueError:
        return default


@dataclass
class Settings:
    host: str = "127.0.0.1"
    port: int = 5000
    debug: bool = False
    allowed_origins: tuple[str, ...] = ("http://localhost:8080", "http://127.0.0.1:8080")
    token: str = field(default_factory=lambda: secrets.token_urlsafe(32), repr=False)
    data_dir: Path = field(default_factory=default_data_dir)
    search_roots: tuple[Path, ...] = field(default_factory=default_search_roots)
    max_command_chars: int = 500

    llm_enabled: bool = True
    llm_url: str = "http://127.0.0.1:11434"
    llm_model: str = "llama3.2:3b"
    llm_timeout_s: int = 90
    # CPU threads for the model. Measured on an i5-1240P: 8 threads read prompts ~1.9x faster than Ollama's
    # default; 12 was slower (efficiency cores). Default: half the logical CPUs, at most 8.
    llm_threads: int = field(default_factory=lambda: max(1, min(8, (os.cpu_count() or 2) // 2)))
    # Optional Ollama vision model (e.g. "qwen2.5vl:3b", "llava") used with OCR to describe the screen.
    vision_model: str | None = None

    stt_model: str = "base.en"
    stt_device: str = "cpu"
    stt_compute_type: str = "int8"

    tts_enabled: bool = True
    tts_voice: str = "en_GB-alan-medium"
    tts_rate: float = 1.0

    tesseract_cmd: str | None = None
    app_overrides: dict[str, Any] = field(default_factory=dict)

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def voices_dir(self) -> Path:
        return self.data_dir / "voices"


LEGACY_PREFIX = "ULTRON_"  # the project was briefly named ULTRON; old .env files keep working


def _with_legacy(env: Mapping[str, str]) -> dict[str, str]:
    merged = dict(env)
    for key, value in env.items():
        if key.startswith(LEGACY_PREFIX):
            merged.setdefault("JARVIS_" + key[len(LEGACY_PREFIX) :], value)
    return merged


def migrate_legacy_data_dir(target: Path) -> bool:
    """Move ~/.local/share/ultron (or %APPDATA%\\ultron) to the JARVIS location once, keeping downloaded models."""
    legacy = target.with_name("ultron")
    if target.exists() or not legacy.is_dir():
        return False
    legacy.rename(target)
    return True


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    env = _with_legacy(os.environ if env is None else env)
    s = Settings()

    s.host = env.get("JARVIS_HOST", s.host)
    if s.host not in LOOPBACK_HOSTS:
        raise ValueError(
            f"JARVIS_HOST={s.host!r} is not a loopback address. JARVIS controls this computer "
            "and must only listen on 127.0.0.1 / localhost."
        )
    s.port = _int(env.get("JARVIS_PORT"), s.port)
    s.debug = _bool(env.get("JARVIS_DEBUG"), False)

    origins = env.get("JARVIS_ALLOWED_ORIGINS")
    if origins:
        s.allowed_origins = tuple(o.strip().rstrip("/") for o in origins.split(",") if o.strip())

    if env.get("JARVIS_DATA_DIR"):
        s.data_dir = Path(env["JARVIS_DATA_DIR"]).expanduser()

    roots = env.get("JARVIS_SEARCH_ROOTS")
    if roots:
        s.search_roots = tuple(
            Path(p).expanduser() for p in roots.split(os.pathsep) if p.strip() and Path(p).expanduser().is_dir()
        )

    s.max_command_chars = _int(env.get("JARVIS_MAX_COMMAND_CHARS"), s.max_command_chars)

    s.llm_enabled = _bool(env.get("JARVIS_LLM_ENABLED"), True)
    s.llm_url = env.get("JARVIS_LLM_URL", s.llm_url).rstrip("/")
    s.llm_model = env.get("JARVIS_LLM_MODEL", s.llm_model)
    s.llm_timeout_s = _int(env.get("JARVIS_LLM_TIMEOUT"), s.llm_timeout_s)
    s.llm_threads = _int(env.get("JARVIS_LLM_THREADS"), s.llm_threads)
    s.vision_model = env.get("JARVIS_VISION_MODEL") or None

    s.stt_model = env.get("JARVIS_STT_MODEL", s.stt_model)
    s.stt_device = env.get("JARVIS_STT_DEVICE", s.stt_device)
    s.stt_compute_type = env.get("JARVIS_STT_COMPUTE_TYPE", s.stt_compute_type)

    s.tts_enabled = _bool(env.get("JARVIS_TTS_ENABLED"), True)
    s.tts_voice = env.get("JARVIS_TTS_VOICE", s.tts_voice)
    try:
        s.tts_rate = float(env.get("JARVIS_TTS_RATE") or s.tts_rate)
    except ValueError:
        pass

    s.tesseract_cmd = env.get("JARVIS_TESSERACT_CMD") or None

    config_file = env.get("JARVIS_CONFIG_FILE")
    if config_file and Path(config_file).expanduser().is_file():
        with open(Path(config_file).expanduser(), encoding="utf-8") as fh:
            s.app_overrides = json.load(fh).get("apps", {})

    return s
