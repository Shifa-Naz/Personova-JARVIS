"""Small JSON document store for memory, notes, tasks and events.

- Atomic writes (temp file + os.replace) so a crash never leaves half-written JSON.
- Corruption recovery: an unreadable file is moved aside (``*.corrupt-<time>.json``) and
  the collection starts empty, instead of crashing the assistant.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

COLLECTIONS = ("memory", "notes", "tasks", "events")


def new_id() -> str:
    return f"{int(time.time() * 1000):x}-{secrets.token_hex(3)}"


class JsonStore:
    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self._lock = threading.RLock()
        self.recovered: list[str] = []

    def _path(self, collection: str) -> Path:
        if collection not in COLLECTIONS:
            raise ValueError(f"Unknown collection: {collection}")
        return self.directory / f"{collection}.json"

    def load(self, collection: str) -> list[dict[str, Any]]:
        path = self._path(collection)
        with self._lock:
            if not path.exists():
                return []
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(data, list) or not all(isinstance(x, dict) for x in data):
                    raise ValueError("expected a list of objects")
                return data
            except (OSError, ValueError) as exc:  # json.JSONDecodeError is a ValueError
                aside = path.with_name(f"{path.stem}.corrupt-{time.strftime('%Y%m%d-%H%M%S')}.json")
                try:
                    path.rename(aside)
                except OSError:
                    aside = path
                log.warning("Recovered from unreadable %s (%s); moved to %s", path.name, exc, aside.name)
                self.recovered.append(collection)
                return []

    def save(self, collection: str, items: list[dict[str, Any]]) -> None:
        path = self._path(collection)
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}-", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(items, fh, ensure_ascii=False, indent=1)
                os.replace(tmp, path)
            except BaseException:
                Path(tmp).unlink(missing_ok=True)
                raise

    # ---- convenience CRUD -------------------------------------------------
    def add(self, collection: str, item: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            items = self.load(collection)
            item = {"id": new_id(), "created": time.time(), **item}
            items.insert(0, item)
            self.save(collection, items)
            return item

    def update(self, collection: str, item_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        with self._lock:
            items = self.load(collection)
            for i, item in enumerate(items):
                if item.get("id") == item_id:
                    items[i] = {**item, **patch, "id": item_id, "updated": time.time()}
                    self.save(collection, items)
                    return items[i]
            return None

    def delete(self, collection: str, item_id: str) -> bool:
        with self._lock:
            items = self.load(collection)
            kept = [x for x in items if x.get("id") != item_id]
            if len(kept) == len(items):
                return False
            self.save(collection, kept)
            return True

    def get(self, collection: str, item_id: str) -> dict[str, Any] | None:
        return next((x for x in self.load(collection) if x.get("id") == item_id), None)
