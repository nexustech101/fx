from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any

from registers import CommandRegistry
from registers.cli import types as t

from fx.context import FxContext
from fx.runtime_ops import run_checked
from fx.state import record_operation
from fx.structure import (
    discover_project_package_dir,
    discover_project_packages,
    package_name as normalize_package_name,
)


@dataclass(frozen=True)
class RuntimeContext:
    root: Path
    package_name: str
    package_dir: Path
    project_type: str
    cwd: Path


def register(registry: CommandRegistry) -> None:
    run = registry.group("run", description="Run project entrypoints", tags=["run"])

    @run.register(
        "auto",
        description="Run the project based on fx metadata or package discovery",
        tags=["run"],
        examples=["run auto MyTool", "run auto ApiService --host 0.0.0.0 --port 9000"],
        default_output="rich",
        capture_logs=True,
    )
    @run.argument("root", type=t.Path(), default="", help="Project root path")
    @run.argument("package", type=str, default="", help="Package name override")
    @run.argument("host", type=str, default="127.0.0.1", help="Host binding for API projects")
    @run.argument("port", type=t.Int(min=1, max=65535), default=8000, help="Port for API projects")
    @run.argument("reload", type=bool, default=False, help="Enable uvicorn reload")
    @run.argument("app", type=str, default="", help="ASGI app target override")
    def auto(
        ctx: FxContext,
        root: Path | str = "",
        package: str = "",
        host: str = "127.0.0.1",
        port: int = 8000,
        reload: bool = False,
        app: str = "",
    ) -> dict[str, Any]:
        runtime = _resolve_runtime_context(ctx, root, package)
        try:
            if runtime.project_type == "db":
                argv = _run_api(runtime, host=host, port=port, reload=reload, app=app)
                mode = "api"
            else:
                argv = _run_python_module(runtime)
                mode = runtime.project_type if runtime.project_type in {"cli", "cron"} else "cli"
        except Exception as exc:
            _record_run(runtime, command_name="run auto", status="failure", argv=[], message=str(exc), host=host, port=port, reload=reload, app=app)
            raise
        _record_run(runtime, command_name="run auto", status="success", argv=argv, message="Application command executed successfully.", host=host, port=port, reload=reload, app=app)
        return _run_result(runtime, mode, argv)

    @run.register(
        "cli",
        description="Run a CLI project package via python -m",
        tags=["run"],
        examples=["run cli MyTool", "run cli MyTool --package demo"],
        default_output="rich",
        capture_logs=True,
    )
    @run.argument("root", type=t.Path(), default="", help="Project root path")
    @run.argument("package", type=str, default="", help="Package name override")
    def cli(ctx: FxContext, root: Path | str = "", package: str = "") -> dict[str, Any]:
        runtime = _resolve_runtime_context(ctx, root, package, project_type="cli")
        try:
            argv = _run_python_module(runtime)
        except Exception as exc:
            _record_run(runtime, command_name="run cli", status="failure", argv=[], message=str(exc))
            raise
        _record_run(runtime, command_name="run cli", status="success", argv=argv, message="CLI command executed successfully.")
        return _run_result(runtime, "cli", argv)

    @run.register(
        "api",
        description="Run a DB/FastAPI project with uvicorn",
        tags=["run", "api"],
        examples=["run api ApiService --host 0.0.0.0 --port 9000 --reload"],
        default_output="rich",
        capture_logs=True,
    )
    @run.argument("root", type=t.Path(), default="", help="Project root path")
    @run.argument("package", type=str, default="", help="Package name override")
    @run.argument("host", type=str, default="127.0.0.1", help="Host binding")
    @run.argument("port", type=t.Int(min=1, max=65535), default=8000, help="Port")
    @run.argument("reload", type=bool, default=False, help="Enable uvicorn reload")
    @run.argument("app", type=str, default="", help="ASGI app target override")
    def api(
        ctx: FxContext,
        root: Path | str = "",
        package: str = "",
        host: str = "127.0.0.1",
        port: int = 8000,
        reload: bool = False,
        app: str = "",
    ) -> dict[str, Any]:
        runtime = _resolve_runtime_context(ctx, root, package, project_type="db")
        try:
            argv = _run_api(runtime, host=host, port=port, reload=reload, app=app)
        except Exception as exc:
            _record_run(runtime, command_name="run api", status="failure", argv=[], message=str(exc), host=host, port=port, reload=reload, app=app)
            raise
        _record_run(runtime, command_name="run api", status="success", argv=argv, message="API command executed successfully.", host=host, port=port, reload=reload, app=app)
        return _run_result(runtime, "api", argv)

    @run.register(
        "cron",
        description="Run a cron project package via python -m",
        tags=["run", "cron"],
        examples=["run cron OpsJobs"],
        default_output="rich",
        capture_logs=True,
    )
    @run.argument("root", type=t.Path(), default="", help="Project root path")
    @run.argument("package", type=str, default="", help="Package name override")
    def cron(ctx: FxContext, root: Path | str = "", package: str = "") -> dict[str, Any]:
        runtime = _resolve_runtime_context(ctx, root, package, project_type="cron")
        try:
            argv = _run_python_module(runtime)
        except Exception as exc:
            _record_run(runtime, command_name="run cron", status="failure", argv=[], message=str(exc))
            raise
        _record_run(runtime, command_name="run cron", status="success", argv=argv, message="Cron command executed successfully.")
        return _run_result(runtime, "cron", argv)


