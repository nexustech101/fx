"""
Public fx command surface.
"""

from __future__ import annotations

from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version as resolve_distribution_version
from threading import Lock
from typing import Any

from registers.cli.plugins import load_plugins
from registers.cli.registry import CommandRegistry


_registry = CommandRegistry()
_fx_DISTRIBUTION_NAME = "fx-tool"
_PLUGINS_PACKAGE = "fx.plugins"

project_group = _registry.group("project", description="Create and inspect fx projects")
run_group = _registry.group("run", description="Run project entrypoints")
module_group = _registry.group("module", description="Manage project modules")
plugin_group = _registry.group("plugin", description="Manage project plugin links")
package_group = _registry.group("package", description="Install, update, and pull packages")
cron_group = _registry.group("cron", description="Manage registers.cron projects")

_REQUIRED_COMMANDS = frozenset(
    {
        "project init",
        "project status",
        "project health",
        "project history",
        "run auto",
        "run cli",
        "run api",
        "run cron",
        "module add",
        "module list",
        "module remove",
        "plugin link",
        "plugin list",
        "plugin unlink",
        "plugin sync",
        "package install",
        "package update",
        "package pull",
        "cron jobs",
        "cron trigger",
        "cron start",
        "cron stop",
        "cron status",
        "cron workspace",
        "cron register",
        "cron workflows",
        "cron run-workflow",
        "cron generate",
        "cron apply",
        "version",
    }
)
_plugins_lock = Lock()
_plugins_loaded = False
_plugin_load_error: Exception | None = None


def _resolve_fx_version() -> str:
    try:
        return resolve_distribution_version(_fx_DISTRIBUTION_NAME)
    except PackageNotFoundError:
        return "dev"


FX_VERSION = _resolve_fx_version()


@_registry.register("version", description="Show fx version")
@_registry.option("--version", help="Show fx version")
@_registry.option("-V", help="Show fx version")
def show_version() -> str:
    return f"fx {FX_VERSION}"


def ensure_plugins_loaded() -> None:
    global _plugins_loaded, _plugin_load_error

    if _plugins_loaded:
        return
    if _plugin_load_error is not None:
        raise RuntimeError("fx command plugins failed to load.") from _plugin_load_error

    with _plugins_lock:
        if _plugins_loaded:
            return
        if _plugin_load_error is not None:
            raise RuntimeError("fx command plugins failed to load.") from _plugin_load_error
        try:
            load_plugins(_PLUGINS_PACKAGE, _registry)
            missing = sorted(name for name in _REQUIRED_COMMANDS if not _registry.has(name))
            if missing:
                raise RuntimeError(
                    "fx command plugins loaded incompletely. Missing commands: "
                    + ", ".join(missing)
                )
            _plugins_loaded = True
        except Exception as exc:
            _plugin_load_error = exc
            raise


def run(
    argv: Sequence[str] | None = None,
    *,
    print_result: bool = True,
    shell_prompt: str = "fx > ",
    shell_input_fn=None,
    shell_banner: bool = True,
    shell_banner_text: str | None = None,
    shell_title: str = "fx",
    shell_description: str = "Manage registers projects, runtimes, packages, plugins, and cron jobs.",
    shell_colors: bool | None = None,
    shell_usage: bool = True,
) -> Any:
    ensure_plugins_loaded()
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
    )


def get_registry() -> CommandRegistry:
    ensure_plugins_loaded()
    return _registry


def main(argv: Sequence[str] | None = None) -> int:
    run(argv)
    return 0


__all__ = [
    "FX_VERSION",
    "cron_group",
    "ensure_plugins_loaded",
    "get_registry",
    "main",
    "module_group",
    "package_group",
    "plugin_group",
    "project_group",
    "run",
    "run_group",
]
