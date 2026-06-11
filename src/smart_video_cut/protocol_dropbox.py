from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any, Mapping

from smart_video_cut.external_handoff_compat import (
    LEGACY_EXPORT_QUEUE_ID,
    LEGACY_EXTERNAL_PROTOCOL_KIND,
)
from smart_video_cut.export_adapters import (
    EXPORT_FILMGEN_HANDOFF_SCHEMA,
)
from smart_video_cut.models import LOCAL_EDIT_TASK_SCHEMA, PROJECT_PACK_SCHEMA
from smart_video_cut.project_manifest import PROJECT_MANIFEST_FILENAME, PROJECT_MANIFEST_SCHEMA
from smart_video_cut.protocol_runner import detect_runnable_protocol_kind
from smart_video_cut.toolkit_protocol import (
    LOCAL_EDIT_RESULT_SCHEMA,
    LOCAL_TOOLKIT_PROTOCOL_FILENAME,
    LOCAL_TOOLKIT_PROTOCOL_SCHEMA,
)
from smart_video_cut.watch_queue import run_watch_queue_once
from smart_video_cut.worker_protocol import WORKER_TASK_FILENAME, WORKER_TASK_PACKAGE_SCHEMA


PROTOCOL_DROPBOX_SCHEMA = "smart_video_cut.local.protocol_dropbox.v0"
PROTOCOL_DROPBOX_IMPORT_SCHEMA = "smart_video_cut.local.protocol_dropbox_import.v0"
PROTOCOL_DROPBOX_RUN_SCHEMA = "smart_video_cut.local.protocol_dropbox_run.v0"
PROTOCOL_DROPBOX_MONITOR_SCHEMA = "smart_video_cut.local.protocol_dropbox_monitor.v0"
PROTOCOL_DROPBOX_HISTORY_SCHEMA = "smart_video_cut.local.protocol_dropbox_history.v0"
PROTOCOL_DROPBOX_REQUEUE_SCHEMA = "smart_video_cut.local.protocol_dropbox_requeue.v0"
PROTOCOL_DROPBOX_FILENAME = "protocol_dropbox.json"
PROTOCOL_DROPBOX_STATUS_FILENAME = "dropbox_status.json"
PROTOCOL_DROPBOX_MONITOR_FILENAME = "dropbox_monitor.json"
PROTOCOL_DROPBOX_HISTORY_FILENAME = "dropbox_history.json"

_QUEUE_DEFINITIONS: tuple[dict[str, str], ...] = (
    {
        "queue_id": "worker_packages",
        "protocol_kind": "worker_task_package",
        "label": "Worker 任务包",
        "relative_watch_dir": "inbox/worker_packages",
    },
    {
        "queue_id": "project_packs",
        "protocol_kind": "project_pack",
        "label": "ProjectPack",
        "relative_watch_dir": "inbox/project_packs",
    },
    {
        "queue_id": LEGACY_EXPORT_QUEUE_ID,
        "protocol_kind": LEGACY_EXTERNAL_PROTOCOL_KIND,
        "label": "外部导出交接",
        "relative_watch_dir": f"inbox/{LEGACY_EXPORT_QUEUE_ID}",
    },
    {
        "queue_id": "local_edit_tasks",
        "protocol_kind": "local_edit_task",
        "label": "本地剪辑任务",
        "relative_watch_dir": "inbox/local_edit_tasks",
    },
    {
        "queue_id": "task_lists",
        "protocol_kind": "batch_tasks",
        "label": "批量任务列表",
        "relative_watch_dir": "inbox/task_lists",
    },
)

_QUEUE_BY_PROTOCOL_KIND = {
    item["protocol_kind"]: item["queue_id"]
    for item in _QUEUE_DEFINITIONS
}

_QUEUE_BY_ID = {
    item["queue_id"]: item
    for item in _QUEUE_DEFINITIONS
}

_TEMPLATE_FILES = {
    "local_edit_task": "templates/local_edit_task.template.json",
    "batch_tasks": "templates/batch_tasks.template.json",
    "worker_task_package": "templates/worker_task_package.template.json",
    "project_pack": "templates/project_pack.template.json",
    "filmgen_handoff": "templates/filmgen_handoff.template.json",
    "readme": "templates/README.md",
}


