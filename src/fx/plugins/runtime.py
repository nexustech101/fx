from __future__ import annotations

from dataclasses import dataclass
import importlib
from pathlib import Path
import shutil
import sys
from typing import Literal

from fx.commands import package_group, run_group
from fx.plugin_sync import sync_plugins_from_checkout
from fx.runtime_ops import (
    clone_repo,
    editable_install_target,
    ensure_venv_python,
    progress_steps,
    run_checked,
)
from fx.state import plugin_registry, project_registry, record_operation, resolve_root, utc_now
from fx.structure import (
    discover_project_package_dir,
    discover_project_packages,
    package_name as normalize_package_name,
    resolve_plugin_import_base,
    resolve_plugin_layout,
)
from fx.support import render_runtime_summary


@dataclass(frozen=True)
class RuntimeContext:
    root: Path
    package_name: str
    package_dir: Path
    project_type: str
    cwd: Path


def _resolve_runtime_context(root: str, package: str = "", project_type: str = "") -> RuntimeContext:
    root_path = resolve_root(root)
    project = project_registry(root_path).get(root_path=str(root_path))
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


def _render_run_result(ctx: RuntimeContext, mode: str, argv: list[str]) -> str:
    return render_runtime_summary(
        "fx Run Result",
        fields=[
            ("Status", "success"),
            ("Mode", mode),
            ("Project", str(ctx.root)),
            ("Package", ctx.package_name),
            ("Project type", ctx.project_type),
            ("Command", " ".join(argv)),
        ],
    )


@run_group.register("auto", description="Run the project based on fx metadata or package discovery")
@run_group.argument("root", type=str, default=".", help="Project root path")
@run_group.argument("package", type=str, default="", help="Package name override")
@run_group.argument("host", type=str, default="127.0.0.1", help="Host binding for API projects")
@run_group.argument("port", type=int, default=8000, help="Port for API projects")
@run_group.argument("reload", type=bool, default=False, help="Enable uvicorn reload for API projects")
@run_group.argument("app", type=str, default="", help="ASGI app target override, for example pkg.api:app")
def run_auto(
    root: str = ".",
    package: str = "",
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
    app: str = "",
) -> str:
    ctx = _resolve_runtime_context(root, package)
    try:
        if ctx.project_type == "db":
            argv = _run_api(ctx, host=host, port=port, reload=reload, app=app)
            mode = "api"
        else:
            argv = _run_python_module(ctx)
            mode = ctx.project_type if ctx.project_type in {"cli", "cron"} else "cli"
    except Exception as exc:
        _record_run(ctx, command_name="run auto", status="failure", argv=[], message=str(exc), host=host, port=port, reload=reload, app=app)
        raise
    _record_run(ctx, command_name="run auto", status="success", argv=argv, message="Application command executed successfully.", host=host, port=port, reload=reload, app=app)
    return _render_run_result(ctx, mode, argv)


@run_group.register("cli", description="Run a CLI project package via python -m")
@run_group.argument("root", type=str, default=".", help="Project root path")
@run_group.argument("package", type=str, default="", help="Package name override")
def run_cli(root: str = ".", package: str = "") -> str:
    ctx = _resolve_runtime_context(root, package, project_type="cli")
    try:
        argv = _run_python_module(ctx)
    except Exception as exc:
        _record_run(ctx, command_name="run cli", status="failure", argv=[], message=str(exc))
        raise
    _record_run(ctx, command_name="run cli", status="success", argv=argv, message="CLI command executed successfully.")
    return _render_run_result(ctx, "cli", argv)


@run_group.register("api", description="Run a DB/FastAPI project with uvicorn")
@run_group.argument("root", type=str, default=".", help="Project root path")
@run_group.argument("package", type=str, default="", help="Package name override")
@run_group.argument("host", type=str, default="127.0.0.1", help="Host binding")
@run_group.argument("port", type=int, default=8000, help="Port")
@run_group.argument("reload", type=bool, default=False, help="Enable uvicorn reload")
@run_group.argument("app", type=str, default="", help="ASGI app target override")
def run_api(
    root: str = ".",
    package: str = "",
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
    app: str = "",
) -> str:
    ctx = _resolve_runtime_context(root, package, project_type="db")
    try:
        argv = _run_api(ctx, host=host, port=port, reload=reload, app=app)
    except Exception as exc:
        _record_run(ctx, command_name="run api", status="failure", argv=[], message=str(exc), host=host, port=port, reload=reload, app=app)
        raise
    _record_run(ctx, command_name="run api", status="success", argv=argv, message="API command executed successfully.", host=host, port=port, reload=reload, app=app)
    return _render_run_result(ctx, "api", argv)


