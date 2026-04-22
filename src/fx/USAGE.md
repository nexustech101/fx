# `fx` Usage Manual

This guide is intentionally exhaustive.

Goal: if an engineer or an agent reads this file, they can use `fx` end-to-end
for project scaffolding, runtime operations, plugin workflows, and cron
automation without needing to inspect internals.

---

## 1. What `fx` Gives You

`fx` is the project manager and operations CLI for the `registers` framework.

It provides:

- project scaffolding for CLI and DB/API apps
- module/plugin structure management
- local runtime operations (`run`, `install`, `update`, `pull`)
- cron runtime + workflow orchestration (`fx cron ...`)
- diagnostics and operation history
- local control-plane state in `.fx/fx.db`

`fx` depends on `registers` (`registers.cli`, `registers.db`,
`registers.cron`).

**Summary**: `fx` is the control plane for creating, operating, and automating `registers` projects.

---

## 2. Install and Entrypoints

Install from PyPI:

```bash
pip install fx-tool
```

Local development install:

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

Expected `--version` output:

```text
fx <version>
```

**Summary**: `fx` can be used as a shell command (`fx`) or as a Python module entrypoint (`python -m fx`).

---

## 3. Command Model and Argument Conventions

`fx` uses `registers.cli` parsing rules:

- positional args are supported
- named args are supported (`--root`, `--project-name`, etc.)
- boolean args are flags (for example `--force`, `--reload`)
- both `snake_case` and kebab-case spellings are accepted for named args

Examples:

```bash
fx init cli MyProject .
fx init --project-type cli --project-name MyProject --root .
fx run . --host 0.0.0.0 --port 9000 --reload
```

If you use `from fx import run`, command handlers return strings directly when
`print_result=False`.

**Summary**: You can invoke every command with positional or named forms, and boolean behavior is flag-based.

---

## 4. Quick Start (Todo-Centered CLI)

Create a todo-focused project (project name is arbitrary):

```bash
fx init cli todo
fx status todo
fx health todo
```

Then run the generated app:

```bash
cd todo
python -m app add "Grocery Shopping" "Bread, milk, eggs, butter"
python -m app list
```

Expected output snippet:

```text
Added: Grocery Shopping (ID: 1)
1: Grocery Shopping [pending]
```

Generated structure:

```text
todo/
  .gitignore
  pyproject.toml
  README.md
  .fx/fx.db
  app/__init__.py
  app/__main__.py
  app/todo.py
  app/plugins/__init__.py
  tests/test_todo_automation.py
```

**Summary**: `fx init cli` creates a root-level `app/` package with todo starter code and ready-to-run tests.

---

## 5. `init` Command (All Shapes + Compatibility)

Primary forms:

```bash
fx init
fx init cli
fx init cli MyProject
fx init cli MyProject .
fx init db DataProject
fx init db DataProject .
```

Backward-compatible legacy forms:

```bash
fx init MyProject
fx init MyProject .
```

These legacy forms are interpreted as CLI initialization.

`--force` behavior:

```bash
fx init cli MyProject . --force
```

- existing files are overwritten when `--force` is used
- otherwise existing files are listed as `Skipped`

Expected output structure:

```text
Initialized cli project 'MyProject' at <ABS_PATH>
Created:
  - pyproject.toml
  - app/todo.py
  ...
Skipped:
  - app/__init__.py
```

DB initialization replaces todo app files with:

- `app/models.py`
- `app/api.py`
- `tests/test_user_api.py`

**Summary**: `init` supports modern explicit syntax and legacy compatibility while preserving deterministic scaffold output.

---

## 6. `status` Command

Show structure and registry state:

```bash
fx status .
```

Expected output fields include:

- root path
- project record presence/type
- `pyproject.toml` presence
- package name + package root
- starter file presence (`todo.py`, `api.py`, `models.py`)
- plugin package presence/import base
- registered module/plugin counts
- filesystem vs registry plugin alignment

