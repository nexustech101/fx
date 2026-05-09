# fx-tool

`fx` is the grouped project manager and operations CLI for projects built on
`registers`. It is implemented as a first-class `registers.cli` application:
commands are grouped, results are structured, global context is supported, and
plain output remains automation-friendly.

## Install

```bash
pip install fx-tool
pip install "fx-tool[cli]"
```

The `cli` extra enables the optional `registers.cli` Rich and prompt_toolkit
integrations for styled help, tables, completion, history, and multiline shell
input. Without the extra, `fx` falls back to standard-library plain text.

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
fx cron trigger OpsJobs sync-cache --payload '{"dry_run":true}'
```

Use a global root when repeatedly operating on one project:

```bash
fx --root MyTool project status
fx --root MyTool module list
fx --root OpsJobs cron status --output json
```

## Command Model

`fx` intentionally supports grouped commands only. Legacy flat forms such as
`fx init`, `fx status`, `fx run .`, `fx install`, `fx update`, and action-router
cron forms are removed.

```text
project init|status|health|history
module add|list|remove
plugin link|list|unlink|sync
run auto|cli|api|cron
package install|update|pull
cron jobs|trigger|start|stop|status|workspace|register|workflows|run-workflow|generate|apply
```

## Output Modes

Commands return dictionaries or lists of dictionaries where possible. That
makes the same command useful for humans and scripts:

```bash
fx project status MyTool
fx project status MyTool --output json
fx module list MyTool --output csv
fx cron jobs OpsJobs --quiet
fx cron status OpsJobs --no-color
```

If a command ever owns an `output` argument, use the framework alias:

```bash
fx some command --output report.txt --cli-output json
```

## Safety

Changing commands support `--dry-run` where practical:

```bash
fx project init cli MyTool --dry-run
fx module add MyTool cli users --dry-run
fx plugin link MyTool my_package.tools tools --dry-run
fx package install MyTool --dry-run
fx cron trigger OpsJobs sync-cache --payload '{"x":1}' --dry-run
```

Destructive state operations require confirmation in interactive sessions or
`--force` in automation:

```bash
fx module remove MyTool users --force
fx plugin unlink MyTool tools --force
fx cron apply OpsJobs --target linux_cron --force
```

## Interactive Shell

Start the shell explicitly:

```bash
fx --interactive
```

Embedded callers can enable optional shell UX:

```python
from fx import run

run(
    ["--interactive"],
    rich=True,
    completion=True,
    history=True,
    multiline=True,
)
```

Shell built-ins include `help`, `commands`, `watch <command> --interval N
--count N`, `pipe <command> | filter FIELD=VALUE | sort FIELD | count`,
`exec <system command>`, and `exit`.

## Project Layouts

The default layout is `src/<package>/`. Use `--layout root` to create
`<root>/<package>/`, and `--package <name>` to choose the package name.

CLI projects create a grouped `registers.cli` starter command. DB projects also
create `api.py` and `models.py`; DB projects run through Uvicorn as
`<package>.api:app`. Cron projects also create `jobs.py` and install the
script-local `registers.cron` CLI inside `main()`.

## Development

```bash
python -m pytest tests/fx
python -m pytest tests
```

For source-tree smoke checks without reinstalling:

```powershell
$env:PYTHONPATH="C:\Users\charl\Documents\Python\framework\fx\src;C:\Users\charl\Documents\Python\framework\registers\src"
python -m fx --help
```
