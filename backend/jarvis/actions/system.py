"""System information, screenshots and clipboard."""

from __future__ import annotations

import platform as py_platform
import time
from datetime import datetime
from pathlib import Path

import psutil
from pydantic import Field

from jarvis.actions.base import ActionResult, ActionSpec, Params, PermissionLevel
from jarvis.platform.base import timestamped_name


def _gb(n: float) -> str:
    return f"{n / 1024**3:.1f} GB"


def telemetry(ctx) -> dict:
    """Snapshot used by both the system_information action and the HUD."""
    vm = psutil.virtual_memory()
    try:
        disk = psutil.disk_usage(str(Path.home()))
        disk_info = {"total": disk.total, "used": disk.used, "free": disk.free, "percent": disk.percent}
    except OSError:
        disk_info = None
    battery = None
    try:
        b = psutil.sensors_battery()
        if b is not None:
            battery = {
                "percent": round(b.percent),
                "plugged": bool(b.power_plugged),
                "secs_left": b.secsleft if isinstance(b.secsleft, int) and b.secsleft > 0 else None,
            }
    except (AttributeError, NotImplementedError, OSError):
        battery = None
    return {
        "cpu_percent": psutil.cpu_percent(interval=None),
        "cpu_count": psutil.cpu_count(),
        "memory": {"total": vm.total, "used": vm.total - vm.available, "percent": vm.percent},
        "disk": disk_info,
        "battery": battery,
        "online": ctx.connectivity.online(),
        "uptime_s": int(time.time() - psutil.boot_time()),
        "os": f"{py_platform.system()} {py_platform.release()}",
        "hostname": py_platform.node(),
    }


class InfoParams(Params):
    topic: str = Field(default="summary", pattern="^(summary|time|date|battery|cpu|memory|storage|network)$")


def system_information(params: InfoParams, ctx, prepared) -> ActionResult:
    now = datetime.now()
    if params.topic == "time":
        return ActionResult(True, f"It's {now.strftime('%I:%M %p').lstrip('0')}.")
    if params.topic == "date":
        return ActionResult(True, f"Today is {now.strftime('%A, %B')} {now.day}, {now.year}.")

    t = telemetry(ctx)
    if params.topic == "battery":
        b = t["battery"]
        if b is None:
            return ActionResult(True, "This computer doesn't report a battery.", data=t)
        state = "charging" if b["plugged"] else "on battery"
        return ActionResult(True, f"Battery is at {b['percent']} percent, {state}.", data=t)
    if params.topic == "cpu":
        return ActionResult(True, f"CPU usage is {t['cpu_percent']:.0f} percent across {t['cpu_count']} cores.", data=t)
    if params.topic == "memory":
        m = t["memory"]
        return ActionResult(
            True, f"Memory usage is {m['percent']:.0f} percent, {_gb(m['used'])} of {_gb(m['total'])}.", data=t
        )
    if params.topic == "storage":
        d = t["disk"]
        if d is None:
            return ActionResult.fail("INFO_UNAVAILABLE", "I couldn't read disk usage.")
        return ActionResult(True, f"You have {_gb(d['free'])} free of {_gb(d['total'])}.", data=t)
    if params.topic == "network":
        return ActionResult(True, "You're online." if t["online"] else "You're offline right now.", data=t)
    m = t["memory"]
    msg = (
        f"CPU at {t['cpu_percent']:.0f} percent, memory at {m['percent']:.0f} percent, "
        f"and you're {'online' if t['online'] else 'offline'}."
    )
    return ActionResult(True, msg, data=t)


def screenshot(params: Params, ctx, prepared) -> ActionResult:
    folder = ctx.files.resolve_known_folder("pictures") or Path.home()
    dest = ctx.platform.screenshot(folder / "Screenshots" / timestamped_name("jarvis", ".png"))
    return ActionResult(True, f"Screenshot saved to {dest.parent.name}.", data={"path": str(dest)})


def clipboard_read(params: Params, ctx, prepared) -> ActionResult:
    text = ctx.platform.clipboard_read()
    if not text:
        return ActionResult(True, "Your clipboard is empty.")
    preview = text if len(text) <= 300 else text[:300] + "…"
    return ActionResult(True, f"Your clipboard says: {preview}", data={"length": len(text)})


class ClipboardWriteParams(Params):
    text: str = Field(min_length=1, max_length=5000)


def clipboard_write(params: ClipboardWriteParams, ctx, prepared) -> ActionResult:
    ctx.platform.clipboard_write(params.text)
    return ActionResult(True, "Copied to the clipboard.")


class _NoParams(Params):
    pass


SPECS = [
    ActionSpec(
        "system_information",
        "Report time, date, battery, cpu, memory, storage, network, or a summary.",
        InfoParams,
        PermissionLevel.READ_ONLY,
        system_information,
        examples=("what time is it", "battery status"),
    ),
    ActionSpec(
        "screenshot",
        "Take a screenshot and save it to Pictures/Screenshots.",
        _NoParams,
        PermissionLevel.SAFE,
        screenshot,
        timeout_s=20,
    ),
    ActionSpec(
        "clipboard_read", "Read the clipboard text aloud.", _NoParams, PermissionLevel.READ_ONLY, clipboard_read
    ),
    ActionSpec(
        "clipboard_write",
        "Put text on the clipboard (replaces what is there).",
        ClipboardWriteParams,
        PermissionLevel.SENSITIVE,
        clipboard_write,
        sensitive_params=("text",),
    ),
]