def initialize_protocol_dropbox(*, dropbox_dir: str | Path = "") -> dict[str, Any]:
    root = _resolve_dropbox_dir(dropbox_dir)
    manifest_path = root / PROTOCOL_DROPBOX_FILENAME
    status_path = root / PROTOCOL_DROPBOX_STATUS_FILENAME

    queue_payloads: dict[str, Any] = {}
    for definition in _QUEUE_DEFINITIONS:
        watch_dir = root / definition["relative_watch_dir"]
        archive_dir = root / "archive" / "processed" / definition["queue_id"]
        failed_dir = root / "archive" / "failed" / definition["queue_id"]
        batch_root = root / "batch_runs" / definition["queue_id"]
        for folder in (watch_dir, archive_dir, failed_dir, batch_root):
            folder.mkdir(parents=True, exist_ok=True)
        queue_payloads[definition["queue_id"]] = {
            "queue_id": definition["queue_id"],
            "protocol_kind": definition["protocol_kind"],
            "label": definition["label"],
            "watch_dir": str(watch_dir),
            "archive_dir": str(archive_dir),
            "failed_dir": str(failed_dir),
            "batch_root": str(batch_root),
            "watch_status_path": str(watch_dir / "watch_status.json"),
        }

    templates = _write_dropbox_templates(root)
    payload = {
        "schema": PROTOCOL_DROPBOX_SCHEMA,
        "ok": True,
        "dropbox_dir": str(root),
        "manifest_path": str(manifest_path),
        "status_path": str(status_path),
        "monitor_path": str(root / PROTOCOL_DROPBOX_MONITOR_FILENAME),
        "history_path": str(root / PROTOCOL_DROPBOX_HISTORY_FILENAME),
        "queue_count": len(queue_payloads),
        "queue_order": [definition["queue_id"] for definition in _QUEUE_DEFINITIONS],
        "queues": queue_payloads,
        "templates": templates,
        "naming_rule": "<timestamp>__<queue_id>__<label>.json",
        "commands": {
            "import": f'protocol-dropbox-import --dropbox-dir "{root}" --source-path "<path>"',
            "run": f'protocol-dropbox-run --dropbox-dir "{root}"',
            "monitor": f'protocol-dropbox-monitor --dropbox-dir "{root}" --interval-seconds 15',
            "history": f'protocol-dropbox-history --dropbox-dir "{root}" --limit 20',
            "requeue_failed": f'protocol-dropbox-requeue-failed --dropbox-dir "{root}" --queue-id all --max-files 20',
            "inspect": f'protocol-inspect --path "{manifest_path}"',
        },
        "ui_panel": "package",
        "created_at": time.time(),
    }
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    if not status_path.exists():
        _write_dropbox_status(
            status_path,
            {
                "schema": PROTOCOL_DROPBOX_RUN_SCHEMA,
                "ok": True,
                "status": "idle",
                "dropbox_dir": str(root),
                "manifest_path": str(manifest_path),
                "status_path": str(status_path),
                "queue_count": len(queue_payloads),
                "queue_order": payload["queue_order"],
                "queues": [],
                "file_count": 0,
                "queued_count": 0,
                "processed_count": 0,
                "failed_count": 0,
                "error_count": 0,
                "started_at": None,
                "finished_at": None,
                "elapsed_seconds": 0.0,
            },
        )
    history_path = root / PROTOCOL_DROPBOX_HISTORY_FILENAME
    if not history_path.exists():
        _write_dropbox_status(
            history_path,
            {
                "schema": PROTOCOL_DROPBOX_HISTORY_SCHEMA,
                "ok": True,
                "dropbox_dir": str(root),
                "manifest_path": str(manifest_path),
                "history_path": str(history_path),
                "updated_at": time.time(),
                "run_count": 0,
                "alert_entry_count": 0,
                "last_alert_level": "ok",
                "entries": [],
            },
        )
    monitor_path = root / PROTOCOL_DROPBOX_MONITOR_FILENAME
    if not monitor_path.exists():
        _write_dropbox_status(
            monitor_path,
            {
                "schema": PROTOCOL_DROPBOX_MONITOR_SCHEMA,
                "ok": True,
                "status": "idle",
                "running": False,
                "stop_requested": False,
                "dropbox_dir": str(root),
                "manifest_path": str(manifest_path),
                "monitor_path": str(monitor_path),
                "status_path": str(status_path),
                "history_path": str(history_path),
                "interval_seconds": 15.0,
                "max_cycles": 0,
                "completed_cycles": 0,
                "current_cycle": 0,
                "default_execute_real_render": False,
                "stop_on_error": False,
                "max_retries": 0,
                "dry_run": False,
                "queue_count": len(queue_payloads),
                "queue_order": payload["queue_order"],
                "started_at": None,
                "finished_at": None,
                "elapsed_seconds": 0.0,
                "last_cycle_started_at": None,
                "last_cycle_finished_at": None,
                "next_poll_at": None,
                "last_run_status_path": "",
                "last_run": {},
                "recent_runs": [],
                "active_alerts": [],
                "alert_count": 0,
                "last_alert_level": "ok",
                "totals": {
                    "file_count": 0,
                    "queued_count": 0,
                    "processed_count": 0,
                    "failed_count": 0,
                    "error_count": 0,
                },
            },
        )
    return payload


