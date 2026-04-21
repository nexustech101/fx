# `fx` Usage

`fx` is the standalone project manager for the Functionals framework.

Use `fx` when you want one CLI to scaffold, operate, and automate Functionals
projects across local development and DevOps workflows.

`fx` is distributed in the `fx-tool` package and depends on `registers` for the
underlying framework runtime (`registers.cli`, `registers.db`,
`registers.cron`).

Package rename note: framework install/import names are now `registers`
(renamed from `registers`/`registers`).

## Install

```bash
pip install fx-tool
```

For local development of this package:

```bash
pip install -e ".[dev]"
```

## Entrypoints

```bash
fx --version
fx --help
fx --interactive
python -m fx --help
```

## What `fx` Manages

- Project layout and bootstrap for Functionals apps (`init`)
- Module and plugin structure registry (`module`, `plugin`)
- Runtime lifecycle operations (`run`, `install`, `update`, `pull`)
- Cron operations and workflow orchestration (`cron ...`)
- Diagnostics and history (`health`, `history`)
- Local control-plane state in `.fx/fx.db`

## Quick Start

Create and operate a Functionals CLI project:

```bash
fx init cli MyService
fx status MyService
fx health MyService
fx run MyService
```

Create and operate a Functionals DB/API project:

```bash
fx init db DataService
fx status DataService
fx run DataService --host 0.0.0.0 --port 8000
```

## Project Structure Created by `fx init`

`fx init cli` creates:

```text
pyproject.toml
README.md
.gitignore
src/app/__init__.py
src/app/__main__.py
src/app/todo.py
src/app/plugins/__init__.py
src/app/ops/__init__.py
src/app/ops/jobs/__init__.py
src/app/ops/jobs/heartbeat.py
src/app/ops/jobs/deploy.py
ops/scripts/deploy.sh
ops/workflows/cron/ops-heartbeat.cron
ops/workflows/ci/deploy-workflow.yml
ops/workflows/windows/ops-heartbeat.xml
tests/test_todo_cli.py
.fx/fx.db
```

`fx init db` creates a similar structure, replacing CLI app files with
`src/app/api.py` and `src/app/models.py`.

## Core Commands

- `fx init [cli|db] [project_name] [root] [--force]`
- `fx status [root]`
- `fx module <add|list> [module_type|root] [module_name] [root] [--force]`
- `fx plugin <make|list> [package_path|root] [alias] [root] [--force]`
- `fx run [root] [--host] [--port] [--reload]`
- `fx install [root] [venv_path] [extras]`
- `fx update [root] [source] [repo] [ref] [path] [venv_path] [package]`
- `fx pull <repo_url> [root] [ref] [subdir] [--force]`
- `fx cron <action> [subject] [root] [--workers] [--foreground] [--target] [--payload] [--workflow-file] [--job] [--command] [--metadata]`
- `fx health [root]`
- `fx history [limit] [root]`

## Cron and DevOps Workflow Operations

`fx cron` is the operations surface for Functionals cron automation.

Actions:

- `start`, `stop`, `status`
- `jobs`, `trigger`
- `generate`, `apply`
- `workspace`
- `register`, `workflows`, `run-workflow`

Typical workflow:

```bash
fx cron workspace .
fx cron jobs .
fx cron start .
fx cron status .
fx cron register deploy-workflow . --workflow-file ops/workflows/ci/deploy.yml --job nightly-build --target github_actions
fx cron workflows .
fx cron run-workflow deploy-workflow . --payload '{"env":"prod"}'
```

Retry-aware runtime visibility:

- `fx cron status` includes `Failed events` and `Dead-letter events`.
- `fx cron jobs` shows retry configuration per job (policy, attempts, backoff, jitter).

## Local State

`fx` stores control-plane data in:

```text
.fx/fx.db
```

Tracked records include:

- project metadata
- module registry
- plugin links
- cron workflow and runtime telemetry
- operation history

## Notes

- `fx` manages Functionals projects; it is not a replacement for the framework runtime.
- New projects use `src/app` as the application package by default.
- `module_name` and `alias` are normalized to valid Python identifiers.
- `health` verifies core project structure and plugin importability.

