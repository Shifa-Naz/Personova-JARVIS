"""Registered actions. `build_registry()` is the single source of what JARVIS can do."""

from __future__ import annotations

from jarvis.actions.registry import ActionRegistry


def build_registry() -> ActionRegistry:
    from jarvis.actions import (
        apps,
        automation,
        briefing,
        browser,
        conversation,
        files,
        media,
        memory,
        productivity,
        screen,
        system,
        web,
    )

    registry = ActionRegistry()
    for module in (
        conversation,
        memory,
        productivity,
        briefing,
        web,
        apps,
        browser,
        files,
        media,
        system,
        screen,
        automation,
    ):
        registry.register_all(module.SPECS)
    return registry