def import_protocol_dropbox_item(
    *,
    source_path: str | Path,
    dropbox_dir: str | Path = "",
    label: str = "",
) -> dict[str, Any]:
    manifest = initialize_protocol_dropbox(dropbox_dir=dropbox_dir)
    resolved = _resolve_import_source(Path(source_path))
    protocol_kind = str(resolved.get("protocol_kind") or "")
    queue_id = _QUEUE_BY_PROTOCOL_KIND.get(protocol_kind)
    if not queue_id:
        raise ValueError(f"unsupported_dropbox_protocol_kind: {protocol_kind or '<missing>'}")
    watch_dir = Path(manifest["queues"][queue_id]["watch_dir"])
    target = _unique_path(
        watch_dir / _normalized_filename(queue_id=queue_id, source_name=str(resolved.get("source_name") or ""), label=label),
    )

    if resolved.get("write_payload") is True:
        payload = dict(resolved.get("payload") or {})
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        preview_payload = payload
    else:
        selected_source = Path(str(resolved.get("resolved_source_path") or ""))
        shutil.copy2(selected_source, target)
        preview_payload = _preview_json_payload(target)

    return {
        "schema": PROTOCOL_DROPBOX_IMPORT_SCHEMA,
        "ok": True,
        "dropbox_dir": manifest["dropbox_dir"],
        "manifest_path": manifest["manifest_path"],
        "source_path": str(source_path),
        "resolved_source_path": str(resolved.get("resolved_source_path") or source_path),
        "protocol_kind": protocol_kind,
        "queue_id": queue_id,
        "queue_label": _QUEUE_BY_ID[queue_id]["label"],
        "imported_path": str(target),
        "normalized": resolved.get("write_payload") is True,
        "normalized_reason": str(resolved.get("normalized_reason") or ""),
        "preview_payload": preview_payload,
        "watch_dir": str(watch_dir),
        "suggested_run_command": manifest["commands"]["run"],
    }


def run_protocol_dropbox_once(
    *,
    dropbox_dir: str | Path = "",
    default_execute_real_render: bool = False,
    stop_on_error: bool = False,
    max_retries: int = 0,
    dry_run: bool = False,
) -> dict[str, Any]:
    manifest = initialize_protocol_dropbox(dropbox_dir=dropbox_dir)
    root = Path(manifest["dropbox_dir"])
    status_path = root / PROTOCOL_DROPBOX_STATUS_FILENAME
    history_path = root / PROTOCOL_DROPBOX_HISTORY_FILENAME
    started_at = time.time()
    queue_summaries: list[dict[str, Any]] = []
    payload = {
        "schema": PROTOCOL_DROPBOX_RUN_SCHEMA,
        "ok": True,
        "status": "running",
        "dropbox_dir": str(root),
        "manifest_path": manifest["manifest_path"],
        "status_path": str(status_path),
        "history_path": str(history_path),
        "queue_count": len(_QUEUE_DEFINITIONS),
        "queue_order": list(manifest.get("queue_order") or []),
        "queues": queue_summaries,
        "file_count": 0,
        "queued_count": 0,
        "processed_count": 0,
        "failed_count": 0,
        "error_count": 0,
        "started_at": started_at,
        "finished_at": None,
        "elapsed_seconds": 0.0,
        "dry_run": dry_run,
    }
    _write_dropbox_status(status_path, payload)

    for definition in _QUEUE_DEFINITIONS:
        queue = manifest["queues"][definition["queue_id"]]
        result = run_watch_queue_once(
            watch_dir=queue["watch_dir"],
            batch_root=queue["batch_root"],
            archive_dir=queue["archive_dir"],
            failed_dir=queue["failed_dir"],
            default_execute_real_render=default_execute_real_render,
            stop_on_error=stop_on_error,
            max_retries=max_retries,
            dry_run=dry_run,
        )
        summary = {
            "queue_id": definition["queue_id"],
            "protocol_kind": definition["protocol_kind"],
            "label": definition["label"],
            "watch_dir": queue["watch_dir"],
            "watch_status_path": queue["watch_status_path"],
            "batch_root": queue["batch_root"],
            "archive_dir": queue["archive_dir"],
            "failed_dir": queue["failed_dir"],
            "ok": result.get("ok") is True,
            "file_count": int(result.get("file_count") or 0),
            "queued_count": int(result.get("queued_count") or 0),
            "processed_count": int(result.get("processed_count") or 0),
            "failed_count": int(result.get("failed_count") or 0),
            "error_count": int(result.get("error_count") or 0),
        }
        queue_summaries.append(summary)
        payload["file_count"] += summary["file_count"]
        payload["queued_count"] += summary["queued_count"]
        payload["processed_count"] += summary["processed_count"]
        payload["failed_count"] += summary["failed_count"]
        payload["error_count"] += summary["error_count"]
        if summary["ok"] is not True:
            payload["ok"] = False
            if stop_on_error:
                break
        _write_dropbox_status(status_path, payload)

    finished_at = time.time()
    payload["status"] = "completed" if payload["ok"] is True else "completed_with_errors"
    payload["finished_at"] = finished_at
    payload["elapsed_seconds"] = round(finished_at - started_at, 3)
    payload["queue_failure_count"] = sum(1 for queue in queue_summaries if queue.get("ok") is not True)
    payload["alerts"] = _build_dropbox_alerts(payload)
    payload["alert_count"] = len(payload["alerts"])
    payload["alert_level"] = _alert_level(payload["alerts"])
    _write_dropbox_status(status_path, payload)
    payload["history_entry"] = _append_dropbox_history(root, payload)
    return payload


