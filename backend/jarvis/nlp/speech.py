"""Turn on-screen Markdown into a short spoken version.

The page shows the full answer; the voice reads only the opening sentences, never code.
"""

from __future__ import annotations

import re

_CODE_BLOCK = re.compile(r"```.*?```", re.DOTALL)
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def to_speech(markdown: str, max_words: int = 45) -> str:
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

    spoken, words = [], 0
    for sentence in _SENTENCE.split(flat):
        n = len(sentence.split())
        if spoken and words + n > max_words:
            break
        spoken.append(sentence)
        words += n
    out = " ".join(spoken).strip()
    truncated = len(out) < len(flat) - 1
    if had_code:
        out = (out + " I've put the code on screen.").strip()
    elif truncated:
        out += " The rest is on screen."
    return out