@run_group.register("cron", description="Run a cron project package via python -m")
@run_group.argument("root", type=str, default=".", help="Project root path")
@run_group.argument("package", type=str, default="", help="Package name override")
def run_cron(root: str = ".", package: str = "") -> str:
    ctx = _resolve_runtime_context(root, package, project_type="cron")
    try:
        argv = _run_python_module(ctx)
    except Exception as exc:
        _record_run(ctx, command_name="run cron", status="failure", argv=[], message=str(exc))
        raise
    _record_run(ctx, command_name="run cron", status="success", argv=argv, message="Cron command executed successfully.")
    return _render_run_result(ctx, "cron", argv)


@package_group.register("install", description="Install a project package in editable mode")
@package_group.argument("root", type=str, default=".", help="Project root path")
@package_group.argument("venv_path", type=str, default="", help="Optional virtualenv path")
@package_group.argument("extras", type=str, default="", help="Optional extras list, for example dev,docs")
def install_project(root: str = ".", venv_path: str = "", extras: str = "") -> str:
    root_path = resolve_root(root)
    editable_target = ""
    argv: list[str] = []
    try:
        with progress_steps(total=3, desc="fx package install") as progress:
            progress.set_postfix_str("resolving python environment")
            python_exe = ensure_venv_python(root_path, venv_path)
            progress.update(1)
            progress.set_postfix_str("building editable target")
            editable_target = editable_install_target(root_path, extras)
            argv = [str(python_exe), "-m", "pip", "install", "-e", editable_target]
            progress.update(1)
            progress.set_postfix_str("running pip install -e")
            run_checked(argv, cwd=root_path)
            progress.update(1)
    except Exception as exc:
        record_operation(root=root_path, command="package install", arguments={"root": str(root_path), "venv_path": venv_path, "extras": extras}, status="failure", message=str(exc))
        raise
    record_operation(root=root_path, command="package install", arguments={"root": str(root_path), "venv_path": venv_path, "extras": extras}, status="success", message="Editable install completed successfully.")
    return render_runtime_summary(
        "fx Package Install Result",
        fields=[("Status", "success"), ("Project", str(root_path)), ("Target", editable_target), ("Command", " ".join(argv))],
    )


@package_group.register("update", description="Update a package from pypi, git, or path")
@package_group.argument("root", type=str, default=".", help="Project root path")
@package_group.argument("source", type=Literal["pypi", "git", "path"], default="pypi", help="Update source")
@package_group.argument("repo", type=str, default="", help="Git repository URL when source=git")
@package_group.argument("ref", type=str, default="main", help="Git ref when source=git")
@package_group.argument("path", type=str, default="", help="Local source path when source=path")
@package_group.argument("venv_path", type=str, default="", help="Optional virtualenv path")
@package_group.argument("package", type=str, default="registers", help="Package name/egg name")
def update_project(
    root: str = ".",
    source: Literal["pypi", "git", "path"] = "pypi",
    repo: str = "",
    ref: str = "main",
    path: str = "",
    venv_path: str = "",
    package: str = "registers",
) -> str:
    root_path = resolve_root(root)
    pkg = package.strip() or "registers"
    argv: list[str] = []
    try:
        with progress_steps(total=3, desc="fx package update") as progress:
            progress.set_postfix_str("resolving python environment")
            python_exe = ensure_venv_python(root_path, venv_path)
            progress.update(1)
            progress.set_postfix_str("resolving update source")
            if source == "pypi":
                if repo.strip() or path.strip():
                    raise ValueError("source='pypi' does not accept --repo or --path.")
                argv = [str(python_exe), "-m", "pip", "install", "--upgrade", pkg]
            elif source == "git":
                if not repo.strip():
                    raise ValueError("source='git' requires --repo.")
                if path.strip():
                    raise ValueError("source='git' does not accept --path.")
                argv = [str(python_exe), "-m", "pip", "install", "--upgrade", f"git+{repo}@{ref}#egg={pkg}"]
            else:
                if not path.strip():
                    raise ValueError("source='path' requires --path.")
                if repo.strip():
                    raise ValueError("source='path' does not accept --repo.")
                source_path = Path(path)
                if not source_path.is_absolute():
                    source_path = (root_path / source_path).resolve()
                if not source_path.exists():
                    raise FileNotFoundError(f"Update source path does not exist: {source_path}")
                argv = [str(python_exe), "-m", "pip", "install", "--upgrade", str(source_path)]
            progress.update(1)
            progress.set_postfix_str("running pip install --upgrade")
            run_checked(argv, cwd=root_path)
            progress.update(1)
    except Exception as exc:
        record_operation(root=root_path, command="package update", arguments={"root": str(root_path), "source": source, "repo": repo, "ref": ref, "path": path, "venv_path": venv_path, "package": pkg}, status="failure", message=str(exc))
        raise
    record_operation(root=root_path, command="package update", arguments={"root": str(root_path), "source": source, "repo": repo, "ref": ref, "path": path, "venv_path": venv_path, "package": pkg}, status="success", message=f"Updated package '{pkg}' from source '{source}'.")
    return render_runtime_summary(
        "fx Package Update Result",
        fields=[("Status", "success"), ("Project", str(root_path)), ("Source", source), ("Package", pkg), ("Command", " ".join(argv))],
    )


