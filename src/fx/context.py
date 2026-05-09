from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from registers.cli import Context

from fx.state import module_registry, operation_registry, plugin_registry, project_registry, resolve_root


@dataclass(frozen=True)
class FxContext(Context):
    """Run-scoped state shared across fx commands."""

    root: Path
    cwd: Path
    version: str

    def resolve(self, root: str | Path | None = None) -> Path:
        if root is None or str(root).strip() == "":
            return self.root
        return resolve_root(root)

    def projects(self, root: str | Path | None = None):
        return project_registry(self.resolve(root))

    def modules(self, root: str | Path | None = None):
        return module_registry(self.resolve(root))

    def plugins(self, root: str | Path | None = None):
        return plugin_registry(self.resolve(root))

    def operations(self, root: str | Path | None = None):
        return operation_registry(self.resolve(root))
