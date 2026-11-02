"""Offline OCR for screen understanding.

Primary engine: RapidOCR (pip-only, ONNX models bundled, same on Linux and Windows).
Fallback: pytesseract, when the Tesseract program is installed.
"""

from __future__ import annotations

import importlib.util
import logging
import re
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from jarvis.actions.base import ActionError

log = logging.getLogger(__name__)

MIN_CONFIDENCE = 0.5
# Long unbroken runs of token-like characters (API keys, JWTs, hashes) are masked before
# the text is spoken, shown or handed to the language model.
_SECRETISH = re.compile(r"\b(?=[A-Za-z0-9_\-+/=]*\d)(?=[A-Za-z0-9_\-+/=]*[A-Za-z])[A-Za-z0-9_\-+/=]{24,}\b")


@dataclass(frozen=True)
class OcrLine:
    text: str
    confidence: float
    x: int
    y: int
    width: int
    height: int


def mask_secrets(text: str) -> str:
    return _SECRETISH.sub("[hidden]", text)


def reading_order(lines: list[OcrLine]) -> list[OcrLine]:
    """Sort top-to-bottom, then left-to-right for boxes on the same visual row."""
    if not lines:
        return []
    row_height = max(8, sorted(line.height for line in lines)[len(lines) // 2])
    return sorted(lines, key=lambda line: (round(line.y / row_height), line.x))


_WORD = re.compile(r"[a-z0-9]{3,}")
_STOP = {"what", "whats", "the", "this", "that", "screen", "display", "monitor", "does", "say", "which", "are", "there"}


def select_lines(lines: list[OcrLine], screen_height: int, max_chars: int, query: str | None = None) -> list[OcrLine]:
    """Pick the most informative lines that fit a character budget.

    A small local model reads prompts slowly on CPU (~26 tokens/s measured), so the screen
    text is budgeted rather than sent whole. Priority: lines matching the user's question,
    then the title/tab bar (names the app or page), then the largest text (headings).
    """
    words = {w for w in _WORD.findall((query or "").lower()) if w not in _STOP}

    def priority(line: OcrLine) -> tuple:
        hits = len(words & set(_WORD.findall(line.text.lower())))
        top_bar = line.y / max(1, screen_height) < 0.08
        return (-hits, not top_bar, -line.height, line.y)

    chosen, used = [], 0
    for line in sorted(lines, key=priority):
        cost = len(line.text) + 1
        if used + cost > max_chars:
            continue
        chosen.append(line)
        used += cost
    return chosen


def layout_text(lines: list[OcrLine], screen_height: int, max_chars: int = 1200, query: str | None = None) -> str:
    """Budgeted plain-text rendering with coarse regions, for the language model."""
    picked = select_lines(lines, screen_height, max_chars, query)
    out, region = [], None
    for line in reading_order(picked):
        frac = line.y / max(1, screen_height)
        name = "TOP BAR" if frac < 0.08 else "BOTTOM" if frac > 0.9 else "MAIN"
        if name != region:
            out.append(f"[{name}]")
            region = name
        out.append(mask_secrets(line.text))
    if len(picked) < len(lines):
        out.append(f"[{len(lines) - len(picked)} smaller lines omitted]")
    return "\n".join(out)


# The old package returns ([[box, text, score], ...], elapsed); the newer `rapidocr` (2.x+) returns an object
# with .boxes/.txts/.scores. Both are supported because Windows users often end up with the newer one.
_RAPID_MODULES = ("rapidocr_onnxruntime", "rapidocr")


def _startup_hint(exc: BaseException) -> str:
    text = str(exc)
    if "DLL load failed" in text or "onnxruntime_pybind11_state" in text:
        return "Install the Microsoft Visual C++ Redistributable (x64) from Microsoft, then restart JARVIS."
    if "numpy" in text.lower() and ("1.x" in text or "2.x" in text or "_ARRAY_API" in text):
        return 'Run: pip install "numpy<2" (in the JARVIS environment), then restart JARVIS.'
    return "Run: pip install --force-reinstall rapidocr_onnxruntime (in the JARVIS environment)."


def rapid_lines(result) -> list[OcrLine]:
    """Normalise either RapidOCR result shape into OcrLines."""
    if hasattr(result, "txts"):
        boxes = result.boxes if getattr(result, "boxes", None) is not None else []
        items = zip(boxes, result.txts or (), result.scores or (), strict=False)
    else:
        if isinstance(result, tuple) and len(result) == 2:
            result = result[0]
        items = result or []
    lines = []
    for box, text, score in items:
        xs = [int(p[0]) for p in box]
        ys = [int(p[1]) for p in box]
        lines.append(OcrLine(str(text).strip(), float(score), min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)))
    return [line for line in lines if line.text]


class OcrEngine:
    def __init__(self, tesseract_cmd: str | None = None) -> None:
        self.tesseract_cmd = tesseract_cmd
        self._rapid = None
        self._rapid_error: ActionError | None = None
        self._lock = threading.Lock()

    @staticmethod
    def _rapid_module() -> str | None:
        return next((name for name in _RAPID_MODULES if importlib.util.find_spec(name) is not None), None)

    def _tesseract_ready(self) -> bool:
        if importlib.util.find_spec("pytesseract") is None:
            return False
        return bool(self.tesseract_cmd and Path(self.tesseract_cmd).exists()) or shutil.which("tesseract") is not None

    def engine_name(self) -> str | None:
        if self._rapid_module() and self._rapid_error is None:
            return "rapidocr"
        if self._tesseract_ready():
            return "tesseract"
        return "rapidocr" if self._rapid_module() else None

    def available(self) -> bool:
        return self.engine_name() is not None

    def warm_up(self) -> None:
        """Load the OCR models ahead of the first "what's on my screen" (about 1-2 s saved)."""
        if self._rapid_module():
            try:
                self._load_rapid()
            except ActionError as exc:
                log.warning("Screen reading unavailable: %s", exc.message)

    def _load_rapid(self):
        with self._lock:
            if self._rapid is not None:
                return self._rapid
            if self._rapid_error is not None:
                raise self._rapid_error
            module = self._rapid_module()
            started = time.time()
            try:
                if module == "rapidocr_onnxruntime":
                    from rapidocr_onnxruntime import RapidOCR
                else:
                    from rapidocr import RapidOCR  # type: ignore[no-redef]
                self._rapid = RapidOCR()
            except Exception as exc:  # noqa: BLE001 - DLL, numpy ABI or model-download errors on import/start
                log.exception("RapidOCR could not start")
                self._rapid_error = ActionError(
                    "OCR_UNAVAILABLE", f"Screen reading couldn't start ({type(exc).__name__}). {_startup_hint(exc)}"
                )
                raise self._rapid_error from exc
            log.info("Loaded OCR engine %s in %.1fs", module, time.time() - started)
            return self._rapid

    def read(self, image_path: Path) -> tuple[list[OcrLine], tuple[int, int]]:
        """Returns (lines with confidence >= MIN_CONFIDENCE, (width, height))."""
        from PIL import Image

        with Image.open(image_path) as img:
            size = img.size
        if self.engine_name() is None:
            raise ActionError(
                "OCR_UNAVAILABLE", "Screen reading isn't installed. Run: pip install rapidocr_onnxruntime"
            )
        started = time.time()
        engine = "rapidocr"
        try:
            if not self._rapid_module():
                raise ActionError("OCR_UNAVAILABLE", "RapidOCR isn't installed.")
            lines = self._read_rapid(image_path)
        except ActionError as exc:
            if exc.code != "OCR_UNAVAILABLE" or not self._tesseract_ready():
                raise
            engine = "tesseract"
            lines = self._read_tesseract(image_path)
        log.info("OCR (%s) found %d lines in %.2fs", engine, len(lines), time.time() - started)
        return [line for line in lines if line.confidence >= MIN_CONFIDENCE], size

    def _read_rapid(self, image_path: Path) -> list[OcrLine]:
        engine = self._load_rapid()
        with self._lock:
            try:
                result = engine(str(image_path))
            except Exception as exc:  # noqa: BLE001 - model/runtime errors become a typed failure
                log.exception("RapidOCR failed")
                raise ActionError("OCR_FAILED", "I couldn't read the screen.") from exc
        return rapid_lines(result)

    def _read_tesseract(self, image_path: Path) -> list[OcrLine]:
        import pytesseract
        from PIL import Image

        if self.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd
        try:
            with Image.open(image_path) as img:
                data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        except Exception as exc:  # noqa: BLE001
            log.exception("Tesseract failed")
            raise ActionError("OCR_FAILED", "I couldn't read the screen.") from exc
        # Merge words into lines using Tesseract's block/paragraph/line numbering.
        groups: dict[tuple[int, int, int], list[int]] = {}
        for i, word in enumerate(data["text"]):
            if word.strip() and float(data["conf"][i]) >= 0:
                groups.setdefault((data["block_num"][i], data["par_num"][i], data["line_num"][i]), []).append(i)
        lines = []
        for idx in groups.values():
            text = " ".join(data["text"][i] for i in idx)
            conf = sum(float(data["conf"][i]) for i in idx) / len(idx) / 100
            x0 = min(data["left"][i] for i in idx)
            y0 = min(data["top"][i] for i in idx)
            x1 = max(data["left"][i] + data["width"][i] for i in idx)
            y1 = max(data["top"][i] + data["height"][i] for i in idx)
            lines.append(OcrLine(text, conf, x0, y0, x1 - x0, y1 - y0))
        return lines
