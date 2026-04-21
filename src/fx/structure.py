"""
Filesystem structuring helpers for ``fx``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from fx.templates import (
    CLI_MAIN_TEMPLATE,
    CLI_PYPROJECT_TEMPLATE,
    CLI_README_TEMPLATE,
    CLI_TEST_TEMPLATE,
    CLI_TODO_TEMPLATE,
    COMMON_GITIGNORE_TEMPLATE,
    DB_API_TEMPLATE,
    DB_MAIN_TEMPLATE,
    DB_MODELS_TEMPLATE,
    DB_PYPROJECT_TEMPLATE,
    DB_README_TEMPLATE,
    DB_TEST_TEMPLATE,
    PACKAGE_INIT_TEMPLATE,
    render_template,
)


_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class StructureResult:
    created: tuple[Path, ...] = ()
    updated: tuple[Path, ...] = ()
    skipped: tuple[Path, ...] = ()
    entry_file: Path | None = None


@dataclass(frozen=True)
class PluginLayout:
    directory: Path
    import_base: str


def normalize_identifier(raw: str) -> str:
    cleaned = raw.strip().replace("-", "_")
    if not cleaned or not _IDENT_RE.match(cleaned):
        raise ValueError(
            f"Invalid name '{raw}'. Use a valid Python identifier (letters, digits, underscore)."
        )
    return cleaned


def distribution_name(raw: str) -> str:
    return normalize_identifier(raw).lower().replace("_", "-")


def package_name(raw: str) -> str:
    return normalize_identifier(raw).lower()


def ensure_package(path: Path, *, created: list[Path], skipped: list[Path]) -> None:
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
        created.append(path)

    init_file = path / "__init__.py"
    if init_file.exists():
        skipped.append(init_file)
    else:
        init_file.write_text("", encoding="utf-8")
        created.append(init_file)


def ensure_directory(path: Path, *, created: list[Path], skipped: list[Path]) -> None:
    if path.exists():
        skipped.append(path)
        return
    path.mkdir(parents=True, exist_ok=True)
    created.append(path)


def write_file(path: Path, content: str, *, force: bool, created: list[Path], updated: list[Path], skipped: list[Path]) -> None:
    if path.exists():
        if force:
            path.write_text(content, encoding="utf-8")
            updated.append(path)
        else:
            skipped.append(path)
        return

    path.write_text(content, encoding="utf-8")
    created.append(path)


def init_project_layout(*, root: Path, project_name: str, project_type: str, force: bool) -> StructureResult:
    created: list[Path] = []
    updated: list[Path] = []
    skipped: list[Path] = []

    # New structured projects always use a stable root package: app/
    pkg_name = "app"
    dist_name = distribution_name(project_name)
    script_name = dist_name
    package_root = root / pkg_name
    plugins_package = package_root / "plugins"

    ensure_directory(root / "tests", created=created, skipped=skipped)
    ensure_directory(package_root, created=created, skipped=skipped)
    ensure_package(plugins_package, created=created, skipped=skipped)
    (root / ".fx").mkdir(parents=True, exist_ok=True)

    shared_values = {
        "project_name": project_name,
        "package_name": pkg_name,
        "dist_name": dist_name,
        "script_name": script_name,
        "plugin_package": f"{pkg_name}.plugins",
        "project_root": str(root),
    }

    files: dict[Path, str] = {
        root / ".gitignore": COMMON_GITIGNORE_TEMPLATE,
        root / pkg_name / "__init__.py": render_template(PACKAGE_INIT_TEMPLATE, **shared_values),
    }

    entry_path: Path | None = None
    if project_type == "cli":
        files.update(
            {
                root / "pyproject.toml": render_template(CLI_PYPROJECT_TEMPLATE, **shared_values),
                root / "README.md": render_template(CLI_README_TEMPLATE, **shared_values),
                root / pkg_name / "__main__.py": render_template(CLI_MAIN_TEMPLATE, **shared_values),
                root / pkg_name / "todo.py": render_template(CLI_TODO_TEMPLATE, **shared_values),
                root / "tests" / "test_todo_automation.py": render_template(CLI_TEST_TEMPLATE, **shared_values),
            }
        )
        entry_path = root / pkg_name / "todo.py"
    elif project_type == "db":
        files.update(
            {
                root / "pyproject.toml": render_template(DB_PYPROJECT_TEMPLATE, **shared_values),
                root / "README.md": render_template(DB_README_TEMPLATE, **shared_values),
                root / pkg_name / "__main__.py": render_template(DB_MAIN_TEMPLATE, **shared_values),
                root / pkg_name / "models.py": render_template(DB_MODELS_TEMPLATE, **shared_values),
                root / pkg_name / "api.py": render_template(DB_API_TEMPLATE, **shared_values),
                root / "tests" / "test_user_api.py": render_template(DB_TEST_TEMPLATE, **shared_values),
            }
        )
        entry_path = root / pkg_name / "api.py"
    else:
        raise ValueError("project_type must be either 'cli' or 'db'.")

    for target, content in files.items():
        write_file(
            target,
            content,
            force=force,
            created=created,
            updated=updated,
            skipped=skipped,
        )

    return StructureResult(
        created=tuple(created),
        updated=tuple(updated),
        skipped=tuple(skipped),
        entry_file=entry_path,
    )


def create_module_layout(
    *,
    root: Path,
    module_type: str,
    module_name: str,
    force: bool,
) -> StructureResult:
    created: list[Path] = []
    updated: list[Path] = []
    skipped: list[Path] = []

    normalized = normalize_identifier(module_name)
    layout = resolve_plugin_layout(root)
    module_dir = layout.directory / normalized
    ensure_package(layout.directory, created=created, skipped=skipped)
    if not module_dir.exists():
        module_dir.mkdir(parents=True, exist_ok=True)
        created.append(module_dir)

    if module_type == "cli":
        module_path = module_dir / f"{normalized}.py"
        init_content = f"from .{normalized} import *\n"
        module_content = _cli_module_template(normalized)
    elif module_type == "db":
        module_path = module_dir / "models.py"
        init_content = "from .models import *\n"
        module_content = _db_module_template(normalized)
    else:
        raise ValueError("module_type must be either 'cli' or 'db'.")

    write_file(
        module_path,
        module_content,
        force=force,
        created=created,
        updated=updated,
        skipped=skipped,
    )
    write_file(
        module_dir / "__init__.py",
        init_content,
        force=force,
        created=created,
        updated=updated,
        skipped=skipped,
    )

    return StructureResult(
        created=tuple(created),
        updated=tuple(updated),
        skipped=tuple(skipped),
        entry_file=module_path,
    )


def create_plugin_link(
    *,
    root: Path,
    package_path: str,
    alias: str,
    force: bool,
) -> StructureResult:
    created: list[Path] = []
    updated: list[Path] = []
    skipped: list[Path] = []

    normalized_alias = normalize_identifier(alias)
    layout = resolve_plugin_layout(root)
    ensure_package(layout.directory, created=created, skipped=skipped)
    alias_dir = layout.directory / normalized_alias
    if not alias_dir.exists():
        alias_dir.mkdir(parents=True, exist_ok=True)
        created.append(alias_dir)

    init_path = alias_dir / "__init__.py"
    init_content = f"from {package_path} import *\n"
    write_file(
        init_path,
        init_content,
        force=force,
        created=created,
        updated=updated,
        skipped=skipped,
    )

    return StructureResult(
        created=tuple(created),
        updated=tuple(updated),
        skipped=tuple(skipped),
        entry_file=init_path,
    )


def discover_local_plugins(root: Path) -> list[str]:
    plugins_dir = resolve_plugin_layout(root).directory
    if not plugins_dir.exists():
        return []

    result: list[str] = []
    for candidate in sorted(plugins_dir.iterdir()):
        if not candidate.is_dir():
            continue
        if (candidate / "__init__.py").exists():
            result.append(candidate.name)
    return result


def discover_project_package(root: Path) -> str | None:
    package_dir = discover_project_package_dir(root)
    if package_dir is not None:
        return package_dir.name
    return None


def discover_project_package_dir(root: Path) -> Path | None:
    # Preferred current layout: ./app
    root_app = root / "app" / "__init__.py"
    if root_app.exists():
        return root / "app"

    # Legacy structured layout: ./src/app
    src_root = root / "src"
    src_app = src_root / "app" / "__init__.py"
    if src_app.exists():
        return src_root / "app"

    # Generic fallback under root for one package directory.
    root_candidates = sorted(
        child
        for child in root.iterdir()
        if child.is_dir() and (child / "__init__.py").exists()
    ) if root.exists() else []
    if len(root_candidates) == 1:
        return root_candidates[0]

    # Generic fallback under ./src for one package directory.
    if not src_root.exists():
        return None
    src_candidates = sorted(
        child
        for child in src_root.iterdir()
        if child.is_dir() and (child / "__init__.py").exists()
    )
    if len(src_candidates) == 1:
        return src_candidates[0]
    return None


def resolve_plugin_layout(root: Path) -> PluginLayout:
    package_dir = discover_project_package_dir(root)
    if package_dir is not None:
        package_plugins = package_dir / "plugins"
        if package_plugins.exists() and (package_plugins / "__init__.py").exists():
            return PluginLayout(package_plugins, f"{package_dir.name}.plugins")

    return PluginLayout(root / "plugins", "plugins")


def resolve_plugin_import_base(root: Path) -> str:
    return resolve_plugin_layout(root).import_base


def _cli_module_template(module_name: str) -> str:
    kebab = module_name.replace("_", "-")
    return (
        "from __future__ import annotations\n\n"
        "import registers.cli as cli\n\n\n"
        f"@cli.register(description=\"Run a command from '{module_name}' module\")\n"
        f"@cli.argument(\"subject\", type=str, help=\"Subject to process\")\n"
        f"@cli.option(\"--{kebab}-run\")\n"
        f"def {module_name}_run(subject: str) -> str:\n"
        f"    return f\"{module_name}: {{subject}}\"\n"
    )


def _db_module_template(module_name: str) -> str:
    class_name = "".join(part.capitalize() for part in module_name.split("_")) + "Record"
    return (
        "from __future__ import annotations\n\n"
        "from pydantic import BaseModel\n\n"
        "import registers.db as db\n\n\n"
        f"@db.database_registry(\"{module_name}.db\", table_name=\"{module_name}\", key_field=\"id\")\n"
        f"class {class_name}(BaseModel):\n"
        "    id: int | None = None\n"
        "    name: str\n"
    )

