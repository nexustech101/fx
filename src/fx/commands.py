"""
Public fx command surface.
"""

from __future__ import annotations

from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version as resolve_distribution_version
from pathlib import Path
from typing import Any

from registers import CommandRegistry

from fx.command_sets import register_all
from fx.context import FxContext
from fx.state import resolve_root


_FX_DISTRIBUTION_NAME = "fx-tool"
_SHELL_DESCRIPTION = "Manage registers projects, runtimes, packages, plugins, and cron jobs."


def _resolve_fx_version() -> str:
    try:
        return resolve_distribution_version(_FX_DISTRIBUTION_NAME)
    except PackageNotFoundError:
        return "dev"


FX_VERSION = _resolve_fx_version()


def build_registry() -> CommandRegistry:
    registry = CommandRegistry()

    @registry.context_factory
    def build_context(root: str = ".") -> FxContext:
        return FxContext(root=resolve_root(root), cwd=Path.cwd().resolve(), version=FX_VERSION)

    @registry.register(
        "version",
        description="Show fx version",
        tags=["meta"],
        examples=["version", "--version", "-V"],
    )
    @registry.option("--version", help="Show fx version")
    @registry.option("-V", help="Show fx version")
    def show_version() -> str:
        return f"fx {FX_VERSION}"

    register_all(registry)
    return registry


_registry = build_registry()


def ensure_plugins_loaded() -> None:
    """Compatibility no-op for callers from the plugin-loading era."""

    return None


def run(
    argv: Sequence[str] | None = None,
    *,
    print_result: bool = True,
    shell_prompt: str = "fx > ",
    shell_input_fn=None,
    shell_banner: bool = True,
    shell_banner_text: str | None = None,
    shell_title: str = "fx",
    shell_description: str = _SHELL_DESCRIPTION,
    shell_colors: bool | None = None,
    shell_usage: bool = True,
    rich: bool = False,
    theme: Any | None = None,
    output: str | None = None,
    quiet: bool = False,
    verbose: bool = False,
    no_color: bool = False,
    completion: bool = False,
    history: bool = False,
    multiline: bool = False,
    log_level: str | int | None = None,
    log_panel: bool = False,
    event_loop: Any | None = None,
) -> Any:
    return _registry.run(
        argv,
        print_result=print_result,
        shell_prompt=shell_prompt,
        shell_input_fn=shell_input_fn,
        shell_banner=shell_banner,
        shell_banner_text=shell_banner_text,
        shell_title=shell_title,
        shell_description=shell_description,
        shell_version=f"Version: {FX_VERSION}",
        shell_colors=shell_colors,
        shell_usage=shell_usage,
        rich=rich,
        theme=theme,
        output=output,
        quiet=quiet,
        verbose=verbose,
        no_color=no_color,
        completion=completion,
        history=history,
        multiline=multiline,
        log_level=log_level,
        log_panel=log_panel,
        event_loop=event_loop,
    )


async def run_async(
    argv: Sequence[str] | None = None,
    *,
    print_result: bool = True,
    rich: bool = False,
    output: str | None = None,
    quiet: bool = False,
    verbose: bool = False,
    no_color: bool = False,
    shell_input_fn=None,
    log_level: str | int | None = None,
) -> Any:
    return await _registry.run_async(
        argv,
        print_result=print_result,
        rich=rich,
        output=output,
        quiet=quiet,
        verbose=verbose,
        no_color=no_color,
        shell_input_fn=shell_input_fn,
        log_level=log_level,
    )


def get_registry() -> CommandRegistry:
    return _registry


def main(argv: Sequence[str] | None = None) -> int:
    run(argv)
    return 0


__all__ = [
    "FX_VERSION",
    "build_registry",
    "ensure_plugins_loaded",
    "get_registry",
    "main",
    "run",
    "run_async",
]
