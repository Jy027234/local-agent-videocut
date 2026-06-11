from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Mapping

from smart_video_cut.external_bridge import (
    load_external_subtitle_handoff,
    validate_external_export_handoff_import,
)
from smart_video_cut.external_handoff_compat import (
    EXTERNAL_EXPORT_RESULT_KEY,
    LEGACY_EXPORT_FILENAME,
    LEGACY_EXPORT_RESULT_KEY,
)
from smart_video_cut.batch_runner import BATCH_RUN_SCHEMA
from smart_video_cut.export_adapters import (
    EXPORT_FILMGEN_HANDOFF_LEGACY_SCHEMA,
    EXPORT_FILMGEN_HANDOFF_SCHEMA,
)
from smart_video_cut.models import (
    MATERIAL_PACK_SCHEMA,
    PROJECT_PACK_SCHEMA,
    STYLE_PACK_SCHEMA,
    STYLE_PACKAGE_SCHEMA,
)
from smart_video_cut.pack_manager import (
    load_pack,
    resolve_effective_settings,
    resolve_project_pack,
    validate_pack_references,
)
from smart_video_cut.project_manifest import (
    PROJECT_MANIFEST_FILENAME,
    PROJECT_MANIFEST_SCHEMA,
    read_project_manifest,
)
from smart_video_cut.subtitle_adapters import (
    FILMGEN_SUBTITLE_HANDOFF_PREVIEW_SCHEMA,
    FILMGEN_SUBTITLE_HANDOFF_SCHEMA,
)


LOCAL_EDIT_RESULT_SCHEMA = "smart_video_cut.local.edit_result.v0"
WORKER_TASK_PACKAGE_SCHEMA = "smart_video_cut.local.worker_task_package.v0"
WORKER_COMPLETION_SCHEMA = "smart_video_cut.local.worker_completion.v0"
LOCAL_TOOLKIT_PROTOCOL_SCHEMA = "smart_video_cut.local.toolkit_protocol.v0"
LOCAL_TOOLKIT_PROTOCOL_INSPECTION_SCHEMA = "smart_video_cut.local.toolkit_protocol_inspection.v0"
LOCAL_TOOLKIT_PROTOCOL_FILENAME = "local_toolkit_protocol.json"
WATCH_QUEUE_SCHEMA = "smart_video_cut.local.watch_queue.v0"
PROTOCOL_DROPBOX_SCHEMA = "smart_video_cut.local.protocol_dropbox.v0"
PROTOCOL_DROPBOX_RUN_SCHEMA = "smart_video_cut.local.protocol_dropbox_run.v0"
PROTOCOL_DROPBOX_HISTORY_SCHEMA = "smart_video_cut.local.protocol_dropbox_history.v0"
PROTOCOL_DROPBOX_REQUEUE_SCHEMA = "smart_video_cut.local.protocol_dropbox_requeue.v0"
PROTOCOL_DROPBOX_FILENAME = "protocol_dropbox.json"
PROTOCOL_DROPBOX_STATUS_FILENAME = "dropbox_status.json"
PROTOCOL_DROPBOX_MONITOR_SCHEMA = "smart_video_cut.local.protocol_dropbox_monitor.v0"
PROTOCOL_DROPBOX_MONITOR_FILENAME = "dropbox_monitor.json"
PROTOCOL_DROPBOX_HISTORY_FILENAME = "dropbox_history.json"


_KNOWN_FILENAMES: dict[str, str] = {
    LOCAL_TOOLKIT_PROTOCOL_FILENAME: "local_toolkit_protocol",
    PROTOCOL_DROPBOX_FILENAME: "protocol_dropbox",
    PROTOCOL_DROPBOX_STATUS_FILENAME: "protocol_dropbox_run",
    PROTOCOL_DROPBOX_MONITOR_FILENAME: "protocol_dropbox_monitor",
    PROTOCOL_DROPBOX_HISTORY_FILENAME: "protocol_dropbox_history",
    "worker_task_package.json": "worker_task_package",
    "completion.json": "worker_completion",
    "project_pack.json": "project_pack",
    "style_pack.json": "style_pack",
    "material_pack.json": "material_pack",
    "style_package.json": "style_package",
    "local_studio_result.json": "local_edit_result",
    PROJECT_MANIFEST_FILENAME: "project_manifest",
    LEGACY_EXPORT_FILENAME: "filmgen_export_handoff",
    "subtitle_handoff.json": "subtitle_handoff",
    "batch_status.json": "batch_run",
    "watch_status.json": "watch_queue",
}

_SCHEMA_KIND_MAP: dict[str, str] = {
    LOCAL_TOOLKIT_PROTOCOL_SCHEMA: "local_toolkit_protocol",
    PROTOCOL_DROPBOX_SCHEMA: "protocol_dropbox",
    PROTOCOL_DROPBOX_RUN_SCHEMA: "protocol_dropbox_run",
    PROTOCOL_DROPBOX_MONITOR_SCHEMA: "protocol_dropbox_monitor",
    PROTOCOL_DROPBOX_HISTORY_SCHEMA: "protocol_dropbox_history",
    PROTOCOL_DROPBOX_REQUEUE_SCHEMA: "protocol_dropbox_requeue",
    WORKER_TASK_PACKAGE_SCHEMA: "worker_task_package",
    WORKER_COMPLETION_SCHEMA: "worker_completion",
    PROJECT_PACK_SCHEMA: "project_pack",
    STYLE_PACK_SCHEMA: "style_pack",
    STYLE_PACKAGE_SCHEMA: "style_package",
    MATERIAL_PACK_SCHEMA: "material_pack",
    LOCAL_EDIT_RESULT_SCHEMA: "local_edit_result",
    PROJECT_MANIFEST_SCHEMA: "project_manifest",
    EXPORT_FILMGEN_HANDOFF_SCHEMA: "filmgen_export_handoff",
    EXPORT_FILMGEN_HANDOFF_LEGACY_SCHEMA: "filmgen_export_handoff",
    FILMGEN_SUBTITLE_HANDOFF_SCHEMA: "subtitle_handoff",
    FILMGEN_SUBTITLE_HANDOFF_PREVIEW_SCHEMA: "subtitle_handoff_preview",
    BATCH_RUN_SCHEMA: "batch_run",
    WATCH_QUEUE_SCHEMA: "watch_queue",
}


