"""
Runtime/process helpers for ``fx`` commands.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Sequence
import venv


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int


def run_command(argv: Sequence[str], *, cwd: Path | None = None) -> CommandResult:
    completed = subprocess.run(list(argv), cwd=str(cwd) if cwd is not None else None)
    return CommandResult(tuple(str(part) for part in argv), int(completed.returncode))


def run_checked(argv: Sequence[str], *, cwd: Path | None = None) -> CommandResult:
    result = run_command(argv, cwd=cwd)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}: {' '.join(result.argv)}"
        )
    return result


def normalize_extras(extras: str) -> str:
    parts = [part.strip() for part in extras.split(",") if part.strip()]
    return ",".join(parts)


def editable_install_target(root: Path, extras: str = "") -> str:
    target = str(root.resolve())
    normalized = normalize_extras(extras)
    if not normalized:
        return target
    return f"{target}[{normalized}]"


def _venv_python_path(venv_root: Path) -> Path:
    if os.name == "nt":
        return venv_root / "Scripts" / "python.exe"
    return venv_root / "bin" / "python"


def ensure_venv_python(root: Path, venv_path: str) -> Path:
    if not venv_path.strip():
        return Path(sys.executable)

    candidate = Path(venv_path)
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()

    if not candidate.exists():
        builder = venv.EnvBuilder(with_pip=True)
        builder.create(str(candidate))

    python_path = _venv_python_path(candidate)
    if not python_path.exists():
        raise FileNotFoundError(f"Virtualenv python not found at {python_path}")
    return python_path


@dataclass(frozen=True)
class CloneResult:
    repo_path: Path


def clone_repo(*, repo_url: str, ref: str = "main") -> CloneResult:
    checkout_dir = Path(tempfile.mkdtemp(prefix="fx-pull-")).resolve()
    run_checked(
        ["git", "clone", "--depth", "1", "--branch", ref, repo_url, str(checkout_dir)]
    )
    return CloneResult(repo_path=checkout_dir)

