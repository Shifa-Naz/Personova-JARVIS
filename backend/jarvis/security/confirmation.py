"""Single-use, expiring confirmations bound to exact validated steps."""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass

from jarvis.actions.base import PlanStep, Prepared

DEFAULT_TTL_S = 60.0


@dataclass
class Confirmation:
    id: str
    session_id: str
    kind: str  # "confirm" (sensitive/destructive step) | "offer" (assistant suggestion)
    summary: str
    steps: list[PlanStep]
    prepared_first: Prepared | None
    permission: str
    expires_at: float

    def public(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "summary": self.summary,
            "permission": self.permission,
            "expires_at": self.expires_at,
            "action": self.steps[0].action if self.steps else None,
        }


class ConfirmationStore:
    def __init__(self, ttl_s: float = DEFAULT_TTL_S) -> None:
        self.ttl_s = ttl_s
        self._items: dict[str, Confirmation] = {}
        self._lock = threading.Lock()

    def create(
        self,
        session_id: str,
        kind: str,
        summary: str,
        steps: list[PlanStep],
        prepared_first: Prepared | None,
        permission: str,
    ) -> Confirmation:
        conf = Confirmation(
            id=secrets.token_urlsafe(12),
            session_id=session_id,
            kind=kind,
            summary=summary,
            steps=list(steps),
            prepared_first=prepared_first,
            permission=permission,
            expires_at=time.time() + self.ttl_s,
        )
        with self._lock:
            # Only one pending question per session: a new one replaces the old.
            for cid in [c.id for c in self._items.values() if c.session_id == session_id]:
                self._items.pop(cid, None)
            self._items[conf.id] = conf
        return conf

    def take(self, confirmation_id: str, session_id: str) -> Confirmation | None:
        with self._lock:
            conf = self._items.pop(confirmation_id, None)
        if conf is None or conf.session_id != session_id or conf.expires_at < time.time():
            return None
        return conf

    def pending(self, session_id: str) -> Confirmation | None:
        with self._lock:
            for conf in self._items.values():
                if conf.session_id == session_id and conf.expires_at >= time.time():
                    return conf
        return None

    def cancel_session(self, session_id: str) -> None:
        with self._lock:
            for cid in [c.id for c in self._items.values() if c.session_id == session_id]:
                self._items.pop(cid, None)
