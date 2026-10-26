from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.intent import Intent, IntentMatcher
from jarvis.platform.apps import AppRegistry
from jarvis.vision.ocr import OcrLine, layout_text, mask_secrets, reading_order


@pytest.fixture(scope="module")
def matcher():
    return IntentMatcher(AppRegistry())


@pytest.mark.parametrize(
    ("text", "params"),
    [
        ("what's on my screen", {"mode": "describe"}),
        ("Jarvis, what is on the screen right now?", {"mode": "describe"}),
        ("describe my screen", {"mode": "describe"}),
        ("what am I looking at", {"mode": "describe"}),
        ("what do you see", {"mode": "describe"}),
        ("read my screen", {"mode": "read"}),
        ("read me what's on the screen", {"mode": "read"}),
        ("what does my screen say", {"mode": "read"}),
        ("what is the error on my screen", {"mode": "ask", "question": "what is the error on my screen"}),
        ("which song is playing on the screen", {"mode": "ask", "question": "which song is playing on the screen"}),
    ],
)
def test_screen_intents(matcher, text, params):
    r = matcher.parse(text)
    assert r.intent is Intent.QUESTION
    assert [(s.action, s.params) for s in r.steps] == [("describe_screen", params)]


def test_screenshot_is_not_screen_reading(matcher):
    assert matcher.parse("take a screenshot").steps[0].action == "screenshot"


def test_describe_uses_llm_and_deletes_capture(pipeline, fake_ai, fake_ocr, fake_platform):
    resp = pipeline.command("what's on my screen")
    assert resp.status == "done"
    assert resp.reply == "You're looking at a mail app with a quarterly report open."
    sent = fake_ai.screen_calls[0]
    assert "Quarterly Report" in sent["text"] and "[TOP BAR]" in sent["text"]
    assert "sk_live" not in sent["text"]  # secrets masked before the model sees them
    assert sent["request"] is None and sent["image"] is False
    shot = Path(fake_platform.calls[0][1])
    assert fake_ocr.paths == [str(shot)]
    assert not shot.exists()  # the screenshot never outlives the request


def test_ask_passes_question(pipeline, fake_ai):
    pipeline.command("what is the meeting time on my screen")
    assert fake_ai.screen_calls[0]["request"] == "what is the meeting time on my screen"


def test_read_mode_reads_text_without_llm(pipeline, fake_ai):
    resp = pipeline.command("read my screen")
    assert resp.reply.startswith("Your screen says: Inbox - Mail. Quarterly Report")
    assert "[hidden]" in resp.reply and "sk_live" not in resp.reply
    assert fake_ai.screen_calls == []


def test_falls_back_to_text_when_llm_down(pipeline, fake_ai):
    fake_ai.is_available = False
    resp = pipeline.command("describe my screen")
    assert resp.status == "done"
    assert resp.reply.startswith("My language model isn't available, so here's the main text on your screen")
    assert resp.results[0].data["source"] == "ocr"


def test_empty_screen(pipeline, fake_ocr):
    fake_ocr.lines = []
    assert "no readable text" in pipeline.command("what's on my screen").reply


def test_ocr_not_installed(pipeline, fake_ocr, fake_platform):
    fake_ocr.ready = False
    resp = pipeline.command("what's on my screen")
    assert resp.error_code == "OCR_UNAVAILABLE"
    assert fake_platform.calls == []  # don't capture if we can't read it


def test_capture_deleted_even_when_ocr_fails(pipeline, fake_ocr, fake_platform):
    from jarvis.actions.base import ActionError

    def boom(path):
        raise ActionError("OCR_FAILED", "I couldn't read the screen.")

    fake_ocr.read = boom
    resp = pipeline.command("what's on my screen")
    assert resp.error_code == "OCR_FAILED"
    assert not Path(fake_platform.calls[0][1]).exists()


def test_capture_denied_is_reported(pipeline, fake_platform):
    from jarvis.actions.base import ActionError

    fake_platform.fail["screenshot"] = ActionError(
        "SCREENSHOT_DENIED", "Screen capture was cancelled or not permitted."
    )
    assert pipeline.command("what's on my screen").error_code == "SCREENSHOT_DENIED"


