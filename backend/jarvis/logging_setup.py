"""Structured JSON logging to a rotating file + readable console output.

Never log clipboard contents, file contents, typed text or secrets — actions
declare `sensitive_params` and `redact()` masks them.
"""

from __future__ import annotations

import json
import logging
import time
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import Lock
from typing import Any

REDACTED = "[redacted]"
_SECRET_KEYS = {"token", "api_key", "password", "secret", "authorization"}


def redact(params: dict[str, Any], sensitive: tuple[str, ...] = ()) -> dict[str, Any]:
    out = {}
    for key, value in params.items():
        if key in sensitive or key.lower() in _SECRET_KEYS:
            out[key] = REDACTED
        elif isinstance(value, str) and len(value) > 200:
            out[key] = value[:200] + "…"
        else:
            out[key] = value
    return out


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra = getattr(record, "event", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class RecentEvents:
    """In-memory ring buffer feeding the UI logs panel."""

    def __init__(self, size: int = 200) -> None:
        self._items: deque[dict[str, Any]] = deque(maxlen=size)
        self._lock = Lock()

    def add(self, event: dict[str, Any]) -> None:
        with self._lock:
            self._items.append({"ts": time.time(), **event})

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._items)[-limit:]


recent_events = RecentEvents()


def log_event(logger: logging.Logger, msg: str, level: int = logging.INFO, **event: Any) -> None:
    recent_events.add({"msg": msg, **event})
    logger.log(level, msg, extra={"event": event})


def setup_logging(logs_dir: Path, debug: bool = False) -> None:
    root = logging.getLogger()
    if getattr(root, "_jarvis_configured", False):
        return
    root.setLevel(logging.DEBUG if debug else logging.INFO)

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S"))
    root.addHandler(console)

    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(logs_dir / "jarvis.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        file_handler.setFormatter(JsonFormatter())
        root.addHandler(file_handler)
    except OSError as exc:  # logging must never stop the assistant from starting
        root.warning("File logging disabled: %s", exc)

    # Werkzeug request lines are noise at INFO.
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    root._jarvis_configured = True  # type: ignore[attr-defined]