def get_protocol_dropbox_history(
    *,
    dropbox_dir: str | Path = "",
    limit: int = 20,
    queue_id: str = "",
    alerts_only: bool = False,
) -> dict[str, Any]:
    manifest = initialize_protocol_dropbox(dropbox_dir=dropbox_dir)
    root = Path(manifest["dropbox_dir"])
    history_path = root / PROTOCOL_DROPBOX_HISTORY_FILENAME
    history = _read_json(history_path)
    entries = history.get("entries") if isinstance(history.get("entries"), list) else []
    filtered: list[dict[str, Any]] = []
    selected_queue_id = str(queue_id or "").strip()
    for item in reversed(entries):
        entry = _mapping(item)
        if alerts_only and entry.get("alert_count", 0) <= 0:
            continue
        if selected_queue_id and selected_queue_id not in {"all", "*"}:
            queues = entry.get("queues") if isinstance(entry.get("queues"), list) else []
            if not any(
                _mapping(queue).get("queue_id") == selected_queue_id
                and (
                    int(_mapping(queue).get("file_count") or 0) > 0
                    or int(_mapping(queue).get("processed_count") or 0) > 0
                    or int(_mapping(queue).get("failed_count") or 0) > 0
                )
                for queue in queues
            ):
                continue
        filtered.append(entry)
        if limit > 0 and len(filtered) >= int(limit):
            break
    return {
        "schema": PROTOCOL_DROPBOX_HISTORY_SCHEMA,
        "ok": True,
        "dropbox_dir": str(root),
        "manifest_path": manifest["manifest_path"],
        "history_path": str(history_path),
        "limit": int(limit),
        "queue_id": selected_queue_id,
        "alerts_only": alerts_only,
        "run_count": int(history.get("run_count") or len(entries)),
        "alert_entry_count": int(history.get("alert_entry_count") or 0),
        "last_alert_level": str(history.get("last_alert_level") or "ok"),
        "entries": filtered,
    }


