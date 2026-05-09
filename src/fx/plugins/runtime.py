from __future__ import annotations

from registers import CommandRegistry

from fx.command_sets import package, run


def register(registry: CommandRegistry) -> None:
    """Compatibility wrapper for the former runtime plugin module."""

    run.register(registry)
    package.register(registry)


__all__ = ["register"]
