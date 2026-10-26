"""In-memory adapter for tests: records calls, never touches the real system."""

from __future__ import annotations

from pathlib import Path

from jarvis.actions.base import ActionError
from jarvis.platform.apps import AppEntry
from jarvis.platform.base import PlatformAdapter


class FakeAdapter(PlatformAdapter):
    os_key = "linux"

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.running: dict[str, int] = {}
        self.clipboard = ""
        self.volume_level = 50
        self.fail: dict[str, ActionError] = {}

    def _record(self, *call) -> None:
        name = call[0]
        if name in self.fail:
            raise self.fail[name]
        self.calls.append(call)

    def open_path(self, path: Path) -> None:
        self._record("open_path", str(path))

    def open_url(self, url: str, browser: AppEntry | None = None) -> None:
        self._record("open_url", url, browser.name if browser else None)

    def launch_app(self, app: AppEntry, extra_args: list[str] | None = None) -> None:
        self._record("launch_app", app.name, tuple(extra_args or ()))
        self.running[app.name] = self.running.get(app.name, 0) + 1

    def close_app(self, app: AppEntry, dry_run: bool = False) -> int:
        count = self.running.get(app.name, 0)
        if not dry_run:
            self._record("close_app", app.name)
            self.running.pop(app.name, None)
        return count

    def media(self, command: str) -> str:
        self._record("media", command)
        return "fake"

    def volume(self, command: str, value: int | None = None) -> int | None:
        self._record("volume", command, value)
        if command == "up":
            self.volume_level = min(100, self.volume_level + 5)
        elif command == "down":
            self.volume_level = max(0, self.volume_level - 5)
        elif command == "set":
            self.volume_level = value or 0
        return self.volume_level

    def screenshot(self, dest: Path) -> Path:
        self._record("screenshot", str(dest))
        from PIL import Image

        dest.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (1920, 1080)).save(dest)
        return dest

    def clipboard_read(self) -> str:
        self._record("clipboard_read")
        return self.clipboard

    def clipboard_write(self, text: str) -> None:
        self._record("clipboard_write")
        self.clipboard = text

    def type_text(self, text: str) -> None:
        self._record("type_text", text)

    def press_key(self, key: str) -> None:
        self._record("press_key", key)

    def scroll(self, direction: str, amount: int = 5) -> None:
        self._record("scroll", direction)

    def click_at(self, x: int, y: int) -> None:
        self._record("click_at", x, y)
