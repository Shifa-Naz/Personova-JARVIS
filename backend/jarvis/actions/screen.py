"""Screen understanding: capture → OCR → (offline LLM) → spoken description.

Privacy: the screenshot is written to a private temp file and always deleted after OCR;
it is never kept, logged, or sent anywhere except the local language model. Token-like
strings are masked before anything is spoken or shown.
"""

from __future__ import annotations

import base64
import io
import logging
import secrets
from pathlib import Path

from pydantic import Field

from jarvis.actions.base import ActionError, ActionResult, ActionSpec, Params, PermissionLevel
from jarvis.ai.provider import AiUnavailable
from jarvis.vision.ocr import layout_text, mask_secrets, reading_order

log = logging.getLogger(__name__)

READ_ALOUD_WORDS = 90
FALLBACK_WORDS = 45


class ScreenParams(Params):
    mode: str = Field(default="describe", pattern="^(describe|read|ask)$")
    question: str | None = Field(default=None, max_length=300)


def _excerpt(lines: list[str], max_words: int) -> str:
    """Speakable excerpt: skips OCR noise, stops at a word budget."""
    words: list[str] = []
    parts: list[str] = []
    for line in lines:
        if len(line) < 3 or not any(c.isalpha() for c in line):
            continue
        tokens = line.split()
        if len(words) + len(tokens) > max_words:
            remaining = max_words - len(words)
            if remaining > 3:
                parts.append(" ".join(tokens[:remaining]) + "…")
            break
        words += tokens
        parts.append(line.rstrip(".:;,"))
    return ". ".join(parts) + ("." if parts and not parts[-1].endswith("…") else "")


# Sending the screenshot to a vision model is very slow on CPU (measured with qwen2.5vl:3b on an i5-1240P:
# OCR text only 7.5 s, +672 px image 48 s, +1280 px image 255 s). So the image is only sent when OCR finds
# almost no text (photos, video, diagrams), and at a small size.
IMAGE_ONLY_BELOW_LINES = 4
VISION_IMAGE_SIDE = 448


def _thumbnail_b64(path: Path, max_side: int = VISION_IMAGE_SIDE) -> str:
    from PIL import Image

    with Image.open(path) as img:
        img = img.convert("RGB")
        img.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode()


def describe_screen(params: ScreenParams, ctx, prepared) -> ActionResult:
    if ctx.ocr is None or not ctx.ocr.available():
        raise ActionError("OCR_UNAVAILABLE", "Screen reading isn't installed. Run: pip install rapidocr_onnxruntime")

    tmp = ctx.settings.data_dir / "tmp" / f"screen-{secrets.token_hex(6)}.png"
    image_b64 = None
    try:
        ctx.platform.screenshot(tmp)
        lines, (_width, height) = ctx.ocr.read(tmp)
        if params.mode != "read" and len(lines) < IMAGE_ONLY_BELOW_LINES and ctx.ai.vision_available():
            image_b64 = _thumbnail_b64(tmp)
    finally:
        tmp.unlink(missing_ok=True)

    if not lines and image_b64 is None:
        return ActionResult(True, "I can see your screen, but there's no readable text on it.", data={"lines": 0})

    ordered = [mask_secrets(line.text) for line in reading_order(lines)]
    data = {"lines": len(lines), "text": "\n".join(ordered)[:4000], "engine": ctx.ocr.engine_name()}

    if params.mode == "read":
        return ActionResult(True, f"Your screen says: {_excerpt(ordered, READ_ALOUD_WORDS)}", data=data)

    request = params.question if params.mode == "ask" else None
    try:
        # Questions get a larger budget so the answer is more likely to be included.
        screen_text = layout_text(lines, height, max_chars=1200 if request else 900, query=request)
        message = ctx.ai.describe_screen(screen_text, request, ctx.session.history_list(), image_b64)
        data["source"] = "vision" if image_b64 else "llm"
    except AiUnavailable as exc:
        log.info("Screen description without LLM: %s", exc)
        data["source"] = "ocr"
        data["detail"] = str(exc)
        message = (
            "My language model isn't available, so here's the main text on your screen: "
            f"{_excerpt(ordered, FALLBACK_WORDS)}"
        )
    return ActionResult(True, message, data=data)


SPECS = [
    ActionSpec(
        "describe_screen",
        "Look at the user's screen (screenshot + OCR) and describe it, read its text aloud, or answer a question "
        "about it. mode: describe | read | ask (with question).",
        ScreenParams,
        PermissionLevel.READ_ONLY,
        describe_screen,
        timeout_s=150,
        examples=("what's on my screen", "read my screen", "what does the error on my screen say"),
    ),
]
