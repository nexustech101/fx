from __future__ import annotations

import builtins
from dataclasses import dataclass
import json
from pathlib import Path
import sys

import pytest

from registers.cli.exceptions import CommandExecutionError, DuplicateCommandError
from registers.cron.state import clear_state_caches as clear_cron_state_caches
from fx import run, run_async
from fx.commands import FX_VERSION, build_registry
from fx.state import clear_state_caches, operation_registry, project_registry


@pytest.fixture(autouse=True)
def _clear_fx_state_caches():
    clear_state_caches()
    clear_cron_state_caches()
    yield
    clear_state_caches()
    clear_cron_state_caches()


def test_grouped_help_exposes_canonical_commands_only(capsys: pytest.CaptureFixture[str]) -> None:
    run(["--help"], print_result=False)
    out = capsys.readouterr().out
    assert "  project  Create and inspect fx projects" in out
    assert "    init" in out
    assert "  run  Run project entrypoints" in out
    assert "    api" in out
    assert "  package  Install, update, and pull packages" in out
    assert "    install" in out
    assert "  cron  Manage registers.cron projects" in out
    assert "    jobs" in out
    assert "\n  project init" not in out
    assert "module-add" not in out

    run(["help", "project"], print_result=False)
    project_help = capsys.readouterr().out
    assert "Command group: project" in project_help
    assert "  init" in project_help
    assert "project init" not in project_help


def test_version_option_returns_current_version() -> None:
    assert run(["--version"], print_result=False) == f"fx {FX_VERSION}"


async def test_run_async_supports_embedded_callers() -> None:
    assert await run_async(["version"], print_result=False) == f"fx {FX_VERSION}"