Expected output snippet:

```text
Project record: present
Project type: cli
package: app
plugins package: present
Registry and filesystem plugin lists are aligned.
```

**Summary**: `status` is the fastest way to verify scaffold, metadata, and plugin-registry coherence.

---

## 7. `module` Command (`add`, `list`)

Add a CLI module:

```bash
fx module add cli users .
```

Creates:

- `app/plugins/users/__init__.py`
- `app/plugins/users/users.py`

Add a DB module:

```bash
fx module add db audit .
```

Creates:

- `app/plugins/audit/__init__.py`
- `app/plugins/audit/models.py`

List modules:

```bash
fx module list .
```

Expected list output:

```text
Registered modules:
  users  (cli)  app.plugins.users
  audit  (db)   app.plugins.audit
```

Compatibility shorthand for list root:

```bash
fx module list /path/to/project
```

Validation behavior:

- module type must be `cli` or `db`
- module name must be a valid Python identifier after normalization

**Summary**: `module add` writes structured plugin modules and auto-registers them in both module and plugin registries.

---

## 8. `plugin` Command (`make`, `list`)

Link an importable package into local plugins:

```bash
fx plugin make math math_ops .
```

Creates shim:

- `app/plugins/math_ops/__init__.py` with `from math import *`

Alias default behavior:

```bash
fx plugin make my_package.tools .
```

If no alias is provided, alias defaults to the last package segment (`tools`).

List linked plugins:

```bash
fx plugin list .
```

Expected output:

```text
Linked plugins:
  math_ops  ->  math  (enabled)
```

Supported actions:

- `make` (primary)
- `link` (alias for `make`)
- `list`

**Summary**: `plugin make` creates import shims under your project plugin package and records them for runtime diagnostics.

---

## 9. Runtime Operations (`run`, `install`, `update`, `pull`)

### `run`

CLI project:

```bash
fx run .
```

DB/API project:

```bash
fx run . --host 0.0.0.0 --port 9000 --reload
```

Expected summary:

```text
fx Run Result
Status: success
Project type: cli
Command: <python> -m app
```

DB projects use:

```text
<python> -m uvicorn app.api:app --host ... --port ...
```

### `install`

Editable install:

```bash
fx install .
```

With extras:

```bash
fx install . --extras dev,docs
```

With virtual environment path:

```bash
fx install . --venv-path .venv
```

### `update`

From PyPI:

```bash
fx update .
```

From Git:

```bash
fx update . --source git --repo https://github.com/nexustech101/registers.git --ref main
```

From local path:

```bash
fx update . --source path --path ../registers
```

Validation rules:

- `source=git` requires `--repo` and rejects `--path`
- `source=path` requires `--path` and rejects `--repo`
- `source=pypi` rejects both `--repo` and `--path`

### `pull`

Pull plugin packages from a repository:

```bash
fx pull https://github.com/org/plugins-repo.git . --ref main --subdir plugins
```

Force overwrite existing plugin dirs:

```bash
fx pull https://github.com/org/plugins-repo.git . --force
```

`pull` validates plugin imports after copy; import failures fail the command.

Expected summary snippet:

```text
Summary: created=1, updated=0, skipped=2
```

**Summary**: Runtime commands cover execution, packaging, framework upgrades, and plugin sync with explicit validation.

---

## 10. Diagnostics (`health`, `history`)

### `health`

```bash
fx health .
```

Success output:

```text
Health checks passed.
```

Failure output pattern:

```text
Health checks failed:
  - Missing plugins package at <path>
  - Import failed for app.plugins.users: ...
```

`health` validates:

- project starter layout by project type
- plugin package presence
- `pyproject.toml` presence for structured projects
- importability of local plugin packages

### `history`

```bash
fx history 20 .
```

Expected output pattern:

```text
Recent operations:
  [12] 2026-04-21T12:00:00Z  init  success
      Initialized cli project 'DemoProject'.
```

