"""Offline language-model provider (Ollama) behind a small interface.

The model only ever returns DATA: a spoken answer or a JSON plan that the
pipeline validates against the action registry. It never produces commands
that are executed directly.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any

from jarvis.ai import prompts

log = logging.getLogger(__name__)


# Answers are capped at ~320 tokens (~20 s at 16 tokens/s on the dev CPU); the prompt asks for brevity too.
ANSWER_TOKENS = 320


class AiUnavailable(Exception):
    pass


class AiProvider(ABC):
    name = "none"

    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    def answer(self, question: str, history: list[dict[str, str]], memories: list[str] | None = None) -> str:
        """Markdown answer. `memories` are facts the user explicitly asked JARVIS to remember."""

    def answer_stream(
        self, question: str, history: list[dict[str, str]], memories: list[str] | None = None
    ) -> Iterator[str]:
        """Yields the answer in pieces as it is generated. Default: the whole answer at once."""
        yield self.answer(question, history, memories)

    def warm_up(self) -> None:  # noqa: B027 - optional hook, deliberately a no-op by default
        """Load the model into memory ahead of the first question (no-op by default)."""

    def answer_with_memory(self, question: str, facts: list[str]) -> str:
        raise AiUnavailable("No language model is configured.")

    def answer_from_sources(self, question: str, results: list[dict[str, str]]) -> str:
        raise AiUnavailable("No language model is configured.")

    @abstractmethod
    def plan(
        self, utterance: str, catalog: str, action_names: list[str], history: list[dict[str, str]]
    ) -> dict[str, Any]:
        """`catalog` is the compact one-line-per-action list; `action_names` constrains the JSON output."""

    def vision_available(self) -> bool:
        return False

    def describe_screen(
        self, screen_text: str, request: str | None, history: list[dict[str, str]], image_b64: str | None = None
    ) -> str:
        """Summarize OCR'd screen text (and optionally the image) or answer a question about it."""
        raise AiUnavailable("No language model is configured.")


class NullProvider(AiProvider):
    name = "none"

    def available(self) -> bool:
        return False

    def answer(self, question: str, history: list[dict[str, str]], memories: list[str] | None = None) -> str:
        raise AiUnavailable("No language model is configured.")

    def plan(self, utterance, catalog, action_names, history):
        raise AiUnavailable("No language model is configured.")


