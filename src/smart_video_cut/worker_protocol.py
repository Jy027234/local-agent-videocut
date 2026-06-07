from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Mapping

from smart_video_cut.bundled_runtime import run_edit_with_style_package
from smart_video_cut.models import LocalEditTask


WORKER_TASK_PACKAGE_SCHEMA = "smart_video_cut.local.worker_task_package.v0"
WORKER_COMPLETION_SCHEMA = "smart_video_cut.local.worker_completion.v0"
WORKER_TASK_FILENAME = "worker_task_package.json"
WORKER_COMPLETION_FILENAME = "completion.json"


def create_worker_task_package(
    *,
    package_dir: str | Path,
    style_package: str,
    input_video: str = "",
    input_videos: list[str] | None = None,
    output_dir: str,
    user_request: str,
    project_id: str = "local_project",
    execute_real_render: bool = False,
    allow_edge_tts: bool = False,
    voiceover_text: str | None = None,
    use_memory: bool = True,
    confirmed_brief: str | None = None,
    settings_overrides: dict[str, Any] | None = None,
    timeline_override: dict[str, Any] | None = None,
    task_id: str | None = None,
    package_name: str = "",
) -> dict[str, Any]:
    worker_dir = Path(package_dir)
    worker_dir.mkdir(parents=True, exist_ok=True)
    task = _task_from_values(
        style_package=style_package,
        input_video=input_video,
        input_videos=input_videos,
        output_dir=output_dir,
        user_request=user_request,
        project_id=project_id,
        execute_real_render=execute_real_render,
        allow_edge_tts=allow_edge_tts,
        voiceover_text=voiceover_text,
        use_memory=use_memory,
        confirmed_brief=confirmed_brief,
        settings_overrides=settings_overrides,
        timeline_override=timeline_override,
        task_id=task_id,
    )
    package_id = package_name.strip() or f"worker_pkg_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    payload = _worker_task_payload(package_id=package_id, package_dir=worker_dir, task=task)
    package_path = worker_dir / WORKER_TASK_FILENAME
    package_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return {
        "ok": True,
        "schema": WORKER_TASK_PACKAGE_SCHEMA,
        "package_id": package_id,
        "package_dir": str(worker_dir),
        "package_path": str(package_path),
        "task_package": payload,
        "cli_command": f'worker-run --package-path "{package_path}"',
    }


def load_worker_task_package(package_path: str | Path) -> dict[str, Any]:
    path = _resolve_package_path(package_path)
    if not path.is_file():
        return {
            "ok": False,
            "schema": WORKER_TASK_PACKAGE_SCHEMA,
            "reason": "worker_task_package_not_found",
            "package_path": str(path),
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "ok": False,
            "schema": WORKER_TASK_PACKAGE_SCHEMA,
            "reason": "worker_task_package_invalid_json",
            "package_path": str(path),
        }
    completion_path = path.parent / WORKER_COMPLETION_FILENAME
    completion = _read_json(completion_path)
    return {
        "ok": True,
        "schema": WORKER_TASK_PACKAGE_SCHEMA,
        "package_path": str(path),
        "task_package": payload if isinstance(payload, dict) else {},
        "completion_path": str(completion_path),
        "completion": completion,
    }


