from __future__ import annotations

import importlib
import sys

from fx.commands import project_group
from fx.state import operation_registry, project_registry, record_operation, resolve_root
from fx.structure import (
    discover_local_plugins,
    discover_project_package_dir,
    discover_project_packages,
    package_name as normalize_package_name,
    resolve_plugin_import_base,
)


@project_group.register("health", description="Validate runnable package, imports, and project metadata")
@project_group.argument("root", type=str, default=".", help="Project root path")
@project_group.argument("package", type=str, default="", help="Package name override")
def health(root: str = ".", package: str = "") -> str:
    root_path = resolve_root(root)
    project = project_registry(root_path).get(root_path=str(root_path))
    project_type = getattr(project, "project_type", "")
    package_value = normalize_package_name(package) if package.strip() else getattr(project, "package_name", "")
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
    if not failures:
        return "Health checks passed."
    return "Health checks failed:\n" + "\n".join(f"  - {failure}" for failure in failures)


def _validate_import(root_path, dotted: str, *, require_attr: str = "") -> list[str]:
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


@project_group.register("history", description="Show recent fx operation history")
@project_group.argument("root", type=str, default=".", help="Project root path")
@project_group.argument("limit", type=int, default=20, help="Maximum number of operations to show")
def history(root: str = ".", limit: int = 20) -> str:
    root_path = resolve_root(root)
    rows = operation_registry(root_path).filter(project_root=str(root_path), order_by="-id", limit=limit)
    if not rows:
        return "No operation history found."
    lines = ["Recent operations:"]
    for row in rows:
        lines.append(f"  [{row.id}] {row.created_at}  {row.command}  {row.status}")
        if row.message:
            lines.append(f"      {row.message}")
    return "\n".join(lines)
