"""
Filesystem helpers for minimal ``fx`` project layouts.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


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


@dataclass(frozen=True)
class ProjectPackage:
    name: str
    directory: Path
    layout: str


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


def _project_package_name(project_name: str, package: str = "") -> str:
    return package_name(package or project_name)


def _package_parent(root: Path, layout: str) -> Path:
    if layout == "src":
        return root / "src"
    if layout == "root":
        return root
    raise ValueError("layout must be either 'src' or 'root'.")


def _write_file(
    path: Path,
    content: str,
    *,
    force: bool,
    created: list[Path],
    updated: list[Path],
    skipped: list[Path],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if force:
            path.write_text(content, encoding="utf-8")
            updated.append(path)
        else:
            skipped.append(path)
        return
    path.write_text(content, encoding="utf-8")
    created.append(path)


def _ensure_dir(path: Path, *, created: list[Path], skipped: list[Path]) -> None:
    if path.exists():
        skipped.append(path)
        return
    path.mkdir(parents=True, exist_ok=True)
    created.append(path)


def _pyproject(
    *,
    project_name: str,
    package: str,
    layout: str,
    project_type: str,
) -> str:
    dependencies = ['"registers>=6.1.0"']
    dev_dependencies = ['"pytest>=7.4"']
    if project_type == "db":
        dependencies.extend(['"fastapi>=0.111"', '"uvicorn>=0.30"'])
        dev_dependencies.append('"httpx>=0.27"')
    where = "src" if layout == "src" else "."
    dep_lines = ",\n    ".join(dependencies)
    dev_lines = ",\n    ".join(dev_dependencies)
    return f"""[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "{distribution_name(project_name)}"
version = "0.1.0"
description = "{project_name} project managed by fx"
readme = "README.md"
requires-python = ">=3.10"
dependencies = [
    {dep_lines},
]

[project.scripts]
{distribution_name(project_name)} = "{package}.__main__:main"

[project.optional-dependencies]
dev = [
    {dev_lines},
]

[tool.setuptools.packages.find]
where = ["{where}"]
include = ["{package}*"]
"""


def _readme(project_name: str, package: str, project_type: str) -> str:
    run_hint = "python -m uvicorn {package}.api:app" if project_type == "db" else f"python -m {package}"
    return f"""# {project_name}

Minimal {project_type} project managed by `fx`.

## Run

```bash
{run_hint}
```
"""


def _gitignore() -> str:
    return """.venv/
__pycache__/
.pytest_cache/
.mypy_cache/
.ruff_cache/
*.pyc
*.pyo
*.pyd
*.sqlite
*.db
.DS_Store
"""


def _package_init(project_name: str) -> str:
    return f'"""Minimal package for {project_name}."""\n\n__all__ = []\n'


def _cli_main(project_name: str) -> str:
    return f'''from __future__ import annotations

from registers import CommandRegistry


cli = CommandRegistry()


def main() -> None:
    cli.run(shell_title="{project_name}", shell_usage=True)


if __name__ == "__main__":
    main()
'''


def _db_main(package: str) -> str:
    return f'''from __future__ import annotations

import uvicorn


def main() -> None:
    uvicorn.run("{package}.api:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
'''


def _db_models() -> str:
    return '''from __future__ import annotations

from registers import DatabaseRegistry


db = DatabaseRegistry()
MODEL_REGISTRY: tuple[type, ...] = ()
'''


def _db_api() -> str:
    return '''from __future__ import annotations

from contextlib import asynccontextmanager

try:
    from fastapi import FastAPI
except ImportError:  # pragma: no cover - exercised when generated deps are not installed
    FastAPI = None

from .models import MODEL_REGISTRY


@asynccontextmanager
async def lifespan(app):
    for model in MODEL_REGISTRY:
        if hasattr(model, "schema_exists") and not model.schema_exists():
            model.create_schema()
    yield
    for model in MODEL_REGISTRY:
        objects = getattr(model, "objects", None)
        dispose = getattr(objects, "dispose", None)
        if callable(dispose):
            dispose()


if FastAPI is not None:
    app = FastAPI(lifespan=lifespan)


    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}
else:
    async def app(scope, receive, send):
        if scope["type"] != "http":
            return
        body = b'{"status":"ok","runtime":"fallback"}'
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": body})
'''


def _cron_main(project_name: str) -> str:
    return f'''from __future__ import annotations

import registers.cli as cli
import registers.cron as cron

from . import jobs as _jobs


def main() -> None:
    cron.install_cli()
    cli.run(shell_title="{project_name} Automation", shell_usage=True)


if __name__ == "__main__":
    main()
'''


def _cron_jobs() -> str:
    return '''from __future__ import annotations

import registers.cron as cron


__all__: list[str] = []
'''


def init_project_layout(
    *,
    root: Path,
    project_name: str,
    project_type: str,
    package: str = "",
    layout: str = "src",
    force: bool,
) -> StructureResult:
    normalized_type = project_type.strip().lower()
    if normalized_type not in {"cli", "db", "cron"}:
        raise ValueError("project_type must be one of: cli, db, cron.")
    normalized_layout = layout.strip().lower() or "src"
    pkg = _project_package_name(project_name, package)
    package_dir = _package_parent(root, normalized_layout) / pkg

    created: list[Path] = []
    updated: list[Path] = []
    skipped: list[Path] = []

    _ensure_dir(package_dir, created=created, skipped=skipped)
    (root / ".fx").mkdir(parents=True, exist_ok=True)

    files: dict[Path, str] = {
        root / ".gitignore": _gitignore(),
        root / "README.md": _readme(project_name, pkg, normalized_type),
        root / "pyproject.toml": _pyproject(
            project_name=project_name,
            package=pkg,
            layout=normalized_layout,
            project_type=normalized_type,
        ),
        package_dir / "__init__.py": _package_init(project_name),
    }

    if normalized_type == "cli":
        files[package_dir / "__main__.py"] = _cli_main(project_name)
        entry_file = package_dir / "__main__.py"
    elif normalized_type == "db":
        files[package_dir / "__main__.py"] = _db_main(pkg)
        files[package_dir / "api.py"] = _db_api()
        files[package_dir / "models.py"] = _db_models()
        entry_file = package_dir / "__main__.py"
    else:
        files[package_dir / "__main__.py"] = _cron_main(project_name)
        files[package_dir / "jobs.py"] = _cron_jobs()
        entry_file = package_dir / "__main__.py"

    for target, content in files.items():
        _write_file(target, content, force=force, created=created, updated=updated, skipped=skipped)

    return StructureResult(
        created=tuple(created),
        updated=tuple(updated),
        skipped=tuple(skipped),
        entry_file=entry_file,
    )


def discover_project_packages(root: Path) -> list[ProjectPackage]:
    if not root.exists():
        return []
    result: list[ProjectPackage] = []
    src_root = root / "src"
    if src_root.exists():
        result.extend(_discover_packages_under(src_root, layout="src"))
    result.extend(_discover_packages_under(root, layout="root"))
    return result


def _discover_packages_under(parent: Path, *, layout: str) -> list[ProjectPackage]:
    result: list[ProjectPackage] = []
    for child in sorted(parent.iterdir()) if parent.exists() else []:
        if not child.is_dir() or child.name.startswith(".") or child.name in {"src", "tests"}:
            continue
        if (child / "__init__.py").exists() and (child / "__main__.py").exists():
            result.append(ProjectPackage(child.name, child, layout))
    return result


def discover_project_package_dir(root: Path, package: str = "") -> Path | None:
    normalized = package_name(package) if package.strip() else ""
    packages = discover_project_packages(root)
    if normalized:
        for candidate in packages:
            if candidate.name == normalized:
                return candidate.directory
        return None
    if len(packages) == 1:
        return packages[0].directory
    return None


def discover_project_package(root: Path, package: str = "") -> str | None:
    package_dir = discover_project_package_dir(root, package)
    return package_dir.name if package_dir is not None else None


def resolve_plugin_layout(root: Path, package: str = "") -> PluginLayout:
    package_dir = discover_project_package_dir(root, package)
    if package_dir is not None:
        return PluginLayout(package_dir / "plugins", f"{package_dir.name}.plugins")
    return PluginLayout(root / "plugins", "plugins")


def resolve_plugin_import_base(root: Path, package: str = "") -> str:
    return resolve_plugin_layout(root, package).import_base


def ensure_package(path: Path, *, created: list[Path], skipped: list[Path]) -> None:
    _ensure_dir(path, created=created, skipped=skipped)
    init_file = path / "__init__.py"
    if init_file.exists():
        skipped.append(init_file)
    else:
        init_file.write_text("", encoding="utf-8")
        created.append(init_file)


def create_module_layout(
    *,
    root: Path,
    module_type: str,
    module_name: str,
    force: bool,
    package: str = "",
) -> StructureResult:
    normalized_type = module_type.strip().lower()
    if normalized_type not in {"cli", "db", "cron"}:
        raise ValueError("module_type must be one of: cli, db, cron.")
    normalized = normalize_identifier(module_name)
    layout = resolve_plugin_layout(root, package)
    module_dir = layout.directory / normalized

    created: list[Path] = []
    updated: list[Path] = []
    skipped: list[Path] = []

    ensure_package(layout.directory, created=created, skipped=skipped)
    ensure_package(module_dir, created=created, skipped=skipped)

    if normalized_type == "cli":
        entry_file = module_dir / "commands.py"
        content = "from __future__ import annotations\n\nfrom registers import CommandRegistry\n\n\ncli = CommandRegistry()\n"
    elif normalized_type == "db":
        entry_file = module_dir / "models.py"
        content = _db_models()
    else:
        entry_file = module_dir / "jobs.py"
        content = _cron_jobs()

    _write_file(entry_file, content, force=force, created=created, updated=updated, skipped=skipped)
    return StructureResult(tuple(created), tuple(updated), tuple(skipped), entry_file)


def create_plugin_link(
    *,
    root: Path,
    package_path: str,
    alias: str,
    force: bool,
    package: str = "",
) -> StructureResult:
    normalized_alias = normalize_identifier(alias)
    layout = resolve_plugin_layout(root, package)

    created: list[Path] = []
    updated: list[Path] = []
    skipped: list[Path] = []

    ensure_package(layout.directory, created=created, skipped=skipped)
    alias_dir = layout.directory / normalized_alias
    ensure_package(alias_dir, created=created, skipped=skipped)
    init_path = alias_dir / "__init__.py"
    _write_file(
        init_path,
        f"from {package_path} import *\n",
        force=force,
        created=created,
        updated=updated,
        skipped=skipped,
    )
    return StructureResult(tuple(created), tuple(updated), tuple(skipped), init_path)


def discover_local_plugins(root: Path, package: str = "") -> list[str]:
    plugins_dir = resolve_plugin_layout(root, package).directory
    if not plugins_dir.exists():
        return []
    return sorted(
        candidate.name
        for candidate in plugins_dir.iterdir()
        if candidate.is_dir() and (candidate / "__init__.py").exists()
    )
