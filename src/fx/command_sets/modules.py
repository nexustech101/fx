from __future__ import annotations

from pathlib import Path
from typing import Any

from registers import CommandRegistry
from registers.cli import types as t

from fx.context import FxContext
from fx.state import record_operation, utc_now
from fx.structure import (
    create_module_layout,
    normalize_identifier,
    resolve_plugin_import_base,
)


MODULE_TYPES = ("cli", "db", "cron")


def register(registry: CommandRegistry) -> None:
    module = registry.group("module", description="Manage project modules", tags=["module"])

    @module.register(
        "add",
        description="Add a minimal module package under the project plugins package",
        tags=["module", "create"],
        examples=["module add MyTool cli users", "module add MyTool cron sync_jobs --dry-run"],
        capture_logs=True,
    )
    @module.dry_run()
    @module.argument("root", type=t.Path(), default="", help="Project root path")
    @module.argument("module_type", type=t.Choice(MODULE_TYPES), help="Module type")
    @module.argument("module_name", type=str, help="Module identifier")
    @module.argument("package", type=str, default="", help="Package name override")
    @module.argument("force", type=bool, default=False, help="Overwrite existing module files")
    def add(
        ctx: FxContext,
        root: Path | str = "",
        module_type: str = "cli",
        module_name: str = "",
        package: str = "",
        force: bool = False,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        root_path = ctx.resolve(root)
        normalized = normalize_identifier(module_name)
        package_value = package or _project_package(ctx, root_path)
        import_base = resolve_plugin_import_base(root_path, package_value)
        package_path = f"{import_base}.{normalized}"

        if dry_run:
            return {
                "status": "dry-run",
                "message": f"Would add {module_type} module '{normalized}'.",
                "root": str(root_path),
                "module_type": module_type,
                "module_name": normalized,
                "package_path": package_path,
                "force": force,
            }

        structure = create_module_layout(
            root=root_path,
            module_type=module_type,
            module_name=normalized,
            force=force,
            package=package_value,
        )
        modules = ctx.modules(root_path)
        existing = modules.get(package_path=package_path)
        created_at = existing.created_at if existing is not None else utc_now()
        modules.upsert(
            project_root=str(root_path),
            module_type=module_type,
            module_name=normalized,
            package_path=package_path,
            entry_file=str(structure.entry_file or ""),
            created_at=created_at,
            updated_at=utc_now(),
        )
        plugins = ctx.plugins(root_path)
        existing_plugin = plugins.get(alias=normalized)
        plugin_created_at = existing_plugin.created_at if existing_plugin is not None else utc_now()
        plugins.upsert(
            project_root=str(root_path),
            alias=normalized,
            package_path=package_path,
            enabled=True,
            link_file=str((structure.entry_file or root_path).parent / "__init__.py"),
            created_at=plugin_created_at,
            updated_at=utc_now(),
        )
        record_operation(
            root=root_path,
            command="module add",
            arguments={"root": str(root_path), "module_type": module_type, "module_name": normalized},
            status="success",
            message=f"Added {module_type} module '{normalized}'.",
        )
        return {
            "status": "success",
            "message": f"Added {module_type} module '{normalized}'.",
            "root": str(root_path),
            "module_type": module_type,
            "module_name": normalized,
            "package_path": package_path,
            "entry_file": str(structure.entry_file) if structure.entry_file else "",
            "created": [str(path.relative_to(root_path)) for path in structure.created],
            "updated": [str(path.relative_to(root_path)) for path in structure.updated],
            "skipped": [str(path.relative_to(root_path)) for path in structure.skipped],
        }

    @module.register(
        "list",
        description="List registered modules",
        tags=["module", "inspect"],
        examples=["module list MyTool", "module list MyTool --output csv"],
        default_output="rich",
    )
    @module.argument("root", type=t.Path(), default="", help="Project root path")
    def list_modules(ctx: FxContext, root: Path | str = "") -> list[dict[str, Any]]:
        root_path = ctx.resolve(root)
        rows = ctx.modules(root_path).filter(project_root=str(root_path), order_by="module_name")
        return [
            {
                "module_name": row.module_name,
                "module_type": row.module_type,
                "package_path": row.package_path,
                "entry_file": row.entry_file,
            }
            for row in rows
        ]

    @module.register(
        "remove",
        description="Remove a module from fx state",
        tags=["module", "danger"],
        examples=["module remove MyTool users --force"],
        capture_logs=True,
    )
    @module.confirm(
        "Remove module '{module_name}' from fx state for {root}?",
        danger=True,
        confirm_phrase="remove {module_name}",
    )
    @module.dry_run()
    @module.argument("root", type=t.Path(), default="", help="Project root path")
    @module.argument("module_name", type=str, help="Module identifier")
    def remove(
        ctx: FxContext,
        root: Path | str = "",
        module_name: str = "",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        root_path = ctx.resolve(root)
        normalized = normalize_identifier(module_name)
        if dry_run:
            return {
                "status": "dry-run",
                "message": f"Would remove module '{normalized}' from fx state.",
                "root": str(root_path),
                "module_name": normalized,
            }
        removed = ctx.modules(root_path).delete_where(project_root=str(root_path), module_name=normalized)
        ctx.plugins(root_path).delete_where(project_root=str(root_path), alias=normalized)
        record_operation(
            root=root_path,
            command="module remove",
            arguments={"root": str(root_path), "module_name": normalized},
            status="success",
            message=f"Removed module '{normalized}' from fx state.",
        )
        return {
            "status": "success",
            "message": f"Removed module '{normalized}' from fx state.",
            "root": str(root_path),
            "module_name": normalized,
            "removed": removed,
        }


def _project_package(ctx: FxContext, root_path: Path) -> str:
    project = ctx.projects(root_path).get(root_path=str(root_path))
    return getattr(project, "package_name", "") if project is not None else ""
