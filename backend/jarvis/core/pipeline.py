"""The orchestrator: utterance -> intent -> validated plan -> permission/confirmation -> execution.

    VOICE/TEXT → IntentMatcher (rules) ─┬→ steps
                                        └→ LLM planner (fallback, JSON only)
    steps → registry.validate → BLOCKED? refuse → online? → prepare → confirm? → handler → result

The AI decides WHAT should happen; this module decides HOW it safely runs.
"""

from __future__ import annotations

import logging
import re
import secrets
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel

from jarvis.actions.base import ActionError, ActionResult, ActionSpec, PermissionLevel, PlanStep, Prepared
from jarvis.actions.registry import ActionRegistry
from jarvis.ai.provider import AiProvider, AiUnavailable
from jarvis.core.context import Connectivity, ExecContext, SessionContext, SessionStore
from jarvis.core.intent import Intent, IntentMatcher, IntentResult
from jarvis.logging_setup import log_event, redact
from jarvis.nlp.speech import to_speech
from jarvis.security.confirmation import Confirmation, ConfirmationStore

log = logging.getLogger("jarvis.pipeline")

PLAN_TTL_S = 120.0


class StepView(BaseModel):
    action: str
    params: dict[str, Any]
    permission: str
    requires_confirmation: bool
    description: str


class StepResult(BaseModel):
    action: str
    ok: bool
    message: str
    error_code: str | None = None
    data: dict[str, Any] | None = None
    latency_ms: int = 0


class PlanResponse(BaseModel):
    request_id: str
    status: Literal["ready", "needs_clarification", "confirmation_decision", "empty", "error"]
    intent: str
    source: str = "rules"
    text: str = ""
    plan_id: str | None = None
    steps: list[StepView] = []
    reply: str | None = None
    error_code: str | None = None
    confirmation_id: str | None = None
    decision: Literal["confirm", "cancel"] | None = None
    confidence: float = 1.0
    entities: dict[str, Any] = {}
    risk: str = "READ_ONLY"


class ExecResponse(BaseModel):
    request_id: str
    status: Literal["done", "needs_confirmation", "needs_clarification", "cancelled", "error", "empty"]
    intent: str = ""
    reply: str = ""
    results: list[StepResult] = []
    confirmation: dict[str, Any] | None = None
    error_code: str | None = None
    # PDF §19 contract: success flag, response type, and the text to speak (may be shorter than `reply`).
    success: bool = True
    response_type: Literal["conversation", "action", "confirmation", "clarification", "error"] = "action"
    speech: str = ""
    # True when the voice already said the answer sentence by sentence while it streamed.
    spoken_live: bool = False

    def model_post_init(self, _ctx: Any) -> None:
        self.success = self.status not in ("error",)
        if self.status == "needs_confirmation":
            self.response_type = "confirmation"
        elif self.status == "needs_clarification":
            self.response_type = "clarification"
        elif self.status == "error":
            self.response_type = "error"
        elif self.results and all(r.action in CONVERSATION_ACTIONS for r in self.results):
            self.response_type = "conversation"
        if not self.speech:
            text, exact = self.reply, False
            for r in self.results:
                data = r.data or {}
                spoken = data.get("speech")
                if spoken is not None and r.message and r.message in text:
                    text = text.replace(r.message, spoken)
                    exact = exact or bool(data.get("speech_exact"))
            # speech_exact: the action wrote its spoken version on purpose (briefing, news) or already said it live.
            self.speech = " ".join(text.split()) if exact else to_speech(text, max_words=60)
            self.spoken_live = any((r.data or {}).get("spoken_live") for r in self.results)


CONVERSATION_ACTIONS = {
    "reply",
    "answer_question",
    "calculate",
    "memory_recall",
    "memory_list",
    "web_answer",
    "describe_screen",
    "system_information",
    "note_read",
    "note_list",
    "task_list",
    "event_list",
    "daily_briefing",
    "schedule_today",
    "news_headlines",
}
ENTITY_KEYS = (
    "app",
    "query",
    "url",
    "path",
    "folder",
    "known",
    "destination",
    "title",
    "due",
    "date",
    "time",
    "priority",
    "text",
    "name",
    "new_name",
    "question",
    "topic",
    "command",
    "value",
)
PERMISSION_ORDER = ["READ_ONLY", "SAFE", "SENSITIVE", "DESTRUCTIVE", "BLOCKED"]
LOW_CONFIDENCE = 0.45
_DEFAULT_CONFIDENCE = {
    "COMMAND": 0.9,
    "COMPOUND": 0.85,
    "SMALL_TALK": 0.95,
    "QUESTION": 0.8,
    "REALTIME_QUERY": 0.75,
    "BLOCKED": 0.95,
    "UNKNOWN": 0.2,
    "AMBIGUOUS": 0.3,
}


