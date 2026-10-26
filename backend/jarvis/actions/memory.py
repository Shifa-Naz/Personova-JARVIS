"""Explicit, user-approved long-term memory.

Nothing is remembered automatically: only "remember that …" saves a memory. Saved
memories are used as context for answers ("what language do I prefer?") and can be
listed, updated and forgotten. Secrets (passwords, PINs, card numbers) are refused.
"""

from __future__ import annotations

import re

from pydantic import Field

from jarvis.actions.base import ActionError, ActionResult, ActionSpec, Params, PermissionLevel, Prepared
from jarvis.ai.provider import AiUnavailable

CATEGORIES = ("preference", "fact", "project", "instruction")
_SECRET = re.compile(
    r"\b(?:password|passcode|passwd|pin|otp|cvv|cvc|secret key|api key|private key|card number|credit card|"
    r"debit card|bank account|aadhaar|ssn|social security)\b|\b(?:\d[ -]?){12,19}\b",
    re.IGNORECASE,
)
_WORD = re.compile(r"[a-z0-9+#]+")
_STOP = {
    "i",
    "me",
    "my",
    "the",
    "a",
    "an",
    "is",
    "are",
    "do",
    "does",
    "what",
    "which",
    "who",
    "that",
    "to",
    "of",
    "you",
    "remember",
    "about",
    "know",
    "and",
    "in",
    "on",
    "for",
    "it",
    "am",
    "was",
    "did",
}
# Words that point at the same memory although phrased differently ("prefer" ~ "like" ~ "favourite").
_SYNONYMS = {
    "prefer": {"like", "favourite", "favorite", "love", "use"},
    "like": {"prefer", "favourite", "favorite"},
    "favourite": {"prefer", "like", "favorite"},
    "favorite": {"prefer", "like", "favourite"},
    "language": {"c++", "python", "java", "javascript", "rust", "go", "c", "kotlin", "typescript"},
    "name": {"called"},
    "live": {"from", "city"},
    "study": {"college", "university", "studying"},
}


def categorize(text: str) -> str:
    t = text.lower()
    if re.search(r"\b(?:prefer|like|love|favou?rite|hate|dislike|enjoy)\b", t):
        return "preference"
    if re.search(r"\b(?:always|never|call me|when i say|don't|do not|please)\b", t):
        return "instruction"
    if re.search(r"\b(?:project|working on|building|deadline|repo|assignment)\b", t):
        return "project"
    return "fact"


def _terms(text: str) -> set[str]:
    words = {w for w in _WORD.findall(text.lower()) if w not in _STOP}
    expanded = set(words)
    for w in words:
        expanded |= _SYNONYMS.get(w, set())
    return expanded


def relevant_memories(store, query: str, limit: int = 3) -> list[dict]:
    if store is None:
        return []
    q = _terms(query)
    scored = []
    for item in store.load("memory"):
        overlap = len(q & _terms(item["text"]))
        if overlap:
            scored.append((overlap, item.get("created", 0), item))
    scored.sort(key=lambda s: (s[0], s[1]), reverse=True)
    return [s[2] for s in scored[:limit]]


def _first_person(text: str) -> str:
    """'that I prefer C++' -> 'I prefer C++'; 'my name is Sourab' stays as is."""
    text = re.sub(r"^(?:that|about)\s+", "", text.strip(), flags=re.IGNORECASE).strip(" .")
    return text[:1].upper() + text[1:] if text else text


def _require_store(ctx):
    if ctx.store is None:
        raise ActionError("STORAGE_UNAVAILABLE", "Memory storage isn't available.")
    return ctx.store


class SaveParams(Params):
    text: str = Field(min_length=2, max_length=300)
    category: str | None = Field(default=None, pattern=f"^({'|'.join(CATEGORIES)})$")


def memory_save(params: SaveParams, ctx, prepared) -> ActionResult:
    store = _require_store(ctx)
    if _SECRET.search(params.text):
        return ActionResult.fail("SENSITIVE_DATA", "I won't store passwords, PINs, card or account numbers.")
    text = _first_person(params.text)
    existing = next((m for m in store.load("memory") if m["text"].lower() == text.lower()), None)
    if existing:
        return ActionResult(True, "I already remember that.", data={"memory": existing})
    item = store.add("memory", {"text": text, "category": params.category or categorize(text)})
    return ActionResult(True, f"Got it. I'll remember that {_as_second_person(text)}.", data={"memory": item})


def _as_second_person(text: str) -> str:
    out = re.sub(r"\bI am\b", "you are", text)
    out = re.sub(r"\bI'm\b", "you're", out)
    out = re.sub(r"\bI\b", "you", out)
    out = re.sub(r"\bmy\b", "your", out, flags=re.IGNORECASE)
    out = re.sub(r"\bmine\b", "yours", out, flags=re.IGNORECASE)
    return out[:1].lower() + out[1:] if out[:2] != "I " else out