class OllamaProvider(AiProvider):
    name = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_s: int = 90,
        vision_model: str | None = None,
        threads: int | None = None,
    ) -> None:
        self.threads = threads
        self.vision_model = vision_model or None
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s
        self._avail_cache: tuple[float, bool] = (0.0, False)
        self._models: set[str] = set()
        self.last_error: str | None = None

    def _http_error(self, exc: urllib.error.HTTPError) -> AiUnavailable:
        body = exc.read().decode(errors="replace")
        if exc.code == 404 and "not found" in body:
            return AiUnavailable(f"The model '{self.model}' isn't downloaded. Run: ollama pull {self.model}")
        try:
            reason = str(json.loads(body).get("error", "")).strip()
        except (json.JSONDecodeError, AttributeError):
            reason = ""
        if "more system memory" in reason:
            # e.g. "model requires more system memory (4.9 GiB) than is available (4.5 GiB)"
            return AiUnavailable(
                f"There isn't enough free memory to load '{self.model}' ({reason}). "
                "Close some apps or switch JARVIS_LLM_MODEL to a smaller model."
            )
        return AiUnavailable(f"Ollama returned HTTP {exc.code}" + (f": {reason}" if reason else ""))

    def _request(self, path: str, payload: dict[str, Any] | None, timeout: float) -> dict[str, Any]:
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST" if data is not None else "GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - configured local URL
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            raise self._http_error(exc) from exc
        except TimeoutError as exc:
            raise AiUnavailable(
                f"The language model took longer than {int(timeout)} seconds to respond. It may still be loading, "
                "or it is too slow on this computer."
            ) from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise AiUnavailable(f"The language model took longer than {int(timeout)} seconds to respond.") from exc
            raise AiUnavailable("Ollama isn't running. Start it with: ollama serve") from exc
        except (ConnectionError, OSError) as exc:
            raise AiUnavailable("Ollama isn't running. Start it with: ollama serve") from exc

    @staticmethod
    def _has(names: set[str], model: str | None) -> bool:
        return bool(model) and (model in names or f"{model}:latest" in names)

    def available(self) -> bool:
        checked, ok = self._avail_cache
        if time.time() - checked < 15:
            return ok
        try:
            tags = self._request("/api/tags", None, timeout=2)
            self._models = {m.get("name", "") for m in tags.get("models", [])}
            ok = self._has(self._models, self.model)
            self.last_error = None if ok else f"Model '{self.model}' not pulled (ollama pull {self.model})"
        except AiUnavailable as exc:
            ok = False
            self._models = set()
            self.last_error = str(exc)
        self._avail_cache = (time.time(), ok)
        return ok

    def vision_available(self) -> bool:
        self.available()  # refreshes the installed-model list
        return self._has(self._models, self.vision_model)

    def _chat(
        self,
        messages: list[dict[str, Any]],
        fmt: Any = None,
        temperature: float = 0.2,
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> str:
        payload = self._payload(messages, temperature, model, max_tokens, stream=False)
        if fmt is not None:
            payload["format"] = fmt
        started = time.time()
        result = self._request("/api/chat", payload, timeout=self.timeout_s)
        log.info("LLM call took %.2fs", time.time() - started)
        return (result.get("message") or {}).get("content", "").strip()

    def _payload(
        self,
        messages: list[dict[str, Any]],
        temperature: float,
        model: str | None,
        max_tokens: int | None,
        stream: bool,
    ) -> dict[str, Any]:
        options: dict[str, Any] = {"temperature": temperature}
        if max_tokens:
            options["num_predict"] = max_tokens
        if self.threads:
            options["num_thread"] = self.threads
        # 30 min keep-alive: reloading a 3B model costs several seconds on the first question after a pause.
        return {
            "model": model or self.model,
            "messages": messages,
            "stream": stream,
            "keep_alive": "30m",
            "options": options,
        }

    def _answer_messages(self, question, history, memories) -> list[dict[str, Any]]:
        system = prompts.ANSWER_SYSTEM + prompts.memory_context(memories)
        return [{"role": "system", "content": system}, *history[-6:], {"role": "user", "content": question}]

    def answer(self, question: str, history: list[dict[str, str]], memories: list[str] | None = None) -> str:
        text = self._chat(self._answer_messages(question, history, memories), temperature=0.4, max_tokens=ANSWER_TOKENS)
        if not text:
            raise AiUnavailable("The language model returned an empty answer.")
        return text

    def answer_stream(
        self, question: str, history: list[dict[str, str]], memories: list[str] | None = None
    ) -> Iterator[str]:
        payload = self._payload(self._answer_messages(question, history, memories), 0.4, None, ANSWER_TOKENS, True)
        req = urllib.request.Request(
            f"{self.base_url}/api/chat", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
        )
        started, produced = time.time(), False
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:  # noqa: S310 - configured local URL
                for line in resp:
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    if chunk.get("error"):
                        raise AiUnavailable(str(chunk["error"]))
                    piece = (chunk.get("message") or {}).get("content", "")
                    if piece:
                        if not produced:
                            log.info("LLM first token after %.2fs", time.time() - started)
                        produced = True
                        yield piece
                    if chunk.get("done"):
                        break
        except AiUnavailable:
            raise
        except urllib.error.HTTPError as exc:
            raise self._http_error(exc) from exc
        except (TimeoutError, urllib.error.URLError, ConnectionError, OSError) as exc:
            if produced:
                raise AiUnavailable("The language model stopped responding mid-answer.") from exc
            raise AiUnavailable(
                f"The language model didn't respond within {self.timeout_s} seconds, or Ollama isn't running."
            ) from exc
        log.info("LLM streamed answer in %.2fs", time.time() - started)
        if not produced:
            raise AiUnavailable("The language model returned an empty answer.")

    def warm_up(self) -> None:
        if not self.available():
            return
        try:
            # An empty prompt makes Ollama load the model without generating anything.
            # Same options as real requests: a different num_thread makes Ollama reload the model on the first question.
            body = {"model": self.model, "prompt": "", "keep_alive": "30m"}
            if self.threads:
                body["options"] = {"num_thread": self.threads}
            self._request("/api/generate", body, timeout=180)
            log.info("Language model %s loaded and ready", self.model)
        except AiUnavailable as exc:
            log.warning("Couldn't preload the language model: %s", exc)

    def answer_with_memory(self, question: str, facts: list[str]) -> str:
        messages = [
            {"role": "system", "content": prompts.MEMORY_SYSTEM + prompts.memory_context(facts)},
            {"role": "user", "content": question},
        ]
        text = self._chat(messages, temperature=0.2, max_tokens=80)
        if not text:
            raise AiUnavailable("The language model returned an empty answer.")
        return text

    def answer_from_sources(self, question: str, results: list[dict[str, str]]) -> str:
        messages = [
            {"role": "system", "content": prompts.SOURCES_SYSTEM},
            {"role": "user", "content": prompts.sources_user(question, results)},
        ]
        text = self._chat(messages, temperature=0.2, max_tokens=160)
        if not text:
            raise AiUnavailable("The language model returned an empty answer.")
        return text

    def plan(
        self, utterance: str, catalog: str, action_names: list[str], history: list[dict[str, str]]
    ) -> dict[str, Any]:
        schema = prompts.plan_schema(action_names)
        messages = [
            {"role": "system", "content": prompts.plan_system(catalog)},
            *history[-4:],
            {"role": "user", "content": utterance},
        ]
        raw = self._chat(messages, fmt=schema, temperature=0.0)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AiUnavailable("The language model returned invalid JSON.") from exc
        if not isinstance(data, dict):
            raise AiUnavailable("The language model returned an unexpected plan shape.")
        return data

    def describe_screen(
        self, screen_text: str, request: str | None, history: list[dict[str, str]], image_b64: str | None = None
    ) -> str:
        user: dict[str, Any] = {"role": "user", "content": prompts.screen_user(screen_text, request)}
        model = None
        if image_b64 and self.vision_available():
            user["images"] = [image_b64]
            model = self.vision_model
        # No conversation history here: every prompt token costs ~40 ms on CPU, and the screen is self-contained.
        messages = [{"role": "system", "content": prompts.SCREEN_SYSTEM}, user]
        text = self._chat(messages, temperature=0.3, model=model, max_tokens=90)
        if not text:
            raise AiUnavailable("The language model returned an empty description.")
        return text


def build_provider(settings) -> AiProvider:
    if not settings.llm_enabled:
        return NullProvider()
    return OllamaProvider(
        settings.llm_url, settings.llm_model, settings.llm_timeout_s, settings.vision_model, settings.llm_threads
    )