def requeue_protocol_dropbox_failed(
    *,
    dropbox_dir: str | Path = "",
    queue_id: str = "",
    max_files: int = 20,
) -> dict[str, Any]:
    manifest = initialize_protocol_dropbox(dropbox_dir=dropbox_dir)
    root = Path(manifest["dropbox_dir"])
    selected_queue = str(queue_id or "").strip()
    selected_queue_ids = (
        [selected_queue]
        if selected_queue and selected_queue not in {"all", "*"}
        else [definition["queue_id"] for definition in _QUEUE_DEFINITIONS]
    )
    invalid = [item for item in selected_queue_ids if item not in _QUEUE_BY_ID]
    if invalid:
        raise ValueError(f"unknown_protocol_dropbox_queue: {invalid[0]}")
    remaining = max(0, int(max_files))
    moved_entries: list[dict[str, Any]] = []
    queue_summaries: list[dict[str, Any]] = []
    for queue_name in selected_queue_ids:
        queue = manifest["queues"][queue_name]
        failed_dir = Path(queue["failed_dir"])
        watch_dir = Path(queue["watch_dir"])
        candidates = sorted(
            (path for path in failed_dir.glob("*.json") if path.is_file()),
            key=lambda path: path.stat().st_mtime,
        )
        if remaining > 0:
            candidates = candidates[:remaining]
        moved_count = 0
        for source in candidates:
            target = _unique_path(watch_dir / source.name)
            shutil.move(str(source), str(target))
            moved_count += 1
            moved_entries.append({
                "queue_id": queue_name,
                "source_path": str(source),
                "requeued_path": str(target),
                "filename": target.name,
            })
            if remaining > 0:
                remaining -= 1
                if remaining == 0:
                    break
        queue_summaries.append({
            "queue_id": queue_name,
            "label": _QUEUE_BY_ID[queue_name]["label"],
            "moved_count": moved_count,
            "watch_dir": str(watch_dir),
            "failed_dir": str(failed_dir),
        })
        if remaining == 0 and max_files > 0:
            break
    return {
        "schema": PROTOCOL_DROPBOX_REQUEUE_SCHEMA,
        "ok": True,
        "dropbox_dir": str(root),
        "manifest_path": manifest["manifest_path"],
        "queue_id": selected_queue or "all",
        "max_files": int(max_files),
        "moved_count": len(moved_entries),
        "queues": queue_summaries,
        "entries": moved_entries,
        "suggested_run_command": manifest["commands"]["run"],
    }


def _resolve_dropbox_dir(dropbox_dir: str | Path) -> Path:
    value = str(dropbox_dir or "").strip()
    if value:
        path = Path(value)
    else:
        path = Path(__file__).resolve().parents[2] / "workspace" / "protocol_dropbox"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_dropbox_templates(root: Path) -> dict[str, str]:
    templates_dir = root / "templates"
    templates_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        key: str(root / relative)
        for key, relative in _TEMPLATE_FILES.items()
    }
    worker_payload = {
        "schema": WORKER_TASK_PACKAGE_SCHEMA,
        "package_id": "demo_worker_package",
        "task": _local_edit_task_template(
            style_package="D:\\path\\to\\packages\\door-flash-reference",
            input_video="D:\\path\\to\\input.mp4",
            output_dir="D:\\path\\to\\workspace\\output\\demo_case",
            user_request="15 秒竖屏安装展示短片，先给全景再切锁具细节。",
            project_id="demo_worker_project",
        ),
    }
    project_pack_payload = {
        "schema": PROJECT_PACK_SCHEMA,
        "name": "demo_project_pack",
        "style_pack_ref": "D:\\path\\to\\packages\\door-flash-reference",
        "input_videos": [
            "D:\\path\\to\\input.mp4",
            "D:\\path\\to\\detail.mp4",
        ],
        "output_dir": "D:\\path\\to\\workspace\\output\\demo_case",
        "project_settings_overrides": {},
        "source_output_dir": "D:\\path\\to\\workspace\\output\\demo_case",
        "project_manifest": {
            "project_id": "demo_project_pack",
            "user_request": "沿用原项目风格继续剪辑。",
        },
        "timeline_plan": {},
        "version_history": {},
        "artifact_refs": {},
    }
    filmgen_payload = {
        "schema": EXPORT_FILMGEN_HANDOFF_SCHEMA,
        "schema_version": 1,
        "status": "ready",
        "output_dir": "D:\\path\\to\\workspace\\output\\filmgen_case",
        "final_video": {
            "ready": True,
            "path": "D:\\path\\to\\workspace\\output\\filmgen_case\\final.mp4",
        },
        "input_video_candidates": [
            {"path": "D:\\path\\to\\source\\clip01.mp4"},
        ],
        "toolkit_summary": {
            "project_id": "filmgen_case",
            "workflow_kind": "creative_edit_runner",
            "creative_objective": "电影感五秒产品桥段",
        },
        "filmgen_contract": {
            "reader_endpoint": "/api/filmgen/export-handoff/validate",
        },
    }
    template_payloads = {
        "local_edit_task": _local_edit_task_template(
            style_package="D:\\path\\to\\packages\\door-flash-reference",
            input_video="D:\\path\\to\\input.mp4",
            output_dir="D:\\path\\to\\workspace\\output\\demo_case",
            user_request="15 秒竖屏安装展示短片，先给全景再切锁具细节。",
            project_id="demo_local_task",
        ),
        "batch_tasks": {
            "tasks": [
                _local_edit_task_template(
                    style_package="D:\\path\\to\\packages\\door-flash-reference",
                    input_video="D:\\path\\to\\input.mp4",
                    output_dir="D:\\path\\to\\workspace\\output\\batch_case_001",
                    user_request="生成第一条批量样片。",
                    project_id="demo_batch_project",
                ),
                _local_edit_task_template(
                    style_package="D:\\path\\to\\packages\\door-flash-reference",
                    input_video="D:\\path\\to\\input2.mp4",
                    output_dir="D:\\path\\to\\workspace\\output\\batch_case_002",
                    user_request="生成第二条批量样片。",
                    project_id="demo_batch_project",
                ),
            ]
        },
        "worker_task_package": worker_payload,
        "project_pack": project_pack_payload,
        "filmgen_handoff": filmgen_payload,
    }
    for key, payload in template_payloads.items():
        path = Path(paths[key])
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    Path(paths["readme"]).write_text(_readme_template(root), encoding="utf-8")
    return paths