def test_reading_order_and_layout():
    lines = [
        OcrLine("second", 0.9, 300, 200, 50, 20),
        OcrLine("first", 0.9, 10, 202, 50, 20),
        OcrLine("Title", 0.9, 10, 5, 50, 20),
        OcrLine("status", 0.9, 10, 1050, 50, 20),
    ]
    assert [line.text for line in reading_order(lines)] == ["Title", "first", "second", "status"]
    assert layout_text(lines, 1080).splitlines() == [
        "[TOP BAR]",
        "Title",
        "[MAIN]",
        "first",
        "second",
        "[BOTTOM]",
        "status",
    ]


def test_budget_prefers_question_matches_title_bar_and_headings():
    from jarvis.vision.ocr import select_lines

    lines = [
        OcrLine("Visual Studio Code - main.py", 0.9, 0, 5, 300, 18),
        OcrLine("Big Heading", 0.9, 0, 300, 300, 48),
        *[OcrLine(f"small filler line number {i}", 0.9, 0, 400 + i * 20, 300, 14) for i in range(40)],
        OcrLine("TypeError: unsupported operand", 0.9, 0, 1000, 300, 14),
    ]
    picked = [line.text for line in select_lines(lines, 1080, 120, query="what is the error on my screen")]
    assert picked[:3] == ["Visual Studio Code - main.py", "Big Heading", "small filler line number 0"]
    picked = [line.text for line in select_lines(lines, 1080, 120, query="what does the TypeError say")]
    assert picked[0] == "TypeError: unsupported operand"
    text = layout_text(lines, 1080, max_chars=120)
    assert text.endswith("smaller lines omitted]") and len(text) < 260


def test_mask_secrets_keeps_normal_words():
    assert mask_secrets("Quarterly Report 2026") == "Quarterly Report 2026"
    assert mask_secrets("token " + "ghp_" + "abcdefghij1234567890abcd" + " end") == "token [hidden] end"


def test_capabilities_report_ocr(client):
    h = {"Origin": "http://localhost:8080", "X-Jarvis-Token": "test-token"}
    assert client.get("/api/v1/status", headers=h).json["capabilities"]["screen_ocr"] == "fake"


def test_real_rapidocr_on_synthetic_screen(tmp_path):
    pytest.importorskip("rapidocr_onnxruntime")
    import glob

    from PIL import Image, ImageDraw, ImageFont

    from jarvis.vision.ocr import OcrEngine

    fonts = glob.glob("/usr/share/fonts/**/DejaVuSans.ttf", recursive=True) + glob.glob("C:/Windows/Fonts/arial.ttf")
    if not fonts:
        pytest.skip("no TrueType font available")
    img = Image.new("RGB", (1280, 720), (30, 30, 34))
    draw = ImageDraw.Draw(img)
    draw.text((60, 80), "Deploy the backend before Friday", font=ImageFont.truetype(fonts[0], 28), fill="white")
    draw.text((60, 160), "Meeting at 4:30 PM", font=ImageFont.truetype(fonts[0], 28), fill="white")
    path = tmp_path / "screen.png"
    img.save(path)
    lines, size = OcrEngine().read(path)
    texts = [line.text for line in reading_order(lines)]
    assert size == (1280, 720)
    assert texts == ["Deploy the backend before Friday", "Meeting at 4:30 PM"]


def test_image_only_sent_for_text_poor_screens(pipeline, fake_ai, fake_ocr):
    fake_ai.vision_available = lambda: True
    pipeline.command("what's on my screen")
    assert fake_ai.screen_calls[-1]["image"] is False  # text-heavy screen: OCR text is enough (and ~30x faster)
    fake_ocr.lines = fake_ocr.lines[:1]
    pipeline.command("what's on my screen")
    assert fake_ai.screen_calls[-1]["image"] is True


def test_text_free_screen_uses_vision_when_available(pipeline, fake_ai, fake_ocr):
    fake_ai.vision_available = lambda: True
    fake_ocr.lines = []
    resp = pipeline.command("what's on my screen")
    assert resp.reply == "You're looking at a mail app with a quarterly report open."
