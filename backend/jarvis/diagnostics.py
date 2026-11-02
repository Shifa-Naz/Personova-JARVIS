"""Startup warm-up and the `run.py --check` self-tests.

The self-tests exercise the real code paths (screen capture, OCR) so a broken install shows up with its
actual error instead of as "Something went wrong" during a demo. They print counts and timings only, never
screen text.
"""

from __future__ import annotations

import logging
import secrets
import threading
import time

from jarvis.actions.base import ActionError

log = logging.getLogger(__name__)

SELF_TEST_TEXT = "JARVIS screen test 2468"


def warm_up(services) -> None:
    """Load every local model in the background so the first command doesn't pay the loading time."""

    def run(name: str, fn) -> None:
        started = time.time()
        try:
            fn()
            log.info("Warmed up %s in %.1fs", name, time.time() - started)
        except Exception as exc:  # noqa: BLE001 - a missing optional engine must not stop the others
            log.info("Skipped warming %s: %s", name, exc)

    def all_engines() -> None:
        if services.transcriber.installed():
            run("speech recognition", services.transcriber.load)
        if services.synthesizer.available():
            run("voice", services.synthesizer.load)
        if services.ocr is not None:
            run("screen reading", services.ocr.warm_up)

    threading.Thread(target=services.ai.warm_up, name="jarvis-llm-warmup", daemon=True).start()
    threading.Thread(target=all_engines, name="jarvis-engine-warmup", daemon=True).start()


def check_ocr(services, settings) -> str:
    """OCR a generated image with known text."""
    from PIL import Image, ImageDraw, ImageFont

    if services.ocr is None or not services.ocr.available():
        return "not installed (pip install rapidocr_onnxruntime)"
    tmp = settings.data_dir / "tmp" / f"ocr-test-{secrets.token_hex(4)}.png"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    try:
        img = Image.new("RGB", (900, 160), "white")
        try:
            font = ImageFont.load_default(size=48)
        except TypeError:  # Pillow < 10.1 has only the small bitmap font
            font = ImageFont.load_default()
        ImageDraw.Draw(img).text((30, 50), SELF_TEST_TEXT, fill="black", font=font)
        img.save(tmp)
        started = time.time()
        lines, _ = services.ocr.read(tmp)
        took = time.time() - started
        found = " ".join(line.text for line in lines)
        ok = "2468" in found
        return f"{'ok' if ok else 'ran, but misread the test text'} ({services.ocr.engine_name()}, {took:.1f}s)"
    except ActionError as exc:
        return f"FAILED: {exc.message}"
    except Exception as exc:  # noqa: BLE001 - report, don't crash the check
        return f"FAILED: {type(exc).__name__}: {exc}"
    finally:
        tmp.unlink(missing_ok=True)


def check_screen_capture(services, settings) -> str:
    """Capture the screen and OCR it; reports size, line count and time only."""
    tmp = settings.data_dir / "tmp" / f"screen-test-{secrets.token_hex(4)}.png"
    try:
        started = time.time()
        services.platform.screenshot(tmp)
        from PIL import Image

        with Image.open(tmp) as img:
            size = img.size
        captured = time.time() - started
        detail = f"{size[0]}x{size[1]} in {captured:.1f}s"
        if services.ocr is not None and services.ocr.available():
            started = time.time()
            lines, _ = services.ocr.read(tmp)
            detail += f", {len(lines)} text lines read in {time.time() - started:.1f}s"
        return f"ok ({detail})"
    except ActionError as exc:
        return f"FAILED: {exc.message}"
    except Exception as exc:  # noqa: BLE001
        return f"FAILED: {type(exc).__name__}: {exc}"
    finally:
        tmp.unlink(missing_ok=True)
