def clean_text(s):

    s = s.lower()

    remove_words = [
        "please",
        "jarvis",
        "can you",
        "could you",
        "would you",
        "for me",
        "the",
        "a",
        "an",
        "on",
        "to",
        "which",
        "that",
        "says",
        "button",
        "link",
        "result",
        ".",
    ]

    for w in remove_words:
        s = s.replace(w, "")

    return s.strip()


OPEN_WORDS = [
    "open",
    "launch",
    "start",
    "go",
    "visit",
]

CLICK_WORDS = [
    "click",
    "tap",
    "press",
    "select",
    "choose",
]

SEARCH_WORDS = [
    "search",
    "find",
    "look",
]

SEND_WORDS = [
    "send",
]

SCROLL_DOWN = [
    "scroll down",
    "go down",
]

SCROLL_UP = [
    "scroll up",
    "go up",
]

# NEW
CHAT_WORDS = [
    "hello", "hi", "hey",
    "how are you",
    "who are you",
    "what is your name",
    "your name",
    "thank",
    "thanks",
    "bye",
    "good morning",
    "good afternoon",
    "good evening",
    "help",
]


def has_word(s, words):

    for w in words:
        if w in s:
            return True

    return False


def extract_after(word, s):

    if word in s:
        return s.split(word, 1)[1].strip()

    return ""


def get_order(s):

    if "first" in s:
        return "first"

    if "second" in s:
        return "second"

    if "third" in s:
        return "3"

    return ""


def plan_steps(steps):

    actions = []

    for step in steps:

        s = clean_text(step)

        # ---------- CONVERSATION ----------
        if has_word(s, CHAT_WORDS):
            actions.append((f"chat {s}", ""))
            continue

        # ---------- FILE ----------
        if "open file" in s:
            actions.append((s, ""))

        elif "open folder" in s:
            actions.append((s, ""))

        elif "delete file" in s:
            actions.append((s, ""))

        elif "copy file" in s:
            actions.append((s, ""))

        elif "move file" in s:
            actions.append((s, ""))

        # ---------- SEARCH ----------
        elif has_word(s, SEARCH_WORDS):

            for w in SEARCH_WORDS:
                if w in s:
                    q = extract_after(w, s)
                    actions.append((f"search {q}", ""))
                    break

        # ---------- OPEN ----------
        elif has_word(s, OPEN_WORDS):

            if "chrome" in s:
                actions.append(("open chrome", ""))

            elif "downloads" in s:
                actions.append(("open downloads", ""))

            elif "notepad" in s:
                actions.append(("open notepad", ""))

            elif "linkedin" in s:
                actions.append(("open chrome", ""))
                actions.append(("search linkedin", ""))

            else:
                actions.append((s, ""))

        # ---------- CLICK ----------
        elif has_word(s, CLICK_WORDS):

            order = get_order(s)

            if order == "first":
                actions.append(("click first", ""))

            elif order == "second":
                actions.append(("click second", ""))

            else:

                for w in CLICK_WORDS:
                    s = s.replace(w, "")

                s = s.strip()

                if s:
                    actions.append((f"click {s}", ""))
                else:
                    actions.append(("click", ""))

        # ---------- SEND ----------
        elif has_word(s, SEND_WORDS):

            actions.append(("send", ""))

        # ---------- TYPE ----------
        elif "type" in s:

            actions.append((s, ""))

        # ---------- SCROLL ----------
        elif has_word(s, SCROLL_DOWN):

            actions.append(("scroll down", ""))

        elif has_word(s, SCROLL_UP):

            actions.append(("scroll up", ""))

        else:

            actions.append((s, ""))

    return actions