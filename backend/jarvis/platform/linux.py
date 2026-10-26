"""Linux adapter: xdg-open, MPRIS (playerctl or gdbus), PipeWire/PulseAudio volume."""

from __future__ import annotations

import logging
import os
import re
import secrets
import shutil
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlparse

from jarvis.actions.base import ActionError
from jarvis.platform.apps import AppEntry
from jarvis.platform.base import PlatformAdapter, run_quiet

_MPRIS_METHODS = {"play_pause": "PlayPause", "play": "Play", "pause": "Pause", "next": "Next", "previous": "Previous"}
_FLATPAK_DIRS = (Path("/var/lib/flatpak/app"), Path.home() / ".local/share/flatpak/app")
log = logging.getLogger(__name__)


def portal_screenshot(dest: Path, timeout_s: float = 30.0) -> Path:
    """Capture the screen through xdg-desktop-portal (the supported way on Wayland).

    Non-interactive; the desktop may ask the user for permission the first time.
    The portal writes the image itself (usually into ~/Pictures); it is moved to `dest`.
    """
    try:
        from jeepney import DBusAddress, MatchRule, new_method_call
        from jeepney.bus_messages import message_bus
        from jeepney.io.blocking import open_dbus_connection
    except ImportError as exc:
        raise ActionError(
            "SCREENSHOT_UNAVAILABLE", "Screen capture on Wayland needs jeepney (pip install jeepney)."
        ) from exc

    token = "jarvis" + secrets.token_hex(6)
    try:
        conn = open_dbus_connection(bus="SESSION")
    except Exception as exc:  # noqa: BLE001 - no session bus (e.g. headless)
        raise ActionError("SCREENSHOT_UNAVAILABLE", "I can't reach the desktop session to capture the screen.") from exc
    try:
        sender = conn.unique_name[1:].replace(".", "_")
        request_path = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"
        rule = MatchRule(
            type="signal", interface="org.freedesktop.portal.Request", member="Response", path=request_path
        )
        conn.send_and_get_reply(message_bus.AddMatch(rule), timeout=5)
        portal = DBusAddress(
            "/org/freedesktop/portal/desktop",
            bus_name="org.freedesktop.portal.Desktop",
            interface="org.freedesktop.portal.Screenshot",
        )
        call = new_method_call(
            portal, "Screenshot", "sa{sv}", ("", {"handle_token": ("s", token), "interactive": ("b", False)})
        )
        with conn.filter(rule) as queue:
            conn.send_and_get_reply(call, timeout=10)
            signal = conn.recv_until_filtered(queue, timeout=timeout_s)
        code, results = signal.body
    except TimeoutError as exc:
        raise ActionError("SCREENSHOT_TIMEOUT", "The screen capture permission wasn't answered in time.") from exc
    except Exception as exc:  # noqa: BLE001 - D-Bus errors become a typed failure
        log.warning("Portal screenshot failed: %s", exc)
        raise ActionError("SCREENSHOT_UNAVAILABLE", "The desktop refused the screen capture.") from exc
    finally:
        conn.close()

    if code != 0:
        raise ActionError("SCREENSHOT_DENIED", "Screen capture was cancelled or not permitted.")
    src = Path(unquote(urlparse(results["uri"][1]).path))
    if not src.is_file():
        raise ActionError("SCREENSHOT_UNAVAILABLE", "The desktop didn't return a screenshot file.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dest))
    return dest


def _spawn(argv: list[str]) -> None:
    try:
        subprocess.Popen(  # noqa: S603 - argv list from the allow-listed registry
            argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True
        )
    except OSError as exc:
        raise ActionError("APP_LAUNCH_FAILED", f"Launching {argv[0]} failed: {exc.strerror or exc}") from exc


class LinuxAdapter(PlatformAdapter):
    os_key = "linux"

    def open_path(self, path: Path) -> None:
        if not shutil.which("xdg-open"):
            raise ActionError("OPEN_UNAVAILABLE", "xdg-open is not installed, so I can't open files.")
        _spawn(["xdg-open", str(path)])

    def resolve_launch(self, app: AppEntry) -> list[str] | None:
        for spec in app.linux:
            if isinstance(spec, dict) and "flatpak" in spec:
                app_id = spec["flatpak"]
                if shutil.which("flatpak") and any((d / app_id).exists() for d in _FLATPAK_DIRS):
                    return ["flatpak", "run", app_id]
            elif isinstance(spec, list | tuple) and spec and shutil.which(spec[0]):
                return [shutil.which(spec[0]) or spec[0], *spec[1:]]
        return None

    def launch_app(self, app: AppEntry, extra_args: list[str] | None = None) -> None:
        argv = self.resolve_launch(app)
        if argv is None:
            raise ActionError("APP_NOT_INSTALLED", f"{app.display_name} doesn't seem to be installed.")
        _spawn(argv + list(extra_args or []))

    # ---- media ---------------------------------------------------------
    def media(self, command: str) -> str:
        if shutil.which("playerctl"):
            arg = {"play_pause": "play-pause"}.get(command, command)
            target = ["--all-players"] if command == "pause" else []
            result = run_quiet(["playerctl", *target, arg])
            if result.returncode == 0:
                return "playerctl"
            if "No players found" in (result.stderr or ""):
                raise ActionError("NO_MEDIA_PLAYER", "There's no media player running right now.")
        return self._media_gdbus(command)

    def _mpris_players(self) -> list[str]:
        if not shutil.which("gdbus"):
            raise ActionError("MEDIA_UNAVAILABLE", "I need playerctl or gdbus to control media on Linux.")
        result = run_quiet(
            [
                "gdbus",
                "call",
                "--session",
                "--dest",
                "org.freedesktop.DBus",
                "--object-path",
                "/org/freedesktop/DBus",
                "--method",
                "org.freedesktop.DBus.ListNames",
            ]
        )
        return re.findall(r"'(org\.mpris\.MediaPlayer2\.[^']+)'", result.stdout or "")

    def _player_status(self, player: str) -> str:
        result = run_quiet(
            [
                "gdbus",
                "call",
                "--session",
                "--dest",
                player,
                "--object-path",
                "/org/mpris/MediaPlayer2",
                "--method",
                "org.freedesktop.DBus.Properties.Get",
                "org.mpris.MediaPlayer2.Player",
                "PlaybackStatus",
            ]
        )
        match = re.search(r"'(Playing|Paused|Stopped)'", result.stdout or "")
        return match.group(1) if match else "Unknown"

    def _media_gdbus(self, command: str) -> str:
        players = self._mpris_players()
        if not players:
            raise ActionError("NO_MEDIA_PLAYER", "There's no media player running right now.")
        playing = [p for p in players if self._player_status(p) == "Playing"]
        if command == "pause":
            targets = playing or players
        else:
            targets = [(playing or players)[0]]
        method = f"org.mpris.MediaPlayer2.Player.{_MPRIS_METHODS[command]}"
        for player in targets:
            run_quiet(
                [
                    "gdbus",
                    "call",
                    "--session",
                    "--dest",
                    player,
                    "--object-path",
                    "/org/mpris/MediaPlayer2",
                    "--method",
                    method,
                ]
            )
        return "mpris"

    # ---- volume --------------------------------------------------------
    def volume(self, command: str, value: int | None = None) -> int | None:
        if shutil.which("wpctl"):
            sink = "@DEFAULT_AUDIO_SINK@"
            argv = {
                "up": ["wpctl", "set-volume", "-l", "1.0", sink, "5%+"],
                "down": ["wpctl", "set-volume", sink, "5%-"],
                "mute": ["wpctl", "set-mute", sink, "1"],
                "unmute": ["wpctl", "set-mute", sink, "0"],
                "set": ["wpctl", "set-volume", "-l", "1.0", sink, f"{(value or 0) / 100:.2f}"],
            }[command]
            if command in ("up", "down", "set"):
                run_quiet(["wpctl", "set-mute", sink, "0"])
            if run_quiet(argv).returncode != 0:
                raise ActionError("VOLUME_FAILED", "Changing the volume failed.")
            out = run_quiet(["wpctl", "get-volume", sink]).stdout or ""
            match = re.search(r"Volume:\s*([\d.]+)", out)
            return round(float(match.group(1)) * 100) if match else None
        if shutil.which("pactl"):
            sink = "@DEFAULT_SINK@"
            argv = {
                "up": ["pactl", "set-sink-volume", sink, "+5%"],
                "down": ["pactl", "set-sink-volume", sink, "-5%"],
                "mute": ["pactl", "set-sink-mute", sink, "1"],
                "unmute": ["pactl", "set-sink-mute", sink, "0"],
                "set": ["pactl", "set-sink-volume", sink, f"{value or 0}%"],
            }[command]
            if run_quiet(argv).returncode != 0:
                raise ActionError("VOLUME_FAILED", "Changing the volume failed.")
            match = re.search(r"(\d+)%", run_quiet(["pactl", "get-sink-volume", sink]).stdout or "")
            return int(match.group(1)) if match else None
        raise ActionError("VOLUME_UNAVAILABLE", "I need wpctl or pactl to control the volume.")

    def screenshot(self, dest: Path) -> Path:
        if os.environ.get("XDG_SESSION_TYPE") == "wayland" or os.environ.get("WAYLAND_DISPLAY"):
            try:
                return portal_screenshot(dest)
            except ActionError as exc:
                if exc.code in ("SCREENSHOT_DENIED", "SCREENSHOT_TIMEOUT"):
                    raise
                log.info("Portal capture unavailable (%s); trying other tools", exc.message)
        return super().screenshot(dest)

    def _screenshot_fallbacks(self, dest: Path) -> list[list[str]]:
        return [
            ["gnome-screenshot", "-f", str(dest)],
            ["grim", str(dest)],
            ["spectacle", "-b", "-n", "-o", str(dest)],
        ]
