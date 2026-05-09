from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Any

from registers import CommandRegistry
from registers.cli import types as t
from registers.cron.adapters import apply_artifacts, generate_artifacts
from registers.cron.runtime import run_daemon, sync_project_jobs
from registers.cron.state import (
    create_event as create_cron_event,
    cron_event_registry,
    cron_job_registry,
    cron_run_registry,
    cron_runtime_registry,
    mark_runtime_stopped,
    upsert_runtime,
)
from registers.cron.workspace import (
    ensure_workspace as ensure_cron_workspace,
    list_workflows as list_cron_workflows,
    register_workflow as register_cron_workflow,
    run_registered_workflow,
)

from fx.context import FxContext
from fx.state import record_operation


def register(registry: CommandRegistry) -> None:
    cron = registry.group("cron", description="Manage registers.cron projects", tags=["cron"])

    @cron.register(
        "jobs",
        description="Discover and list project cron jobs",
        tags=["cron", "inspect"],
        examples=["cron jobs OpsJobs", "cron jobs OpsJobs --output json"],
        default_output="rich",
        capture_logs=True,
    )
    @cron.argument("root", type=t.Path(), default="", help="Project root path")
    def jobs(ctx: FxContext, root: Path | str = "") -> list[dict[str, Any]]:
        root_path = ctx.resolve(root)
        package, loaded_modules, synced = sync_project_jobs(root_path)
        rows = cron_job_registry(root_path).filter(project_root=str(root_path), order_by="name")
        return [
            {
                "name": row.name,
                "trigger_kind": row.trigger_kind,
                "target": row.target,
                "enabled": row.enabled,
                "retry_policy": row.retry_policy,
                "retry_max_attempts": row.retry_max_attempts,
                "package": package or "",
                "loaded_modules": loaded_modules,
                "synced_jobs": synced,
            }
            for row in rows
        ]

    @cron.register(
        "trigger",
        description="Queue a manual cron job event",
        tags=["cron"],
        examples=['cron trigger OpsJobs sync-cache --payload "{\"dry_run\":true}"'],
        default_output="rich",
        capture_logs=True,
    )
    @cron.dry_run()
    @cron.argument("root", type=t.Path(), default="", help="Project root path")
    @cron.argument("job_name", type=str, help="Cron job name")
    @cron.argument("payload", type=t.JSON, default={}, help="Optional JSON payload")
    def trigger(
        ctx: FxContext,
        root: Path | str = "",
        job_name: str = "",
        payload: dict[str, Any] | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        root_path = ctx.resolve(root)
        payload_dict = _payload(payload)
        if dry_run:
            return {
                "status": "dry-run",
                "message": f"Would queue manual trigger for '{job_name}'.",
                "root": str(root_path),
                "job": job_name,
                "payload": payload_dict,
            }
        sync_project_jobs(root_path)
        job_row = cron_job_registry(root_path).get(job_key=f"{root_path}:{job_name}")
        if job_row is None:
            raise ValueError(f"No cron job named '{job_name}' is registered for {root_path}.")
        event = create_cron_event(root=root_path, job_name=job_name, source="manual", payload=payload_dict, status="pending")
        record_operation(root=root_path, command="cron trigger", arguments={"root": str(root_path), "job_name": job_name, "payload": payload_dict}, status="success", message=f"Queued manual trigger for '{job_name}' (event_id={event.id}).")
        return {
            "status": "success",
            "message": f"Queued manual trigger for '{job_name}'.",
            "root": str(root_path),
            "job": job_name,
            "event_id": event.id,
            "queue_status": event.status,
        }

    @cron.register(
        "start",
        description="Start the cron runtime",
        tags=["cron", "runtime"],
        examples=["cron start OpsJobs --workers 4", "cron start OpsJobs --foreground"],
        default_output="rich",
        capture_logs=True,
    )
    @cron.argument("root", type=t.Path(), default="", help="Project root path")
    @cron.argument("workers", type=t.Int(min=1), default=4, help="Worker count")
    @cron.argument("foreground", type=bool, default=False, help="Run in foreground mode")
    async def start(
        ctx: FxContext,
        root: Path | str = "",
        workers: int = 4,
        foreground: bool = False,
    ) -> dict[str, Any]:
        root_path = ctx.resolve(root)
        package, loaded_modules, synced = sync_project_jobs(root_path)
        if foreground:
            summary = await run_daemon(root=root_path, workers=max(1, workers))
            record_operation(root=root_path, command="cron start", arguments={"root": str(root_path), "workers": workers, "foreground": foreground}, status="success", message=f"cron start foreground completed (jobs={summary.jobs}).")
            return {
                "status": "success",
                "mode": "foreground",
                "root": str(root_path),
                "jobs": summary.jobs,
                "workers": summary.workers,
                "package": package or "missing",
                "loaded_modules": loaded_modules,
                "synced_jobs": synced,
            }

        runtime = cron_runtime_registry(root_path).get(project_root=str(root_path))
        if runtime is not None and runtime.status == "running" and _pid_is_alive(runtime.pid):
            return {
                "status": "success",
                "mode": "background",
                "root": str(root_path),
                "pid": runtime.pid,
                "message": "Cron daemon is already running.",
            }
        pid = _spawn_cron_daemon(root_path=root_path, workers=max(1, workers))
        time.sleep(0.4)
        started = _pid_is_alive(pid)
        message = f"Started cron daemon (pid={pid})." if started else "Cron daemon failed to start."
        record_operation(root=root_path, command="cron start", arguments={"root": str(root_path), "workers": workers, "foreground": foreground}, status="success" if started else "failure", message=message)
        if not started:
            raise RuntimeError(message)
        upsert_runtime(root=root_path, pid=pid, status="running", workers=max(1, workers))
        return {
            "status": "success",
            "mode": "background",
            "root": str(root_path),
            "pid": pid,
            "workers": max(1, workers),
            "package": package or "missing",
            "loaded_modules": loaded_modules,
            "synced_jobs": synced,
        }

    @cron.register(
        "stop",
        description="Stop the cron runtime",
        tags=["cron", "runtime"],
        examples=["cron stop OpsJobs"],
        default_output="rich",
        capture_logs=True,
    )
    @cron.argument("root", type=t.Path(), default="", help="Project root path")
    def stop(ctx: FxContext, root: Path | str = "") -> dict[str, Any]:
        root_path = ctx.resolve(root)
        runtime = cron_runtime_registry(root_path).get(project_root=str(root_path))
        if runtime is None:
            record_operation(root=root_path, command="cron stop", arguments={"root": str(root_path)}, status="success", message="Cron daemon not running.")
            return {"status": "success", "root": str(root_path), "message": "Cron daemon is not running.", "pid": 0}
        pid = int(runtime.pid)
        if _pid_is_alive(pid):
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError as exc:
                raise RuntimeError(f"Failed to stop cron daemon pid={pid}: {exc}") from exc
            exited = _wait_for_pid_exit(pid)
        else:
            exited = True
        mark_runtime_stopped(root_path)
        message = "Stopped cron daemon." if exited else "Cron daemon did not exit in time."
        record_operation(root=root_path, command="cron stop", arguments={"root": str(root_path)}, status="success" if exited else "failure", message=message)
        if not exited:
            raise RuntimeError(message)
        return {"status": "success", "root": str(root_path), "pid": pid, "message": message}

    @cron.register(
        "status",
        description="Show cron runtime status",
        tags=["cron", "inspect"],
        examples=["cron status OpsJobs", "cron status OpsJobs --output json"],
        default_output="rich",
    )
    @cron.argument("root", type=t.Path(), default="", help="Project root path")
    def status(ctx: FxContext, root: Path | str = "") -> dict[str, Any]:
        root_path = ctx.resolve(root)
        runtime = cron_runtime_registry(root_path).get(project_root=str(root_path))
        jobs_total = cron_job_registry(root_path).count(project_root=str(root_path))
        workflows_total = list_cron_workflows(root_path)
        running = False
        pid = 0
        workers_value = 0
        runtime_status = "stopped"
        if runtime is not None:
            pid = int(runtime.pid)
            workers_value = int(runtime.workers)
            running = runtime.status == "running" and _pid_is_alive(pid)
            runtime_status = "running" if running else runtime.status
        return {
            "status": "success",
            "root": str(root_path),
            "runtime": runtime_status,
            "pid": pid,
            "workers": workers_value,
            "jobs": jobs_total,
            "workflows": len(workflows_total),
            "pending_events": cron_event_registry(root_path).count(project_root=str(root_path), status="pending"),
            "queued_events": cron_event_registry(root_path).count(project_root=str(root_path), status="queued"),
            "failed_events": cron_event_registry(root_path).count(project_root=str(root_path), status="failed"),
            "dead_letter_events": cron_event_registry(root_path).count(project_root=str(root_path), status="dead_letter"),
            "runs": cron_run_registry(root_path).count(project_root=str(root_path)),
        }

    @cron.register(
        "workspace",
        description="Prepare cron workflow directories",
        tags=["cron"],
        examples=["cron workspace OpsJobs", "cron workspace OpsJobs --dry-run"],
        default_output="rich",
        capture_logs=True,
    )
    @cron.dry_run()
    @cron.argument("root", type=t.Path(), default="", help="Project root path")
    def workspace(ctx: FxContext, root: Path | str = "", dry_run: bool = False) -> dict[str, Any]:
        root_path = ctx.resolve(root)
        if dry_run:
            return {"status": "dry-run", "message": "Would prepare cron workspace.", "root": str(root_path)}
        workspace_result = ensure_cron_workspace(root_path)
        record_operation(root=root_path, command="cron workspace", arguments={"root": str(root_path)}, status="success", message=f"Prepared cron workspace (created={len(workspace_result.created)}, existing={len(workspace_result.existing)}).")
        return {
            "status": "success",
            "root": str(root_path),
            "created": [str(path) for path in workspace_result.created],
            "existing": [str(path) for path in workspace_result.existing],
        }

    @cron.register(
        "register",
        description="Register a named workflow",
        tags=["cron", "workflow"],
        examples=["cron register OpsJobs deploy-flow ops/workflows/deploy.yml --job deploy"],
        default_output="rich",
        capture_logs=True,
    )
    @cron.dry_run()
    @cron.argument("root", type=t.Path(), default="", help="Project root path")
    @cron.argument("workflow_name", type=str, help="Workflow name")
    @cron.argument("workflow_file", type=t.Path(exists=True), help="Workflow file path")
    @cron.argument("job", type=str, default="", help="Linked cron job name")
    @cron.argument("command", type=str, default="", help="Shell command")
    @cron.argument("target", type=str, default="", help="Scheduler/deployment target")
    @cron.argument("metadata", type=t.JSON, default={}, help="Optional JSON metadata")
    def register_workflow(
        ctx: FxContext,
        root: Path | str = "",
        workflow_name: str = "",
        workflow_file: Path | str = "",
        job: str = "",
        command: str = "",
        target: str = "",
        metadata: dict[str, Any] | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        root_path = ctx.resolve(root)
        metadata_dict = _payload(metadata)
        if dry_run:
            return {
                "status": "dry-run",
                "message": f"Would register workflow '{workflow_name}'.",
                "root": str(root_path),
                "workflow": workflow_name,
                "file": str(workflow_file),
                "target": target or "local_async",
                "job": job,
                "command": command,
                "metadata": metadata_dict,
            }
        row = register_cron_workflow(root=root_path, name=workflow_name, file_path=str(workflow_file), target=target or "local_async", job_name=job.strip(), command=command.strip(), metadata=metadata_dict)
        record_operation(root=root_path, command="cron register", arguments={"root": str(root_path), "workflow_name": workflow_name, "workflow_file": str(workflow_file), "job": job, "command": command, "target": target, "metadata": metadata_dict}, status="success", message=f"Registered workflow '{row.name}'.")
        return {
            "status": "success",
            "root": str(root_path),
            "workflow": row.name,
            "file": row.file_path,
            "target": row.target,
            "job": row.job_name or "",
            "command": row.command or "",
        }

    @cron.register(
        "workflows",
        description="List registered workflows",
        tags=["cron", "workflow", "inspect"],
        examples=["cron workflows OpsJobs", "cron workflows OpsJobs --output csv"],
        default_output="rich",
    )
    @cron.argument("root", type=t.Path(), default="", help="Project root path")
    def workflows(ctx: FxContext, root: Path | str = "") -> list[dict[str, Any]]:
        root_path = ctx.resolve(root)
        rows = list_cron_workflows(root_path)
        return [
            {
                "name": row.name,
                "target": row.target,
                "enabled": row.enabled,
                "file": row.file_path,
                "job": row.job_name,
                "command": row.command,
            }
            for row in rows
        ]

    @cron.register(
        "run-workflow",
        description="Run a registered workflow",
        tags=["cron", "workflow"],
        examples=['cron run-workflow OpsJobs deploy-flow --payload "{\"sha\":\"abc\"}"'],
        default_output="rich",
        capture_logs=True,
    )
    @cron.dry_run()
    @cron.argument("root", type=t.Path(), default="", help="Project root path")
    @cron.argument("workflow_name", type=str, help="Workflow name")
    @cron.argument("payload", type=t.JSON, default={}, help="Optional JSON payload")
    def run_workflow(
        ctx: FxContext,
        root: Path | str = "",
        workflow_name: str = "",
        payload: dict[str, Any] | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        root_path = ctx.resolve(root)
        payload_dict = _payload(payload)
        if dry_run:
            return {"status": "dry-run", "message": f"Would run workflow '{workflow_name}'.", "root": str(root_path), "workflow": workflow_name, "payload": payload_dict}
        result = run_registered_workflow(root=root_path, name=workflow_name, payload=payload_dict)
        status_value = "success" if result.status in {"success", "skipped"} else "failure"
        record_operation(root=root_path, command="cron run-workflow", arguments={"root": str(root_path), "workflow_name": workflow_name, "payload": payload_dict}, status=status_value, message=result.message)
        return {
            "status": result.status,
            "root": str(root_path),
            "workflow": workflow_name,
            "mode": result.kind,
            "message": result.message,
            "event_id": result.event_id,
            "exit_code": result.exit_code,
        }

    @cron.register(
        "generate",
        description="Generate cron deployment artifacts",
        tags=["cron", "deploy"],
        examples=["cron generate OpsJobs --target github_actions"],
        default_output="rich",
        capture_logs=True,
    )
    @cron.dry_run()
    @cron.argument("root", type=t.Path(), default="", help="Project root path")
    @cron.argument("target", type=str, default="", help="Target filter")
    def generate(ctx: FxContext, root: Path | str = "", target: str = "", dry_run: bool = False) -> dict[str, Any]:
        root_path = ctx.resolve(root)
        if dry_run:
            return {"status": "dry-run", "message": "Would generate cron artifacts.", "root": str(root_path), "target": target or "all"}
        sync_project_jobs(root_path)
        report = generate_artifacts(root=root_path, target=target)
        record_operation(root=root_path, command="cron generate", arguments={"root": str(root_path), "target": target}, status="success", message=f"Generated cron artifacts (created={len(report.created)}, updated={len(report.updated)}, skipped={len(report.skipped)}).")
        return {"status": "success", "root": str(root_path), "target": target or "all", "created": report.created, "updated": report.updated, "skipped": report.skipped}

    @cron.register(
        "apply",
        description="Apply cron deployment artifacts",
        tags=["cron", "deploy", "danger"],
        examples=["cron apply OpsJobs --target linux_cron --force"],
        default_output="rich",
        capture_logs=True,
    )
    @cron.confirm("Apply cron deployment artifacts for {root}?", danger=True, confirm_phrase="apply cron")
    @cron.argument("root", type=t.Path(), default="", help="Project root path")
    @cron.argument("target", type=str, default="", help="Target filter")
    def apply(ctx: FxContext, root: Path | str = "", target: str = "") -> dict[str, Any]:
        root_path = ctx.resolve(root)
        sync_project_jobs(root_path)
        report = apply_artifacts(root=root_path, target=target)
        success = len(report.errors) == 0
        record_operation(root=root_path, command="cron apply", arguments={"root": str(root_path), "target": target}, status="success" if success else "failure", message=f"Applied cron artifacts (applied={len(report.applied)}, errors={len(report.errors)}).")
        return {
            "status": "success" if success else "failure",
            "root": str(root_path),
            "target": target or "all",
            "applied": report.applied,
            "skipped": report.skipped,
            "errors": report.errors,
        }


def _payload(value: Any) -> dict[str, Any]:
    if value is None or value == "":
        return {}
    if isinstance(value, dict):
        return value
    return {"value": value}


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _wait_for_pid_exit(pid: int, *, timeout_seconds: float = 6.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if not _pid_is_alive(pid):
            return True
        time.sleep(0.15)
    return not _pid_is_alive(pid)


def _spawn_cron_daemon(*, root_path: Path, workers: int) -> int:
    argv = [
        sys.executable,
        "-m",
        "registers.cron.daemon",
        "--root",
        str(root_path),
        "--workers",
        str(max(1, workers)),
    ]
    popen_kwargs: dict[str, Any] = {
        "cwd": str(root_path),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "start_new_session": True,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
    proc = subprocess.Popen(argv, **popen_kwargs)
    return int(proc.pid)