def write_local_toolkit_protocol(
    *,
    output_dir: str | Path,
    result: Mapping[str, Any] | None = None,
    project_manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    result_path = output_path / "local_studio_result.json"
    manifest_path = output_path / PROJECT_MANIFEST_FILENAME
    protocol_path = output_path / LOCAL_TOOLKIT_PROTOCOL_FILENAME

    result_data = _mapping(result) or _read_json(result_path)
    manifest_data = _mapping(project_manifest) or _mapping(read_project_manifest(output_path))
    toolkit_summary = _mapping(result_data.get("toolkit_summary"))
    subtitle_result = _mapping(result_data.get("subtitle_adapter_result"))
    export_result = _mapping(result_data.get("export_adapter_result"))
    export_entries = _mapping(export_result.get("exports"))
    project_pack_export = _mapping(export_entries.get("project_pack"))
    filmgen_export = _mapping(export_entries.get(EXTERNAL_EXPORT_RESULT_KEY) or export_entries.get(LEGACY_EXPORT_RESULT_KEY))
    manifest_version_history = _mapping(manifest_data.get("version_history"))
    filmgen_handoff_payload = _mapping(filmgen_export.get("handoff"))

    input_videos = _string_list(
        result_data.get("input_videos")
        or manifest_data.get("input_videos")
        or [result_data.get("input_video")]
    )
    project_id = str(
        manifest_data.get("project_id")
        or toolkit_summary.get("project_id")
        or result_data.get("project_id")
        or "local_project"
    )
    copied_output_video = str(
        result_data.get("copied_output_video")
        or manifest_data.get("copied_output_video")
        or ""
    ).strip()
    filmgen_handoff_path = str(filmgen_export.get("handoff_path") or "").strip()
    subtitle_handoff_path = str(subtitle_result.get("handoff_path") or "").strip()
    execute_real_render = (
        result_data.get("execute_real_render", manifest_data.get("execute_real_render", False)) is True
    )

    artifacts = [
        _artifact_entry(
            artifact_id="local_studio_result",
            label="结果清单",
            path=result_path,
            required=True,
            schema=LOCAL_EDIT_RESULT_SCHEMA,
        ),
        _artifact_entry(
            artifact_id="project_manifest",
            label="项目清单",
            path=manifest_path,
            required=False,
            schema=PROJECT_MANIFEST_SCHEMA,
        ),
        _artifact_entry(
            artifact_id="final_video",
            label="成片视频",
            path=copied_output_video,
            required=False,
            schema="local.file.final_video",
        ),
        _artifact_entry(
            artifact_id="filmgen_export_handoff",
            label="外部导出交接",
            path=filmgen_handoff_path,
            required=False,
            schema=EXPORT_FILMGEN_HANDOFF_SCHEMA,
        ),
        _artifact_entry(
            artifact_id="subtitle_handoff",
            label="字幕交接",
            path=subtitle_handoff_path,
            required=False,
            schema=FILMGEN_SUBTITLE_HANDOFF_SCHEMA,
        ),
    ]

    warnings: list[dict[str, str]] = []
    if not result_data:
        warnings.append({
            "code": "local_result_missing",
            "message": "输出目录中未找到 local_studio_result.json，协议清单将只包含部分信息。",
            "path": str(result_path),
        })
    if not manifest_data:
        warnings.append({
            "code": "project_manifest_missing",
            "message": "输出目录中未找到 project_manifest.json，项目库联动信息不完整。",
            "path": str(manifest_path),
        })
    if execute_real_render and not copied_output_video:
        warnings.append({
            "code": "final_video_missing",
            "message": "当前任务标记为真实渲染，但未发现 copied_output_video。",
            "path": str(output_path / "final.mp4"),
        })

    required_missing = [item for item in artifacts if item["required"] is True and item["ready"] is not True]
    payload = {
        "schema": LOCAL_TOOLKIT_PROTOCOL_SCHEMA,
        "ok": not required_missing,
        "protocol_kind": "local_studio_output_contract",
        "protocol_version": 0,
        "created_at": time.time(),
        "protocol_path": str(protocol_path),
        "output_dir": str(output_path),
        "project_id": project_id,
        "task_id": str(result_data.get("task_id") or ""),
        "status": "ready" if not required_missing else "incomplete",
        "workflow_kind": str(toolkit_summary.get("workflow_kind") or ""),
        "execution_mode": str(
            toolkit_summary.get("execution_mode")
            or ("worker_real_render" if execute_real_render else "plan_only")
        ),
        "style_package": _mapping(result_data.get("style_package")),
        "input_videos": input_videos,
        "input_video_count": len(input_videos),
        "current_version": result_data.get("current_version") or manifest_version_history.get("current_version"),
        "paths": {
            "result_path": str(result_path),
            "project_manifest_path": str(manifest_path),
            "copied_output_video": copied_output_video,
            "filmgen_handoff_path": filmgen_handoff_path,
            "external_handoff_path": filmgen_handoff_path,
            "subtitle_handoff_path": subtitle_handoff_path,
        },
        "artifacts": artifacts,
        "contracts": {
            "inspection": {
                "build_endpoint": "/api/protocol/build",
                "inspect_endpoint": "/api/protocol/inspect",
                "cli_build_command": f'protocol-build --output-dir "{output_path}"',
                "cli_inspect_command": f'protocol-inspect --path "{protocol_path}"',
                "ui_panel": "package",
            },
            "worker": {
                "build_endpoint": "/api/worker/package",
                "run_endpoint": "/api/worker/run",
                "cli_build_command": "worker-pack",
                "cli_run_command": "worker-run",
            },
            "project_pack_export": {
                "available": project_pack_export.get("status") == "available",
                "api_endpoint": project_pack_export.get("api_endpoint") or "/api/packs/project/export",
                "cli_command": project_pack_export.get("cli_command") or "export-project-pack",
                "agent_tool": project_pack_export.get("agent_tool") or "export_project_pack",
            },
            "filmgen_import": {
                "ready": bool(filmgen_handoff_path),
                "validate_endpoint": "/api/filmgen/export-handoff/validate",
                "preview_endpoint": "/api/filmgen/edit-pack/preview",
                "source_schema": str(filmgen_handoff_payload.get("schema") or EXPORT_FILMGEN_HANDOFF_SCHEMA),
            },
            "external_import": {
                "ready": bool(filmgen_handoff_path),
                "validate_endpoint": "/api/external/export-handoff/validate",
                "preview_endpoint": "/api/external/edit-pack/preview",
                "source_schema": str(filmgen_handoff_payload.get("schema") or EXPORT_FILMGEN_HANDOFF_SCHEMA),
            },
        },
        "warnings": warnings,
    }
    protocol_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return payload


def inspect_local_toolkit_path(path: str | Path) -> dict[str, Any]:
    selected = Path(path)
    if not selected.exists():
        return {
            "schema": LOCAL_TOOLKIT_PROTOCOL_INSPECTION_SCHEMA,
            "ok": False,
            "reason": "path_not_found",
            "path": str(selected),
            "protocol_kind": "missing_path",
        }
    if selected.is_dir():
        entries = [
            _compact_inspection(_inspect_json_file(candidate, include_payload=False))
            for candidate in _recognized_files(selected)
        ]
        primary = None
        primary_path = selected / LOCAL_TOOLKIT_PROTOCOL_FILENAME
        if primary_path.is_file():
            primary = _compact_inspection(_inspect_json_file(primary_path, include_payload=False))
        elif (selected / PROTOCOL_DROPBOX_FILENAME).is_file():
            primary_path = selected / PROTOCOL_DROPBOX_FILENAME
            primary = _compact_inspection(_inspect_json_file(primary_path, include_payload=False))
        return {
            "schema": LOCAL_TOOLKIT_PROTOCOL_INSPECTION_SCHEMA,
            "ok": bool(entries),
            "path": str(selected),
            "protocol_kind": "directory_index",
            "label": "本地协议目录",
            "recognized_file_count": len(entries),
            "entries": entries,
            "primary": primary,
            "recommended_protocol_path": str(primary_path),
        }
    return _inspect_json_file(selected, include_payload=True)


def _inspect_json_file(path: Path, *, include_payload: bool) -> dict[str, Any]:
    payload = _read_json(path)
    if not payload:
        return {
            "schema": LOCAL_TOOLKIT_PROTOCOL_INSPECTION_SCHEMA,
            "ok": False,
            "path": str(path),
            "protocol_kind": "invalid_json",
            "label": "无效 JSON",
            "reason": "json_not_found_or_invalid",
        }
    kind = _detected_kind(path, payload)
    if kind == "local_toolkit_protocol":
        return _inspect_protocol_manifest(path, payload, include_payload=include_payload)
    if kind == "protocol_dropbox":
        return _inspect_protocol_dropbox_manifest(path, payload, include_payload=include_payload)
    if kind == "protocol_dropbox_run":
        return _inspect_protocol_dropbox_run(path, payload, include_payload=include_payload)
    if kind == "protocol_dropbox_monitor":
        return _inspect_protocol_dropbox_monitor(path, payload, include_payload=include_payload)
    if kind == "protocol_dropbox_history":
        return _inspect_protocol_dropbox_history(path, payload, include_payload=include_payload)
    if kind == "protocol_dropbox_requeue":
        return _inspect_protocol_dropbox_requeue(path, payload, include_payload=include_payload)
    if kind == "worker_task_package":
        return _inspect_worker_task_package(path, include_payload=include_payload)
    if kind == "worker_completion":
        return _inspect_worker_completion(path, payload, include_payload=include_payload)
    if kind in {"project_pack", "style_pack", "style_package", "material_pack"}:
        return _inspect_pack(path, payload, include_payload=include_payload)
    if kind == "filmgen_export_handoff":
        return _inspect_filmgen_export_handoff(path, include_payload=include_payload)
    if kind in {"subtitle_handoff", "subtitle_handoff_preview"}:
        return _inspect_subtitle_handoff(path, include_payload=include_payload)
    if kind == "project_manifest":
        return _inspect_project_manifest(path, payload, include_payload=include_payload)
    if kind == "local_edit_result":
        return _inspect_local_edit_result(path, payload, include_payload=include_payload)
    if kind == "batch_run":
        return _inspect_batch_run(path, payload, include_payload=include_payload)
    if kind == "watch_queue":
        return _inspect_watch_queue(path, payload, include_payload=include_payload)
    return {
        "schema": LOCAL_TOOLKIT_PROTOCOL_INSPECTION_SCHEMA,
        "ok": True,
        "path": str(path),
        "protocol_kind": kind,
        "label": "未专门识别的本地 JSON",
        "source_schema": str(payload.get("schema") or ""),
        "summary": {
            "keys": sorted(payload.keys()),
            "field_count": len(payload),
        },
        "payload": payload if include_payload else None,
    }


def _inspect_protocol_manifest(path: Path, payload: dict[str, Any], *, include_payload: bool) -> dict[str, Any]:
    artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), list) else []
    validation = _validate_protocol_manifest(payload, artifacts)
    return {
        "schema": LOCAL_TOOLKIT_PROTOCOL_INSPECTION_SCHEMA,
        "ok": validation["valid"],
        "path": str(path),
        "protocol_kind": "local_toolkit_protocol",
        "label": "本地 Toolkit 协议清单",
        "source_schema": str(payload.get("schema") or ""),
        "summary": {
            "project_id": payload.get("project_id"),
            "task_id": payload.get("task_id"),
            "status": payload.get("status"),
            "workflow_kind": payload.get("workflow_kind"),
            "execution_mode": payload.get("execution_mode"),
            "artifact_count": len(artifacts),
            "ready_artifact_count": sum(1 for item in artifacts if isinstance(item, Mapping) and item.get("ready") is True),
        },
        "validation": validation,
        "actions": [{
            "label": "重新生成协议清单",
            "api_endpoint": "/api/protocol/build",
            "cli_command": f'protocol-build --output-dir "{path.parent}"',
        }],
        "payload": payload if include_payload else None,
    }


