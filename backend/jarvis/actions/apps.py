"""Application launch/close — only for apps in the AppRegistry."""

from __future__ import annotations

import time

from pydantic import Field

from jarvis.actions.base import ActionError, ActionResult, ActionSpec, Params, PermissionLevel, Prepared


class AppParams(Params):
    app: str = Field(
        min_length=1, max_length=60, description="Application name, e.g. chrome, firefox, vs code, terminal"
    )


def _resolve(ctx, spoken: str):
    app = ctx.apps.resolve(spoken)
    if app is None:
        known = ", ".join(a.display_name for a in ctx.apps.all())
        raise ActionError("APP_NOT_REGISTERED", f"{spoken} isn't in my application list. I can open: {known}.")
    return app


LAUNCH_VERIFY_S = 5.0


def _wait_until_running(ctx, app) -> bool | None:
    """Poll the process list until the app appears. None = this app can't be verified on this OS."""
    if not app.processes_for(ctx.platform.os_key):
        return None
    deadline = time.monotonic() + LAUNCH_VERIFY_S
    while True:
        try:
            if ctx.platform.close_app(app, dry_run=True) > 0:
                return True
        except ActionError:
            return None
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.25)


def open_application(params: AppParams, ctx, prepared) -> ActionResult:
    app = _resolve(ctx, params.app)
    ctx.platform.launch_app(app)
    ctx.session.last_app = app.name
    running = _wait_until_running(ctx, app)
    if running is False:
        return ActionResult.fail(
            "APP_NOT_CONFIRMED",
            f"I asked {app.display_name} to start, but it isn't running. It may have failed to open.",
        )
    msg = f"{app.display_name} is open." if running else f"Opening {app.display_name}."
    return ActionResult(True, msg, data={"app": app.name, "verified": bool(running)})


def prepare_close(params: AppParams, ctx) -> Prepared:
    app = _resolve(ctx, params.app)
    count = ctx.platform.close_app(app, dry_run=True)
    if count == 0:
        raise ActionError("APP_NOT_RUNNING", f"{app.display_name} isn't running.")
    noun = "process" if count == 1 else "processes"
    return Prepared(
        summary=f"This will close {app.display_name} ({count} {noun}). Any unsaved work in it may be lost.",
        data={"app": app.name},
    )


def close_application(params: AppParams, ctx, prepared: Prepared | None) -> ActionResult:
    app = _resolve(ctx, params.app)
    closed = ctx.platform.close_app(app)
    if closed == 0:
        return ActionResult.fail("APP_NOT_RUNNING", f"{app.display_name} isn't running.")
    return ActionResult(True, f"Closed {app.display_name}.", data={"app": app.name, "closed": closed})


SPECS = [
    ActionSpec(
        "open_application",
        "Launch an installed, allow-listed application.",
        AppParams,
        PermissionLevel.SAFE,
        open_application,
        examples=("open chrome", "launch calculator"),
    ),
    ActionSpec(
        "close_application",
        "Close a running allow-listed application.",
        AppParams,
        PermissionLevel.SENSITIVE,
        close_application,
        prepare=prepare_close,
        examples=("close chrome",),
    ),
]