def run_worker_task_package(
    package_path: str | Path,
    *,
    run_edit: Any | None = None,
) -> dict[str, Any]:
    loaded = load_worker_task_package(package_path)
    if loaded.get("ok") is not True:
        return {
            "ok": False,
            "schema": WORKER_COMPLETION_SCHEMA,
            "reason": loaded.get("reason") or "worker_task_package_not_ready",
            "package_path": str(_resolve_package_path(package_path)),
        }
    payload = loaded.get("task_package") if isinstance(loaded.get("task_package"), Mapping) else {}
    task_payload = payload.get("task") if isinstance(payload.get("task"), Mapping) else {}
    package_file = Path(str(loaded.get("package_path") or ""))
    started_at = time.time()
    task = _task_from_payload(task_payload)
    result = (run_edit or run_edit_with_style_package)(task)
    finished_at = time.time()
    completion_path = package_file.parent / WORKER_COMPLETION_FILENAME
    completion = {
        "schema": WORKER_COMPLETION_SCHEMA,
        "ok": result.get("ok") is True,
        "status": "completed" if result.get("ok") is True else "failed",
        "started_at": started_at,
        "finished_at": finished_at,
        "elapsed_seconds": round(finished_at - started_at, 3),
        "package_id": payload.get("package_id") or "",
        "package_path": str(package_file),
        "completion_path": str(completion_path),
        "project_id": task.project_id,
        "task_id": task.task_id,
        "execution_mode": "worker_real_render" if task.execute_real_render else "plan_only",
        "output_dir": str(task.output_dir),
        "result_path": str(task.output_dir / "local_studio_result.json"),
        "copied_output_video": result.get("copied_output_video") or "",
        "toolkit_status": result.get("toolkit_status") or result.get("workflow_kind") or "",
        "current_version": result.get("current_version"),
        "error": str(result.get("error") or result.get("reason") or "") if result.get("ok") is not True else "",
        "result_summary": _result_summary(result),
    }
    completion_path.write_text(
        json.dumps(completion, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return completion


def _worker_task_payload(*, package_id: str, package_dir: Path, task: LocalEditTask) -> dict[str, Any]:
    return {
        "schema": WORKER_TASK_PACKAGE_SCHEMA,
        "package_id": package_id,
        "created_at": time.time(),
        "package_dir": str(package_dir),
        "task": task.to_dict(),
        "worker_contract": {
            "package_file": WORKER_TASK_FILENAME,
            "completion_file": WORKER_COMPLETION_FILENAME,
            "execution_modes": ["plan_only", "worker_real_render"],
            "cli_run_command": f'worker-run --package-path "{package_dir / WORKER_TASK_FILENAME}"',
            "api_run_endpoint": "/api/worker/run",
            "preview_endpoint": "/api/worker/package/load",
        },
    }


def _resolve_package_path(package_path: str | Path) -> Path:
    path = Path(package_path)
    if path.is_dir():
        return path / WORKER_TASK_FILENAME
    return path


def _task_from_payload(payload: Mapping[str, Any]) -> LocalEditTask:
    input_videos = [str(item) for item in payload.get("input_videos") or [] if str(item or "").strip()]
    primary = str(payload.get("input_video") or "").strip()
    return LocalEditTask(
        style_package=Path(str(payload.get("style_package") or "")),
        input_video=Path(primary),
        input_videos=[Path(path) for path in input_videos],
        output_dir=Path(str(payload.get("output_dir") or "")),
        user_request=str(payload.get("user_request") or ""),
        execute_real_render=bool(payload.get("execute_real_render", False)),
        allow_edge_tts=bool(payload.get("allow_edge_tts", False)),
        voiceover_text=payload.get("voiceover_text"),
        use_memory=payload.get("use_memory", True) is not False,
        project_id=str(payload.get("project_id") or "local_project"),
        settings_overrides=payload.get("settings_overrides") if isinstance(payload.get("settings_overrides"), dict) else {},
        confirmed_brief=payload.get("confirmed_brief"),
        timeline_override=payload.get("timeline_override") if isinstance(payload.get("timeline_override"), dict) else None,
        task_id=str(payload.get("task_id") or "") or None,
    )


def _task_from_values(
    *,
    style_package: str,
    input_video: str = "",
    input_videos: list[str] | None = None,
    output_dir: str,
    user_request: str,
    project_id: str,
    execute_real_render: bool,
    allow_edge_tts: bool,
    voiceover_text: str | None,
    use_memory: bool,
    confirmed_brief: str | None,
    settings_overrides: dict[str, Any] | None,
    timeline_override: dict[str, Any] | None,
    task_id: str | None,
) -> LocalEditTask:
    merged_inputs = [str(item) for item in input_videos or [] if str(item or "").strip()]
    primary = str(input_video or (merged_inputs[0] if merged_inputs else "")).strip()
    if primary and primary not in merged_inputs:
        merged_inputs.insert(0, primary)
    return LocalEditTask(
        style_package=Path(style_package),
        input_video=Path(primary),
        input_videos=[Path(path) for path in merged_inputs],
        output_dir=Path(output_dir),
        user_request=user_request,
        execute_real_render=execute_real_render,
        allow_edge_tts=allow_edge_tts,
        voiceover_text=voiceover_text,
        use_memory=use_memory,
        project_id=project_id,
        settings_overrides=settings_overrides or {},
        confirmed_brief=confirmed_brief,
        timeline_override=timeline_override,
        task_id=task_id,
    )


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _result_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "ok",
        "workflow_kind",
        "toolkit_status",
        "creative_objective",
        "current_version",
        "copied_output_video",
        "style_package",
        "project_id",
    )
    return {key: result.get(key) for key in keys if key in result}
