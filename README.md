# fx-tool

`fx` is the grouped project manager and operations CLI for projects built on
`registers`.

It creates minimal `cli`, `db`, and `cron` projects, runs packages by
discovering `__main__.py`, manages project-local `.fx/fx.db` state, and
operates `registers.cron` workflows.

## Quick Start

```bash
fx project init cli MyTool
fx project status MyTool
fx project health MyTool
fx run cli MyTool
```

DB/FastAPI project:

```bash
fx project init db ApiService --layout src
fx run api ApiService --host 0.0.0.0 --port 9000 --reload
```

Cron project:

```bash
fx project init cron OpsJobs
fx cron jobs OpsJobs
```

## Project Layout

The default layout is `src/<package>/`. Use `--layout root` to create
`<root>/<package>/`, and `--package <name>` to choose the package name.

Scaffolds are intentionally bare-bones. They do not generate todo apps, sample
user APIs, or domain-specific tests.

CLI projects create:

```text
.gitignore
README.md
pyproject.toml
.fx/fx.db
src/<package>/__init__.py
src/<package>/__main__.py
```

DB projects also create `api.py` and `models.py`; DB projects run through
Uvicorn as `<package>.api:app`. Cron projects also create `jobs.py`.

## Commands

```bash
fx project init cli|db|cron <name> [root] --package <package> --layout src|root --force
fx project status <root>
fx project health <root>
fx project history <root> [limit]

fx run auto|cli|api|cron <root> --package <package>

fx module add <root> cli|db|cron <module_name>
fx module list <root>
fx module remove <root> <module_name>

fx plugin link <root> <package_path> [alias]
fx plugin list <root>
fx plugin unlink <root> <alias>
fx plugin sync <root>

fx package install <root> --extras dev
fx package update <root> --source pypi|git|path
fx package pull <root> <repo_url>

fx cron jobs <root>
fx cron trigger <root> <job_name> --payload '{"k":"v"}'
fx cron start <root> --workers 4
fx cron status <root>
fx cron stop <root>
fx cron workspace <root>
fx cron generate <root> --target github_actions
fx cron apply <root> --target linux_cron
fx cron register <root> <workflow_name> <workflow_file> --job <job_name>
fx cron workflows <root>
fx cron run-workflow <root> <workflow_name>
```

Legacy flat commands such as `fx init`, `fx status`, `fx run .`, `fx install`,
and action-router cron forms are intentionally removed.
