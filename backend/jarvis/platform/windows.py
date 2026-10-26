"""Windows adapter: ShellExecute for files/apps, virtual media keys for media/volume.

Uses only the standard library (ctypes) for media and volume keys, so no extra
Windows-only packages are required.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from jarvis.actions.base import ActionError
from jarvis.platform.apps import AppEntry
from jarvis.platform.base import PlatformAdapter

VK = {
    "play_pause": 0xB3,
    "next": 0xB0,
    "previous": 0xB1,
    "mute": 0xAD,
    "down": 0xAE,
    "up": 0xAF,
}
KEYEVENTF_KEYUP = 0x0002


def _tap(vk: int, times: int = 1) -> None:
    import ctypes

    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    for _ in range(times):
        user32.keybd_event(vk, 0, 0, 0)
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


def _quote_args(args: list[str]) -> str:
    return subprocess.list2cmdline(args)


class WindowsAdapter(PlatformAdapter):
    os_key = "windows"

    def open_path(self, path: Path) -> None:
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
        except OSError as exc:
            raise ActionError("OPEN_FAILED", f"Windows couldn't open {path.name}: {exc.strerror or exc}") from exc

    def launch_app(self, app: AppEntry, extra_args: list[str] | None = None) -> None:
        extra = list(extra_args or [])
        errors = []
        for spec in app.windows:
            try:
                if "start" in spec:
                    target = spec["start"]
                    # "wt" and other App Execution Aliases must exist on PATH.
                    if not target.endswith(":") and target in ("wt",) and not shutil.which(target):
                        continue
                    if extra:
                        os.startfile(target, arguments=_quote_args(extra))  # type: ignore[attr-defined]
                    else:
                        os.startfile(target)  # type: ignore[attr-defined]
                    return
                argv = list(spec["argv"])
                resolved = shutil.which(argv[0])
                if not resolved:
                    continue
                flags = subprocess.CREATE_NEW_CONSOLE if spec.get("new_console") else 0  # type: ignore[attr-defined]
                subprocess.Popen([resolved, *argv[1:], *extra], creationflags=flags)  # noqa: S603
                return
            except OSError as exc:
                errors.append(str(exc))
        detail = f" ({errors[-1]})" if errors else ""
        raise ActionError("APP_NOT_INSTALLED", f"{app.display_name} doesn't seem to be installed{detail}.")

    def media(self, command: str) -> str:
        # Windows has no separate play/pause keys; the toggle covers both.
        key = "play_pause" if command in ("play", "pause", "play_pause") else command
        _tap(VK[key])
        return "media-keys"

    def volume(self, command: str, value: int | None = None) -> int | None:
        if command in ("up", "down"):
            _tap(VK[command], times=3)  # each key press is ~2%
            return None
        if command in ("mute", "unmute"):
            # The mute key toggles; Windows offers no stdlib way to read state.
            _tap(VK["mute"])
            return None
        if command == "set":
            _tap(VK["down"], times=50)
            _tap(VK["up"], times=round((value or 0) / 2))
            return value
        raise ActionError("INVALID_PARAMS", f"Unknown volume command {command}.")
