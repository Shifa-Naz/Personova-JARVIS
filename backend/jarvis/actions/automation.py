"""Keyboard/mouse automation (ported from the original command_handler/vision).

These act on whatever window has focus, so typing, key presses and clicks are
SENSITIVE and always confirmed. Requires pyautogui (and pytesseract for OCR
clicks); unavailable on Linux Wayland sessions.
"""

from __future__ import annotations

import os
import shutil
import sys

from pydantic import Field

from jarvis.actions.base import ActionError, ActionResult, ActionSpec, Params, PermissionLevel, Prepared
from jarvis.platform.base import ALLOWED_KEYS


class TypeParams(Params):
    text: str = Field(min_length=1, max_length=500)


def prepare_type(params: TypeParams, ctx) -> Prepared:
    return Prepared(summary=f'This will type "{params.text[:60]}" into the window that currently has focus.')


def type_text(params: TypeParams, ctx, prepared) -> ActionResult:
    ctx.platform.type_text(params.text)
    return ActionResult(True, "Typed it.")


class KeyParams(Params):
    key: str = Field(pattern=f"^({'|'.join(ALLOWED_KEYS)})$")


def prepare_key(params: KeyParams, ctx) -> Prepared:
    return Prepared(summary=f"This will press {params.key} in the window that currently has focus.")


def press_key(params: KeyParams, ctx, prepared) -> ActionResult:
    ctx.platform.press_key(params.key)
    return ActionResult(True, f"Pressed {params.key}.")


class ScrollParams(Params):
    direction: str = Field(pattern="^(up|down)$")


def scroll(params: ScrollParams, ctx, prepared) -> ActionResult:
    ctx.platform.scroll(params.direction)
    return ActionResult(True, f"Scrolled {params.direction}.")


class ClickParams(Params):
    text: str = Field(min_length=2, max_length=80, description="Visible on-screen text to click")


def _ocr_positions(ctx) -> list[dict]:
    try:
        import pytesseract
    except ImportError as exc:
        raise ActionError("OCR_UNAVAILABLE", "Clicking on text needs pytesseract and Tesseract installed.") from exc
    cmd = ctx.settings.tesseract_cmd
    if not cmd and sys.platform == "win32":
        default = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        cmd = default if os.path.exists(default) else None
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd
    elif not shutil.which("tesseract"):
        raise ActionError("OCR_UNAVAILABLE", "The Tesseract OCR program isn't installed.")
    image = ctx.platform.screen_capture_for_ocr()
    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    words = []
    for i, txt in enumerate(data["text"]):
        if txt.strip():
            words.append(
                {
                    "text": txt.lower(),
                    "x": data["left"][i] + data["width"][i] // 2,
                    "y": data["top"][i] + data["height"][i] // 2,
                }
            )
    return words


def prepare_click(params: ClickParams, ctx) -> Prepared:
    target = params.text.lower()
    words = _ocr_positions(ctx)
    matches = [w for w in words if w["text"] == target] or [w for w in words if target in w["text"]]
    if not matches:
        raise ActionError("TEXT_NOT_ON_SCREEN", f"I can't see '{params.text}' on the screen.")
    if len(matches) > 1:
        raise ActionError(
            "AMBIGUOUS", f"'{params.text}' appears {len(matches)} times on screen; please be more specific."
        )
    m = matches[0]
    return Prepared(summary=f"This will click '{params.text}' on the screen.", data={"x": m["x"], "y": m["y"]})


def click_text(params: ClickParams, ctx, prepared: Prepared | None) -> ActionResult:
    if prepared is None:
        raise ActionError("NOT_CONFIRMED", "Clicking needs a confirmed target.")
    ctx.platform.click_at(prepared.data["x"], prepared.data["y"])
    return ActionResult(True, f"Clicked {params.text}.")


SPECS = [
    ActionSpec(
        "type_text",
        "Type text into the focused window.",
        TypeParams,
        PermissionLevel.SENSITIVE,
        type_text,
        prepare=prepare_type,
        sensitive_params=("text",),
    ),
    ActionSpec(
        "press_key",
        "Press one key (enter, tab, escape, space, arrows...) in the focused window.",
        KeyParams,
        PermissionLevel.SENSITIVE,
        press_key,
        prepare=prepare_key,
    ),
    ActionSpec("scroll", "Scroll the focused window up or down.", ScrollParams, PermissionLevel.SAFE, scroll),
    ActionSpec(
        "click_text",
        "Click visible on-screen text found by OCR.",
        ClickParams,
        PermissionLevel.SENSITIVE,
        click_text,
        prepare=prepare_click,
        timeout_s=30,
    ),
]
