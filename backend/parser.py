import difflib
import re


KNOWN = [
    "open", "chrome", "search", "youtube", "linkedin", "downloads",
    "click", "first", "second", "scroll", "down", "up",
    "type", "send", "file", "folder", "delete", "copy", "move",
    "notepad", "link", "result", "button",

    # Conversation words
    "hello", "hi", "hey", "thanks", "thank", "who", "what",
    "how", "are", "you", "your", "name", "help", "good",
    "morning", "afternoon", "evening", "bye"
]


REMOVE = [
    "jarvis", "please", "can", "could", "would",
    "for", "me", "the", "a", "an", "to", "on", "which",
    "that", "says", "with", "my", "this", "is", "of"
]


def closest(word):

    m = difflib.get_close_matches(
        word,
        KNOWN,
        n=1,
        cutoff=0.6,
    )

    if m:
        return m[0]

    return word


def fix_words(text):

    parts = text.split()

    fixed = []

    for p in parts:

        if p in REMOVE:
            continue

        fixed.append(
            closest(p)
        )

    return " ".join(fixed)


def normalize(text):

    text = text.lower()

    text = re.sub(r"[^\w\s]", "", text)

    text = fix_words(text)

    return text.strip()


def parse_command(text):

    text = normalize(text)

    print("PARSED:", text)

    return text