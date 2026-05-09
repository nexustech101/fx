from __future__ import annotations

from pathlib import Path
from typing import Any

from registers import CommandRegistry
from registers.cli import types as t

from fx.context import FxContext
from fx.state import record_operation, utc_now
from fx.structure import (
    create_plugin_link,
    discover_local_plugins,
    normalize_identifier,
    resolve_plugin_import_base,
    resolve_plugin_layout,
)


def register(registry: CommandRegistry) -> None:
    plugin = registry.group("plugin", description="Manage project plugin links", tags=["plugin"])

    @plugin.register(
        "link",
        description="Link an importable package under the project plugins package",
        tags=["plugin", "create"],
        examples=["plugin link MyTool my_package.tools tools", "plugin link MyTool my_package.tools --dry-run"],
        capture_logs=True,
    )
    @plugin.dry_run()
    @plugin.argument("root", type=t.Path(), default="", help="Project root path")
    @plugin.argument("package_path", type=str, help="Importable package path")
    @plugin.argument("alias", type=str, default="", help="Local alias under plugins/")
    @plugin.argument("package", type=str, default="", help="Project package override")
    @plugin.argument("force", type=bool, default=False, help="Overwrite existing alias shim")
    def link(
        ctx: FxContext,
        root: Path | str = "",
        package_path: str = "",
        alias: str = "",
        package: str = "",
        force: bool = False,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        root_path = ctx.resolve(root)
        resolved_alias = normalize_identifier(alias or package_path.split(".")[-1])
        package_value = package or _project_package(ctx, root_path)
        if dry_run:
            return {
                "status": "dry-run",
                "message": f"Would link plugin '{resolved_alias}' to {package_path}.",
                "root": str(root_path),
                "alias": resolved_alias,
                "package_path": package_path,
                "package": package_value,
                "force": force,
            }
        structure = create_plugin_link(
            root=root_path,
            package_path=package_path,
            alias=resolved_alias,
            force=force,
            package=package_value,
        )
        plugins = ctx.plugins(root_path)
        existing = plugins.get(alias=resolved_alias)
        created_at = existing.created_at if existing is not None else utc_now()
        plugins.upsert(
            project_root=str(root_path),
            alias=resolved_alias,
            package_path=package_path,
            enabled=True,
            link_file=str(structure.entry_file or ""),
            created_at=created_at,
            updated_at=utc_now(),
        )
        record_operation(
            root=root_path,
            command="plugin link",
            arguments={"root": str(root_path), "package_path": package_path, "alias": resolved_alias},
            status="success",
            message=f"Linked plugin '{resolved_alias}' to {package_path}.",
        )
        return {
            "status": "success",
            "message": f"Linked plugin '{resolved_alias}' -> {package_path}",
            "root": str(root_path),
            "alias": resolved_alias,
            "package_path": package_path,
            "link_file": str(structure.entry_file or ""),
            "created": [str(path.relative_to(root_path)) for path in structure.created],
            "updated": [str(path.relative_to(root_path)) for path in structure.updated],
            "skipped": [str(path.relative_to(root_path)) for path in structure.skipped],
        }

    @plugin.register(
        "list",
        description="List plugin links",
        tags=["plugin", "inspect"],
        examples=["plugin list MyTool", "plugin list MyTool --output json"],
        default_output="rich",
    )
    @plugin.argument("root", type=t.Path(), default="", help="Project root path")
    def list_plugins(ctx: FxContext, root: Path | str = "") -> list[dict[str, Any]]:
        root_path = ctx.resolve(root)
        rows = ctx.plugins(root_path).filter(project_root=str(root_path), order_by="alias")
        return [
            {
                "alias": row.alias,
                "package_path": row.package_path,
                "enabled": row.enabled,
                "link_file": row.link_file,
            }
            for row in rows
        ]

    @plugin.register(
        "unlink",
        description="Remove a plugin link from fx state",
        tags=["plugin", "danger"],
        examples=["plugin unlink MyTool tools --force"],
        capture_logs=True,
    )
    @plugin.confirm(
        "Unlink plugin '{alias}' from fx state for {root}?",
        danger=True,
        confirm_phrase="unlink {alias}",
    )
    @plugin.dry_run()
    @plugin.argument("root", type=t.Path(), default="", help="Project root path")
    @plugin.argument("alias", type=str, help="Plugin alias")
    def unlink(
        ctx: FxContext,
        root: Path | str = "",
        alias: str = "",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        root_path = ctx.resolve(root)
        normalized = normalize_identifier(alias)
        if dry_run:
            return {
                "status": "dry-run",
                "message": f"Would unlink plugin '{normalized}'.",
                "root": str(root_path),
                "alias": normalized,
            }
        removed = ctx.plugins(root_path).delete_where(project_root=str(root_path), alias=normalized)
        record_operation(
            root=root_path,
            command="plugin unlink",
            arguments={"root": str(root_path), "alias": normalized},
            status="success",
            message=f"Unlinked plugin '{normalized}'.",
        )
        return {
            "status": "success",
            "message": f"Unlinked plugin '{normalized}'.",
            "root": str(root_path),
            "alias": normalized,
            "removed": removed,
        }

    @plugin.register(
        "sync",
        description="Sync local plugin packages into fx state",
        tags=["plugin"],
        examples=["plugin sync MyTool", "plugin sync MyTool --package demo --dry-run"],
        default_output="rich",
        capture_logs=True,
    )
    @plugin.progress("Syncing plugins")
    @plugin.dry_run()
    @plugin.argument("root", type=t.Path(), default="", help="Project root path")
    @plugin.argument("package", type=str, default="", help="Project package override")
    def sync(
        ctx: FxContext,
        root: Path | str = "",
        package: str = "",
        dry_run: bool = False,
        progress=None,
    ) -> dict[str, Any]:
        root_path = ctx.resolve(root)
        package_value = package or _project_package(ctx, root_path)
        import_base = resolve_plugin_import_base(root_path, package_value)
        aliases = discover_local_plugins(root_path, package_value)
        if dry_run:
            return {
                "status": "dry-run",
                "message": f"Would sync {len(aliases)} plugin(s).",
                "root": str(root_path),
                "package": package_value,
                "synced": 0,
                "aliases": aliases,
            }
        plugins = ctx.plugins(root_path)
        task = progress.add_task("Syncing plugins", total=len(aliases)) if progress is not None else None
        synced = 0
        for plugin_alias in aliases:
            package_path = f"{import_base}.{plugin_alias}"
            existing = plugins.get(alias=plugin_alias)
            created_at = existing.created_at if existing is not None else utc_now()
            plugins.upsert(
                project_root=str(root_path),
                alias=plugin_alias,
                package_path=package_path,
                enabled=True,
                link_file=str(resolve_plugin_layout(root_path, package_value).directory / plugin_alias / "__init__.py"),
                created_at=created_at,
                updated_at=utc_now(),
            )
            synced += 1
            if progress is not None and task is not None:
                progress.advance(task)
        record_operation(
            root=root_path,
            command="plugin sync",
            arguments={"root": str(root_path), "package": package_value},
            status="success",
            message=f"Synced {synced} plugin(s).",
        )
        return {
            "status": "success",
            "message": f"Synced {synced} plugin(s).",
            "root": str(root_path),
            "package": package_value,
            "synced": synced,
            "aliases": aliases,
        }


def _project_package(ctx: FxContext, root_path: Path) -> str:
    project = ctx.projects(root_path).get(root_path=str(root_path))
    return getattr(project, "package_name", "") if project is not None else ""