def _inspect_protocol_dropbox_manifest(path: Path, payload: dict[str, Any], *, include_payload: bool) -> dict[str, Any]:
    queues = _mapping(payload.get("queues"))
    templates = _mapping(payload.get("templates"))
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    if payload.get("schema") != PROTOCOL_DROPBOX_SCHEMA:
        errors.append({"code": "unsupported_schema", "message": f"期望 schema={PROTOCOL_DROPBOX_SCHEMA}"})
    for queue_id, item in queues.items():
        watch_dir = str(_mapping(item).get("watch_dir") or "").strip()
        if watch_dir and not Path(watch_dir).exists():
            warnings.append({
                "code": "watch_dir_missing",
                "message": f"队列目录不存在：{queue_id}",
                "path": watch_dir,
            })
    return {
        "schema": LOCAL_TOOLKIT_PROTOCOL_INSPECTION_SCHEMA,
        "ok": not errors,
        "path": str(path),
        "protocol_kind": "protocol_dropbox",
        "label": "标准协议投递箱",
        "source_schema": str(payload.get("schema") or PROTOCOL_DROPBOX_SCHEMA),
        "summary": {
            "dropbox_dir": payload.get("dropbox_dir"),
            "queue_count": payload.get("queue_count") or len(queues),
            "template_count": len(templates),
            "naming_rule": payload.get("naming_rule"),
        },
        "validation": {
            "valid": not errors,
            "errors": errors,
            "warnings": warnings,
        },
        "actions": [
            {
                "label": "初始化投递箱",
                "api_endpoint": "/api/protocol/dropbox/init",
                "cli_command": f'protocol-dropbox-init --dropbox-dir "{payload.get("dropbox_dir") or path.parent}"',
            },
            {
                "label": "执行投递箱",
                "api_endpoint": "/api/protocol/dropbox/run",
                "cli_command": f'protocol-dropbox-run --dropbox-dir "{payload.get("dropbox_dir") or path.parent}"',
            },
            {
                "label": "查看运行历史",
                "api_endpoint": "/api/protocol/dropbox/history",
                "cli_command": f'protocol-dropbox-history --dropbox-dir "{payload.get("dropbox_dir") or path.parent}" --limit 20',
            },
        ],
        "payload": payload if include_payload else None,
    }


