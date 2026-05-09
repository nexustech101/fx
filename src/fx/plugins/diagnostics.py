from __future__ import annotations

from registers import CommandRegistry

from fx.command_sets import project


def register(registry: CommandRegistry) -> None:
    """Compatibility wrapper for the former diagnostics plugin module."""

    project.register(registry)


__all__ = ["register"]
