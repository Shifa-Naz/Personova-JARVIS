"""Turn on-screen Markdown into a short spoken version.

The page shows the full answer; the voice reads only the opening sentences, never code.
"""

from __future__ import annotations

import re

_CODE_BLOCK = re.compile(r"```.*?```", re.DOTALL)
_SENTENCE = re.compile(r"(?<=[.!?:])\s+")


def _sentences(markdown: str) -> tuple[list[str], bool]:
    """Markdown -> plain spoken sentences (code removed), and whether there was code."""
    text = markdown or ""
    had_code = bool(_CODE_BLOCK.search(text))
    text = _CODE_BLOCK.sub(" ", text)
    text = re.sub(r"^\s*\*\*Sources\*\*.*", "", text, flags=re.DOTALL | re.MULTILINE)  # source lists aren't read
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)  # images
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)  # links -> their text
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"(\*\*|__|\*|_|~~)(.+?)\1", r"\2", text)
    text = re.sub(r"^\s*>\s?", "", text, flags=re.MULTILINE)
    text = re.sub(r"\|", " ", text)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    # Lines without end punctuation (list items, headings) become sentences of their own.
    flat = " ".join(ln if ln[-1] in ".!?:" else ln + "." for ln in lines)
    flat = re.sub(r"\s+", " ", flat).strip()
    return [x for x in _SENTENCE.split(flat) if x], had_code


def _budget(sentences: list[str], max_words: int, start_words: int = 0, first: bool = True) -> list[str]:
    spoken, words = [], start_words
    for sentence in sentences:
        n = len(sentence.split())
        if (spoken or not first) and words + n > max_words:
            break
        spoken.append(sentence)
        words += n
    return spoken


def _closing(had_code: bool, truncated: bool) -> str:
    if had_code:
        return "I've put the code on screen."
    return "The rest is on screen." if truncated else ""


def to_speech(markdown: str, max_words: int = 45) -> str:
    sentences, had_code = _sentences(markdown)
    spoken = _budget(sentences, max_words)
    return " ".join([*spoken, _closing(had_code, len(spoken) < len(sentences))]).strip()


# A sentence may end where the model has reached ". " / "! " / "? " after a word (not "1. " list numbers), or at
# the end of a line.
_BOUNDARY = re.compile(r"(?<=[A-Za-z)\]\"'*_`])[.!?](?=\s)|\n")


def _stable_prefix(text: str) -> str:
    """The part of a still-growing answer whose sentences can't change any more."""
    while True:
        fences = [m.start() for m in re.finditer("```", text)]
        if len(fences) % 2:  # inside an unfinished code block
            text = text[: fences[-1]]
        ends = [m.end() for m in _BOUNDARY.finditer(text)]
        cut = text[: ends[-1]] if ends else ""
        if cut.count("```") % 2 == 0:
            return cut
        text = cut  # the cut fell inside a code block; cut again before it


class SpeechStreamer:
    """Turns a streaming Markdown answer into spoken sentences as soon as each one is complete.

    Speaks exactly what `to_speech` would for the finished answer, so the voice can start seconds earlier.
    """

    def __init__(self, max_words: int = 45) -> None:
        self.max_words = max_words
        self.text = ""
        self.said: list[str] = []
        self.words = 0
        self.full = False

    def feed(self, piece: str) -> list[str]:
        self.text += piece
        if self.full:
            return []
        sentences, _ = _sentences(_stable_prefix(self.text))
        # The last stable sentence can still grow if the model continues the same line ("Hello." -> "Hello.").
        ready = sentences[len(self.said) :]
        out = _budget(ready, self.max_words, self.words, first=not self.said)
        if len(out) < len(ready):
            self.full = True
        self.said += out
        self.words += sum(len(x.split()) for x in out)
        return out

    def finish(self) -> str:
        """What is left to say once the answer is complete (remaining sentences and the closing note)."""
        sentences, had_code = _sentences(self.text)
        if sentences[: len(self.said)] != self.said:  # the text changed shape; say the closing note only
            return _closing(had_code, True)
        rest = (
            [] if self.full else _budget(sentences[len(self.said) :], self.max_words, self.words, first=not self.said)
        )
        total = len(self.said) + len(rest)
        return " ".join([*rest, _closing(had_code, total < len(sentences))]).strip()
