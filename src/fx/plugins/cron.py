from __future__ import annotations

from registers import CommandRegistry

from fx.command_sets import cron


def register(registry: CommandRegistry) -> None:
    """Compatibility wrapper for the former cron plugin module."""

    cron.register(registry)


__all__ = ["register"]
