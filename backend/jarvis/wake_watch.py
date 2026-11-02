"""Lid-open briefing: notice when the computer wakes up, wait until the screen is unlocked, then publish a briefing.

Sleep is detected by comparing the wall clock with the monotonic clock: on Linux the monotonic clock stops while
the machine sleeps, so the difference is the time asleep, and heavy CPU load can't trigger it. Where the monotonic
clock keeps running through sleep, a tick that arrives far too late is treated the same way. Screen unlocks after
a lock of at least `MIN_LOCK_S` also count, which covers Windows "modern standby" laptops that never fully sleep.

The frontend receives the briefing through `EventBus` (long-poll on /api/v1/events).
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from collections import deque
from collections.abc import Callable

log = logging.getLogger(__name__)

TICK_S = 2.0
SLEEP_GAP_S = 6.0  # this much unexplained time between ticks means the machine was asleep
MIN_LOCK_S = 20.0  # an unlock after a lock at least this long counts as "back at the computer"
SETTLE_S = 2.0  # after waking, look at the lock screen state once more before speaking
COOLDOWN_S = 15.0
NETWORK_WAIT_S = 20.0  # Wi-Fi usually reconnects within a few seconds of waking
RECENT_S = 90.0  # a page opened just after a wake-up still gets that briefing


class EventBus:
    """Numbered events with blocking waits (for long-polling)."""

    def __init__(self, keep: int = 20) -> None:
        self._events: deque[dict] = deque(maxlen=keep)
        self._seq = 0
        self._cond = threading.Condition()

    @property
    def seq(self) -> int:
        return self._seq

    def publish(self, event: dict) -> dict:
        with self._cond:
            self._seq += 1
            stored = {**event, "seq": self._seq, "ts": time.time()}
            self._events.append(stored)
            self._cond.notify_all()
        return stored

    def since(self, after: int) -> list[dict]:
        with self._cond:
            if after < 0:
                cutoff = time.time() - RECENT_S
                return [e for e in self._events if e["ts"] >= cutoff]
            return [e for e in self._events if e["seq"] > after]

    def wait(self, after: int, timeout: float) -> list[dict]:
        """Events after `after`, waiting up to `timeout` for one. `after < 0` returns recent events at once."""
        if after < 0:
            return self.since(after)
        deadline = time.monotonic() + timeout
        with self._cond:
            while True:
                found = self.since(after)
                remaining = deadline - time.monotonic()
                if found or remaining <= 0:
                    return found
                self._cond.wait(remaining)


# ---------------------------------------------------------------- lock-screen state
def windows_locked() -> bool | None:
    """True while the Windows lock screen (or another secure desktop) is showing."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    # Handles are pointer-sized: without these declarations ctypes truncates them on 64-bit Windows.
    user32.OpenInputDesktop.restype = wintypes.HANDLE
    user32.OpenInputDesktop.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    user32.CloseDesktop.argtypes = (wintypes.HANDLE,)
    desktop = user32.OpenInputDesktop(0, False, 0x0100)  # DESKTOP_SWITCHDESKTOP
    if not desktop:
        return True
    user32.CloseDesktop(desktop)
    return False


class GnomeLockState:
    """org.gnome.ScreenSaver.GetActive over the session bus (jeepney). None when unavailable."""

    def __init__(self) -> None:
        self._conn = None
        self._failed = False

    def __call__(self) -> bool | None:
        if self._failed:
            return None
        try:
            from jeepney import DBusAddress, new_method_call
            from jeepney.io.blocking import open_dbus_connection

            if self._conn is None:
                self._conn = open_dbus_connection(bus="SESSION")
            addr = DBusAddress(
                "/org/gnome/ScreenSaver", bus_name="org.gnome.ScreenSaver", interface="org.gnome.ScreenSaver"
            )
            reply = self._conn.send_and_get_reply(new_method_call(addr, "GetActive"), timeout=2)
            return bool(reply.body[0])
        except Exception as exc:  # noqa: BLE001 - no GNOME, no jeepney or no session bus
            log.info("Lock-screen state unavailable: %s", exc)
            self._failed = True
            if self._conn is not None:
                self._conn.close()
            return None


def default_lock_state() -> Callable[[], bool | None]:
    if sys.platform == "win32":
        return windows_locked
    if sys.platform.startswith("linux") and os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
        return GnomeLockState()
    return lambda: None


# ---------------------------------------------------------------- watcher
class WakeWatcher:
    def __init__(
        self,
        on_wake: Callable[[str], None],
        lock_state: Callable[[], bool | None] | None = None,
        wall: Callable[[], float] = time.time,
        mono: Callable[[], float] = time.monotonic,
    ) -> None:
        self.on_wake = on_wake
        self.lock_state = lock_state or default_lock_state()
        self.wall, self.mono = wall, mono
        self._stop = threading.Event()
        self._last_wall, self._last_mono = wall(), mono()
        self._pending: str | None = None
        self._pending_since = 0.0
        self._locked_since: float | None = None
        self._last_fired = -1e9

    def start(self) -> None:
        threading.Thread(target=self._loop, name="jarvis-wake-watch", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.wait(TICK_S):
            try:
                self.tick()
            except Exception:  # noqa: BLE001 - keep watching
                log.exception("Wake watcher tick failed")

    def tick(self) -> None:
        wall, mono = self.wall(), self.mono()
        d_wall, d_mono = wall - self._last_wall, mono - self._last_mono
        self._last_wall, self._last_mono = wall, mono
        if d_wall - d_mono > SLEEP_GAP_S or d_mono > TICK_S + SLEEP_GAP_S:
            log.info("Computer woke up after about %.0f s", max(d_wall, d_mono))
            self._mark("wake", wall)

        try:
            locked = self.lock_state()
        except Exception:  # noqa: BLE001
            locked = None
        if locked:
            if self._locked_since is None:
                self._locked_since = wall
        elif self._locked_since is not None:
            if wall - self._locked_since >= MIN_LOCK_S:
                self._mark(self._pending or "unlock", wall)
            self._locked_since = None

        if (
            self._pending
            and not locked
            and wall - self._pending_since >= SETTLE_S
            and wall - self._last_fired >= COOLDOWN_S
        ):
            reason, self._pending = self._pending, None
            self._last_fired = wall
            self.on_wake(reason)

    def _mark(self, reason: str, wall: float) -> None:
        if not self._pending:
            self._pending_since = wall
        self._pending = self._pending or reason


def make_briefing_publisher(services) -> Callable[[str], None]:
    """on_wake handler: wait briefly for the network, build the briefing, publish it."""
    from datetime import datetime

    from jarvis.actions.system import telemetry
    from jarvis.briefing import build_briefing
    from jarvis.core.context import ExecContext

    def publish(reason: str) -> None:
        def work() -> None:
            conn = services.connectivity
            deadline = time.monotonic() + NETWORK_WAIT_S
            conn.invalidate()
            while not conn.online() and time.monotonic() < deadline:
                conn.invalidate()
                time.sleep(1.0)  # polling an OS condition with a deadline (allowed by CLAUDE.md rule 15)
            ctx = ExecContext(
                services.settings,
                services.platform,
                services.pipeline.apps,
                services.files,
                services.ai,
                conn,
                services.pipeline.sessions.get("default"),
            )
            b = build_briefing(services.store, services.news, telemetry(ctx), conn.online(), datetime.now())
            services.events.publish({"type": "briefing", "reason": reason, **b})
            log.info("Published the %s briefing", reason)

        threading.Thread(target=work, name="jarvis-briefing", daemon=True).start()

    return publish
