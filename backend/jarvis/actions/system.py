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


_IDLE_NAMES = {"system idle process", "idle", "kernel_task", "swapper/0"}


def top_processes(limit: int = 5, sample_s: float = 0.0) -> list[dict]:
    """Busiest apps by CPU then memory, grouped by name (Chrome's many processes count as one).

    psutil caches Process objects across calls, so CPU % is measured since the previous call. `sample_s` takes a
    short measurement first, for one-off questions where there was no previous call.
    """
    procs = list(psutil.process_iter(["name", "memory_info"]))
    if sample_s:
        for p in procs:
            try:
                p.cpu_percent(None)
            except psutil.Error:
                pass
        time.sleep(sample_s)  # the measurement window, not synchronisation
    cpus = psutil.cpu_count() or 1
    usage: dict[str, dict] = {}
    for p in procs:
        try:
            cpu = p.cpu_percent(None)
            name = p.info["name"] or ""
            mem = p.info["memory_info"].rss if p.info["memory_info"] else 0
        except psutil.Error:
            continue
        if not name or name.lower() in _IDLE_NAMES:
            continue
        label = name[:-4] if name.lower().endswith(".exe") else name
        u = usage.setdefault(label.lower(), {"name": label, "cpu_percent": 0.0, "memory": 0, "count": 0})
        u["cpu_percent"] += cpu / cpus
        u["memory"] += mem
        u["count"] += 1
    ranked = sorted(usage.values(), key=lambda u: (round(u["cpu_percent"], 1), u["memory"]), reverse=True)
    for u in ranked:
        u["cpu_percent"] = round(u["cpu_percent"], 1)
    return ranked[:limit]


def _uptime(seconds: int) -> str:
    hours, minutes = divmod(seconds // 60, 60)
    days, hours = divmod(hours, 24)
    if days:
        return f"{days} day{'s' if days != 1 else ''} {hours} hour{'s' if hours != 1 else ''}"
    if hours:
        return f"{hours} hour{'s' if hours != 1 else ''} {minutes} minutes"
    return f"{minutes} minutes"


class InfoParams(Params):
    topic: str = Field(
        default="summary", pattern="^(summary|time|date|battery|cpu|memory|storage|network|processes|uptime)$"
    )


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
    if params.topic == "uptime":
        return ActionResult(True, f"This computer has been on for {_uptime(t['uptime_s'])}.", data=t)
    if params.topic == "processes":
        top = top_processes(5, sample_s=0.5)
        if not top:
            return ActionResult(True, "I couldn't read the running apps.", data=t)
        rows = "\n".join(f"- **{p['name']}**: CPU {p['cpu_percent']:.0f}%, memory {_gb(p['memory'])}" for p in top)
        lead = top[0]
        spoken = f"{lead['name']} is the busiest, at {lead['cpu_percent']:.0f} percent CPU and {_gb(lead['memory'])} of memory."
        return ActionResult(
            True,
            f"**Busiest apps right now**\n{rows}",
            data={**t, "processes": top, "speech": spoken, "speech_exact": True},
        )
    m = t["memory"]
    parts = [
        f"CPU at {t['cpu_percent']:.0f} percent",
        f"memory at {m['percent']:.0f} percent ({_gb(m['used'])} of {_gb(m['total'])})",
    ]
    b = t["battery"]
    if b:
        parts.append(f"battery at {b['percent']} percent{' and charging' if b['plugged'] else ''}")
    if t["disk"]:
        parts.append(f"{_gb(t['disk']['free'])} free on disk")
    msg = (
        ", ".join(parts[:-1])
        + f", and {parts[-1]}. "
        + f"You're {'online' if t['online'] else 'offline'}, and the computer has been on for {_uptime(t['uptime_s'])}."
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
        "Report time, date, battery, cpu, memory, storage, network, uptime, the busiest apps (processes), or a "
        "summary of all of it.",
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
