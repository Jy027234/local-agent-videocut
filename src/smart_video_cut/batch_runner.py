from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Mapping

from smart_video_cut.bundled_runtime import run_edit_with_style_package
from smart_video_cut.models import LocalEditTask


BATCH_RUN_SCHEMA = "smart_video_cut.local.batch_run.v0"


def run_batch_edits(
    *,
    tasks: list[Mapping[str, Any]],
    batch_dir: str | Path = "",
    batch_id: str = "",
    default_execute_real_render: bool = False,
    stop_on_error: bool = False,
    max_retries: int = 0,
) -> dict[str, Any]:
    """Run multiple local edit tasks sequentially and persist batch status."""
    selected_batch_id = batch_id or f"batch_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    selected_batch_dir = Path(batch_dir) if batch_dir else _default_batch_dir(selected_batch_id)
    selected_batch_dir.mkdir(parents=True, exist_ok=True)
    started_at = time.time()
    status: dict[str, Any] = {
        "schema": BATCH_RUN_SCHEMA,
        "ok": True,
        "batch_id": selected_batch_id,
        "batch_dir": str(selected_batch_dir),
        "started_at": started_at,
        "finished_at": None,
        "task_count": len(tasks),
        "completed_count": 0,
        "failed_count": 0,
        "retry_count": 0,
        "stop_on_error": stop_on_error,
        "max_retries": max(0, int(max_retries)),
        "tasks": [],
    }
    _write_status(selected_batch_dir, status)

    for index, raw_task in enumerate(tasks):
        item = _task_status_item(index, raw_task)
        status["tasks"].append(item)
        _write_status(selected_batch_dir, status)
        task = None
        for attempt_index in range(max(0, int(max_retries)) + 1):
            if attempt_index > 0:
                status["retry_count"] += 1
                item["retry_count"] += 1
            attempt = _attempt_status(attempt_index)
            item["attempts"].append(attempt)
            item["attempt_count"] = attempt_index + 1
            item["status"] = "running" if attempt_index == 0 else "retrying"
            _write_status(selected_batch_dir, status)
            try:
                task = task or _task_from_payload(
                    raw_task,
                    default_execute_real_render=default_execute_real_render,
                    batch_dir=selected_batch_dir,
                    index=index,
                )
                item["output_dir"] = str(task.output_dir)
                attempt["status"] = "running"
                _write_status(selected_batch_dir, status)
                result = run_edit_with_style_package(task)
                attempt["finished_at"] = time.time()
                attempt["elapsed_seconds"] = round(attempt["finished_at"] - attempt["started_at"], 3)
                attempt["ok"] = result.get("ok") is True
                attempt["status"] = "completed" if attempt["ok"] else "failed"
                attempt["error"] = "" if attempt["ok"] else str(result.get("error") or result.get("reason") or "task_failed")
                item["ok"] = attempt["ok"]
                item["status"] = "completed" if item["ok"] else "failed"
                item["result_path"] = str(task.output_dir / "local_studio_result.json")
                item["error"] = attempt["error"]
                item["summary"] = {
                    "toolkit_status": result.get("toolkit_status"),
                    "copied_output_video": result.get("copied_output_video"),
                    "current_version": result.get("current_version"),
                }
            except Exception as exc:  # pragma: no cover - exercised through registry safety too
                attempt["finished_at"] = time.time()
                attempt["elapsed_seconds"] = round(attempt["finished_at"] - attempt["started_at"], 3)
                attempt["ok"] = False
                attempt["status"] = "failed"
                attempt["error"] = f"{type(exc).__name__}: {exc}"
                item["status"] = "failed"
                item["ok"] = False
                item["error"] = attempt["error"]
            _write_status(selected_batch_dir, status)
            if item["ok"]:
                break
        if item["ok"]:
            status["completed_count"] += 1
        else:
            status["failed_count"] += 1
            status["ok"] = False
            if stop_on_error:
                break
        _write_status(selected_batch_dir, status)

    status["finished_at"] = time.time()
    status["elapsed_seconds"] = round(status["finished_at"] - started_at, 3)
    _write_status(selected_batch_dir, status)
    return status


def _task_from_payload(
    payload: Mapping[str, Any],
    *,
    default_execute_real_render: bool,
    batch_dir: Path,
    index: int,
) -> LocalEditTask:
    input_videos = [str(item) for item in payload.get("input_videos") or [] if str(item or "").strip()]
    primary = str(payload.get("input_video") or (input_videos[0] if input_videos else "")).strip()
    if primary and primary not in input_videos:
        input_videos.insert(0, primary)
    output_dir = str(payload.get("output_dir") or "").strip()
    if not output_dir:
        output_dir = str(batch_dir / f"task_{index + 1:03d}")
    return LocalEditTask(
        style_package=Path(str(payload.get("style_package") or "")),
        input_video=Path(primary),
        input_videos=[Path(path) for path in input_videos],
        output_dir=Path(output_dir),
        user_request=str(payload.get("user_request") or ""),
        project_id=str(payload.get("project_id") or "local_project"),
        execute_real_render=bool(payload.get("execute_real_render", default_execute_real_render)),
        allow_edge_tts=bool(payload.get("allow_edge_tts", False)),
        voiceover_text=payload.get("voiceover_text"),
        use_memory=payload.get("use_memory", True) is not False,
        settings_overrides=payload.get("settings_overrides") if isinstance(payload.get("settings_overrides"), dict) else {},
        confirmed_brief=payload.get("confirmed_brief"),
        timeline_override=payload.get("timeline_override") if isinstance(payload.get("timeline_override"), dict) else None,
    )


def _task_status_item(index: int, payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "index": index,
        "name": str(payload.get("name") or payload.get("project_id") or f"task_{index + 1:03d}"),
        "status": "queued",
        "ok": False,
        "output_dir": str(payload.get("output_dir") or ""),
        "result_path": "",
        "error": "",
        "attempt_count": 0,
        "retry_count": 0,
        "attempts": [],
        "summary": {},
    }


def _attempt_status(attempt_index: int) -> dict[str, Any]:
    return {
        "attempt": attempt_index + 1,
        "status": "queued",
        "ok": False,
        "started_at": time.time(),
        "finished_at": None,
        "elapsed_seconds": None,
        "error": "",
    }


def _write_status(batch_dir: Path, status: dict[str, Any]) -> None:
    (batch_dir / "batch_status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _default_batch_dir(batch_id: str) -> Path:
    return Path(__file__).resolve().parents[2] / "workspace" / "batch_runs" / batch_id