@package_group.register("pull", description="Pull plugin packages from a git repository")
@package_group.argument("root", type=str, help="Project root path")
@package_group.argument("repo_url", type=str, help="Git repository URL or local git path")
@package_group.argument("ref", type=str, default="main", help="Git ref/branch/tag")
@package_group.argument("subdir", type=str, default="plugins", help="Plugin directory inside the repository")
@package_group.argument("package", type=str, default="", help="Project package override")
@package_group.argument("force", type=bool, default=False, help="Overwrite existing plugin directories")
def pull_plugins(
    root: str,
    repo_url: str,
    ref: str = "main",
    subdir: str = "plugins",
    package: str = "",
    force: bool = False,
) -> str:
    root_path = resolve_root(root)
    project = project_registry(root_path).get(root_path=str(root_path))
    package_value = package or getattr(project, "package_name", "")
    arguments = {"root": str(root_path), "repo_url": repo_url, "ref": ref, "subdir": subdir, "package": package_value, "force": force}
    try:
        plugin_layout = resolve_plugin_layout(root_path, package_value)
        plugin_layout.directory.mkdir(parents=True, exist_ok=True)
        init_path = plugin_layout.directory / "__init__.py"
        if not init_path.exists():
            init_path.write_text("", encoding="utf-8")
        clone_result = clone_repo(repo_url=repo_url, ref=ref)
        try:
            report = sync_plugins_from_checkout(
                checkout_root=clone_result.repo_path,
                subdir=subdir,
                target_plugins_dir=plugin_layout.directory,
                force=force,
            )
        finally:
            shutil.rmtree(clone_result.repo_path, ignore_errors=True)

        import_base = resolve_plugin_import_base(root_path, package_value)
        import_failures: list[str] = []
        original_sys_path = list(sys.path)
        try:
            for candidate in (root_path, root_path / "src"):
                if candidate.exists() and str(candidate) not in sys.path:
                    sys.path.insert(0, str(candidate))
            root_pkg = import_base.split(".")[0]
            for key in [key for key in list(sys.modules) if key == root_pkg or key.startswith(f"{root_pkg}.")]:
                sys.modules.pop(key, None)
            for alias in report.synced_aliases:
                dotted = f"{import_base}.{alias}"
                try:
                    importlib.invalidate_caches()
                    importlib.import_module(dotted)
                except Exception as exc:
                    import_failures.append(f"{dotted}: {exc}")
        finally:
            sys.path[:] = original_sys_path
        if import_failures:
            raise RuntimeError("Import validation failed for pulled plugins: " + "; ".join(import_failures))

        plugins = plugin_registry(root_path)
        for alias in report.synced_aliases:
            package_path = f"{import_base}.{alias}"
            existing = plugins.get(alias=alias)
            created_at = existing.created_at if existing is not None else utc_now()
            plugins.upsert(
                project_root=str(root_path),
                alias=alias,
                package_path=package_path,
                enabled=True,
                link_file=str(plugin_layout.directory / alias / "__init__.py"),
                created_at=created_at,
                updated_at=utc_now(),
            )
        summary = f"created={len(report.created)}, updated={len(report.updated)}, skipped={len(report.skipped)}"
        record_operation(root=root_path, command="package pull", arguments=arguments, status="success", message=f"Pulled plugins successfully ({summary}).")
        return render_runtime_summary(
            "fx Package Pull Result",
            fields=[("Status", "success"), ("Project", str(root_path)), ("Repository", repo_url), ("Summary", summary)],
            sections=[("Created", report.created), ("Updated", report.updated), ("Skipped", report.skipped)],
        )
    except Exception as exc:
        record_operation(root=root_path, command="package pull", arguments=arguments, status="failure", message=str(exc))
        raise
