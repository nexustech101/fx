from __future__ import annotations

from typing import Literal

from fx.commands import module_group, plugin_group, project_group
from fx.state import (
    module_registry,
    plugin_registry,
    project_registry,
    record_operation,
    resolve_root,
    utc_now,
)
from fx.structure import (
    create_module_layout,
    create_plugin_link,
    discover_local_plugins,
    discover_project_package,
    discover_project_package_dir,
    discover_project_packages,
    init_project_layout,
    normalize_identifier,
    package_name as normalize_package_name,
    resolve_plugin_import_base,
    resolve_plugin_layout,
)
from fx.support import render_structure_result


def _project_metadata(root: str) -> tuple[str, str, str]:
    root_path = resolve_root(root)
    project = project_registry(root_path).get(root_path=str(root_path))
    if project is None:
        return "", "", ""
    return (
        getattr(project, "project_type", ""),
        getattr(project, "package_name", ""),
        getattr(project, "layout", ""),
    )


@project_group.register("init", description="Create a minimal cli, db, or cron project")
@project_group.argument("project_type", type=str, help="Project type: cli, db, or cron")
@project_group.argument("project_name", type=str, help="Project display/package name")
@project_group.argument("root", type=str, default="", help="Project root path; defaults to project name")
@project_group.argument("package", type=str, default="", help="Python package name; defaults to normalized project name")
@project_group.argument("layout", type=Literal["src", "root"], default="src", help="Project layout: src or root")
@project_group.argument("force", type=bool, default=False, help="Overwrite existing files")
def init_project(
    project_type: str,
    project_name: str,
    root: str = "",
    package: str = "",
    layout: Literal["src", "root"] = "src",
    force: bool = False,
) -> str:
    normalized_type = project_type.strip().lower()
    if normalized_type not in {"cli", "db", "cron"}:
        raise ValueError("project_type must be one of: cli, db, cron.")

    name = project_name.strip()
    if not name:
        raise ValueError("project_name is required.")
    root_path = resolve_root(root.strip() or name)
    root_path.mkdir(parents=True, exist_ok=True)
    package_value = normalize_package_name(package or name)

    structure = init_project_layout(
        root=root_path,
        project_name=name,
        project_type=normalized_type,
        package=package_value,
        layout=layout,
        force=force,
    )

    projects = project_registry(root_path)
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
    return render_structure_result(
        title=f"Initialized {normalized_type} project '{name}' at {root_path}",
        root=root_path,
        result=structure,
    )


@project_group.register("status", description="Show project structure and fx state")
@project_group.argument("root", type=str, default=".", help="Project root path")
@project_group.argument("package", type=str, default="", help="Package name override")
def status(root: str = ".", package: str = "") -> str:
    root_path = resolve_root(root)
    project = project_registry(root_path).get(root_path=str(root_path))
    project_type = getattr(project, "project_type", "unknown") if project else "unknown"
    package_value = normalize_package_name(package) if package.strip() else getattr(project, "package_name", "")
    layout_value = getattr(project, "layout", "unknown") if project else "unknown"
    packages = discover_project_packages(root_path)
    package_dir = discover_project_package_dir(root_path, package_value)
    package_name = discover_project_package(root_path, package_value)
    plugin_layout = resolve_plugin_layout(root_path, package_value)
    local_plugins = discover_local_plugins(root_path, package_value)
    modules = module_registry(root_path).filter(project_root=str(root_path), order_by="module_name")
    plugins = plugin_registry(root_path).filter(project_root=str(root_path), order_by="alias")
    registered_aliases = [plugin.alias for plugin in plugins]
    missing_on_disk = sorted(set(registered_aliases) - set(local_plugins))
    untracked_on_disk = sorted(set(local_plugins) - set(registered_aliases))

    lines = [
        f"Root: {root_path}",
        f"Project record: {'present' if project else 'missing'}",
        f"Project type: {project_type}",
        f"Package: {package_name or 'missing'}",
        f"Layout: {layout_value}",
        f"Runnable packages: {', '.join(pkg.name for pkg in packages) if packages else 'none'}",
        f"Package root: {package_dir if package_dir is not None else 'missing'}",
        f"__main__.py: {'present' if package_dir and (package_dir / '__main__.py').exists() else 'missing'}",
        f"api.py: {'present' if package_dir and (package_dir / 'api.py').exists() else 'missing'}",
        f"jobs.py: {'present' if package_dir and (package_dir / 'jobs.py').exists() else 'missing'}",
        f"pyproject.toml: {'present' if (root_path / 'pyproject.toml').exists() else 'missing'}",
        f"plugins package: {'present' if (plugin_layout.directory / '__init__.py').exists() else 'missing'}",
        f"plugins import base: {plugin_layout.import_base}",
        f"Registered modules: {len(modules)}",
        f"Registered plugin links: {len(plugins)}",
        f"Local plugin packages: {len(local_plugins)}",
    ]
    if missing_on_disk:
        lines.append(f"Missing on disk: {', '.join(missing_on_disk)}")
    if untracked_on_disk:
        lines.append(f"Untracked on disk: {', '.join(untracked_on_disk)}")
    if not missing_on_disk and not untracked_on_disk:
        lines.append("Registry and filesystem plugin lists are aligned.")
    return "\n".join(lines)


