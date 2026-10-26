"""Platform adapter interface + behaviour shared by every OS.

Adapters are the only code that spawns processes or sends input events. They
use argv lists (never `shell=True`) and raise `ActionError` with a typed code
when something is unavailable.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
import webbrowser
from abc import ABC, abstractmethod
from pathlib import Path

import psutil

from jarvis.actions.base import ActionError
from jarvis.platform.apps import AppEntry

MEDIA_COMMANDS = ("play_pause", "play", "pause", "next", "previous")
ALLOWED_KEYS = ("enter", "tab", "escape", "space", "backspace", "up", "down", "left", "right", "pageup", "pagedown")


def run_quiet(argv: list[str], timeout: float = 5.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)


class PlatformAdapter(ABC):
    os_key: str = "generic"

    # ---- files / urls -------------------------------------------------
    @abstractmethod
    def open_path(self, path: Path) -> None: ...

    def open_url(self, url: str, browser: AppEntry | None = None) -> None:
        if browser is not None:
            self.launch_app(browser, extra_args=[url])
            return
        if not webbrowser.open(url, new=2):
            raise ActionError("BROWSER_UNAVAILABLE", "I couldn't open a web browser.")

    # ---- applications -------------------------------------------------
    @abstractmethod
    def launch_app(self, app: AppEntry, extra_args: list[str] | None = None) -> None: ...

    def close_app(self, app: AppEntry, dry_run: bool = False) -> int:
        names = {n.lower() for n in app.processes_for(self.os_key)}
        if not names:
            raise ActionError("CLOSE_NOT_SUPPORTED", f"I'm not allowed to close {app.display_name} on this system.")
        try:
            me = psutil.Process().username()
        except psutil.Error:
            me = None
        procs = []
        for proc in psutil.process_iter(["name", "username"]):
            try:
                if (proc.info["name"] or "").lower() in names and (me is None or proc.info["username"] == me):
                    procs.append(proc)
            except psutil.Error:
                continue
        if dry_run or not procs:
            return len(procs)
        for proc in procs:
            try:
                proc.terminate()
            except psutil.Error:
                pass
        _, alive = psutil.wait_procs(procs, timeout=3)
        return len(procs) - len(alive)

    # ---- media / volume -----------------------------------------------
    @abstractmethod
    def media(self, command: str) -> str: ...

    @abstractmethod
    def volume(self, command: str, value: int | None = None) -> int | None:
        """command: up | down | mute | unmute | set. Returns the new level (0-100) when known."""

    # ---- screen / clipboard -------------------------------------------
    def screenshot(self, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            from PIL import ImageGrab

            ImageGrab.grab().save(dest)
            return dest
        except Exception as exc:  # noqa: BLE001 - fall through to OS tools
            last = exc
        for argv in self._screenshot_fallbacks(dest):
            if shutil.which(argv[0]):
                result = run_quiet(argv, timeout=15)
                if result.returncode == 0 and dest.exists():
                    return dest
        raise ActionError("SCREENSHOT_UNAVAILABLE", f"I couldn't capture the screen ({last}).")

    def _screenshot_fallbacks(self, dest: Path) -> list[list[str]]:
        return []

    def clipboard_read(self) -> str:
        try:
            import pyperclip

            return pyperclip.paste()
        except Exception as exc:  # noqa: BLE001
            raise ActionError("CLIPBOARD_UNAVAILABLE", f"I can't access the clipboard: {exc}") from exc

    def clipboard_write(self, text: str) -> None:
        try:
            import pyperclip

            pyperclip.copy(text)
        except Exception as exc:  # noqa: BLE001
            raise ActionError("CLIPBOARD_UNAVAILABLE", f"I can't access the clipboard: {exc}") from exc

    # ---- input automation (optional, pyautogui) ------------------------
    def _pyautogui(self):
        if os.environ.get("XDG_SESSION_TYPE") == "wayland" and self.os_key == "linux":
            raise ActionError(
                "AUTOMATION_UNAVAILABLE",
                "Keyboard and mouse control isn't available on a Wayland session. Log in with an X11 session to use it.",
            )
        try:
            import pyautogui
        except Exception as exc:  # noqa: BLE001 - ImportError or display errors
            raise ActionError("AUTOMATION_UNAVAILABLE", f"Keyboard and mouse control isn't available: {exc}") from exc
        pyautogui.FAILSAFE = True
        return pyautogui

    def type_text(self, text: str) -> None:
        self._pyautogui().write(text, interval=0.02)

    def press_key(self, key: str) -> None:
        if key not in ALLOWED_KEYS:
            raise ActionError("INVALID_PARAMS", f"I'm not allowed to press '{key}'.")
        self._pyautogui().press(key)

    def scroll(self, direction: str, amount: int = 5) -> None:
        clicks = amount * 100 if direction == "up" else -amount * 100
        self._pyautogui().scroll(clicks)

    def click_at(self, x: int, y: int) -> None:
        self._pyautogui().click(x, y)

    def screen_capture_for_ocr(self):
        return self._pyautogui().screenshot()


def which_first(candidates: list[list[str]]) -> list[str] | None:
    for argv in candidates:
        if argv and shutil.which(argv[0]):
            return [shutil.which(argv[0]) or argv[0], *argv[1:]]
    return None


def timestamped_name(prefix: str, ext: str) -> str:
    return f"{prefix}-{time.strftime('%Y%m%d-%H%M%S')}{ext}"
