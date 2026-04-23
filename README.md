# fx-tool

`fx` is the project manager and operations CLI for projects built on
[`registers`](https://pypi.org/project/registers/).

It is designed for both local developer workflows and operational workflows:

- scaffold new projects (`cli` and `db`)
- add plugin/modules and keep plugin registry aligned with filesystem
- run/install/update projects
- pull plugins from repositories
- manage cron jobs, workflows, and runtime state
- record local operation history in `.fx/fx.db`

## Install

Install from PyPI:

```bash
pip install fx-tool
```

For local development:

```bash
pip install -e ".[dev]"
```

Entrypoints:

```bash
fx --version
fx --help
fx --interactive
python -m fx --help
```

## Quick Start

CLI project:

```bash
fx init cli TodoApp
fx status TodoApp
fx health TodoApp
fx run TodoApp
```

DB/API project:

```bash
fx init db DataApp
fx status DataApp
fx health DataApp
fx run DataApp --host 0.0.0.0 --port 9000 --reload
```

### Typical Scaffold Output (`fx init`)

CLI projects create:

```text
app/__main__.py
app/todo.py
app/plugins/__init__.py
tests/test_todo_automation.py
pyproject.toml
README.md
.fx/fx.db
```

DB projects create:

```text
app/__main__.py
app/models.py
app/api.py
app/plugins/__init__.py
tests/test_user_api.py
pyproject.toml
README.md
.fx/fx.db
```

## Interactive Shell (TUI-Style REPL)

Launch interactive mode:

```bash
fx --interactive
```

Built-ins:

- `help`
- `help <command>`
- `commands`
- `exec <system command>`
- `exit` / `quit`

Example scripted session:

```bash
commands
help module
exec echo hello-from-shell
quit
```

The generated app started by `fx run <cli_project>` also opens an interactive
console (same built-in model) and exits cleanly on EOF/non-interactive input.

## Command Style and Argument Rules

`fx` uses `registers.cli` parsing conventions:

- positional and named forms are both supported
- named options accept both snake and kebab case
- boolean values are flags (`--force`, `--reload`, `--foreground`)
- grouped commands are top-level (`module`, `plugin`, `cron`) with action args

Examples:

```bash
fx init cli MyProject .
fx init --project-type cli --project-name MyProject --root .
fx module add cli users .
fx run . --host 0.0.0.0 --port 9000 --reload
```

## Command Reference

### `init`

Initialize project structure and local fx state.

```bash
fx init
fx init cli
fx init cli MyProject
fx init cli MyProject .
fx init db DataProject .
fx init cli MyProject . --force
```

Backward-compatible forms are supported:

```bash
fx init MyProject
fx init MyProject .
```

### `status`

Inspect project structure and registry status:

```bash
fx status .
```

Includes:

- project record/type
- package and plugin package discovery
- starter file checks (`todo.py`, `api.py`, `models.py`)
- registered modules/plugins
- registry vs filesystem plugin alignment

### `module`

Manage structured modules under `<package>/plugins`:

```bash
fx module add cli users .
fx module add db audit .
fx module list .
```

Validation:

- action must be `add` or `list`
- add type must be `cli` or `db`
- module name is normalized to a valid identifier

### `plugin`

Create alias links to importable plugin packages:

```bash
fx plugin make math math_ops .
fx plugin link my_package.tools .
fx plugin list .
```

Notes:

- `link` is an alias for `make`
- alias defaults to the last package segment if omitted

### `run`

Run the project entrypoint:

```bash
fx run .
fx run . --host 0.0.0.0 --port 9000 --reload
```

Behavior:

- CLI projects run `python -m <package>`
- DB projects run `python -m uvicorn <package>.api:app`

### `install`

Editable install in current/selected environment:

```bash
fx install .
fx install . --extras dev
fx install . --extras dev,docs
fx install . --venv-path .venv
```

### `update`

Update runtime dependencies from `pypi`, `git`, or `path`:

```bash
fx update .
fx update . --source git --repo https://github.com/nexustech101/registers.git --ref main
fx update . --source path --path ../registers
fx update . --package registers
```

Validation rules:

- `source=pypi` rejects `--repo` and `--path`
- `source=git` requires `--repo` and rejects `--path`
- `source=path` requires `--path` and rejects `--repo`

### `pull`

Sync plugins from a Git repository/local checkout:

```bash
fx pull https://github.com/org/plugins-repo.git . --ref main --subdir plugins
fx pull ../local-plugins-repo . --force
```

`pull` import-validates copied plugins and fails if imports are broken.

### `health`

Run structure and import checks:

```bash
fx health .
```

Alias: `fx --doctor .`

### `history`

Inspect operation history from `.fx/fx.db`:

```bash
fx history
fx history 50 .
```

### `cron`

Command shape:

```bash
fx cron <action> [subject] [root] [--workers] [--foreground] [--target] [--payload] [--workflow-file] [--job] [--command] [--metadata]
```

Actions:

- `workspace` prepares directories/files for cron workflows
- `jobs` discovers/syncs jobs and lists current registrations
- `start` / `stop` / `status` manage runtime daemon state
- `trigger` queues a manual event for a job
- `generate` / `apply` generate and apply deployment artifacts
- `register` registers named workflows
- `workflows` lists registered workflows
- `run-workflow` executes a registered workflow

Common flow:

```bash
fx cron workspace .
fx cron jobs .
fx cron start . --workers 4
fx cron status .
fx cron trigger nightly-build . --payload '{"env":"prod"}'
```

Workflow flow:

```bash
fx cron register deploy-workflow . --workflow-file ops/workflows/ci/deploy-workflow.yml --job nightly-build --target github_actions
fx cron workflows .
fx cron run-workflow deploy-workflow . --payload '{"env":"prod"}'
```

Registration rules:

- `register` requires `--workflow-file`
- choose one execution mode: `--job` or `--command` (not both)

### `version`

```bash
fx version
fx --version
fx -V
```

## Programmatic API

`fx` can be imported for automation:

```python
from fx import run, get_registry, __version__

result = run(["status", "."], print_result=False)
print(result)

registry = get_registry()
print(registry.list_commands())
print(__version__)
```

## Operational Notes

- `fx` writes control-plane/project metadata to `.fx/fx.db` per project root.
- Command failures raise command errors via `registers.cli`; run with `--help`
  and `help <command>` to validate argument shape.
- If cron job discovery does not detect root-level `app/` jobs in your runtime,
  mirror/import jobs under `src/app` as a compatibility workaround.

## Additional Documentation

For a deeper, exhaustive guide, see:

- [`src/fx/USAGE.md`](./src/fx/USAGE.md)