def _local_edit_task_template(
    *,
    style_package: str,
    input_video: str,
    output_dir: str,
    user_request: str,
    project_id: str,
) -> dict[str, Any]:
    return {
        "schema": LOCAL_EDIT_TASK_SCHEMA,
        "style_package": style_package,
        "input_video": input_video,
        "input_videos": [input_video],
        "output_dir": output_dir,
        "user_request": user_request,
        "execute_real_render": False,
        "allow_edge_tts": False,
        "voiceover_text": "",
        "use_memory": True,
        "project_id": project_id,
        "settings_overrides": {},
        "confirmed_brief": "",
        "task_id": "",
    }


def _readme_template(root: Path) -> str:
    return "\n".join([
        "# 协议投递箱模板",
        "",
        "这个目录把单机版批处理统一成固定结构：",
        "",
        "- `inbox/worker_packages`：投递 `worker_task_package.json`。",
        "- `inbox/project_packs`：投递 `project_pack.json`。",
        "- `inbox/filmgen_handoffs`：投递外部导出交接 JSON。",
        "- `inbox/local_edit_tasks`：投递 `smart_video_cut.local.edit_task.v0`。",
        "- `inbox/task_lists`：投递批量 `{\"tasks\": [...]}` JSON。",
        "- `archive/processed/*`：执行成功后归档。",
        "- `archive/failed/*`：执行失败后归档。",
        "- `batch_runs/*`：每个队列的实际输出目录。",
        "",
        "推荐命令：",
        "",
        f'- 初始化：`protocol-dropbox-init --dropbox-dir "{root}"`',
        f'- 投递：`protocol-dropbox-import --dropbox-dir "{root}" --source-path "<path>"`',
        f'- 执行：`protocol-dropbox-run --dropbox-dir "{root}"`',
        f'- 自动轮询：`protocol-dropbox-monitor --dropbox-dir "{root}" --interval-seconds 15`',
        f'- 查看历史：`protocol-dropbox-history --dropbox-dir "{root}" --limit 20`',
        f'- 回投失败：`protocol-dropbox-requeue-failed --dropbox-dir "{root}" --queue-id all --max-files 20`',
        "",
        "模板文件仅用于快速起步；真实外部交接 handoff 和 ProjectPack 更推荐由系统自动导出。",
        "",
    ])


def _resolve_import_source(source_path: Path) -> dict[str, Any]:
    if not source_path.exists():
        raise ValueError(f"dropbox_source_not_found: {source_path}")
    if source_path.is_dir():
        worker_path = source_path / WORKER_TASK_FILENAME
        if worker_path.is_file():
            return _resolve_import_file(worker_path)
        project_pack_path = source_path / "project_pack.json"
        if project_pack_path.is_file():
            return _resolve_import_file(project_pack_path)
        manifest_path = source_path / "manifest.json"
        if manifest_path.is_file() and detect_runnable_protocol_kind(manifest_path) == "filmgen_edit_pack":
            return _resolve_import_file(manifest_path)
        if _has_output_context(source_path):
            return _resolve_output_context(source_path, source_path)
        for candidate in sorted(path for path in source_path.glob("*.json") if path.is_file()):
            try:
                return _resolve_import_file(candidate)
            except ValueError:
                continue
        raise ValueError(f"unsupported_dropbox_source_dir: {source_path}")
    return _resolve_import_file(source_path)


