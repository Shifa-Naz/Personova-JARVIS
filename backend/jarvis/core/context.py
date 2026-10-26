"""Session memory and the context object handed to every action."""

from __future__ import annotations

import socket
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jarvis.ai.provider import AiProvider
    from jarvis.config import Settings
    from jarvis.files.search import FileSearchService
    from jarvis.platform.apps import AppRegistry
    from jarvis.platform.base import PlatformAdapter
    from jarvis.storage.store import JsonStore
    from jarvis.vision.ocr import OcrEngine


@dataclass
class SessionContext:
    """Short-lived, in-process memory used to resolve "it", "that song", "the first one".

    Nothing here is persisted to disk.
    """

    session_id: str
    history: deque = field(default_factory=lambda: deque(maxlen=12))
    last_media_query: str | None = None
    last_media_path: str | None = None
    last_file_path: str | None = None
    last_search_query: str | None = None
    last_search_kind: str | None = None  # "web" | "youtube" — decides what "open the first result" means
    last_app: str | None = None
    last_results: list[str] = field(default_factory=list)

    def add_turn(self, user: str, assistant: str) -> None:
        if user:
            self.history.append({"role": "user", "content": user})
        if assistant:
            self.history.append({"role": "assistant", "content": assistant})

    def history_list(self) -> list[dict[str, str]]:
        return list(self.history)


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, SessionContext] = {}
        self._lock = threading.Lock()

    def get(self, session_id: str) -> SessionContext:
        with self._lock:
            if session_id not in self._sessions:
                if len(self._sessions) > 50:  # local single-user app; keep bounded
                    self._sessions.pop(next(iter(self._sessions)))
                self._sessions[session_id] = SessionContext(session_id)
            return self._sessions[session_id]


class Connectivity:
    """Cheap, cached internet check (TCP connect to public DNS resolvers)."""

    def __init__(self, ttl_s: float = 10.0) -> None:
        self.ttl_s = ttl_s
        self._cache: tuple[float, bool] = (0.0, False)
        self.override: bool | None = None  # tests

    def online(self) -> bool:
        if self.override is not None:
            return self.override
        checked, value = self._cache
        if time.time() - checked < self.ttl_s:
            return value
        value = False
        for host in ("1.1.1.1", "8.8.8.8"):
            try:
                with socket.create_connection((host, 53), timeout=1.5):
                    value = True
                    break
            except OSError:
                continue
        self._cache = (time.time(), value)
        return value


@dataclass
class ExecContext:
    settings: Settings
    platform: PlatformAdapter
    apps: AppRegistry
    files: FileSearchService
    ai: AiProvider
    connectivity: Connectivity
    session: SessionContext
    ocr: OcrEngine | None = None
    store: JsonStore | None = None
    # Set while a streaming request runs: answer pieces are passed here as the model writes them.
    on_delta: Callable[[str], None] | None = None