def test_project_init_cli_src_layout_is_bare_bones(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = run(["project", "init", "cli", "Demo"], print_result=False)

    project_root = tmp_path / "Demo"
    assert result["status"] == "success"
    assert result["message"] == "Initialized cli project 'Demo'."
    assert (project_root / "src" / "demo" / "__main__.py").exists()
    assert (project_root / "src" / "demo" / "__init__.py").exists()
    assert (project_root / "pyproject.toml").exists()
    assert not (project_root / "src" / "demo" / "todo.py").exists()
    assert not (project_root / "tests" / "test_todo_automation.py").exists()

    record = project_registry(project_root).get(root_path=str(project_root))
    assert record is not None
    assert record.project_type == "cli"
    assert record.package_name == "demo"
    assert record.layout == "src"


def test_project_init_db_and_cron_root_layouts_are_minimal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    db_result = run(
        ["project", "init", "db", "ApiDemo", "--layout", "root", "--package", "api_app"],
        print_result=False,
    )
    cron_result = run(
        ["project", "init", "cron", "OpsDemo", "--layout", "root", "--package", "ops_app"],
        print_result=False,
    )

    api_root = tmp_path / "ApiDemo"
    ops_root = tmp_path / "OpsDemo"
    assert db_result["message"] == "Initialized db project 'ApiDemo'."
    assert (api_root / "api_app" / "__main__.py").exists()
    assert (api_root / "api_app" / "api.py").exists()
    assert (api_root / "api_app" / "models.py").exists()
    assert "@app.post" not in (api_root / "api_app" / "api.py").read_text(encoding="utf-8")
    assert cron_result["message"] == "Initialized cron project 'OpsDemo'."
    assert (ops_root / "ops_app" / "__main__.py").exists()
    assert (ops_root / "ops_app" / "jobs.py").exists()
    assert "cron.install_cli()" in (ops_root / "ops_app" / "__main__.py").read_text(encoding="utf-8")


def test_project_status_and_health_use_runnable_package_discovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    run(["project", "init", "db", "ApiDemo"], print_result=False)
    project_root = tmp_path / "ApiDemo"

    status = run(["project", "status", str(project_root)], print_result=False)
    health = run(["project", "health", str(project_root)], print_result=False)

    assert status["runnable_packages"] == ["apidemo"]
    assert status["__main__.py"] == "present"
    assert status["api.py"] == "present"
    assert "todo.py" not in status
    assert health["status"] == "success"
    assert health["failures"] == []


def test_project_health_passes_when_generated_fastapi_dependency_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    run(["project", "init", "db", "ApiDemo"], print_result=False)
    project_root = tmp_path / "ApiDemo"
    original_import = builtins.__import__

    def _blocked_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "fastapi":
            raise ImportError("No module named 'fastapi'")
        return original_import(name, globals, locals, fromlist, level)

    for key in [key for key in list(sys.modules) if key == "apidemo" or key.startswith("apidemo.")]:
        sys.modules.pop(key, None)
    monkeypatch.setattr(builtins, "__import__", _blocked_import)

    health = run(["project", "health", str(project_root)], print_result=False)

    assert health["status"] == "success"
    assert health["failures"] == []


def test_run_api_uses_uvicorn_and_src_package_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    run(["project", "init", "db", "ApiDemo"], print_result=False)
    project_root = tmp_path / "ApiDemo"
    calls: list[tuple[list[str], Path | None]] = []

    def _fake_run_checked(argv: list[str], *, cwd: Path | None = None):
        calls.append((list(argv), cwd))
        return None

    monkeypatch.setattr("fx.command_sets.run.run_checked", _fake_run_checked)

    result = run(
        ["run", "api", str(project_root), "--host", "0.0.0.0", "--port", "9000", "--reload"],
        print_result=False,
    )

    assert result["status"] == "success"
    assert result["mode"] == "api"
    argv, cwd = calls[-1]
    assert argv[1:4] == ["-m", "uvicorn", "apidemo.api:app"]
    assert "--reload" in argv
    assert cwd == project_root / "src"


def test_run_discovery_requires_package_when_ambiguous(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    for package in ("alpha", "beta"):
        package_dir = tmp_path / "src" / package
        package_dir.mkdir(parents=True)
        (package_dir / "__init__.py").write_text("", encoding="utf-8")
        (package_dir / "__main__.py").write_text("def main(): pass\n", encoding="utf-8")

    with pytest.raises(CommandExecutionError, match="Multiple runnable packages"):
        run(["run", "cli", "."], print_result=False)


def test_run_package_override_resolves_ambiguous_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    for package in ("alpha", "beta"):
        package_dir = tmp_path / "src" / package
        package_dir.mkdir(parents=True)
        (package_dir / "__init__.py").write_text("", encoding="utf-8")
        (package_dir / "__main__.py").write_text("def main(): pass\n", encoding="utf-8")
    calls: list[tuple[list[str], Path | None]] = []

    def _fake_run_checked(argv: list[str], *, cwd: Path | None = None):
        calls.append((list(argv), cwd))
        return None

    monkeypatch.setattr("fx.command_sets.run.run_checked", _fake_run_checked)

    run(["run", "cli", ".", "--package", "beta"], print_result=False)

    argv, cwd = calls[-1]
    assert argv[1:3] == ["-m", "beta"]
    assert cwd == tmp_path / "src"


def test_module_and_plugin_grouped_commands_update_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    run(["project", "init", "cli", "Demo"], print_result=False)
    project_root = tmp_path / "Demo"

    module_result = run(["module", "add", str(project_root), "cli", "users"], print_result=False)
    plugin_result = run(["plugin", "link", str(project_root), "math", "math_ops"], print_result=False)
    module_list = run(["module", "list", str(project_root)], print_result=False)
    plugin_list = run(["plugin", "list", str(project_root)], print_result=False)

    assert module_result["message"] == "Added cli module 'users'."
    assert plugin_result["message"] == "Linked plugin 'math_ops' -> math"
    assert module_list == [
        {
            "module_name": "users",
            "module_type": "cli",
            "package_path": "demo.plugins.users",
            "entry_file": str(project_root / "src" / "demo" / "plugins" / "users" / "commands.py"),
        }
    ]
    linked_plugin = next(row for row in plugin_list if row["alias"] == "math_ops")
    assert linked_plugin["package_path"] == "math"
    assert linked_plugin["enabled"] is True


def test_package_install_and_update_build_commands(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    run(["project", "init", "cli", "Demo"], print_result=False)
    project_root = tmp_path / "Demo"
    calls: list[list[str]] = []

    def _fake_run_checked(argv: list[str], *, cwd: Path | None = None):
        calls.append(list(argv))
        return None

    monkeypatch.setattr("fx.command_sets.package.run_checked", _fake_run_checked)

    run(["package", "install", str(project_root), "--extras", "dev"], print_result=False)
    run(["package", "update", str(project_root), "--package", "registers"], print_result=False)

    assert calls[0][1:5] == ["-m", "pip", "install", "-e"]
    assert calls[0][-1].endswith("[dev]")
    assert calls[1][1:5] == ["-m", "pip", "install", "--upgrade"]


def test_package_pull_syncs_plugins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    run(["project", "init", "cli", "Demo"], print_result=False)
    project_root = tmp_path / "Demo"
    checkout = tmp_path / "checkout"
    (checkout / "plugins" / "alpha").mkdir(parents=True)
    (checkout / "plugins" / "alpha" / "__init__.py").write_text("VALUE='alpha'\n", encoding="utf-8")

    @dataclass(frozen=True)
    class _Clone:
        repo_path: Path

    monkeypatch.setattr("fx.command_sets.package.clone_repo", lambda **_kwargs: _Clone(checkout))

    result = run(["package", "pull", str(project_root), str(checkout)], print_result=False)
    plugin_list = run(["plugin", "list", str(project_root)], print_result=False)

    assert result["status"] == "success"
    assert result["created"] == ["alpha"]
    assert plugin_list == [
        {
            "alias": "alpha",
            "package_path": "demo.plugins.alpha",
            "enabled": True,
            "link_file": str(project_root / "src" / "demo" / "plugins" / "alpha" / "__init__.py"),
        }
    ]


def test_cron_grouped_commands_and_cron_project_surface(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    run(["project", "init", "cron", "Ops"], print_result=False)
    project_root = tmp_path / "Ops"
    jobs_file = project_root / "src" / "ops" / "jobs.py"
    jobs_file.write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "import registers.cron as cron",
                "@cron.job(name='sync-cache', trigger=cron.event('manual'))",
                "def sync_cache(payload: dict | None = None) -> str:",
                "    return 'ok'",
            ]
        ),
        encoding="utf-8",
    )

    jobs = run(["cron", "jobs", str(project_root)], print_result=False)
    trigger = run(["cron", "trigger", str(project_root), "sync-cache"], print_result=False)

    assert jobs[0]["name"] == "sync-cache"
    assert trigger["status"] == "success"
    assert trigger["job"] == "sync-cache"


def test_failed_run_records_operation_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    run(["project", "init", "cli", "Demo"], print_result=False)
    project_root = tmp_path / "Demo"

    with pytest.raises(CommandExecutionError, match="DB/API run requires"):
        run(["run", "api", str(project_root)], print_result=False)

    rows = operation_registry(project_root).filter(project_root=str(project_root), order_by="-id", limit=1)
    assert rows
    assert rows[0].command == "run api"
    assert rows[0].status == "failure"


def test_global_root_context_and_output_modes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    run(["project", "init", "cli", "Demo"], print_result=False)
    project_root = tmp_path / "Demo"

    status = run(["--root", str(project_root), "project", "status"], print_result=False)
    assert status["root"] == str(project_root)
    assert status["runnable_packages"] == ["demo"]

    run(["--root", str(project_root), "project", "status", "--output", "json"])
    rendered = capsys.readouterr().out
    assert json.loads(rendered)["package"] == "demo"

    run(["module", "add", str(project_root), "cli", "users"], print_result=False)
    run(["module", "list", str(project_root), "--output", "csv"])
    csv_out = capsys.readouterr().out
    assert "module_name,module_type,package_path,entry_file" in csv_out
    assert "users,cli,demo.plugins.users" in csv_out


def test_dry_run_and_confirmation_safety(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    run(["project", "init", "cli", "Demo"], print_result=False)
    project_root = tmp_path / "Demo"

    dry_run = run(["module", "add", str(project_root), "cli", "users", "--dry-run"], print_result=False)
    assert dry_run["status"] == "dry-run"
    assert run(["module", "list", str(project_root)], print_result=False) == []

    run(["module", "add", str(project_root), "cli", "users"], print_result=False)
    with pytest.raises(SystemExit) as exc_info:
        run(["module", "remove", str(project_root), "users"], print_result=False)
    assert exc_info.value.code == 2
    assert run(["module", "list", str(project_root)], print_result=False)[0]["module_name"] == "users"

    removed = run(["module", "remove", str(project_root), "users", "--force"], print_result=False)
    assert removed["status"] == "success"
    assert run(["module", "list", str(project_root)], print_result=False) == []


def test_json_parse_failures_exit_with_parse_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    run(["project", "init", "cron", "Ops"], print_result=False)
    project_root = tmp_path / "Ops"

    with pytest.raises(SystemExit) as exc_info:
        run(["cron", "trigger", str(project_root), "sync-cache", "--payload", "{bad"], print_result=False)
    assert exc_info.value.code == 2


def test_shell_builtins_use_grouped_registry(
    capsys: pytest.CaptureFixture[str],
) -> None:
    commands = iter(["commands", "help project", "exit"])

    def input_fn(prompt: str) -> str:
        return next(commands)

    run(["--interactive"], print_result=False, shell_input_fn=input_fn, shell_banner=False)
    out = capsys.readouterr().out
    assert "project init" in out
    assert "Command group: project" in out


def test_registry_duplicate_commands_fail_fast() -> None:
    registry = build_registry()

    with pytest.raises(DuplicateCommandError):
        registry.register("version")(lambda: "duplicate")