def _resolve_runtime_context(
    ctx: FxContext,
    root: Path | str = "",
    package: str = "",
    project_type: str = "",
) -> RuntimeContext:
    root_path = ctx.resolve(root)
    project = ctx.projects(root_path).get(root_path=str(root_path))
    package_value = normalize_package_name(package) if package.strip() else getattr(project, "package_name", "")
    discovered = discover_project_packages(root_path)

    package_dir = discover_project_package_dir(root_path, package_value)
    if package_dir is None:
        if package_value:
            raise ValueError(f"No runnable package named '{package_value}' found under {root_path}.")
        if len(discovered) > 1:
            names = ", ".join(pkg.name for pkg in discovered)
            raise ValueError(f"Multiple runnable packages found ({names}); pass --package.")
        if not discovered:
            raise ValueError(f"No runnable package with __main__.py found under {root_path}.")
        package_dir = discovered[0].directory
        package_value = discovered[0].name

    resolved_type = project_type or getattr(project, "project_type", "")
    if not resolved_type:
        resolved_type = "db" if (package_dir / "api.py").exists() else "cli"
    cwd = package_dir.parent if package_dir.parent.name == "src" else root_path
    return RuntimeContext(root_path, package_value, package_dir, resolved_type, cwd)


def _run_python_module(ctx: RuntimeContext) -> list[str]:
    argv = [str(Path(sys.executable)), "-m", ctx.package_name]
    run_checked(argv, cwd=ctx.cwd)
    return argv


def _run_api(ctx: RuntimeContext, *, host: str, port: int, reload: bool, app: str = "") -> list[str]:
    app_target = app.strip() or f"{ctx.package_name}.api:app"
    if not app.strip() and not (ctx.package_dir / "api.py").exists():
        raise ValueError(f"DB/API run requires {ctx.package_dir / 'api.py'} or --app module:object.")
    argv = [
        str(Path(sys.executable)),
        "-m",
        "uvicorn",
        app_target,
        "--host",
        host,
        "--port",
        str(port),
    ]
    if reload:
        argv.append("--reload")
    run_checked(argv, cwd=ctx.cwd)
    return argv


def _record_run(
    ctx: RuntimeContext,
    *,
    command_name: str,
    status: str,
    argv: list[str],
    message: str,
    host: str = "",
    port: int = 0,
    reload: bool = False,
    app: str = "",
) -> None:
    record_operation(
        root=ctx.root,
        command=command_name,
        arguments={
            "root": str(ctx.root),
            "project_type": ctx.project_type,
            "package": ctx.package_name,
            "host": host,
            "port": port,
            "reload": reload,
            "app": app,
        },
        status=status,
        message=message,
    )


def _run_result(ctx: RuntimeContext, mode: str, argv: list[str]) -> dict[str, Any]:
    return {
        "status": "success",
        "mode": mode,
        "root": str(ctx.root),
        "package": ctx.package_name,
        "project_type": ctx.project_type,
        "cwd": str(ctx.cwd),
        "command": " ".join(argv),
        "argv": argv,
    }
