"""Core action types shared by the registry, executor and action modules.

An action is the ONLY way JARVIS touches the operating system. The AI or the
rule matcher produces `PlanStep`s (data); the executor validates them against
the registered `ActionSpec` and decides whether/how they run.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from jarvis.core.context import ExecContext


class PermissionLevel(StrEnum):
    READ_ONLY = "READ_ONLY"
    SAFE = "SAFE"
    SENSITIVE = "SENSITIVE"
    DESTRUCTIVE = "DESTRUCTIVE"
    BLOCKED = "BLOCKED"


class ActionError(Exception):
    """A user-facing, typed failure raised by validation, prepare or run."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class Params(BaseModel):
    """Base for every action's parameter schema — unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class NoParams(Params):
    pass


class PlanStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    params: dict[str, Any] = {}


@dataclass
class Offer:
    """A follow-up the assistant proposes ("Shall I search online?").

    Accepting an offer is an explicit user confirmation for its first step.
    """

    question: str
    steps: list[PlanStep]


@dataclass
class ActionResult:
    ok: bool
    message: str
    data: dict[str, Any] | None = None
    error_code: str | None = None
    offer: Offer | None = None

    @classmethod
    def fail(cls, code: str, message: str, offer: Offer | None = None) -> ActionResult:
        return cls(ok=False, message=message, error_code=code, offer=offer)


@dataclass
class Prepared:
    """Output of an action's `prepare` step.

    `summary` is the concrete impact statement shown before confirmation;
    `data` binds the exact targets (e.g. resolved file paths) so that what the
    user confirmed is exactly what runs.
    """

    summary: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


Handler = Callable[[Any, "ExecContext", Prepared | None], ActionResult]
Preparer = Callable[[Any, "ExecContext"], Prepared]


@dataclass(frozen=True)
class ActionSpec:
    name: str
    description: str
    params_model: type[Params]
    permission: PermissionLevel
    handler: Handler
    prepare: Preparer | None = None
    timeout_s: float = 15.0
    online: bool = False
    # Shown to the LLM planner; keep short.
    examples: tuple[str, ...] = ()
    # Parameters whose values must never be written to logs.
    sensitive_params: tuple[str, ...] = ()

    @property
    def requires_confirmation(self) -> bool:
        return self.permission in (PermissionLevel.SENSITIVE, PermissionLevel.DESTRUCTIVE)
