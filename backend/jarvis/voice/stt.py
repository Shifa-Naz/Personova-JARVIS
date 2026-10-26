"""Offline speech-to-text with faster-whisper (optional dependency).

The model is downloaded once into the JARVIS data dir (needs internet the first
time; run `python run.py --download-models`), then works fully offline.
"""

from __future__ import annotations

import importlib.util
import logging
import math
import os
import tempfile
import threading
import time

from jarvis.actions.base import ActionError

log = logging.getLogger(__name__)


class Transcriber:
    def __init__(self, model: str, device: str, compute_type: str, download_root: str) -> None:
        self.model_name = model
        self.device = device
        self.compute_type = compute_type
        self.download_root = download_root
        self._model = None
        self._lock = threading.Lock()

    @staticmethod
    def installed() -> bool:
        return importlib.util.find_spec("faster_whisper") is not None

    def load(self):
        if not self.installed():
            raise ActionError("STT_UNAVAILABLE", "Offline speech recognition isn't installed (faster-whisper).")
        with self._lock:
            if self._model is None:
                from faster_whisper import WhisperModel

                started = time.time()
                os.makedirs(self.download_root, exist_ok=True)
                self._model = WhisperModel(
                    self.model_name,
                    device=self.device,
                    compute_type=self.compute_type,
                    download_root=self.download_root,
                )
                log.info("Loaded Whisper model %s in %.1fs", self.model_name, time.time() - started)
        return self._model

    def transcribe(self, audio: bytes, suffix: str = ".webm", prompt: str | None = None) -> str:
        """`prompt` biases Whisper toward expected words (e.g. the name "Jarvis" for wake detection)."""
        return self.transcribe_detailed(audio, suffix, prompt)[0]

    def transcribe_detailed(self, audio: bytes, suffix: str = ".webm", prompt: str | None = None) -> tuple[str, float]:
        """Returns (text, confidence 0-1). Confidence is exp(mean token log-probability) over the speech."""
        if not audio:
            raise ActionError("NO_AUDIO", "I didn't receive any audio.")
        model = self.load()
        fd, path = tempfile.mkstemp(suffix=suffix, prefix="jarvis-stt-")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(audio)
            started = time.time()
            segments_iter, _info = model.transcribe(
                path,
                language="en",
                beam_size=1,
                vad_filter=True,
                condition_on_previous_text=False,
                initial_prompt=prompt,
            )
            segments = [s for s in segments_iter if s.no_speech_prob < 0.8 or s.avg_logprob > -0.5]
            text = " ".join(seg.text.strip() for seg in segments).strip()
            if segments:
                total = sum(max(1, len(s.text)) for s in segments)
                avg = sum(s.avg_logprob * max(1, len(s.text)) for s in segments) / total
                confidence = round(math.exp(avg), 2)
            else:
                confidence = 0.0
            log.info("Transcribed %d bytes in %.2fs (confidence %.2f)", len(audio), time.time() - started, confidence)
            return text, confidence
        except ActionError:
            raise
        except Exception as exc:  # noqa: BLE001 - decoder/model errors become a typed failure
            log.exception("Transcription failed")
            raise ActionError("STT_FAILED", "I couldn't understand the recording.") from exc
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