def _inspect_protocol_dropbox_run(path: Path, payload: dict[str, Any], *, include_payload: bool) -> dict[str, Any]:
    queues = payload.get("queues") if isinstance(payload.get("queues"), list) else []
    alerts = payload.get("alerts") if isinstance(payload.get("alerts"), list) else []
    return {
        "schema": LOCAL_TOOLKIT_PROTOCOL_INSPECTION_SCHEMA,
        "ok": payload.get("ok") is True,
        "path": str(path),
        "protocol_kind": "protocol_dropbox_run",
        "label": "协议投递箱运行状态",
        "source_schema": str(payload.get("schema") or PROTOCOL_DROPBOX_RUN_SCHEMA),
        "summary": {
            "dropbox_dir": payload.get("dropbox_dir"),
            "status": payload.get("status"),
            "queue_count": payload.get("queue_count") or len(queues),
            "file_count": payload.get("file_count"),
            "processed_count": payload.get("processed_count"),
            "failed_count": payload.get("failed_count"),
            "error_count": payload.get("error_count"),
            "alert_count": payload.get("alert_count") or len(alerts),
            "alert_level": payload.get("alert_level") or "ok",
        },
        "validation": {
            "valid": payload.get("ok") is True,
            "errors": [],
            "warnings": [],
        },
        "actions": [
            {
                "label": "再次执行投递箱",
                "api_endpoint": "/api/protocol/dropbox/run",
                "cli_command": f'protocol-dropbox-run --dropbox-dir "{payload.get("dropbox_dir") or path.parent}"',
            },
            {
                "label": "查看运行历史",
                "api_endpoint": "/api/protocol/dropbox/history",
                "cli_command": f'protocol-dropbox-history --dropbox-dir "{payload.get("dropbox_dir") or path.parent}" --limit 20',
            },
            {
                "label": "回投失败文件",
                "api_endpoint": "/api/protocol/dropbox/requeue-failed",
                "cli_command": f'protocol-dropbox-requeue-failed --dropbox-dir "{payload.get("dropbox_dir") or path.parent}" --queue-id all --max-files 20',
            },
        ],
        "payload": payload if include_payload else None,
    }