class RecallParams(Params):
    query: str = Field(min_length=2, max_length=300)


def memory_recall(params: RecallParams, ctx, prepared) -> ActionResult:
    store = _require_store(ctx)
    hits = relevant_memories(store, params.query)
    if not hits:
        return ActionResult(
            True, "I don't have anything saved about that. You can tell me: remember that …", data={"memories": []}
        )
    facts = [h["text"] for h in hits]
    try:
        message = ctx.ai.answer_with_memory(params.query, facts)
    except AiUnavailable:
        message = "You told me: " + "; ".join(_as_second_person(f) for f in facts) + "."
    return ActionResult(True, message, data={"memories": hits})


def memory_list(params: Params, ctx, prepared) -> ActionResult:
    items = _require_store(ctx).load("memory")
    if not items:
        return ActionResult(True, "I'm not remembering anything about you yet.", data={"memories": []})
    shown = "; ".join(_as_second_person(m["text"]) for m in items[:8])
    more = f" And {len(items) - 8} more." if len(items) > 8 else ""
    return ActionResult(True, f"I remember that {shown}.{more}", data={"memories": items})


class ForgetParams(Params):
    query: str = Field(min_length=2, max_length=300)


def prepare_forget(params: ForgetParams, ctx) -> Prepared:
    hits = relevant_memories(_require_store(ctx), params.query, limit=5)
    if not hits:
        raise ActionError("MEMORY_NOT_FOUND", "I don't have a memory matching that.")
    if len(hits) > 1 and _overlap(params.query, hits[0]) == _overlap(params.query, hits[1]):
        options = "; ".join(h["text"] for h in hits[:3])
        raise ActionError("AMBIGUOUS", f"Which one should I forget: {options}?")
    target = hits[0]
    return Prepared(summary=f'This will forget: "{target["text"]}".', data={"id": target["id"]})


def _overlap(query: str, item: dict) -> int:
    return len(_terms(query) & _terms(item["text"]))


def memory_forget(params: ForgetParams, ctx, prepared: Prepared | None) -> ActionResult:
    if prepared is None:
        raise ActionError("NOT_CONFIRMED", "Forgetting needs a confirmed memory.")
    if not _require_store(ctx).delete("memory", prepared.data["id"]):
        return ActionResult.fail("MEMORY_NOT_FOUND", "That memory was already gone.")
    return ActionResult(True, "Forgotten.")


class UpdateParams(Params):
    query: str = Field(min_length=2, max_length=300)
    text: str = Field(min_length=2, max_length=300)


def prepare_update(params: UpdateParams, ctx) -> Prepared:
    if _SECRET.search(params.text):
        raise ActionError("SENSITIVE_DATA", "I won't store passwords, PINs, card or account numbers.")
    prep = prepare_forget(ForgetParams(query=params.query), ctx)
    old = _require_store(ctx).get("memory", prep.data["id"])
    new = _first_person(params.text)
    return Prepared(summary=f'This will change "{old["text"]}" to "{new}".', data={"id": old["id"], "text": new})


def memory_update(params: UpdateParams, ctx, prepared: Prepared | None) -> ActionResult:
    if prepared is None:
        raise ActionError("NOT_CONFIRMED", "Updating needs a confirmed memory.")
    text = prepared.data["text"]
    item = _require_store(ctx).update("memory", prepared.data["id"], {"text": text, "category": categorize(text)})
    if item is None:
        return ActionResult.fail("MEMORY_NOT_FOUND", "That memory no longer exists.")
    return ActionResult(True, f"Updated. I'll remember that {_as_second_person(text)}.", data={"memory": item})


class _NoParams(Params):
    pass


SPECS = [
    ActionSpec(
        "memory_save",
        "Save something the user explicitly asked you to remember (a preference, fact, project detail or instruction).",
        SaveParams,
        PermissionLevel.SAFE,
        memory_save,
        examples=("remember that I prefer C++",),
    ),
    ActionSpec(
        "memory_recall",
        "Answer a question about the user from their saved memories.",
        RecallParams,
        PermissionLevel.READ_ONLY,
        memory_recall,
        timeout_s=90,
        examples=("what language do I prefer",),
    ),
    ActionSpec(
        "memory_list",
        "List what the user asked you to remember.",
        _NoParams,
        PermissionLevel.READ_ONLY,
        memory_list,
        examples=("what do you remember about me",),
    ),
    ActionSpec(
        "memory_update",
        "Change a saved memory.",
        UpdateParams,
        PermissionLevel.SENSITIVE,
        memory_update,
        prepare=prepare_update,
    ),
    ActionSpec(
        "memory_forget",
        "Delete a saved memory.",
        ForgetParams,
        PermissionLevel.SENSITIVE,
        memory_forget,
        prepare=prepare_forget,
        examples=("forget that I prefer C++",),
    ),
]