@dataclass
class _StoredPlan:
    session_id: str
    steps: list[PlanStep]
    intent: str
    text: str
    created: float


# "Greetings.txt created." / "I've opened it": completion claims only an executed step may make. Short
# announcements and first-person claims count; a knowledge answer ("C was created by Dennis Ritchie") doesn't.
_DONE_VERB = r"(?:created|saved|opened|deleted|moved|copied|renamed|written|launched|closed|added|done)"
_FIRST_PERSON_DONE = re.compile(rf"\bi(?:'ve| have)? (?:just |now )?{_DONE_VERB}\b", re.IGNORECASE)
_SHORT_DONE = re.compile(rf"\b{_DONE_VERB}\b(?! by\b)", re.IGNORECASE)


def _claims_done(text: str) -> bool:
    return bool(_FIRST_PERSON_DONE.search(text) or (len(text) <= 80 and _SHORT_DONE.search(text)))


def _as_confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.6  # model omitted it: treat as moderately sure, not certain


class Pipeline:
    def __init__(
        self,
        *,
        settings,
        registry: ActionRegistry,
        matcher: IntentMatcher,
        ai: AiProvider,
        platform,
        apps,
        files,
        connectivity: Connectivity | None = None,
        confirmations: ConfirmationStore | None = None,
        ocr=None,
        store=None,
        news=None,
    ) -> None:
        self.ocr = ocr
        self.store = store
        self.news = news
        self.settings = settings
        self.registry = registry
        self.matcher = matcher
        self.ai = ai
        self.platform = platform
        self.apps = apps
        self.files = files
        self.connectivity = connectivity or Connectivity()
        self.confirmations = confirmations or ConfirmationStore()
        self.sessions = SessionStore()
        self._plans: dict[str, _StoredPlan] = {}
        self._lock = threading.RLock()
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="jarvis-action")

    # ------------------------------------------------------------ public API
    def plan(self, text: str, session_id: str = "default") -> PlanResponse:
        rid = secrets.token_hex(6)
        text = (text or "").strip()
        if len(text) > self.settings.max_command_chars:
            return PlanResponse(
                request_id=rid,
                status="error",
                intent="ERROR",
                text=text[:80],
                reply="That request is too long.",
                error_code="TOO_LONG",
            )
        with self._lock:
            session = self.sessions.get(session_id)
            started = time.time()
            result = self.matcher.parse(text, session)
            if result.intent is Intent.UNKNOWN:
                result = self._llm_plan(text, session)
            log_event(
                log,
                "plan",
                request_id=rid,
                intent=result.intent.value,
                source=result.source,
                steps=[{"action": s.action, "params": self._redacted(s)} for s in result.steps],
                latency_ms=int((time.time() - started) * 1000),
            )
            return self._plan_response(rid, result, session)

    def execute(
        self,
        plan_id: str,
        session_id: str = "default",
        on_delta: Callable[[str], None] | None = None,
        on_say: Callable[[str], None] | None = None,
    ) -> ExecResponse:
        """`on_delta` receives answer text as it is generated, `on_say` each finished spoken sentence (streaming)."""
        rid = secrets.token_hex(6)
        with self._lock:
            stored = self._plans.pop(plan_id, None)
            if stored is None or stored.session_id != session_id or time.time() - stored.created > PLAN_TTL_S:
                return ExecResponse(
                    request_id=rid,
                    status="error",
                    error_code="PLAN_EXPIRED",
                    reply="That plan expired. Please say it again.",
                )
            session = self.sessions.get(session_id)
            # A new command abandons any question that was still pending.
            self.confirmations.cancel_session(session_id)
            resp = self._run(rid, stored.steps, session, on_delta=on_delta, on_say=on_say)
            resp.intent = stored.intent
            session.add_turn(stored.text, resp.reply)
            return resp

    def confirm(self, confirmation_id: str, decision: str, session_id: str = "default") -> ExecResponse:
        rid = secrets.token_hex(6)
        with self._lock:
            conf = self.confirmations.take(confirmation_id, session_id)
            session = self.sessions.get(session_id)
            if conf is None:
                return ExecResponse(
                    request_id=rid,
                    status="error",
                    error_code="CONFIRMATION_EXPIRED",
                    reply="That request expired, so I didn't do anything.",
                )
            log_event(
                log,
                "confirmation",
                request_id=rid,
                decision=decision,
                kind=conf.kind,
                action=conf.steps[0].action if conf.steps else None,
            )
            if decision != "confirm":
                reply = "Okay." if conf.kind == "offer" else "Cancelled. Nothing was changed."
                session.add_turn("", reply)
                return ExecResponse(request_id=rid, status="cancelled", reply=reply)
            resp = self._run(rid, conf.steps, session, first_confirmed=True, first_prepared=conf.prepared_first)
            session.add_turn("", resp.reply)
            return resp

    def command(self, text: str, session_id: str = "default") -> ExecResponse:
        """Plan + execute in one call (CLI, tests, and simple clients)."""
        plan = self.plan(text, session_id)
        if plan.status == "ready" and plan.plan_id:
            return self.execute(plan.plan_id, session_id)
        if plan.status == "confirmation_decision" and plan.confirmation_id and plan.decision:
            return self.confirm(plan.confirmation_id, plan.decision, session_id)
        status = {"needs_clarification": "needs_clarification", "empty": "empty"}.get(plan.status, "error")
        return ExecResponse(
            request_id=plan.request_id,
            status=status,
            intent=plan.intent,
            reply=plan.reply or "",
            error_code=plan.error_code,
        )

    # ------------------------------------------------------------ planning
    def _plan_response(self, rid: str, result: IntentResult, session: SessionContext) -> PlanResponse:
        base = {"request_id": rid, "intent": result.intent.value, "source": result.source, "text": result.text}
        if result.intent is Intent.EMPTY:
            return PlanResponse(status="empty", **base)
        if result.intent in (Intent.CONFIRM_YES, Intent.CONFIRM_NO):
            pending = self.confirmations.pending(session.session_id)
            if pending is not None:
                return PlanResponse(
                    status="confirmation_decision",
                    confirmation_id=pending.id,
                    decision="confirm" if result.intent is Intent.CONFIRM_YES else "cancel",
                    **base,
                )
            # Nothing pending: "open it" / "play it" may still be a real command.
            reparsed = self.matcher.parse(result.text, session, confirmations=False)
            if reparsed.intent in (Intent.UNKNOWN, Intent.SMALL_TALK, Intent.EMPTY):
                reply = (
                    "There's nothing waiting for your confirmation." if result.intent is Intent.CONFIRM_YES else "Okay."
                )
                reparsed = IntentResult(
                    Intent.SMALL_TALK, [PlanStep(action="reply", params={"text": reply})], result.text
                )
            result = reparsed
            base["intent"] = result.intent.value
        confidence = (
            result.confidence if result.confidence is not None else _DEFAULT_CONFIDENCE.get(result.intent.value, 0.8)
        )
        base["confidence"] = round(float(confidence), 2)
        base["entities"] = {
            k: v for st in result.steps for k, v in st.params.items() if k in ENTITY_KEYS and v not in (None, "", False)
        }
        if result.intent is Intent.AMBIGUOUS:
            return PlanResponse(status="needs_clarification", reply=result.clarification, **base)
        if not result.steps:
            return PlanResponse(
                status="error", reply="I'm not sure how to help with that.", error_code="NO_PLAN", **base
            )

        views = []
        for st in result.steps:
            try:
                spec, _ = self.registry.validate(st)
            except ActionError as exc:
                return PlanResponse(status="error", reply=exc.message, error_code=exc.code, **base)
            views.append(
                StepView(
                    action=spec.name,
                    params=self._redacted(st),
                    permission=spec.permission.value,
                    requires_confirmation=spec.requires_confirmation,
                    description=spec.description,
                )
            )
        plan_id = secrets.token_urlsafe(12)
        self._gc_plans()
        self._plans[plan_id] = _StoredPlan(
            session.session_id, result.steps, result.intent.value, result.text, time.time()
        )
        base["risk"] = max((v.permission for v in views), key=PERMISSION_ORDER.index)
        return PlanResponse(status="ready", plan_id=plan_id, steps=views, **base)

    def _llm_plan(self, text: str, session: SessionContext) -> IntentResult:
        not_understood = IntentResult(
            Intent.UNKNOWN,
            [PlanStep(action="reply", params={"text": "I didn't understand that. Say 'help' to hear what I can do."})],
            text,
        )
        if not self.ai.available():
            return not_understood
        catalog = self.registry.catalog_compact()
        action_names = [c["action"] for c in self.registry.catalog()]
        error_note = ""
        for _attempt in range(2):
            try:
                data = self.ai.plan(text + error_note, catalog, action_names, session.history_list())
            except AiUnavailable as exc:
                log.warning("LLM planning unavailable: %s", exc)
                return not_understood
            kind = data.get("kind")
            reply_text = str(data.get("text") or "")[:500]
            if kind == "answer" and reply_text and _claims_done(reply_text):
                # Only executed steps change anything. An "answer" that says it did something is false (PDF §21).
                log_event(log, "llm_plan_rejected", level=logging.WARNING, reason="answer claimed an action")
                return IntentResult(
                    Intent.UNKNOWN,
                    [PlanStep(action="reply", params={"text": "I can't do that with my current abilities."})],
                    text,
                    source="llm",
                )
            if kind == "answer" and reply_text:
                return IntentResult(
                    Intent.QUESTION, [PlanStep(action="reply", params={"text": reply_text})], text, source="llm"
                )
            if kind == "clarify":
                return IntentResult(
                    Intent.AMBIGUOUS, text=text, clarification=reply_text or "Could you rephrase that?", source="llm"
                )
            if kind == "unsupported":
                return IntentResult(
                    Intent.UNKNOWN,
                    [
                        PlanStep(
                            action="reply", params={"text": reply_text or "I can't do that with my current abilities."}
                        )
                    ],
                    text,
                    source="llm",
                )
            if kind == "plan":
                try:
                    steps = [PlanStep.model_validate(s) for s in data.get("steps", [])][:6]
                    if not steps:
                        raise ActionError("NO_PLAN", "The plan had no steps.")
                    for st in steps:
                        if st.action not in action_names:
                            raise ActionError("UNKNOWN_ACTION", f"{st.action} is not one of the listed actions.")
                        spec, _ = self.registry.validate(st)
                        if spec.permission is PermissionLevel.BLOCKED:
                            raise ActionError("BLOCKED", f"{spec.name} is not allowed.")
                    intent = Intent.COMPOUND if len(steps) > 1 else Intent.COMMAND
                    confidence = _as_confidence(data.get("confidence"))
                    if confidence < LOW_CONFIDENCE:
                        guess = reply_text or ", ".join(st.action.replace("_", " ") for st in steps)
                        return IntentResult(
                            Intent.AMBIGUOUS,
                            text=text,
                            source="llm",
                            confidence=confidence,
                            clarification=f"I'm not sure I understood. Did you mean: {guess}?",
                        )
                    return IntentResult(intent, steps, text, source="llm", confidence=confidence)
                except (ActionError, ValueError) as exc:
                    message = exc.message if isinstance(exc, ActionError) else str(exc)
                    log_event(log, "llm_plan_rejected", level=logging.WARNING, reason=message)
                    error_note = (
                        f"\n(Your previous plan was rejected: {message}. Use only the listed actions and parameters.)"
                    )
                    continue
            error_note = "\n(Respond with the required JSON shape.)"
        return IntentResult(
            Intent.UNKNOWN,
            [PlanStep(action="reply", params={"text": "I'm not sure how to do that safely."})],
            text,
            source="llm",
        )

    def _gc_plans(self) -> None:
        cutoff = time.time() - PLAN_TTL_S
        for pid in [p for p, v in self._plans.items() if v.created < cutoff]:
            self._plans.pop(pid, None)

    # ------------------------------------------------------------ execution
    def _context(
        self,
        session: SessionContext,
        on_delta: Callable[[str], None] | None = None,
        on_say: Callable[[str], None] | None = None,
    ) -> ExecContext:
        return ExecContext(
            settings=self.settings,
            platform=self.platform,
            apps=self.apps,
            files=self.files,
            ai=self.ai,
            connectivity=self.connectivity,
            session=session,
            ocr=self.ocr,
            store=self.store,
            news=self.news,
            on_delta=on_delta,
            on_say=on_say,
        )

    def _run(
        self,
        rid: str,
        steps: list[PlanStep],
        session: SessionContext,
        *,
        first_confirmed: bool = False,
        first_prepared: Prepared | None = None,
        on_delta: Callable[[str], None] | None = None,
        on_say: Callable[[str], None] | None = None,
    ) -> ExecResponse:
        ctx = self._context(session, on_delta, on_say)
        results: list[StepResult] = []
        messages: list[str] = []

        def finish(status, reply=None, confirmation: Confirmation | None = None, code=None) -> ExecResponse:
            text = reply if reply is not None else " ".join(m for m in messages if m)
            if code == "AMBIGUOUS":  # "which one do you mean?" is a question, not a failure
                status = "needs_clarification"
            return ExecResponse(
                request_id=rid,
                status=status,
                reply=text,
                results=results,
                error_code=code,
                confirmation=confirmation.public() if confirmation else None,
            )

        for i, st in enumerate(steps):
            try:
                spec, params = self.registry.validate(st)
            except ActionError as exc:
                results.append(StepResult(action=st.action, ok=False, message=exc.message, error_code=exc.code))
                return finish("error", " ".join([*messages, exc.message]), code=exc.code)

            if spec.permission is PermissionLevel.BLOCKED:
                reason = getattr(params, "reason", None) or "That action is blocked for safety."
                log_event(log, "blocked", level=logging.WARNING, request_id=rid, action=spec.name)
                results.append(StepResult(action=spec.name, ok=False, message=reason, error_code="BLOCKED"))
                return finish("error", reason, code="BLOCKED")

            if spec.online and not ctx.connectivity.online():
                msg = "I'm offline right now, so I can't do that. Local commands still work."
                results.append(StepResult(action=spec.name, ok=False, message=msg, error_code="OFFLINE"))
                return finish("error", " ".join([*messages, msg]), code="OFFLINE")

            confirmed_now = first_confirmed and i == 0
            prepared = first_prepared if confirmed_now else None
            if prepared is None and spec.prepare is not None:
                outcome = self._call(spec, spec.prepare, (params, ctx))
                if isinstance(outcome, ActionResult):  # prepare failed
                    results.append(self._step_result(spec, outcome, 0))
                    self._log_step(rid, spec, st, outcome, 0)
                    return finish("error", " ".join([*messages, outcome.message]), code=outcome.error_code)
                prepared = outcome

            if spec.requires_confirmation and not confirmed_now:
                summary = (
                    prepared.summary
                    if prepared and prepared.summary
                    else f"This will run: {spec.description.rstrip('.')}."
                )
                conf = self.confirmations.create(
                    session.session_id, "confirm", summary, steps[i:], prepared, spec.permission.value
                )
                log_event(
                    log, "confirmation_required", request_id=rid, action=spec.name, permission=spec.permission.value
                )
                return finish(
                    "needs_confirmation", " ".join([*messages, f"{summary} Do you want me to proceed?"]), conf
                )

            started = time.time()
            outcome = self._call(spec, spec.handler, (params, ctx, prepared))
            latency = int((time.time() - started) * 1000)
            result = (
                outcome
                if isinstance(outcome, ActionResult)
                else ActionResult.fail("INTERNAL_ERROR", f"{spec.name} returned an invalid result.")
            )
            self._log_step(rid, spec, st, result, latency)
            results.append(self._step_result(spec, result, latency))
            messages.append(result.message)

            is_last = i == len(steps) - 1
            if result.offer and (is_last or not result.ok):
                conf = self.confirmations.create(
                    session.session_id,
                    "offer",
                    result.offer.question,
                    result.offer.steps,
                    None,
                    PermissionLevel.SAFE.value,
                )
                return finish("needs_confirmation", " ".join([*messages, result.offer.question]), conf)
            if not result.ok:
                return finish("error", code=result.error_code)

        return finish("done")

    def _call(self, spec: ActionSpec, fn, args: tuple) -> Any:
        """Run prepare/handler with a timeout; convert every failure into a typed ActionResult."""
        future = self._pool.submit(fn, *args)
        try:
            return future.result(timeout=spec.timeout_s)
        except FutureTimeout:
            return ActionResult.fail("TIMEOUT", f"{spec.name.replace('_', ' ')} took too long, so I stopped waiting.")
        except ActionError as exc:
            return ActionResult.fail(exc.code, exc.message)
        except Exception:  # noqa: BLE001 - never crash the assistant on an action bug
            log.exception("Action %s crashed", spec.name)
            return ActionResult.fail(
                "INTERNAL_ERROR", f"Something went wrong while running {spec.name.replace('_', ' ')}."
            )

    def _redacted(self, st: PlanStep) -> dict[str, Any]:
        spec = self.registry.get(st.action)
        return redact(dict(st.params), spec.sensitive_params if spec else ())

    @staticmethod
    def _step_result(spec: ActionSpec, result: ActionResult, latency: int) -> StepResult:
        data = result.data
        if spec.sensitive_params and data:
            data = redact(data, spec.sensitive_params)
        return StepResult(
            action=spec.name,
            ok=result.ok,
            message=result.message,
            error_code=result.error_code,
            data=data,
            latency_ms=latency,
        )

    def _log_step(self, rid: str, spec: ActionSpec, st: PlanStep, result: ActionResult, latency: int) -> None:
        log_event(
            log,
            "action",
            level=logging.INFO if result.ok else logging.WARNING,
            request_id=rid,
            action=spec.name,
            permission=spec.permission.value,
            params=self._redacted(st),
            ok=result.ok,
            error_code=result.error_code,
            latency_ms=latency,
        )
