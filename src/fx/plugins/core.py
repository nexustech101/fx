from __future__ import annotations

from registers import CommandRegistry

from fx.command_sets import modules, plugin, project


def register(registry: CommandRegistry) -> None:
    """Compatibility wrapper for the former core plugin module."""

    project.register(registry)
    modules.register(registry)
    plugin.register(registry)


__all__ = ["register"]
