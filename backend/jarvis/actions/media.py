"""Media playback (local first, YouTube on request) and transport/volume control."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, model_validator

from jarvis.actions.base import ActionResult, ActionSpec, Offer, Params, PermissionLevel, PlanStep
from jarvis.files.search import KNOWN_FOLDERS


class PlayParams(Params):
    query: str = Field(default="", max_length=200, description="Song/video title; empty plays the latest local music")
    kind: str = Field(default="media", pattern="^(audio|video|media)$")
    folder: str | None = Field(default=None, pattern=f"^({'|'.join(KNOWN_FOLDERS)})$")
    online_fallback: bool = True

    @model_validator(mode="after")
    def query_or_filter(self):
        if self.query and len(self.query.strip()) < 2:
            raise ValueError("the title is too short")
        return self


def play_media(params: PlayParams, ctx, prepared) -> ActionResult:
    within = ctx.files.resolve_known_folder(params.folder) if params.folder else None
    kind = params.kind if params.query else ("audio" if params.kind == "media" else params.kind)
    results = ctx.files.search(
        params.query, kind=kind, within=within, sort="relevance" if params.query else "latest", limit=5
    )
    if results:
        best = results[0]
        ctx.platform.open_path(Path(best.path))
        ctx.session.last_media_path = best.path
        ctx.session.last_media_query = params.query or best.name
        return ActionResult(True, f"Playing {Path(best.name).stem}.", data={"path": best.path})

    what = params.query or "any music"
    offer = None
    if params.query and params.online_fallback:
        offer = Offer("Shall I search online?", [PlanStep(action="play_youtube", params={"query": params.query})])
    place = f"in {params.folder}" if params.folder else "locally"
    return ActionResult.fail("FILE_NOT_FOUND", f"I couldn't find {what} {place}.", offer=offer)


class MediaParams(Params):
    command: str = Field(pattern="^(play_pause|play|pause|next|previous)$")


_MEDIA_MESSAGES = {
    "play_pause": "Toggled playback.",
    "play": "Resuming.",
    "pause": "Paused.",
    "next": "Next track.",
    "previous": "Previous track.",
}


def media_control(params: MediaParams, ctx, prepared) -> ActionResult:
    ctx.platform.media(params.command)
    return ActionResult(True, _MEDIA_MESSAGES[params.command])


class VolumeParams(Params):
    command: str = Field(pattern="^(up|down|mute|unmute|set)$")
    value: int | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def set_needs_value(self):
        if self.command == "set" and self.value is None:
            raise ValueError("'set' needs a value between 0 and 100")
        return self


def volume_control(params: VolumeParams, ctx, prepared) -> ActionResult:
    level = ctx.platform.volume(params.command, params.value)
    if params.command == "mute":
        return ActionResult(True, "Muted.", data={"level": level})
    if params.command == "unmute":
        return ActionResult(True, "Sound is back on.", data={"level": level})
    suffix = f" Volume is now {level} percent." if level is not None else ""
    verb = {"up": "Turned it up.", "down": "Turned it down.", "set": "Volume set."}[params.command]
    return ActionResult(True, verb + suffix, data={"level": level})


SPECS = [
    ActionSpec(
        "play_media",
        "Play a local song or video by title (searches this computer first).",
        PlayParams,
        PermissionLevel.SAFE,
        play_media,
        timeout_s=30,
        examples=("play believer", "play my music"),
    ),
    ActionSpec(
        "media_control",
        "Control the active media player: play_pause, play, pause, next, previous.",
        MediaParams,
        PermissionLevel.SAFE,
        media_control,
        examples=("pause", "next song"),
    ),
    ActionSpec(
        "volume_control",
        "Change system volume: up, down, mute, unmute, or set to a value 0-100.",
        VolumeParams,
        PermissionLevel.SAFE,
        volume_control,
        examples=("volume up", "set volume to 40"),
    ),
]
