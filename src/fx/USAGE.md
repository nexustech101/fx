# `fx` Usage

`fx` manages minimal `registers` projects through grouped `registers.cli`
commands and project-local state in `.fx/fx.db`.

## Create Projects

```bash
fx project init cli MyTool
fx project init db ApiService --layout src
fx project init cron OpsJobs --package ops --layout root
```

Defaults:

- package layout: `src/<package>/`
- package name: normalized project name
- scaffold style: bare-bones, no generated todo/user domain code

## Inspect Projects

```bash
fx project status MyTool
fx project health MyTool
fx project history MyTool 20
```

Status and health use `.fx` metadata when present, then package discovery.
Runnable packages are packages with `__main__.py`.

## Run Projects

```bash
fx run auto MyTool
fx run cli MyTool
fx run api ApiService --host 0.0.0.0 --port 9000 --reload
fx run cron OpsJobs
```

DB/API projects run with:

```bash
python -m uvicorn <package>.api:app --host ... --port ...
```

Use `--package` when more than one runnable package is present. Use `--app` to
override the default FastAPI app target.

## Expand Projects

```bash
fx module add MyTool cli users
fx module list MyTool
fx module remove MyTool users

fx plugin link MyTool my_package.tools tools
fx plugin sync MyTool
fx plugin list MyTool
fx plugin unlink MyTool tools
```

Module files are minimal placeholders; `fx` does not impose application
structure beyond importable package boundaries.

## Package Operations

```bash
fx package install MyTool --extras dev
fx package update MyTool --source pypi --package registers
fx package pull MyTool https://github.com/example/plugins --subdir plugins
```

## Cron Operations

```bash
fx cron jobs OpsJobs
fx cron trigger OpsJobs sync-cache --payload '{"dry_run":true}'
fx cron start OpsJobs --workers 4
fx cron status OpsJobs
fx cron stop OpsJobs
fx cron workspace OpsJobs
fx cron generate OpsJobs --target github_actions
fx cron apply OpsJobs --target linux_cron
fx cron register OpsJobs deploy-flow ops/workflows/ci/deploy.yml --job deploy
fx cron workflows OpsJobs
fx cron run-workflow OpsJobs deploy-flow
```

Cron project `__main__.py` installs script-local cron commands inside
`main()`, so package imports used by discovery do not mutate global CLI state.