def _inspect_protocol_dropbox_monitor(path: Path, payload: dict[str, Any], *, include_payload: bool) -> dict[str, Any]:
    totals = _mapping(payload.get("totals"))
    last_run = _mapping(payload.get("last_run"))
    alerts = payload.get("active_alerts") if isinstance(payload.get("active_alerts"), list) else []
    return {
        "schema": LOCAL_TOOLKIT_PROTOCOL_INSPECTION_SCHEMA,
        "ok": payload.get("ok") is True,
        "path": str(path),
        "protocol_kind": "protocol_dropbox_monitor",
        "label": "协议投递箱自动轮询状态",
        "source_schema": str(payload.get("schema") or PROTOCOL_DROPBOX_MONITOR_SCHEMA),
        "summary": {
            "dropbox_dir": payload.get("dropbox_dir"),
            "status": payload.get("status"),
            "running": payload.get("running") is True,
            "interval_seconds": payload.get("interval_seconds"),
            "completed_cycles": payload.get("completed_cycles"),
            "processed_count": totals.get("processed_count"),
            "failed_count": totals.get("failed_count"),
            "last_cycle_status": last_run.get("status"),
            "alert_count": payload.get("alert_count") or len(alerts),
            "last_alert_level": payload.get("last_alert_level") or "ok",
        },
        "validation": {
            "valid": payload.get("ok") is True,
            "errors": [],
            "warnings": [],
        },
        "actions": [
            {
                "label": "查看自动轮询状态",
                "api_endpoint": "/api/protocol/dropbox/monitor/status",
                "cli_command": f'protocol-dropbox-monitor-status --dropbox-dir "{payload.get("dropbox_dir") or path.parent}"',
            },
            {
                "label": "查看运行历史",
                "api_endpoint": "/api/protocol/dropbox/history",
                "cli_command": f'protocol-dropbox-history --dropbox-dir "{payload.get("dropbox_dir") or path.parent}" --limit 20',
            },
        ],
        "payload": payload if include_payload else None,
    }


def _inspect_protocol_dropbox_history(path: Path, payload: dict[str, Any], *, include_payload: bool) -> dict[str, Any]:
    entries = payload.get("entries") if isinstance(payload.get("entries"), list) else []
    latest = _mapping(entries[0]) if entries else {}
    return {
        "schema": LOCAL_TOOLKIT_PROTOCOL_INSPECTION_SCHEMA,
        "ok": payload.get("ok") is True,
        "path": str(path),
        "protocol_kind": "protocol_dropbox_history",
        "label": "协议投递箱运行历史",
        "source_schema": str(payload.get("schema") or PROTOCOL_DROPBOX_HISTORY_SCHEMA),
        "summary": {
            "dropbox_dir": payload.get("dropbox_dir"),
            "run_count": payload.get("run_count") or len(entries),
            "alert_entry_count": payload.get("alert_entry_count") or 0,
            "last_alert_level": payload.get("last_alert_level") or "ok",
            "latest_status": latest.get("status"),
            "latest_finished_at": latest.get("finished_at"),
        },
        "validation": {
            "valid": payload.get("ok") is True,
            "errors": [],
            "warnings": [],
        },
        "actions": [
            {
                "label": "查看运行历史",
                "api_endpoint": "/api/protocol/dropbox/history",
                "cli_command": f'protocol-dropbox-history --dropbox-dir "{payload.get("dropbox_dir") or path.parent}" --limit 20',
            },
            {
                "label": "仅查看告警历史",
                "api_endpoint": "/api/protocol/dropbox/history",
                "cli_command": f'protocol-dropbox-history --dropbox-dir "{payload.get("dropbox_dir") or path.parent}" --limit 20 --alerts-only',
            },
        ],
        "payload": payload if include_payload else None,
    }


def _inspect_protocol_dropbox_requeue(path: Path, payload: dict[str, Any], *, include_payload: bool) -> dict[str, Any]:
    queues = payload.get("queues") if isinstance(payload.get("queues"), list) else []
    return {
        "schema": LOCAL_TOOLKIT_PROTOCOL_INSPECTION_SCHEMA,
        "ok": payload.get("ok") is True,
        "path": str(path),
        "protocol_kind": "protocol_dropbox_requeue",
        "label": "协议投递箱失败回投结果",
        "source_schema": str(payload.get("schema") or PROTOCOL_DROPBOX_REQUEUE_SCHEMA),
        "summary": {
            "dropbox_dir": payload.get("dropbox_dir"),
            "queue_id": payload.get("queue_id") or "all",
            "moved_count": payload.get("moved_count") or 0,
            "queue_count": len(queues),
        },
        "validation": {
            "valid": payload.get("ok") is True,
            "errors": [],
            "warnings": [],
        },
        "actions": [
            {
                "label": "执行投递箱",
                "api_endpoint": "/api/protocol/dropbox/run",
                "cli_command": f'protocol-dropbox-run --dropbox-dir "{payload.get("dropbox_dir") or path.parent}"',
            },
            {
                "label": "再次回投失败文件",
                "api_endpoint": "/api/protocol/dropbox/requeue-failed",
                "cli_command": f'protocol-dropbox-requeue-failed --dropbox-dir "{payload.get("dropbox_dir") or path.parent}" --queue-id "{payload.get("queue_id") or "all"}"',
            },
        ],
        "payload": payload if include_payload else None,
    }


