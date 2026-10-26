"""Conversation actions: canned replies, LLM answers, arithmetic, refusals."""

from __future__ import annotations

import ast
import operator

from pydantic import Field

from jarvis.actions.base import ActionError, ActionResult, ActionSpec, Offer, Params, PermissionLevel, PlanStep
from jarvis.actions.memory import relevant_memories
from jarvis.ai.provider import AiUnavailable
from jarvis.nlp.speech import to_speech


class ReplyParams(Params):
    text: str = Field(min_length=1, max_length=500)


def reply(params: ReplyParams, ctx, prepared) -> ActionResult:
    return ActionResult(True, params.text)


class QuestionParams(Params):
    question: str = Field(min_length=1, max_length=500)


def answer_question(params: QuestionParams, ctx, prepared) -> ActionResult:
    try:
        memories = [m["text"] for m in relevant_memories(ctx.store, params.question)]
        if ctx.on_delta is not None:
            parts: list[str] = []
            for piece in ctx.ai.answer_stream(params.question, ctx.session.history_list(), memories):
                parts.append(piece)
                ctx.on_delta(piece)
            text = "".join(parts).strip()
        else:
            text = ctx.ai.answer(params.question, ctx.session.history_list(), memories)
    except AiUnavailable as exc:
        offer = None
        if ctx.connectivity.online():
            offer = Offer(
                "Shall I look it up on the web instead?",
                [PlanStep(action="web_answer", params={"query": params.question})],
            )
        result = ActionResult.fail(
            "AI_UNAVAILABLE", "My offline language model isn't available right now.", offer=offer
        )
        result.data = {"detail": str(exc)}  # shown in the UI, not spoken
        return result
    return ActionResult(True, text, data={"source": "llm", "speech": to_speech(text), "markdown": True})


class CalcParams(Params):
    expression: str = Field(min_length=1, max_length=120, pattern=r"^[\d\s.+\-*/()%]+$")


_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def safe_eval(expression: str) -> float:
    """Evaluate +-*/%** arithmetic only. No names, calls or attributes."""

    def ev(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            left, right = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 100:
                raise ActionError("INVALID_PARAMS", "That exponent is too large.")
            return _OPS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.operand))
        raise ActionError("INVALID_PARAMS", "I can only do basic arithmetic.")

    try:
        return ev(ast.parse(expression, mode="eval"))
    except ZeroDivisionError as exc:
        raise ActionError("MATH_ERROR", "That would divide by zero.") from exc
    except SyntaxError as exc:
        raise ActionError("INVALID_PARAMS", "I couldn't read that calculation.") from exc


def _fmt(value: float) -> str:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, float):
        return f"{value:,.6g}"
    return f"{value:,}"


def calculate(params: CalcParams, ctx, prepared) -> ActionResult:
    value = safe_eval(params.expression)
    return ActionResult(True, f"That's {_fmt(value)}.", data={"value": value})


class RefuseParams(Params):
    reason: str = Field(default="That request is blocked for safety.", max_length=300)


def refuse(params: RefuseParams, ctx, prepared) -> ActionResult:
    # Never executed: the executor refuses BLOCKED actions before calling handlers.
    return ActionResult.fail("BLOCKED", params.reason)


SPECS = [
    ActionSpec(
        "reply",
        "Say a short fixed reply (greetings, thanks, small talk).",
        ReplyParams,
        PermissionLevel.READ_ONLY,
        reply,
    ),
    ActionSpec(
        "answer_question",
        "Answer a general knowledge question conversationally using the offline model.",
        QuestionParams,
        PermissionLevel.READ_ONLY,
        answer_question,
        timeout_s=120,
        examples=("what is docker", "explain recursion"),
    ),
    ActionSpec(
        "calculate",
        "Evaluate an arithmetic expression using digits and + - * / % ( ).",
        CalcParams,
        PermissionLevel.READ_ONLY,
        calculate,
        examples=("25*18",),
    ),
    ActionSpec(
        "blocked_request",
        "Shell commands, scripts, installs, payments, messages, shutdown. Always refused.",
        RefuseParams,
        PermissionLevel.BLOCKED,
        refuse,
    ),
]
