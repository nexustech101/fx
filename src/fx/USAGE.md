# `fx` Usage

`fx` manages minimal `registers` projects through grouped `registers.cli`
commands and project-local state in `.fx/fx.db`.

## Runtime Flags

```bash
fx --help
fx --interactive
fx --root MyTool project status
fx project status MyTool --output json
fx module list MyTool --output csv
fx cron status OpsJobs --quiet
fx cron status OpsJobs --no-color
```

Optional embedded shell settings:

```python
from fx import run

run(["--interactive"], rich=True, completion=True, history=True, multiline=True)
```

## Create Projects

```bash
fx project init cli MyTool
fx project init db ApiService --layout src
fx project init cron OpsJobs --package ops --layout root
fx project init cli MyTool --dry-run
```

Defaults:

- package layout: `src/<package>/`
- package name: normalized project name
- scaffold style: bare-bones, grouped-command ready, no domain demo app

## Inspect Projects

```bash
fx project status MyTool
fx project status MyTool --output json
fx --root MyTool project health
fx project history MyTool --limit 20 --output csv
```

Status and health use `.fx` metadata when present, then package discovery.
Runnable packages are packages with `__main__.py`.

## Run Projects

```bash
fx run auto MyTool
fx run cli MyTool
fx run api ApiService --host 0.0.0.0 --port 9000 --reload
fx run api ApiService --app api_service.api:app
fx run cron OpsJobs
```

Use `--package` when more than one runnable package is present. DB/API projects
run with:

```bash
python -m uvicorn <package>.api:app --host ... --port ...
```

## Expand Projects

```bash
fx module add MyTool cli users
fx module add MyTool cron sync_jobs --dry-run
fx module list MyTool --output csv
fx module remove MyTool users --force

fx plugin link MyTool my_package.tools tools
fx plugin sync MyTool
fx plugin list MyTool --output json
fx plugin unlink MyTool tools --force
```

Module files are minimal placeholders; `fx` does not impose application
structure beyond importable package boundaries.

## Package Operations

```bash
fx package install MyTool --extras dev
fx package install MyTool --venv-path .venv --dry-run
fx package update MyTool --source pypi --package registers
fx package update MyTool --source git --repo https://github.com/example/pkg --ref main
fx package update MyTool --source path --path ../registers
fx package pull MyTool https://github.com/example/plugins --subdir plugins
```

Package operations use `registers.cli` progress wrappers when Rich is available
and no-op progress otherwise.

## Cron Operations

```bash
fx cron jobs OpsJobs
fx cron jobs OpsJobs --output json
fx cron trigger OpsJobs sync-cache --payload '{"dry_run":true}'
fx cron start OpsJobs --workers 4
fx cron start OpsJobs --foreground
fx cron status OpsJobs
fx cron stop OpsJobs
fx cron workspace OpsJobs
fx cron generate OpsJobs --target github_actions
fx cron apply OpsJobs --target linux_cron --force
fx cron register OpsJobs deploy-flow ops/workflows/ci/deploy.yml --job deploy
fx cron workflows OpsJobs --output csv
fx cron run-workflow OpsJobs deploy-flow --payload '{"sha":"abc"}'
```

JSON payload and metadata arguments are validated before command execution.
Invalid JSON exits with parse status `2`.

## Shell Built-ins

```text
help
help project
help project init
commands
watch project status MyTool --interval 5 --count 3
pipe module list MyTool | filter module_type=cli | sort module_name | count
exec python --version
exit
```

The shell uses prompt_toolkit completion/history/multiline features only when
the optional dependencies are installed and the caller enables them.

## Compatibility

Grouped commands are the supported public surface. Legacy flat commands such as
`fx init`, `fx status`, `fx run .`, `fx install`, `fx update`, `fx pull`, and
action-router cron commands are intentionally unsupported.