def _inspect_worker_task_package(path: Path, *, include_payload: bool) -> dict[str, Any]:
    from smart_video_cut.worker_protocol import load_worker_task_package

    loaded = load_worker_task_package(path)
    task_package = _mapping(loaded.get("task_package"))
    task = _mapping(task_package.get("task"))
    completion = _mapping(loaded.get("completion"))
    warnings: list[dict[str, str]] = []
    _append_missing_path_warnings(
        warnings,
        [
            ("style_package_missing", "风格包路径不存在", task.get("style_package")),
            ("output_dir_missing", "输出目录不存在", task.get("output_dir")),
        ],
    )
    for item in _string_list(task.get("input_videos")):
        _append_missing_path_warnings(
            warnings,
            [("input_video_missing", "输入素材不存在", item)],
        )
    return {
        "schema": LOCAL_TOOLKIT_PROTOCOL_INSPECTION_SCHEMA,
        "ok": loaded.get("ok") is True,
        "path": str(path),
        "protocol_kind": "worker_task_package",
        "label": "Worker 任务包",
        "source_schema": str(task_package.get("schema") or WORKER_TASK_PACKAGE_SCHEMA),
        "summary": {
            "package_id": task_package.get("package_id"),
            "project_id": task.get("project_id"),
            "task_id": task.get("task_id"),
            "input_video_count": len(_string_list(task.get("input_videos"))),
            "output_dir": task.get("output_dir"),
            "execute_real_render": task.get("execute_real_render") is True,
            "status": completion.get("status") or "pending",
        },
        "validation": {
            "valid": loaded.get("ok") is True,
            "errors": [] if loaded.get("ok") is True else [{"code": str(loaded.get("reason") or "worker_task_package_invalid"), "message": "Worker 任务包不可用"}],
            "warnings": warnings,
        },
        "actions": [{
            "label": "执行任务包",
            "api_endpoint": "/api/worker/run",
            "cli_command": f'worker-run --package-path "{path}"',
        }],
        "payload": task_package if include_payload else None,
        "completion": completion if include_payload and completion else None,
    }


def _inspect_worker_completion(path: Path, payload: dict[str, Any], *, include_payload: bool) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    if not str(payload.get("result_path") or "").strip():
        errors.append({"code": "result_path_missing", "message": "completion 未记录 result_path。"})
    return {
        "schema": LOCAL_TOOLKIT_PROTOCOL_INSPECTION_SCHEMA,
        "ok": payload.get("ok") is True,
        "path": str(path),
        "protocol_kind": "worker_completion",
        "label": "Worker 完成回执",
        "source_schema": str(payload.get("schema") or WORKER_COMPLETION_SCHEMA),
        "summary": {
            "project_id": payload.get("project_id"),
            "task_id": payload.get("task_id"),
            "status": payload.get("status"),
            "execution_mode": payload.get("execution_mode"),
            "output_dir": payload.get("output_dir"),
            "result_path": payload.get("result_path"),
        },
        "validation": {
            "valid": not errors,
            "errors": errors,
            "warnings": [],
        },
        "actions": [{
            "label": "检查输出目录协议",
            "api_endpoint": "/api/protocol/inspect",
            "cli_command": f'protocol-inspect --path "{payload.get("output_dir") or path.parent}"',
        }],
        "payload": payload if include_payload else None,
    }


def _inspect_pack(path: Path, payload: dict[str, Any], *, include_payload: bool) -> dict[str, Any]:
    validation = validate_pack_references(payload)
    schema = str(payload.get("schema") or "")
    summary: dict[str, Any] = {
        "name": payload.get("name"),
        "package_id": payload.get("package_id"),
        "schema": schema,
    }
    if schema == PROJECT_PACK_SCHEMA:
        resolved = resolve_project_pack(payload)
        timeline = _mapping(payload.get("timeline_plan"))
        summary.update({
            "input_video_count": len(_string_list(payload.get("input_videos"))),
            "source_output_dir": payload.get("source_output_dir"),
            "timeline_segment_count": len(timeline.get("segments") or []),
            "warning_count": len(validation.get("warnings") or []),
        })
        extra = {"resolved": resolved} if include_payload else {}
    elif schema in {STYLE_PACK_SCHEMA, STYLE_PACKAGE_SCHEMA}:
        visible_settings, timeline_template, edit_brief_profile = resolve_effective_settings(payload)
        summary.update({
            "visible_setting_groups": len(visible_settings),
            "timeline_template_segments": len(_mapping(timeline_template).get("segment_blueprint") or []),
            "edit_brief_keys": sorted(_mapping(edit_brief_profile).keys()),
        })
        extra = {}
    elif schema == MATERIAL_PACK_SCHEMA:
        summary.update({
            "reference_video_path": payload.get("reference_video_path"),
            "thumbnail_count": len(_string_list(payload.get("thumbnail_paths"))),
        })
        extra = {}
    else:
        extra = {}
    return {
        "schema": LOCAL_TOOLKIT_PROTOCOL_INSPECTION_SCHEMA,
        "ok": validation.get("ok") is True,
        "path": str(path),
        "protocol_kind": _SCHEMA_KIND_MAP.get(schema, "pack"),
        "label": "本地包协议",
        "source_schema": schema,
        "summary": summary,
        "validation": {
            "valid": validation.get("ok") is True,
            "errors": validation.get("errors") or [],
            "warnings": validation.get("warnings") or [],
        },
        "actions": [{
            "label": "在包管理中载入",
            "api_endpoint": "/api/packs/load",
            "cli_command": "",
        }],
        "payload": payload if include_payload else None,
        **extra,
    }


