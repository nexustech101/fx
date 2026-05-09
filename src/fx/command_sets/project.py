from __future__ import annotations

import importlib
from pathlib import Path
import sys
from typing import Any

from registers import CommandRegistry
from registers.cli import types as t

from fx.context import FxContext
from fx.state import record_operation, utc_now
from fx.structure import (
    discover_local_plugins,
    discover_project_package,
    discover_project_package_dir,
    discover_project_packages,
    init_project_layout,
    package_name as normalize_package_name,
    resolve_plugin_import_base,
    resolve_plugin_layout,
)


PROJECT_TYPES = ("cli", "db", "cron")
LAYOUTS = ("src", "root")


def register(registry: CommandRegistry) -> None:
    project = registry.group(
        "project",
        description="Create and inspect fx projects",
        tags=["project"],
    )

    @project.register(
        "init",
        description="Create a minimal cli, db, or cron project",
        tags=["create", "scaffold"],
        examples=[
            "project init cli MyTool",
            "project init db ApiService --layout src",
            "project init cron OpsJobs --package ops --layout root",
            "--root ./workspace project init cli MyTool",
        ],
        error_hints={"ValueError": "Check the project type, package name, layout, and target path."},
        capture_logs=True,
    )
    @project.dry_run()
    @project.argument("project_type", type=t.Choice(PROJECT_TYPES), help="Project type")
    @project.argument("project_name", type=str, help="Project display/package name")
    @project.argument("root", type=t.Path(), default="", help="Project root path")
    @project.argument("package", type=str, default="", help="Python package name")
    @project.argument("layout", type=t.Choice(LAYOUTS), default="src", help="Project layout")
    @project.argument("force", type=bool, default=False, help="Overwrite existing files")
    def init_project(
        ctx: FxContext,
        project_type: str,
        project_name: str,
        root: Path | str = "",
        package: str = "",
        layout: str = "src",
        force: bool = False,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        name = project_name.strip()
        if not name:
            raise ValueError("project_name is required.")
        root_path = _init_root(ctx, root, name)
        package_value = normalize_package_name(package or name)
        normalized_type = project_type.strip().lower()

        if dry_run:
            return {
                "status": "dry-run",
                "message": f"Would initialize {normalized_type} project '{name}'.",
                "project": name,
                "project_type": normalized_type,
                "root": str(root_path),
                "package": package_value,
                "layout": layout,
                "force": force,
            }

        root_path.mkdir(parents=True, exist_ok=True)
        structure = init_project_layout(
            root=root_path,
            project_name=name,
            project_type=normalized_type,
            package=package_value,
            layout=layout,
            force=force,
        )

        projects = ctx.projects(root_path)
        existing = projects.get(root_path=str(root_path))
        created_at = existing.created_at if existing is not None else utc_now()
        projects.upsert(
            name=name,
            root_path=str(root_path),
            project_type=normalized_type,
            package_name=package_value,
            layout=layout,
            created_at=created_at,
            updated_at=utc_now(),
        )
        record_operation(
            root=root_path,
            command="project init",
            arguments={
                "project_type": normalized_type,
                "project_name": name,
                "root": str(root_path),
                "package": package_value,
                "layout": layout,
                "force": force,
            },
            status="success",
            message=f"Initialized {normalized_type} project '{name}'.",
        )
        return {
            "status": "success",
            "message": f"Initialized {normalized_type} project '{name}'.",
            "project": name,
            "project_type": normalized_type,
            "root": str(root_path),
            "package": package_value,
            "layout": layout,
            "created": [str(path.relative_to(root_path)) for path in structure.created],
            "updated": [str(path.relative_to(root_path)) for path in structure.updated],
            "skipped": [str(path.relative_to(root_path)) for path in structure.skipped],
            "entry_file": str(structure.entry_file.relative_to(root_path)) if structure.entry_file else "",
        }

    @project.register(
        "status",
        description="Show project structure and fx state",
        tags=["inspect"],
        examples=["project status MyTool", "--root MyTool project status", "project status MyTool --output json"],
        default_output="rich",
    )
    @project.argument("root", type=t.Path(), default="", help="Project root path")
    @project.argument("package", type=str, default="", help="Package name override")
    def status(ctx: FxContext, root: Path | str = "", package: str = "") -> dict[str, Any]:
        root_path = ctx.resolve(root)
        project_row = ctx.projects(root_path).get(root_path=str(root_path))
        project_type = getattr(project_row, "project_type", "unknown") if project_row else "unknown"
        package_value = normalize_package_name(package) if package.strip() else getattr(project_row, "package_name", "")
        layout_value = getattr(project_row, "layout", "unknown") if project_row else "unknown"
        packages = discover_project_packages(root_path)
        package_dir = discover_project_package_dir(root_path, package_value)
        package_name = discover_project_package(root_path, package_value)
        plugin_layout = resolve_plugin_layout(root_path, package_value)
        local_plugins = discover_local_plugins(root_path, package_value)
        modules = ctx.modules(root_path).filter(project_root=str(root_path), order_by="module_name")
        plugins = ctx.plugins(root_path).filter(project_root=str(root_path), order_by="alias")
        registered_aliases = [plugin.alias for plugin in plugins]
        missing_on_disk = sorted(set(registered_aliases) - set(local_plugins))
        untracked_on_disk = sorted(set(local_plugins) - set(registered_aliases))
        return {
            "root": str(root_path),
            "project_record": "present" if project_row else "missing",
            "project_type": project_type,
            "package": package_name or "missing",
            "layout": layout_value,
            "runnable_packages": [pkg.name for pkg in packages],
            "package_root": str(package_dir) if package_dir is not None else "missing",
            "__main__.py": "present" if package_dir and (package_dir / "__main__.py").exists() else "missing",
            "api.py": "present" if package_dir and (package_dir / "api.py").exists() else "missing",
            "jobs.py": "present" if package_dir and (package_dir / "jobs.py").exists() else "missing",
            "pyproject.toml": "present" if (root_path / "pyproject.toml").exists() else "missing",
            "plugins_package": "present" if (plugin_layout.directory / "__init__.py").exists() else "missing",
            "plugins_import_base": plugin_layout.import_base,
            "registered_modules": len(modules),
            "registered_plugin_links": len(plugins),
            "local_plugin_packages": len(local_plugins),
            "missing_on_disk": missing_on_disk,
            "untracked_on_disk": untracked_on_disk,
            "plugin_registry_aligned": not missing_on_disk and not untracked_on_disk,
        }

    @project.register(
        "health",
        description="Validate runnable package, imports, and project metadata",
        tags=["inspect"],
        examples=["project health MyTool", "--root MyTool project health"],
        default_output="rich",
        capture_logs=True,
    )
    @project.argument("root", type=t.Path(), default="", help="Project root path")
    @project.argument("package", type=str, default="", help="Package name override")
    def health(ctx: FxContext, root: Path | str = "", package: str = "") -> dict[str, Any]:
        root_path = ctx.resolve(root)
        project_row = ctx.projects(root_path).get(root_path=str(root_path))
        project_type = getattr(project_row, "project_type", "")
        package_value = normalize_package_name(package) if package.strip() else getattr(project_row, "package_name", "")
        packages = discover_project_packages(root_path)
        package_dir = discover_project_package_dir(root_path, package_value)
        failures: list[str] = []

        if package_dir is None:
            if len(packages) > 1 and not package_value:
                failures.append("Multiple runnable packages found; pass --package.")
            else:
                failures.append("No runnable package with __main__.py found.")
        else:
            if not (package_dir / "__main__.py").exists():
                failures.append(f"Missing __main__.py in {package_dir}.")
            if project_type == "db":
                if not (package_dir / "api.py").exists():
                    failures.append(f"Missing FastAPI module at {package_dir / 'api.py'}.")
                else:
                    failures.extend(_validate_import(root_path, f"{package_dir.name}.api", require_attr="app"))
            if project_type == "cron" and not (package_dir / "jobs.py").exists():
                failures.append(f"Missing cron jobs module at {package_dir / 'jobs.py'}.")

        if not (root_path / "pyproject.toml").exists():
            failures.append("Missing pyproject.toml.")

        if package_dir is not None:
            import_base = resolve_plugin_import_base(root_path, package_value)
            for alias in discover_local_plugins(root_path, package_value):
                failures.extend(_validate_import(root_path, f"{import_base}.{alias}"))

        status_value = "success" if not failures else "failure"
        message = "Project checks passed." if not failures else "; ".join(failures)
        record_operation(
            root=root_path,
            command="project health",
            arguments={"root": str(root_path), "package": package_value, "project_type": project_type},
            status=status_value,
            message=message,
        )
        return {
            "status": status_value,
            "message": message,
            "root": str(root_path),
            "package": package_value or "",
            "project_type": project_type or "unknown",
            "failures": failures,
        }

    @project.register(
        "history",
        description="Show recent fx operation history",
        tags=["inspect"],
        examples=["project history MyTool", "project history MyTool --limit 50 --output json"],
        default_output="rich",
    )
    @project.argument("root", type=t.Path(), default="", help="Project root path")
    @project.argument("limit", type=t.Int(min=1), default=20, help="Maximum number of operations")
    def history(ctx: FxContext, root: Path | str = "", limit: int = 20) -> list[dict[str, Any]]:
        root_path = ctx.resolve(root)
        rows = ctx.operations(root_path).filter(project_root=str(root_path), order_by="-id", limit=limit)
        return [
            {
                "id": row.id,
                "created_at": row.created_at,
                "command": row.command,
                "status": row.status,
                "message": row.message,
            }
            for row in rows
        ]


def _init_root(ctx: FxContext, root: Path | str, project_name: str) -> Path:
    if str(root).strip():
        return ctx.resolve(root)
    if ctx.root != ctx.cwd:
        return ctx.root
    return ctx.resolve(project_name)


def _validate_import(root_path: Path, dotted: str, *, require_attr: str = "") -> list[str]:
    failures: list[str] = []
    original_sys_path = list(sys.path)
    try:
        src_root = root_path / "src"
        for candidate in (root_path, src_root):
            if candidate.exists() and str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
        root_pkg = dotted.split(".")[0]
        for key in [key for key in list(sys.modules) if key == root_pkg or key.startswith(f"{root_pkg}.")]:
            sys.modules.pop(key, None)
        importlib.invalidate_caches()
        module = importlib.import_module(dotted)
        if require_attr and not hasattr(module, require_attr):
            failures.append(f"Import {dotted} succeeded but missing attribute '{require_attr}'.")
    except Exception as exc:
        failures.append(f"Import failed for {dotted}: {exc}")
    finally:
        sys.path[:] = original_sys_path
    return failures