def _resolve_import_file(source_path: Path) -> dict[str, Any]:
    payload = _read_json_any(source_path)
    if payload:
        schema = str(payload.get("schema") or "") if isinstance(payload, Mapping) else ""
        if schema == LOCAL_TOOLKIT_PROTOCOL_SCHEMA:
            output_dir = Path(str(payload.get("output_dir") or source_path.parent))
            return _resolve_output_context(output_dir, source_path, normalized_reason="local_toolkit_protocol")
        if schema in {LOCAL_EDIT_RESULT_SCHEMA, PROJECT_MANIFEST_SCHEMA}:
            return _resolve_output_context(source_path.parent, source_path, normalized_reason=schema)
        protocol_kind = detect_runnable_protocol_kind(source_path)
        if protocol_kind:
            return {
                "protocol_kind": protocol_kind,
                "resolved_source_path": str(source_path),
                "source_name": source_path.stem,
                "write_payload": False,
                "payload": payload,
                "normalized_reason": "",
            }
        if _looks_like_task_list(payload):
            return {
                "protocol_kind": "batch_tasks",
                "resolved_source_path": str(source_path),
                "source_name": source_path.stem,
                "write_payload": False,
                "payload": payload,
                "normalized_reason": "",
            }
    raise ValueError(f"unsupported_dropbox_source_file: {source_path}")


def _resolve_output_context(
    output_dir: Path,
    source_path: Path,
    *,
    normalized_reason: str = "output_dir",
) -> dict[str, Any]:
    payload = _build_local_edit_task_from_output(output_dir)
    return {
        "protocol_kind": "local_edit_task",
        "resolved_source_path": str(source_path),
        "source_name": source_path.stem,
        "write_payload": True,
        "payload": payload,
        "normalized_reason": normalized_reason,
    }


def _build_local_edit_task_from_output(output_dir: Path) -> dict[str, Any]:
    result = _read_json(output_dir / "local_studio_result.json")
    manifest = _read_json(output_dir / PROJECT_MANIFEST_FILENAME)
    latest_result = _mapping(manifest.get("latest_result"))
    source = result or latest_result
    if not source and not manifest:
        raise ValueError(f"output_context_not_found: {output_dir}")
    style_package = str(
        _mapping(source.get("style_package")).get("path")
        or _mapping(manifest.get("style_package")).get("path")
        or ""
    ).strip()
    input_videos = _string_list(source.get("input_videos") or manifest.get("input_videos"))
    primary = str(source.get("input_video") or (input_videos[0] if input_videos else "")).strip()
    if primary and primary not in input_videos:
        input_videos.insert(0, primary)
    if not style_package:
        raise ValueError(f"output_context_missing_style_package: {output_dir}")
    if not input_videos:
        raise ValueError(f"output_context_missing_input_videos: {output_dir}")
    timeline_override = _mapping(source.get("timeline_override")) or _mapping(manifest.get("latest_timeline"))
    return {
        "schema": LOCAL_EDIT_TASK_SCHEMA,
        "style_package": style_package,
        "input_video": primary,
        "input_videos": input_videos,
        "output_dir": str(output_dir),
        "user_request": str(
            source.get("user_request")
            or manifest.get("user_request")
            or "根据历史输出继续剪辑"
        ),
        "execute_real_render": bool(
            source.get("execute_real_render", manifest.get("execute_real_render", False))
        ),
        "allow_edge_tts": bool(source.get("allow_edge_tts", False)),
        "voiceover_text": source.get("voiceover_text"),
        "use_memory": source.get("use_memory", True) is not False,
        "project_id": str(source.get("project_id") or manifest.get("project_id") or "local_project"),
        "settings_overrides": _mapping(source.get("settings_overrides")),
        "confirmed_brief": source.get("confirmed_brief"),
        "timeline_override": timeline_override or None,
        "task_id": str(source.get("task_id") or "") or None,
    }


def _has_output_context(path: Path) -> bool:
    return any(
        (path / filename).is_file()
        for filename in (
            LOCAL_TOOLKIT_PROTOCOL_FILENAME,
            "local_studio_result.json",
            PROJECT_MANIFEST_FILENAME,
        )
    )


def _looks_like_task_list(payload: Any) -> bool:
    tasks = payload.get("tasks") if isinstance(payload, dict) else payload
    if isinstance(tasks, dict):
        tasks = [tasks]
    return isinstance(tasks, list) and tasks and all(isinstance(item, Mapping) for item in tasks)


def _normalized_filename(*, queue_id: str, source_name: str, label: str) -> str:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    slug = _slugify(label or source_name or queue_id)
    return f"{stamp}__{queue_id}__{slug}.json"