def _inspect_filmgen_export_handoff(path: Path, *, include_payload: bool) -> dict[str, Any]:
    validation = validate_external_export_handoff_import(path)
    filmgen_handoff = _mapping(validation.get("filmgen_handoff"))
    local_export = _mapping(validation.get("local_export"))
    return {
        "schema": LOCAL_TOOLKIT_PROTOCOL_INSPECTION_SCHEMA,
        "ok": validation.get("ok") is True,
        "path": str(path),
        "protocol_kind": "filmgen_export_handoff",
        "label": "外部导出交接",
        "source_schema": str(validation.get("source_schema") or local_export.get("schema") or ""),
        "summary": {
            "recommended_project_id": filmgen_handoff.get("recommended_project_id"),
            "recommended_output_dir": filmgen_handoff.get("recommended_output_dir"),
            "input_video_candidate_count": validation.get("input_video_candidate_count"),
            "status": local_export.get("status"),
        },
        "validation": validation.get("validation") or {"valid": False, "errors": [], "warnings": []},
        "actions": [{
            "label": "校验外部导入",
            "api_endpoint": "/api/external/export-handoff/validate",
            "cli_command": "",
        }],
        "payload": local_export if include_payload else None,
        "filmgen_handoff": filmgen_handoff if include_payload else None,
        "external_handoff": filmgen_handoff if include_payload else None,
    }


def _inspect_subtitle_handoff(path: Path, *, include_payload: bool) -> dict[str, Any]:
    preview = load_external_subtitle_handoff(path)
    handoff = _mapping(preview.get("handoff"))
    track_request = _mapping(handoff.get("track_request"))
    return {
        "schema": LOCAL_TOOLKIT_PROTOCOL_INSPECTION_SCHEMA,
        "ok": preview.get("ok") is True,
        "path": str(path),
        "protocol_kind": "subtitle_handoff",
        "label": "字幕交接协议",
        "source_schema": str(handoff.get("schema") or preview.get("schema") or ""),
        "summary": {
            "mode": handoff.get("mode"),
            "status": handoff.get("status"),
            "subtitle_text_count": preview.get("subtitle_text_count"),
            "target": track_request.get("target"),
        },
        "validation": preview.get("validation") or {"valid": False, "errors": [], "warnings": []},
        "actions": [{
            "label": "预览字幕交接",
            "api_endpoint": "/api/external/subtitle-handoff/preview",
            "cli_command": "",
        }],
        "payload": handoff if include_payload else None,
    }


def _inspect_project_manifest(path: Path, payload: dict[str, Any], *, include_payload: bool) -> dict[str, Any]:
    version_history = _mapping(payload.get("version_history"))
    errors: list[dict[str, str]] = []
    copied_output = str(payload.get("copied_output_video") or "")
    if copied_output and not Path(copied_output).exists():
        errors.append({"code": "copied_output_video_missing", "message": "project_manifest 记录的 copied_output_video 不存在。"})
    return {
        "schema": LOCAL_TOOLKIT_PROTOCOL_INSPECTION_SCHEMA,
        "ok": not errors,
        "path": str(path),
        "protocol_kind": "project_manifest",
        "label": "项目清单",
        "source_schema": str(payload.get("schema") or PROJECT_MANIFEST_SCHEMA),
        "summary": {
            "project_id": payload.get("project_id"),
            "input_video_count": payload.get("input_video_count"),
            "current_version": version_history.get("current_version"),
            "version_count": version_history.get("version_count") or len(version_history.get("versions") or []),
            "last_event": payload.get("last_event"),
        },
        "validation": {
            "valid": not errors,
            "errors": errors,
            "warnings": [],
        },
        "actions": [{
            "label": "生成统一协议清单",
            "api_endpoint": "/api/protocol/build",
            "cli_command": f'protocol-build --output-dir "{path.parent}"',
        }],
        "payload": payload if include_payload else None,
    }


def _inspect_local_edit_result(path: Path, payload: dict[str, Any], *, include_payload: bool) -> dict[str, Any]:
    toolkit_summary = _mapping(payload.get("toolkit_summary"))
    export_adapter_result = _mapping(payload.get("export_adapter_result"))
    exports = _mapping(export_adapter_result.get("exports"))
    return {
        "schema": LOCAL_TOOLKIT_PROTOCOL_INSPECTION_SCHEMA,
        "ok": payload.get("ok") is True,
        "path": str(path),
        "protocol_kind": "local_edit_result",
        "label": "本地剪辑结果",
        "source_schema": str(payload.get("schema") or LOCAL_EDIT_RESULT_SCHEMA),
        "summary": {
            "task_id": payload.get("task_id"),
            "project_id": toolkit_summary.get("project_id"),
            "workflow_kind": toolkit_summary.get("workflow_kind"),
            "execution_mode": toolkit_summary.get("execution_mode"),
            "input_video_count": payload.get("input_video_count"),
            "has_filmgen_handoff": bool(_mapping(exports.get("filmgen_handoff")).get("handoff_path")),
        },
        "validation": {
            "valid": payload.get("ok") is True,
            "errors": [],
            "warnings": [],
        },
        "actions": [{
            "label": "生成统一协议清单",
            "api_endpoint": "/api/protocol/build",
            "cli_command": f'protocol-build --output-dir "{path.parent}"',
        }],
        "payload": payload if include_payload else None,
    }


