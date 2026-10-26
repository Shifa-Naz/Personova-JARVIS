"""Central allow-list of actions. Anything not registered here cannot run."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from jarvis.actions.base import ActionError, ActionSpec, Params, PermissionLevel, PlanStep

NOT_FOR_PLANNER = frozenset({"reply"})


class ActionRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, ActionSpec] = {}

    def register(self, spec: ActionSpec) -> None:
        if spec.name in self._specs:
            raise ValueError(f"Action already registered: {spec.name}")
        self._specs[spec.name] = spec

    def register_all(self, specs: list[ActionSpec]) -> None:
        for spec in specs:
            self.register(spec)

    def get(self, name: str) -> ActionSpec | None:
        return self._specs.get(name)

    def names(self) -> list[str]:
        return sorted(self._specs)

    def validate(self, step: PlanStep) -> tuple[ActionSpec, Params]:
        spec = self._specs.get(step.action)
        if spec is None:
            raise ActionError("UNKNOWN_ACTION", f"I don't have an action called '{step.action}'.")
        try:
            params = spec.params_model.model_validate(step.params)
        except ValidationError as exc:
            first = exc.errors()[0]
            where = ".".join(str(p) for p in first.get("loc", ())) or "parameters"
            raise ActionError("INVALID_PARAMS", f"The {where} for {spec.name} is invalid: {first.get('msg')}.") from exc
        return spec, params

    def _for_planner(self) -> list[ActionSpec]:
        # `reply` only says fixed text. Offering it to the planner let the model "do" a task by announcing it
        # ("Greetings.txt created.") with nothing run. The planner answers through kind "answer" instead.
        return [
            s
            for s in self._specs.values()
            if s.permission is not PermissionLevel.BLOCKED and s.name not in NOT_FOR_PLANNER
        ]

    def catalog_compact(self) -> str:
        """One line per action for the LLM planner: `name(required, optional?) - description`.

        About a fifth of the size of the JSON-schema catalog. On a CPU that reads prompts at ~26 tokens/s,
        the full catalog alone took ~3 minutes; parameters are still validated by pydantic after planning.
        """
        lines = []
        for spec in self._for_planner():
            schema = spec.params_model.model_json_schema()
            required = set(schema.get("required", []))
            params = [p if p in required else f"{p}?" for p in schema.get("properties", {})]
            lines.append(f"{spec.name}({', '.join(params)}) - {spec.description}")
        return "\n".join(lines)

    def catalog(self) -> list[dict[str, Any]]:
        """Action descriptions + JSON schemas for the LLM planner (BLOCKED excluded)."""
        out = []
        for spec in self._for_planner():
            schema = spec.params_model.model_json_schema()
            out.append(
                {
                    "action": spec.name,
                    "description": spec.description,
                    "params": schema.get("properties", {}),
                    "required": schema.get("required", []),
                    "examples": list(spec.examples),
                }
            )
        return out
