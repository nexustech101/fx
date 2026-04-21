# fx-tool

`fx` is the standalone project manager and operations CLI for the
Functionals framework.

It is focused on developer and DevOps workflows around Functionals apps:

- project scaffolding (`cli` and `db` project types)
- module and plugin structure management
- runtime operations (`run`, `install`, `update`, `pull`)
- cron workspace, workflow registration, and runtime control
- local control-plane state and operational history

`fx-tool` is intentionally separate from the core framework package now, but it
still manages projects built on the Functionals runtime (`registers`).

Runtime package note: the framework package/import namespace is now `registers`
(renamed from `functionals`/`decorates`).

## Install

```bash
pip install fx-tool
```

`fx-tool` depends on [`registers`](https://pypi.org/project/registers/) for the
framework runtime modules (`registers.cli`, `registers.db`,
`registers.cron`).

## Run

```bash
fx --version
fx --help
fx --interactive
python -m fx --help
```

## Quick Example

```bash
# Initialize a Functionals project
fx init cli MyService

# Validate project structure and plugin wiring
fx status MyService
fx health MyService

# Operate cron workflows
fx cron workspace MyService
fx cron jobs MyService
fx cron start MyService
```

## Documentation

- Usage guide: [`src/fx/USAGE.md`](C:/Users/charl/Documents/Python/framework/fx/src/fx/USAGE.md)