def _inspect_batch_run(path: Path, payload: dict[str, Any], *, include_payload: bool) -> dict[str, Any]:
    return {
        "schema": LOCAL_TOOLKIT_PROTOCOL_INSPECTION_SCHEMA,
        "ok": payload.get("ok") is True,
        "path": str(path),
        "protocol_kind": "batch_run",
        "label": "批量任务状态",
        "source_schema": str(payload.get("schema") or BATCH_RUN_SCHEMA),
        "summary": {
            "batch_id": payload.get("batch_id"),
            "task_count": payload.get("task_count"),
            "completed_count": payload.get("completed_count"),
            "failed_count": payload.get("failed_count"),
            "retry_count": payload.get("retry_count"),
        },
        "validation": {
            "valid": payload.get("ok") is True,
            "errors": [],
            "warnings": [],
        },
        "actions": [{
            "label": "检查批量输出目录",
            "api_endpoint": "/api/protocol/inspect",
            "cli_command": f'protocol-inspect --path "{payload.get("batch_dir") or path.parent}"',
        }],
        "payload": payload if include_payload else None,
    }


def _inspect_watch_queue(path: Path, payload: dict[str, Any], *, include_payload: bool) -> dict[str, Any]:
    return {
        "schema": LOCAL_TOOLKIT_PROTOCOL_INSPECTION_SCHEMA,
        "ok": payload.get("ok") is True,
        "path": str(path),
        "protocol_kind": "watch_queue",
        "label": "监听队列状态",
        "source_schema": str(payload.get("schema") or WATCH_QUEUE_SCHEMA),
        "summary": {
            "watch_dir": payload.get("watch_dir"),
            "file_count": payload.get("file_count"),
            "processed_count": payload.get("processed_count"),
            "failed_count": payload.get("failed_count"),
            "error_count": payload.get("error_count"),
        },
        "validation": {
            "valid": payload.get("ok") is True,
            "errors": [],
            "warnings": [],
        },
        "actions": [{
            "label": "检查 watch 目录",
            "api_endpoint": "/api/protocol/inspect",
            "cli_command": f'protocol-inspect --path "{payload.get("watch_dir") or path.parent}"',
        }],
        "payload": payload if include_payload else None,
    }


def _recognized_files(path: Path) -> list[Path]:
    return [
        path / filename
        for filename in _KNOWN_FILENAMES
        if (path / filename).is_file()
    ]


def _detected_kind(path: Path, payload: Mapping[str, Any]) -> str:
    schema = str(payload.get("schema") or "")
    return _SCHEMA_KIND_MAP.get(schema) or _KNOWN_FILENAMES.get(path.name, "generic_json")


def _validate_protocol_manifest(payload: Mapping[str, Any], artifacts: list[Any]) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    warnings = list(payload.get("warnings") or []) if isinstance(payload.get("warnings"), list) else []
    if payload.get("schema") != LOCAL_TOOLKIT_PROTOCOL_SCHEMA:
        errors.append({
            "code": "unsupported_schema",
            "message": f"期望 schema={LOCAL_TOOLKIT_PROTOCOL_SCHEMA}",
        })
    for item in artifacts:
        artifact = _mapping(item)
        if artifact.get("required") is True and artifact.get("ready") is not True:
            errors.append({
                "code": f'{artifact.get("artifact_id") or "artifact"}_missing',
                "message": f'{artifact.get("label") or artifact.get("artifact_id") or "artifact"} 缺失或路径无效。',
            })
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
    }


def _artifact_entry(
    *,
    artifact_id: str,
    label: str,
    path: str | Path,
    required: bool,
    schema: str,
) -> dict[str, Any]:
    value = str(path or "").strip()
    ready = Path(value).exists() if value else False
    return {
        "artifact_id": artifact_id,
        "label": label,
        "path": value,
        "required": required,
        "ready": ready,
        "schema": schema,
    }


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _string_list(values: Any) -> list[str]:
    return [str(item) for item in values or [] if str(item or "").strip()]


def _append_missing_path_warnings(
    warnings: list[dict[str, str]],
    candidates: list[tuple[str, str, Any]],
) -> None:
    for code, message, value in candidates:
        selected = str(value or "").strip()
        if selected and not Path(selected).exists():
            warnings.append({
                "code": code,
                "message": message,
                "path": selected,
            })


def _compact_inspection(payload: dict[str, Any]) -> dict[str, Any]:
    validation = _mapping(payload.get("validation"))
    return {
        "ok": payload.get("ok") is True,
        "path": payload.get("path"),
        "protocol_kind": payload.get("protocol_kind"),
        "label": payload.get("label"),
        "source_schema": payload.get("source_schema"),
        "summary": _mapping(payload.get("summary")),
        "warning_count": len(validation.get("warnings") or []),
        "error_count": len(validation.get("errors") or []),
    }
