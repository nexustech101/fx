from __future__ import annotations

from registers import CommandRegistry

from fx.command_sets import cron, modules, package, plugin, project, run


def register_all(registry: CommandRegistry) -> None:
    """Register all built-in fx command groups on ``registry``."""

    project.register(registry)
    modules.register(registry)
    plugin.register(registry)
    run.register(registry)
    package.register(registry)
    cron.register(registry)


__all__ = ["register_all"]