**Summary**: `health` protects structure/runtime integrity, and `history` gives a local audit trail of control-plane operations.

---

## 11. `cron` Command (Full Action Surface)

Top-level action:

```bash
fx cron <action> [subject] [root] [--workers] [--foreground] [--target] [--payload] [--workflow-file] [--job] [--command] [--metadata]
```

Supported actions:

- `start`, `stop`, `status`
- `jobs`, `trigger`
- `generate`, `apply`
- `workspace`
- `register`, `workflows`, `run-workflow`

### Root/subject routing rules

- For `start|stop|status|jobs|generate|apply|workspace|workflows`:
  - root is resolved from `subject` when provided, otherwise `root`
- For `trigger|register|run-workflow`:
  - `subject` is the job/workflow identifier
  - `root` is used for project resolution

### Common flows

Prepare workspace:

```bash
fx cron workspace .
```

Discover jobs:

```bash
fx cron jobs .
```

Start runtime:

```bash
fx cron start . --workers 4
```

Inspect runtime:

```bash
fx cron status .
```

Manually queue a job:

```bash
fx cron trigger nightly-build . --payload '{"env":"prod"}'
```

Generate/apply target artifacts:

```bash
fx cron generate . --target github_actions
fx cron apply . --target github_actions
```

Register and run workflows:

```bash
fx cron register deploy-workflow . --workflow-file ops/workflows/ci/deploy-workflow.yml --job nightly-build --target github_actions
fx cron workflows .
fx cron run-workflow deploy-workflow . --payload '{"env":"prod"}'
```

### Workflow registration constraints

- `register` requires `--workflow-file`
- workflow file must already exist
- exactly one execution mode is allowed:
  - `--job <cron_job_name>`, or
  - `--command "<shell command>"`

### Expected output snippets

```text
fx Cron Jobs Result
Status: success
Jobs:
  nightly-build (... retry=exponential, attempts=5, ...)
```

```text
fx Cron Status Result
Failed events: 0
Dead-letter events: 0
```

```text
fx Cron Run Workflow Result
Mode: job
Event ID: 42
```

### Important compatibility note for job discovery

Current `registers.cron` discovery may depend on `src/<package>` package
resolution in some runtime versions. If `fx cron jobs` does not discover jobs
from root-level `app/`, add a compatibility module under `src/app` (or mirror
job module imports there) until your deployed `registers` runtime supports your
project layout directly.

**Summary**: `fx cron` is a full lifecycle surface for scheduler runtime control, event orchestration, and deployment artifact workflows.

---

## 12. Help and Interactive Shell Behavior

Global help:

```bash
fx --help
fx help
fx help cron
```

Interactive shell:

```bash
fx --interactive
```

Built-ins available in shell:

- `help`
- `help <command>`
- `commands`
- `exec <command>`
- `exit` / `quit`

Expected help output snippet:

```text
fx
Manage back-end projects, modules, and plugin structures built with registers.
Version: <version>
```

**Summary**: Help and shell UX come from `registers.cli`, giving `fx` a consistent operator interface for discoverability and ad-hoc execution.

---

## 13. Python API (Programmatic Usage)

`fx` public module surface:

- `from fx import run`
- `from fx import main`
- `from fx import get_registry`
- `from fx import __version__`

Programmatic command execution:

```python
from fx import run

result = run(["init", "cli", "TodoProject", "."], print_result=False)
print(result)
```

Programmatic inspection:

```python
from fx import get_registry

registry = get_registry()
print(registry.list_commands())
```

`main(argv)` returns process-style exit code (`0` on success).

**Summary**: Use `run(...)` for embedded automation and `get_registry()` when you need introspection of the loaded fx command surface.

---

## 14. Error Model and Compatibility Boundaries

### Error behavior

- parse/help target errors: usage + exit code `2` (from `registers.cli`)
- handler failures: surfaced as command execution failures
- many commands record failure details in `.fx` operation history

