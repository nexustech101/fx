from __future__ import annotations

import importlib
from pathlib import Path
import shutil
import sys
from typing import Any

from registers import CommandRegistry
from registers.cli import types as t

from fx.context import FxContext
from fx.plugin_sync import sync_plugins_from_checkout
from fx.runtime_ops import clone_repo, editable_install_target, ensure_venv_python, run_checked
from fx.state import record_operation, utc_now
from fx.structure import (
    resolve_plugin_import_base,
    resolve_plugin_layout,
)


SOURCES = ("pypi", "git", "path")


def register(registry: CommandRegistry) -> None:
    package = registry.group("package", description="Install, update, and pull packages", tags=["package"])

    @package.register(
        "install",
        description="Install a project package in editable mode",
        tags=["package"],
        examples=["package install MyTool --extras dev", "package install MyTool --venv-path .venv --dry-run"],
        default_output="rich",
        capture_logs=True,
    )
    @package.progress("Installing package")
    @package.dry_run()
    @package.argument("root", type=t.Path(), default="", help="Project root path")
    @package.argument("venv_path", type=t.Path(), default="", help="Optional virtualenv path")
    @package.argument("extras", type=str, default="", help="Optional extras list")
    def install(
        ctx: FxContext,
        root: Path | str = "",
        venv_path: Path | str = "",
        extras: str = "",
        dry_run: bool = False,
        progress=None,
    ) -> dict[str, Any]:
        root_path = ctx.resolve(root)
        editable_target = editable_install_target(root_path, extras)
        python_exe = _planned_python(root_path, venv_path)
        argv = [str(python_exe), "-m", "pip", "install", "-e", editable_target]
        if dry_run:
            return {
                "status": "dry-run",
                "message": "Would install project package in editable mode.",
                "root": str(root_path),
                "target": editable_target,
                "command": " ".join(argv),
                "argv": argv,
            }
        task = progress.add_task("Installing", total=3) if progress is not None else None
        try:
            python_exe = ensure_venv_python(root_path, str(venv_path))
            _advance(progress, task)
            editable_target = editable_install_target(root_path, extras)
            argv = [str(python_exe), "-m", "pip", "install", "-e", editable_target]
            _advance(progress, task)
            run_checked(argv, cwd=root_path)
            _advance(progress, task)
        except Exception as exc:
            record_operation(root=root_path, command="package install", arguments={"root": str(root_path), "venv_path": str(venv_path), "extras": extras}, status="failure", message=str(exc))
            raise
        record_operation(root=root_path, command="package install", arguments={"root": str(root_path), "venv_path": str(venv_path), "extras": extras}, status="success", message="Editable install completed successfully.")
        return {
            "status": "success",
            "message": "Editable install completed successfully.",
            "root": str(root_path),
            "target": editable_target,
            "command": " ".join(argv),
            "argv": argv,
        }

    @package.register(
        "update",
        description="Update a package from pypi, git, or path",
        tags=["package"],
        examples=[
            "package update MyTool --package registers",
            "package update MyTool --source git --repo https://github.com/example/pkg --ref main",
            "package update MyTool --source path --path ../registers",
        ],
        default_output="rich",
        capture_logs=True,
    )
    @package.progress("Updating package")
    @package.dry_run()
    @package.argument("root", type=t.Path(), default="", help="Project root path")
    @package.argument("source", type=t.Choice(SOURCES), default="pypi", help="Update source")
    @package.argument("repo", type=str, default="", help="Git repository URL when source=git")
    @package.argument("ref", type=str, default="main", help="Git ref when source=git")
    @package.argument("path", type=t.Path(exists=True), default="", help="Local source path when source=path")
    @package.argument("venv_path", type=t.Path(), default="", help="Optional virtualenv path")
    @package.argument("package", type=str, default="registers", help="Package name/egg name")
    def update(
        ctx: FxContext,
        root: Path | str = "",
        source: str = "pypi",
        repo: str = "",
        ref: str = "main",
        path: Path | str = "",
        venv_path: Path | str = "",
        package: str = "registers",
        dry_run: bool = False,
        progress=None,
    ) -> dict[str, Any]:
        root_path = ctx.resolve(root)
        pkg = package.strip() or "registers"
        argv = _update_argv(root_path, source, repo, ref, path, _planned_python(root_path, venv_path), pkg)
        if dry_run:
            return {
                "status": "dry-run",
                "message": f"Would update package '{pkg}' from source '{source}'.",
                "root": str(root_path),
                "source": source,
                "package": pkg,
                "command": " ".join(argv),
                "argv": argv,
            }
        task = progress.add_task("Updating", total=3) if progress is not None else None
        try:
            python_exe = ensure_venv_python(root_path, str(venv_path))
            _advance(progress, task)
            argv = _update_argv(root_path, source, repo, ref, path, python_exe, pkg)
            _advance(progress, task)
            run_checked(argv, cwd=root_path)
            _advance(progress, task)
        except Exception as exc:
            record_operation(root=root_path, command="package update", arguments={"root": str(root_path), "source": source, "repo": repo, "ref": ref, "path": str(path), "venv_path": str(venv_path), "package": pkg}, status="failure", message=str(exc))
            raise
        record_operation(root=root_path, command="package update", arguments={"root": str(root_path), "source": source, "repo": repo, "ref": ref, "path": str(path), "venv_path": str(venv_path), "package": pkg}, status="success", message=f"Updated package '{pkg}' from source '{source}'.")
        return {
            "status": "success",
            "message": f"Updated package '{pkg}' from source '{source}'.",
            "root": str(root_path),
            "source": source,
            "package": pkg,
            "command": " ".join(argv),
            "argv": argv,
        }

    @package.register(
        "pull",
        description="Pull plugin packages from a git repository",
        tags=["package", "plugin"],
        examples=["package pull MyTool https://github.com/example/plugins --subdir plugins"],
        default_output="rich",
        capture_logs=True,
    )
    @package.progress("Pulling plugins")
    @package.dry_run()
    @package.argument("root", type=t.Path(), default="", help="Project root path")
    @package.argument("repo_url", type=str, help="Git repository URL or local git path")
    @package.argument("ref", type=str, default="main", help="Git ref/branch/tag")
    @package.argument("subdir", type=str, default="plugins", help="Plugin directory inside the repository")
    @package.argument("package", type=str, default="", help="Project package override")
    @package.argument("force", type=bool, default=False, help="Overwrite existing plugin directories")
    def pull(
        ctx: FxContext,
        root: Path | str = "",
        repo_url: str = "",
        ref: str = "main",
        subdir: str = "plugins",
        package: str = "",
        force: bool = False,
        dry_run: bool = False,
        progress=None,
    ) -> dict[str, Any]:
        root_path = ctx.resolve(root)
        project = ctx.projects(root_path).get(root_path=str(root_path))
        package_value = package or getattr(project, "package_name", "")
        arguments = {"root": str(root_path), "repo_url": repo_url, "ref": ref, "subdir": subdir, "package": package_value, "force": force}
        if dry_run:
            return {
                "status": "dry-run",
                "message": "Would pull plugin packages.",
                "root": str(root_path),
                "repository": repo_url,
                "ref": ref,
                "subdir": subdir,
                "package": package_value,
                "force": force,
            }
        task = progress.add_task("Pulling", total=4) if progress is not None else None
        try:
            plugin_layout = resolve_plugin_layout(root_path, package_value)
            plugin_layout.directory.mkdir(parents=True, exist_ok=True)
            init_path = plugin_layout.directory / "__init__.py"
            if not init_path.exists():
                init_path.write_text("", encoding="utf-8")
            _advance(progress, task)
            clone_result = clone_repo(repo_url=repo_url, ref=ref)
            _advance(progress, task)
            try:
                report = sync_plugins_from_checkout(
                    checkout_root=clone_result.repo_path,
                    subdir=subdir,
                    target_plugins_dir=plugin_layout.directory,
                    force=force,
                )
            finally:
                shutil.rmtree(clone_result.repo_path, ignore_errors=True)
            _advance(progress, task)
            import_failures = _validate_synced_imports(root_path, package_value, report.synced_aliases)
            if import_failures:
                raise RuntimeError("Import validation failed for pulled plugins: " + "; ".join(import_failures))

            plugins = ctx.plugins(root_path)
            import_base = resolve_plugin_import_base(root_path, package_value)
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
            _advance(progress, task)
            summary = f"created={len(report.created)}, updated={len(report.updated)}, skipped={len(report.skipped)}"
            record_operation(root=root_path, command="package pull", arguments=arguments, status="success", message=f"Pulled plugins successfully ({summary}).")
            return {
                "status": "success",
                "message": f"Pulled plugins successfully ({summary}).",
                "root": str(root_path),
                "repository": repo_url,
                "summary": summary,
                "created": list(report.created),
                "updated": list(report.updated),
                "skipped": list(report.skipped),
            }
        except Exception as exc:
            record_operation(root=root_path, command="package pull", arguments=arguments, status="failure", message=str(exc))
            raise