@module_group.register("add", description="Add a minimal module package under the project plugins package")
@module_group.argument("root", type=str, help="Project root path")
@module_group.argument("module_type", type=str, help="Module type: cli, db, or cron")
@module_group.argument("module_name", type=str, help="Module identifier")
@module_group.argument("package", type=str, default="", help="Package name override")
@module_group.argument("force", type=bool, default=False, help="Overwrite existing module files")
def module_add(
    root: str,
    module_type: str,
    module_name: str,
    package: str = "",
    force: bool = False,
) -> str:
    root_path = resolve_root(root)
    normalized_type = module_type.strip().lower()
    if normalized_type not in {"cli", "db", "cron"}:
        raise ValueError("module_type must be one of: cli, db, cron.")
    normalized = normalize_identifier(module_name)
    package_value = package or _project_metadata(root)[1]
    import_base = resolve_plugin_import_base(root_path, package_value)
    structure = create_module_layout(
        root=root_path,
        module_type=normalized_type,
        module_name=normalized,
        force=force,
        package=package_value,
    )
    package_path = f"{import_base}.{normalized}"
    modules = module_registry(root_path)
    existing = modules.get(package_path=package_path)
    created_at = existing.created_at if existing is not None else utc_now()
    modules.upsert(
        project_root=str(root_path),
        module_type=normalized_type,
        module_name=normalized,
        package_path=package_path,
        entry_file=str(structure.entry_file or ""),
        created_at=created_at,
        updated_at=utc_now(),
    )
    plugins = plugin_registry(root_path)
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
        arguments={"root": str(root_path), "module_type": normalized_type, "module_name": normalized},
        status="success",
        message=f"Added {normalized_type} module '{normalized}'.",
    )
    return render_structure_result(
        title=f"Added {normalized_type} module '{normalized}'",
        root=root_path,
        result=structure,
    )


@module_group.register("list", description="List registered modules")
@module_group.argument("root", type=str, default=".", help="Project root path")
def module_list(root: str = ".") -> str:
    root_path = resolve_root(root)
    modules = module_registry(root_path).filter(project_root=str(root_path), order_by="module_name")
    if not modules:
        return "No modules registered for this project."
    lines = ["Registered modules:"]
    for entry in modules:
        lines.append(f"  {entry.module_name}  ({entry.module_type})  {entry.package_path}")
    return "\n".join(lines)


@module_group.register("remove", description="Remove a module from fx state")
@module_group.argument("root", type=str, help="Project root path")
@module_group.argument("module_name", type=str, help="Module identifier")
def module_remove(root: str, module_name: str) -> str:
    root_path = resolve_root(root)
    normalized = normalize_identifier(module_name)
    removed = module_registry(root_path).delete_where(project_root=str(root_path), module_name=normalized)
    plugin_registry(root_path).delete_where(project_root=str(root_path), alias=normalized)
    record_operation(
        root=root_path,
        command="module remove",
        arguments={"root": str(root_path), "module_name": normalized},
        status="success",
        message=f"Removed module '{normalized}' from fx state.",
    )
    return f"Removed module '{normalized}' from fx state ({removed} record(s))."