def _slugify(value: str) -> str:
    cleaned = [
        char.lower()
        if char.isalnum()
        else "_"
        for char in str(value or "").strip()
    ]
    collapsed = "".join(cleaned).strip("_")
    while "__" in collapsed:
        collapsed = collapsed.replace("__", "_")
    return collapsed or "item"


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    suffix = f"{int(time.time())}_{int((time.time() % 1) * 1000):03d}"
    return path.with_name(f"{path.stem}_{suffix}{path.suffix}")


def _append_dropbox_history(root: Path, run_payload: Mapping[str, Any]) -> dict[str, Any]:
    history_path = root / PROTOCOL_DROPBOX_HISTORY_FILENAME
    history = _read_json(history_path)
    entries = list(history.get("entries") or []) if isinstance(history.get("entries"), list) else []
    entry = _history_entry_from_run(run_payload)
    entries.append(entry)
    filtered_entries = entries[-200:]
    payload = {
        "schema": PROTOCOL_DROPBOX_HISTORY_SCHEMA,
        "ok": True,
        "dropbox_dir": str(root),
        "manifest_path": str(root / PROTOCOL_DROPBOX_FILENAME),
        "history_path": str(history_path),
        "updated_at": time.time(),
        "run_count": len(filtered_entries),
        "alert_entry_count": sum(1 for item in filtered_entries if int(_mapping(item).get("alert_count") or 0) > 0),
        "last_alert_level": str(entry.get("alert_level") or "ok"),
        "entries": filtered_entries,
    }
    _write_dropbox_status(history_path, payload)
    return entry


def _history_entry_from_run(run_payload: Mapping[str, Any]) -> dict[str, Any]:
    started_at = float(run_payload.get("started_at") or time.time())
    finished_at = float(run_payload.get("finished_at") or time.time())
    return {
        "run_id": f"dropbox_run_{int(started_at * 1000)}",
        "ok": run_payload.get("ok") is True,
        "status": str(run_payload.get("status") or ""),
        "dropbox_dir": str(run_payload.get("dropbox_dir") or ""),
        "started_at": started_at,
        "finished_at": finished_at,
        "elapsed_seconds": float(run_payload.get("elapsed_seconds") or 0.0),
        "dry_run": run_payload.get("dry_run") is True,
        "file_count": int(run_payload.get("file_count") or 0),
        "queued_count": int(run_payload.get("queued_count") or 0),
        "processed_count": int(run_payload.get("processed_count") or 0),
        "failed_count": int(run_payload.get("failed_count") or 0),
        "error_count": int(run_payload.get("error_count") or 0),
        "alert_count": int(run_payload.get("alert_count") or 0),
        "alert_level": str(run_payload.get("alert_level") or "ok"),
        "alerts": list(run_payload.get("alerts") or []),
        "queues": list(run_payload.get("queues") or []),
        "status_path": str(run_payload.get("status_path") or ""),
    }


def _build_dropbox_alerts(run_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    failed_count = int(run_payload.get("failed_count") or 0)
    error_count = int(run_payload.get("error_count") or 0)
    queue_failures = [
        _mapping(queue)
        for queue in run_payload.get("queues") or []
        if _mapping(queue).get("ok") is not True
    ]
    if failed_count > 0:
        alerts.append({
            "code": "failed_files_detected",
            "level": "warn",
            "message": f"本轮有 {failed_count} 个失败文件进入 failed 归档。",
            "failed_count": failed_count,
        })
    if error_count > 0:
        alerts.append({
            "code": "execution_errors_detected",
            "level": "warn",
            "message": f"本轮记录到 {error_count} 个执行错误。",
            "error_count": error_count,
        })
    for queue in queue_failures:
        queue_id = str(queue.get("queue_id") or "")
        queue_failed_count = int(queue.get("failed_count") or 0)
        queue_error_count = int(queue.get("error_count") or 0)
        alerts.append({
            "code": f"{queue_id or 'queue'}_failed",
            "level": "warn",
            "message": f"{queue.get('label') or queue_id or '队列'} 有失败任务。",
            "queue_id": queue_id,
            "failed_count": queue_failed_count,
            "error_count": queue_error_count,
            "failed_dir": queue.get("failed_dir") or "",
        })
    return alerts


def _alert_level(alerts: list[Mapping[str, Any]]) -> str:
    if any(str(item.get("level") or "") == "warn" for item in alerts):
        return "warn"
    return "ok"


def _write_dropbox_status(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_json_any(path: Path) -> Any:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _preview_json_payload(path: Path) -> dict[str, Any]:
    payload = _read_json_any(path)
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, list):
        return {
            "task_count": len(payload),
            "tasks": payload,
        }
    return {}


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _string_list(values: Any) -> list[str]:
    return [str(item) for item in values or [] if str(item or "").strip()]
