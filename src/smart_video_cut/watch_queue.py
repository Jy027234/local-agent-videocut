from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Mapping

from smart_video_cut.batch_runner import run_batch_edits
from smart_video_cut.protocol_runner import detect_runnable_protocol_kind, run_protocol_path


WATCH_QUEUE_SCHEMA = "smart_video_cut.local.watch_queue.v0"


def run_watch_queue_once(
    *,
    watch_dir: str | Path,
    batch_root: str | Path = "",
    archive_dir: str | Path = "",
    failed_dir: str | Path = "",
    pattern: str = "*.json",
    default_execute_real_render: bool = False,
    stop_on_error: bool = False,
    max_retries: int = 0,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Scan one directory for task JSON files and run each file as a batch."""
    if not str(watch_dir).strip():
        raise ValueError("watch_dir is required")
    selected_watch_dir = Path(watch_dir)
    selected_watch_dir.mkdir(parents=True, exist_ok=True)
    selected_batch_root = Path(batch_root) if batch_root else _default_batch_root()
    selected_archive_dir = Path(archive_dir) if archive_dir else selected_watch_dir / "_processed"
    selected_failed_dir = Path(failed_dir) if failed_dir else selected_watch_dir / "_failed"
    started_at = time.time()
    status: dict[str, Any] = {
        "schema": WATCH_QUEUE_SCHEMA,
        "ok": True,
        "watch_dir": str(selected_watch_dir),
        "batch_root": str(selected_batch_root),
        "archive_dir": str(selected_archive_dir),
        "failed_dir": str(selected_failed_dir),
        "pattern": pattern,
        "dry_run": dry_run,
        "started_at": started_at,
        "finished_at": None,
        "file_count": 0,
        "queued_count": 0,
        "processed_count": 0,
        "failed_count": 0,
        "error_count": 0,
        "files": [],
        "errors": [],
    }

    task_files = _discover_task_files(selected_watch_dir, pattern)
    status["file_count"] = len(task_files)
    _write_watch_status(selected_watch_dir, status)

    for task_file in task_files:
        item = _file_status_item(task_file)
        status["files"].append(item)
        try:
            job = _prepare_queue_job(task_file)
            item["protocol_kind"] = str(job.get("protocol_kind") or "")
            item["job_kind"] = str(job.get("job_kind") or "")
            tasks = list(job.get("tasks") or [])
            item["task_count"] = int(job.get("task_count") or len(tasks))
            item["status"] = "queued" if dry_run else "running"
            status["queued_count"] += item["task_count"]
            _write_watch_status(selected_watch_dir, status)
            if dry_run:
                continue

            batch_id = _safe_batch_id(task_file.stem)
            execution_dir = _unique_path(selected_batch_root / batch_id)
            result = _run_queue_job(
                job=job,
                source_file=task_file,
                batch_id=batch_id,
                execution_dir=execution_dir,
                default_execute_real_render=default_execute_real_render,
                stop_on_error=stop_on_error,
                max_retries=max_retries,
            )
            item["batch_id"] = str(result.get("batch_id") or batch_id)
            item["batch_dir"] = str(result.get("batch_dir") or execution_dir)
            item["result"] = _queue_result_summary(result)
            if result.get("ok") is True:
                item["status"] = "completed"
                item["archived_path"] = str(_archive_file(task_file, selected_archive_dir))
                status["processed_count"] += 1
            else:
                item["status"] = "failed"
                item["archived_path"] = str(_archive_file(task_file, selected_failed_dir))
                status["failed_count"] += 1
                status["ok"] = False
                if stop_on_error:
                    break
        except Exception as exc:  # pragma: no cover - registry and CLI cover safety path
            item["status"] = "failed"
            item["error"] = f"{type(exc).__name__}: {exc}"
            status["errors"].append({"file": str(task_file), "error": item["error"]})
            status["error_count"] += 1
            status["failed_count"] += 1
            status["ok"] = False
            if not dry_run and task_file.exists():
                item["archived_path"] = str(_archive_file(task_file, selected_failed_dir))
            if stop_on_error:
                break
        finally:
            _write_watch_status(selected_watch_dir, status)

    status["finished_at"] = time.time()
    status["elapsed_seconds"] = round(status["finished_at"] - started_at, 3)
    _write_watch_status(selected_watch_dir, status)
    return status


def _discover_task_files(watch_dir: Path, pattern: str) -> list[Path]:
    candidates = sorted(path for path in watch_dir.glob(pattern or "*.json") if path.is_file())
    return [
        path for path in candidates
        if path.name != "watch_status.json" and not path.name.startswith(".")
    ]


def _load_task_file(task_file: Path) -> list[Mapping[str, Any]]:
    data = json.loads(task_file.read_text(encoding="utf-8"))
    tasks = data.get("tasks") if isinstance(data, dict) and isinstance(data.get("tasks"), list) else data
    if isinstance(tasks, dict):
        tasks = [tasks]
    if not isinstance(tasks, list):
        raise ValueError("task file must contain a task object, a task list, or {'tasks': [...]}")
    normalized = []
    for index, task in enumerate(tasks):
        if not isinstance(task, Mapping):
            raise ValueError(f"task at index {index} must be an object")
        normalized.append(task)
    return normalized


def _prepare_queue_job(task_file: Path) -> dict[str, Any]:
    protocol_kind = detect_runnable_protocol_kind(task_file)
    if protocol_kind:
        return {
            "job_kind": "protocol_run",
            "protocol_kind": protocol_kind,
            "task_count": 1,
        }
    tasks = _load_task_file(task_file)
    return {
        "job_kind": "batch_tasks",
        "protocol_kind": "",
        "tasks": tasks,
        "task_count": len(tasks),
    }


def _run_queue_job(
    *,
    job: Mapping[str, Any],
    source_file: Path,
    batch_id: str,
    execution_dir: Path,
    default_execute_real_render: bool,
    stop_on_error: bool,
    max_retries: int,
) -> dict[str, Any]:
    job_kind = str(job.get("job_kind") or "")
    if job_kind == "protocol_run":
        return run_protocol_path(
            source_file,
            output_dir=str(execution_dir),
            execute_real_render=default_execute_real_render,
        )
    return run_batch_edits(
        tasks=list(job.get("tasks") or []),
        batch_dir=execution_dir,
        batch_id=batch_id,
        default_execute_real_render=default_execute_real_render,
        stop_on_error=stop_on_error,
        max_retries=max_retries,
    )


def _queue_result_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    if "completed_count" in result or "failed_count" in result or "retry_count" in result:
        return {
            "ok": result.get("ok") is True,
            "completed_count": result.get("completed_count", 0),
            "failed_count": result.get("failed_count", 0),
            "retry_count": result.get("retry_count", 0),
        }
    return {
        "ok": result.get("ok") is True,
        "protocol_kind": result.get("protocol_kind") or "",
        "protocol_runner": result.get("protocol_runner") or "",
        "status": result.get("status") or ("completed" if result.get("ok") is True else "failed"),
        "output_dir": result.get("output_dir") or "",
        "completion_path": result.get("completion_path") or "",
        "result_path": result.get("result_path") or "",
    }


def _file_status_item(task_file: Path) -> dict[str, Any]:
    return {
        "file": str(task_file),
        "name": task_file.name,
        "status": "discovered",
        "job_kind": "",
        "protocol_kind": "",
        "task_count": 0,
        "batch_id": "",
        "batch_dir": "",
        "archived_path": "",
        "error": "",
        "result": {},
    }


def _archive_file(source: Path, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    target = _unique_path(target_dir / source.name)
    shutil.move(str(source), str(target))
    return target


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stamp = int(time.time())
    suffix = f"{stamp}_{uuid.uuid4().hex[:8]}"
    return path.with_name(f"{path.stem}_{suffix}{path.suffix}")


def _safe_batch_id(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in value.strip())
    return cleaned or f"watch_batch_{uuid.uuid4().hex[:8]}"


def _write_watch_status(watch_dir: Path, status: dict[str, Any]) -> None:
    (watch_dir / "watch_status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _default_batch_root() -> Path:
    return Path(__file__).resolve().parents[2] / "workspace" / "batch_runs"