@plugin_group.register("link", description="Link an importable package under the project plugins package")
@plugin_group.argument("root", type=str, help="Project root path")
@plugin_group.argument("package_path", type=str, help="Importable package path")
@plugin_group.argument("alias", type=str, default="", help="Local alias under plugins/")
@plugin_group.argument("package", type=str, default="", help="Project package override")
@plugin_group.argument("force", type=bool, default=False, help="Overwrite existing alias shim")
def plugin_link(
    root: str,
    package_path: str,
    alias: str = "",
    package: str = "",
    force: bool = False,
) -> str:
    root_path = resolve_root(root)
    resolved_alias = normalize_identifier(alias or package_path.split(".")[-1])
    package_value = package or _project_metadata(root)[1]
    structure = create_plugin_link(
        root=root_path,
        package_path=package_path,
        alias=resolved_alias,
        force=force,
        package=package_value,
    )
    plugins = plugin_registry(root_path)
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
    return render_structure_result(
        title=f"Linked plugin '{resolved_alias}' -> {package_path}",
        root=root_path,
        result=structure,
    )


@plugin_group.register("list", description="List plugin links")
@plugin_group.argument("root", type=str, default=".", help="Project root path")
def plugin_list(root: str = ".") -> str:
    root_path = resolve_root(root)
    plugins = plugin_registry(root_path).filter(project_root=str(root_path), order_by="alias")
    if not plugins:
        return "No plugins linked for this project."
    lines = ["Linked plugins:"]
    for entry in plugins:
        marker = "enabled" if entry.enabled else "disabled"
        lines.append(f"  {entry.alias}  ->  {entry.package_path}  ({marker})")
    return "\n".join(lines)


@plugin_group.register("unlink", description="Remove a plugin link from fx state")
@plugin_group.argument("root", type=str, help="Project root path")
@plugin_group.argument("alias", type=str, help="Plugin alias")
def plugin_unlink(root: str, alias: str) -> str:
    root_path = resolve_root(root)
    normalized = normalize_identifier(alias)
    removed = plugin_registry(root_path).delete_where(project_root=str(root_path), alias=normalized)
    record_operation(
        root=root_path,
        command="plugin unlink",
        arguments={"root": str(root_path), "alias": normalized},
        status="success",
        message=f"Unlinked plugin '{normalized}'.",
    )
    return f"Unlinked plugin '{normalized}' ({removed} record(s))."


@plugin_group.register("sync", description="Sync local plugin packages into fx state")
@plugin_group.argument("root", type=str, default=".", help="Project root path")
@plugin_group.argument("package", type=str, default="", help="Project package override")
def plugin_sync(root: str = ".", package: str = "") -> str:
    root_path = resolve_root(root)
    package_value = package or _project_metadata(root)[1]
    import_base = resolve_plugin_import_base(root_path, package_value)
    plugins = plugin_registry(root_path)
    synced = 0
    for alias in discover_local_plugins(root_path, package_value):
        package_path = f"{import_base}.{alias}"
        existing = plugins.get(alias=alias)
        created_at = existing.created_at if existing is not None else utc_now()
        plugins.upsert(
            project_root=str(root_path),
            alias=alias,
            package_path=package_path,
            enabled=True,
            link_file=str(resolve_plugin_layout(root_path, package_value).directory / alias / "__init__.py"),
            created_at=created_at,
            updated_at=utc_now(),
        )
        synced += 1
    record_operation(
        root=root_path,
        command="plugin sync",
        arguments={"root": str(root_path), "package": package_value},
        status="success",
        message=f"Synced {synced} plugin(s).",
    )
    return f"Synced {synced} plugin(s)."