Representative validation failures:

- `module add` with invalid type -> error
- `plugin make` without package path -> error
- `cron register` without `--workflow-file` -> error
- `update --source git` without `--repo` -> error

### Compatibility boundaries

- `init` supports legacy invocation shapes
- `status`, `run`, and `health` include checks for legacy layouts (`app.py`,
  root `models.py`) and structured layouts
- plugin layout resolution supports both root package plugins and fallback plugin
  directories

**Summary**: `fx` enforces strict argument contracts while retaining compatibility paths for older project invocation/layout patterns.

---

## 15. Agent Build Recipe (For Downstream Automation Agents)

When asked to "use fx to build/manage a project that does X", follow this
sequence:

1. Initialize scaffold.

```bash
fx init cli <project_name> <root>
```

2. Verify baseline health.

```bash
fx status <root>
fx health <root>
```

3. Add project modules/plugins as needed.

```bash
fx module add cli <module_name> <root>
fx plugin make <package_path> <alias> <root>
```

4. Install/editable environment.

```bash
fx install <root> --venv-path .venv --extras dev
```

5. Run application or API.

```bash
fx run <root>
```

6. Add cron automation when needed.

```bash
fx cron workspace <root>
fx cron jobs <root>
fx cron generate <root> --target github_actions
```

7. Record and inspect operational history.

```bash
fx history 50 <root>
```

**Summary**: This is the default operational checklist for agents to produce predictable and auditable `fx` workflows.

---

## 16. Medium-Project Pattern (Todo + Plugins + Cron)

Recommended evolution for medium scope:

```text
my_todo_project/
  app/
    __init__.py
    __main__.py
    todo.py
    plugins/
      __init__.py
      users/
        __init__.py
        users.py
      reminders/
        __init__.py
        reminders.py
      reporting/
        __init__.py
        reporting.py
  tests/
    test_todo_automation.py
  .fx/fx.db
```

Typical command lifecycle:

```bash
fx init cli my_todo_project
cd my_todo_project
fx module add cli users .
fx module add cli reminders .
fx module add cli reporting .
fx plugin list .
fx run .
fx cron workspace .
fx cron jobs .
fx cron status .
```

This pattern keeps one unified command surface while allowing gradual plugin
growth and ops automation.

**Summary**: For medium projects, grow by module/plugin boundaries first, then layer cron operations once command domains stabilize.

---

## 17. Bash Aliases and Automation Scripts

Add aliases/functions to `~/.bashrc` (or `~/.bash_profile`):

```bash
alias fxh='fx --help'
alias fxs='fx status .'
alias fxhealth='fx health .'
alias fxhist='fx history 30 .'

fxinit() {
  local name="${1:-todo_app}"
  fx init cli "$name"
}

fxops() {
  fx cron workspace .
  fx cron jobs .
  fx cron status .
}
```

Reload shell:

```bash
source ~/.bashrc
```

Project bootstrap script (`scripts/fx-bootstrap.sh`):

```bash
#!/usr/bin/env bash
set -euo pipefail

PROJECT_NAME="${1:-todo_app}"

fx init cli "$PROJECT_NAME"
cd "$PROJECT_NAME"
fx install . --venv-path .venv --extras dev
fx health .
fx status .
```

Cron prep script (`scripts/fx-cron-prepare.sh`):

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-.}"
TARGET="${2:-github_actions}"

fx cron workspace "$ROOT"
fx cron jobs "$ROOT"
fx cron generate "$ROOT" --target "$TARGET"
fx cron apply "$ROOT" --target "$TARGET"
fx cron status "$ROOT"
```

Make scripts executable:

```bash
chmod +x scripts/fx-bootstrap.sh scripts/fx-cron-prepare.sh
```

**Summary**: Aliases speed up interactive workflows, and bash scripts provide repeatable, agent-friendly automation entrypoints for scaffolding and ops routines.
