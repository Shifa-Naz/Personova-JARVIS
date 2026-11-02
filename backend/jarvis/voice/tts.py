"""Offline text-to-speech with Piper (optional dependency).

Voices are downloaded once into the JARVIS data dir (`python run.py --download-models`,
needs internet the first time); synthesis then runs fully offline on the CPU.
"""

from __future__ import annotations

import importlib.util
import io
import logging
import threading
import time
import wave
from pathlib import Path

from jarvis.actions.base import ActionError

log = logging.getLogger(__name__)

MAX_TTS_CHARS = 1200


class Synthesizer:
    def __init__(self, voice: str, voices_dir: Path, rate: float = 1.0) -> None:
        self.voice = voice
        self.voices_dir = Path(voices_dir)
        # Piper's length_scale is duration: >1 slower, <1 faster.
        self.length_scale = 1.0 / max(0.5, min(rate, 2.0))
        self._voice = None
        self._lock = threading.Lock()

    @staticmethod
    def installed() -> bool:
        return importlib.util.find_spec("piper") is not None

    @property
    def model_path(self) -> Path:
        return self.voices_dir / f"{self.voice}.onnx"

    def voice_downloaded(self) -> bool:
        return self.model_path.is_file() and Path(f"{self.model_path}.json").is_file()

    def available(self) -> bool:
        return self.installed() and self.voice_downloaded()

    def download(self) -> None:
        if not self.installed():
            raise ActionError("TTS_UNAVAILABLE", "Offline speech isn't installed (pip install piper-tts).")
        from piper.download_voices import download_voice

        self.voices_dir.mkdir(parents=True, exist_ok=True)
        download_voice(self.voice, self.voices_dir)

    def _load(self):
        if not self.installed():
            raise ActionError("TTS_UNAVAILABLE", "Offline speech isn't installed (pip install piper-tts).")
        if not self.voice_downloaded():
            raise ActionError(
                "TTS_UNAVAILABLE", f"The voice '{self.voice}' isn't downloaded. Run: python run.py --download-models"
            )
        if self._voice is None:
            from piper import PiperVoice

            started = time.time()
            self._voice = PiperVoice.load(str(self.model_path))
            log.info("Loaded Piper voice %s in %.1fs", self.voice, time.time() - started)
        return self._voice

    def load(self) -> None:
        """Load the voice ahead of the first reply (warm-up)."""
        with self._lock:
            self._load()

    def synthesize(self, text: str) -> bytes:
        text = " ".join(text.split())[:MAX_TTS_CHARS]
        if not text:
            raise ActionError("NO_TEXT", "There's nothing to say.")
        with self._lock:  # one ONNX session; keep synthesis serialized
            voice = self._load()
            from piper.config import SynthesisConfig

            buf = io.BytesIO()
            started = time.time()
            try:
                with wave.open(buf, "wb") as wav:
                    voice.synthesize_wav(text, wav, syn_config=SynthesisConfig(length_scale=self.length_scale))
            except Exception as exc:  # noqa: BLE001 - model/phonemizer errors become a typed failure
                log.exception("Speech synthesis failed")
                raise ActionError("TTS_FAILED", "I couldn't synthesize speech.") from exc
            log.info("Synthesized %d chars in %.2fs", len(text), time.time() - started)
            return buf.getvalue()