def _planned_python(root_path: Path, venv_path: Path | str) -> Path:
    if str(venv_path).strip():
        candidate = Path(venv_path)
        return candidate if candidate.is_absolute() else root_path / candidate
    return Path(sys.executable)


def _update_argv(
    root_path: Path,
    source: str,
    repo: str,
    ref: str,
    path: Path | str,
    python_exe: Path,
    package: str,
) -> list[str]:
    if source == "pypi":
        if repo.strip() or str(path).strip():
            raise ValueError("source='pypi' does not accept --repo or --path.")
        return [str(python_exe), "-m", "pip", "install", "--upgrade", package]
    if source == "git":
        if not repo.strip():
            raise ValueError("source='git' requires --repo.")
        if str(path).strip():
            raise ValueError("source='git' does not accept --path.")
        return [str(python_exe), "-m", "pip", "install", "--upgrade", f"git+{repo}@{ref}#egg={package}"]
    if not str(path).strip():
        raise ValueError("source='path' requires --path.")
    if repo.strip():
        raise ValueError("source='path' does not accept --repo.")
    source_path = Path(path)
    if not source_path.is_absolute():
        source_path = (root_path / source_path).resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"Update source path does not exist: {source_path}")
    return [str(python_exe), "-m", "pip", "install", "--upgrade", str(source_path)]


def _validate_synced_imports(root_path: Path, package_value: str, aliases: list[str]) -> list[str]:
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
        for alias in aliases:
            dotted = f"{import_base}.{alias}"
            try:
                importlib.invalidate_caches()
                importlib.import_module(dotted)
            except Exception as exc:
                import_failures.append(f"{dotted}: {exc}")
    finally:
        sys.path[:] = original_sys_path
    return import_failures


def _advance(progress, task) -> None:
    if progress is not None and task is not None:
        progress.advance(task)
