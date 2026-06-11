from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from smart_video_cut.bundled_runtime import run_edit_with_style_package
from smart_video_cut.external_bridge import build_local_edit_task_from_external_pack
from smart_video_cut.external_handoff_compat import (
    EXTERNAL_EDIT_PACK_SCHEMAS,
    LEGACY_EXTERNAL_PROTOCOL_KIND,
    default_external_style_package_candidates,
)
from smart_video_cut.models import LOCAL_EDIT_TASK_SCHEMA, LocalEditTask, PROJECT_PACK_SCHEMA
from smart_video_cut.pack_manager import load_pack
from smart_video_cut.toolkit_protocol import LOCAL_TOOLKIT_PROTOCOL_SCHEMA
from smart_video_cut.worker_protocol import (
    WORKER_TASK_PACKAGE_SCHEMA,
    load_worker_task_package,
    run_worker_task_package,
)


def detect_runnable_protocol_kind(path: str | Path) -> str:
    selected = Path(path)
    payload = _read_json(selected)
    if not payload:
        return ""
    schema = str(payload.get("schema") or "")
    if schema == WORKER_TASK_PACKAGE_SCHEMA:
        return "worker_task_package"
    if schema == PROJECT_PACK_SCHEMA:
        return "project_pack"
    if schema in EXTERNAL_EDIT_PACK_SCHEMAS:
        return LEGACY_EXTERNAL_PROTOCOL_KIND
    if schema == LOCAL_EDIT_TASK_SCHEMA:
        return "local_edit_task"
    if schema == LOCAL_TOOLKIT_PROTOCOL_SCHEMA:
        nested = _nested_runnable_source(payload)
        return detect_runnable_protocol_kind(nested) if nested else ""
    return ""


def prepare_protocol_run(
    path: str | Path,
    *,
    output_dir: str = "",
    style_package: str = "",
    user_request: str = "",
    execute_real_render: bool | None = None,
    allow_edge_tts: bool | None = None,
    voiceover_text: str | None = None,
    use_memory: bool | None = None,
    confirmed_brief: str | None = None,
) -> dict[str, Any]:
    selected = Path(path)
    payload = _read_json(selected)
    if not payload:
        return {
            "ok": False,
            "runnable": False,
            "reason": "protocol_json_not_found_or_invalid",
            "protocol_kind": "",
            "source_path": str(selected),
        }
    schema = str(payload.get("schema") or "")
    if schema == WORKER_TASK_PACKAGE_SCHEMA:
        loaded = load_worker_task_package(selected)
        if loaded.get("ok") is not True:
            return {
                "ok": False,
                "runnable": False,
                "reason": loaded.get("reason") or "worker_task_package_not_ready",
                "protocol_kind": "worker_task_package",
                "source_path": str(selected),
            }
        return {
            "ok": True,
            "runnable": True,
            "protocol_kind": "worker_task_package",
            "runner": "worker_package",
            "source_path": str(selected),
            "resolved_source_path": str(selected),
            "task_payload": _mapping(_mapping(loaded.get("task_package")).get("task")),
        }
    if schema == PROJECT_PACK_SCHEMA:
        task = _task_from_project_pack(
            selected,
            payload,
            output_dir=output_dir,
            style_package=style_package,
            user_request=user_request,
            execute_real_render=execute_real_render,
            allow_edge_tts=allow_edge_tts,
            voiceover_text=voiceover_text,
            use_memory=use_memory,
            confirmed_brief=confirmed_brief,
        )
        return {
            "ok": True,
            "runnable": True,
            "protocol_kind": "project_pack",
            "runner": "local_edit_task",
            "source_path": str(selected),
            "resolved_source_path": str(selected),
            "task_payload": task.to_dict(),
            "task": task,
        }
    if schema in EXTERNAL_EDIT_PACK_SCHEMAS:
        task = _task_from_external_pack(
            selected,
            output_dir=output_dir,
            style_package=style_package,
            user_request=user_request,
            execute_real_render=execute_real_render,
            allow_edge_tts=allow_edge_tts,
            voiceover_text=voiceover_text,
            use_memory=use_memory,
            confirmed_brief=confirmed_brief,
        )
        return {
            "ok": True,
            "runnable": True,
            "protocol_kind": LEGACY_EXTERNAL_PROTOCOL_KIND,
            "runner": "local_edit_task",
            "source_path": str(selected),
            "resolved_source_path": str(selected),
            "task_payload": task.to_dict(),
            "task": task,
        }
    if schema == LOCAL_EDIT_TASK_SCHEMA:
        task = _task_from_payload(
            payload,
            output_dir=output_dir,
            style_package=style_package,
            user_request=user_request,
            execute_real_render=execute_real_render,
            allow_edge_tts=allow_edge_tts,
            voiceover_text=voiceover_text,
            use_memory=use_memory,
            confirmed_brief=confirmed_brief,
        )
        return {
            "ok": True,
            "runnable": True,
            "protocol_kind": "local_edit_task",
            "runner": "local_edit_task",
            "source_path": str(selected),
            "resolved_source_path": str(selected),
            "task_payload": task.to_dict(),
            "task": task,
        }
    if schema == LOCAL_TOOLKIT_PROTOCOL_SCHEMA:
        nested = _nested_runnable_source(payload)
        if not nested:
            return {
                "ok": False,
                "runnable": False,
                "reason": "protocol_manifest_not_runnable",
                "protocol_kind": "local_toolkit_protocol",
                "source_path": str(selected),
            }
        nested_result = prepare_protocol_run(
            nested,
            output_dir=output_dir,
            style_package=style_package,
            user_request=user_request,
            execute_real_render=execute_real_render,
            allow_edge_tts=allow_edge_tts,
            voiceover_text=voiceover_text,
            use_memory=use_memory,
            confirmed_brief=confirmed_brief,
        )
        nested_result.setdefault("protocol_kind", "local_toolkit_protocol")
        nested_result["source_path"] = str(selected)
        nested_result["resolved_source_path"] = str(nested)
        nested_result["source_protocol_kind"] = "local_toolkit_protocol"
        return nested_result
    return {
        "ok": False,
        "runnable": False,
        "reason": f"unsupported_protocol_schema: {schema or '<missing>'}",
        "protocol_kind": "",
        "source_path": str(selected),
    }


def run_protocol_path(
    path: str | Path,
    *,
    output_dir: str = "",
    style_package: str = "",
    user_request: str = "",
    execute_real_render: bool | None = None,
    allow_edge_tts: bool | None = None,
    voiceover_text: str | None = None,
    use_memory: bool | None = None,
    confirmed_brief: str | None = None,
) -> dict[str, Any]:
    prepared = prepare_protocol_run(
        path,
        output_dir=output_dir,
        style_package=style_package,
        user_request=user_request,
        execute_real_render=execute_real_render,
        allow_edge_tts=allow_edge_tts,
        voiceover_text=voiceover_text,
        use_memory=use_memory,
        confirmed_brief=confirmed_brief,
    )
    if prepared.get("ok") is not True or prepared.get("runnable") is not True:
        return {
            "ok": False,
            "reason": prepared.get("reason") or "protocol_not_runnable",
            "protocol_kind": prepared.get("protocol_kind") or "",
            "protocol_source_path": str(path),
        }
    if prepared.get("runner") == "worker_package":
        result = run_worker_task_package(prepared.get("resolved_source_path") or path)
    else:
        task = prepared.get("task")
        if not isinstance(task, LocalEditTask):
            return {
                "ok": False,
                "reason": "prepared_task_missing",
                "protocol_kind": prepared.get("protocol_kind") or "",
                "protocol_source_path": str(path),
            }
        result = run_edit_with_style_package(task)
    return {
        **result,
        "protocol_kind": prepared.get("protocol_kind") or "",
        "protocol_runner": prepared.get("runner") or "",
        "protocol_source_path": prepared.get("source_path") or str(path),
        "protocol_resolved_source_path": prepared.get("resolved_source_path") or str(path),
    }


def _task_from_project_pack(
    path: Path,
    payload: Mapping[str, Any],
    *,
    output_dir: str,
    style_package: str,
    user_request: str,
    execute_real_render: bool | None,
    allow_edge_tts: bool | None,
    voiceover_text: str | None,
    use_memory: bool | None,
    confirmed_brief: str | None,
) -> LocalEditTask:
    pack = payload if isinstance(payload, dict) else load_pack(path)
    manifest = _mapping(pack.get("project_manifest"))
    latest_result = _mapping(manifest.get("latest_result"))
    style_candidate = (
        str(style_package or "").strip()
        or str(pack.get("style_pack_ref") or "").strip()
        or str(_mapping(manifest.get("style_package")).get("path") or "").strip()
    )
    if not style_candidate:
        raise ValueError("project_pack_missing_style_package")
    inputs = _string_list(pack.get("input_videos"))
    if not inputs:
        raise ValueError("project_pack_missing_input_videos")
    resolved_output_dir = (
        str(output_dir or "").strip()
        or str(pack.get("output_dir") or "").strip()
        or str(pack.get("source_output_dir") or "").strip()
        or str(path.parent / "protocol_project_pack_output")
    )
    timeline = _mapping(pack.get("timeline_plan"))
    return LocalEditTask(
        style_package=Path(style_candidate),
        input_video=Path(inputs[0]),
        input_videos=[Path(item) for item in inputs],
        output_dir=Path(resolved_output_dir),
        user_request=str(user_request or latest_result.get("user_request") or pack.get("name") or "根据项目包继续剪辑"),
        execute_real_render=_bool_with_default(execute_real_render, default=False),
        allow_edge_tts=_bool_with_default(allow_edge_tts, default=False),
        voiceover_text=voiceover_text if voiceover_text is not None else latest_result.get("voiceover_text"),
        use_memory=_bool_with_default(use_memory, default=True),
        project_id=str(manifest.get("project_id") or latest_result.get("project_id") or pack.get("name") or "project_pack_import"),
        settings_overrides=_mapping(pack.get("project_settings_overrides")),
        confirmed_brief=confirmed_brief if confirmed_brief is not None else latest_result.get("confirmed_brief"),
        timeline_override=timeline if timeline.get("segments") else None,
        task_id=latest_result.get("task_id"),
    )


def _task_from_external_pack(
    path: Path,
    *,
    output_dir: str,
    style_package: str,
    user_request: str,
    execute_real_render: bool | None,
    allow_edge_tts: bool | None,
    voiceover_text: str | None,
    use_memory: bool | None,
    confirmed_brief: str | None,
) -> LocalEditTask:
    style_candidate = str(style_package or "").strip() or _default_external_style_package()
    if not style_candidate:
        raise ValueError("filmgen_protocol_missing_style_package")
    task = build_local_edit_task_from_external_pack(
        manifest_path=path,
        style_package=style_candidate,
        output_dir=output_dir,
        user_request=user_request,
        confirmed_brief=confirmed_brief,
        execute_real_render=_bool_with_default(execute_real_render, default=False),
        allow_edge_tts=_bool_with_default(allow_edge_tts, default=False),
        use_memory=_bool_with_default(use_memory, default=True),
    )
    if voiceover_text is not None:
        task.voiceover_text = voiceover_text
    return task


def _task_from_payload(
    payload: Mapping[str, Any],
    *,
    output_dir: str,
    style_package: str,
    user_request: str,
    execute_real_render: bool | None,
    allow_edge_tts: bool | None,
    voiceover_text: str | None,
    use_memory: bool | None,
    confirmed_brief: str | None,
) -> LocalEditTask:
    input_videos = _string_list(payload.get("input_videos"))
    primary = str(payload.get("input_video") or (input_videos[0] if input_videos else "")).strip()
    if primary and primary not in input_videos:
        input_videos.insert(0, primary)
    selected_output_dir = str(output_dir or payload.get("output_dir") or "").strip()
    if not selected_output_dir:
        raise ValueError("protocol_task_missing_output_dir")
    selected_style = str(style_package or payload.get("style_package") or "").strip()
    if not selected_style:
        raise ValueError("protocol_task_missing_style_package")
    return LocalEditTask(
        style_package=Path(selected_style),
        input_video=Path(primary),
        input_videos=[Path(item) for item in input_videos],
        output_dir=Path(selected_output_dir),
        user_request=str(user_request or payload.get("user_request") or ""),
        execute_real_render=_bool_with_default(execute_real_render, default=bool(payload.get("execute_real_render", False))),
        allow_edge_tts=_bool_with_default(allow_edge_tts, default=bool(payload.get("allow_edge_tts", False))),
        voiceover_text=voiceover_text if voiceover_text is not None else payload.get("voiceover_text"),
        use_memory=_bool_with_default(use_memory, default=payload.get("use_memory", True) is not False),
        project_id=str(payload.get("project_id") or "local_project"),
        settings_overrides=_mapping(payload.get("settings_overrides")),
        confirmed_brief=confirmed_brief if confirmed_brief is not None else payload.get("confirmed_brief"),
        timeline_override=_mapping(payload.get("timeline_override")) or None,
        task_id=str(payload.get("task_id") or "") or None,
    )


def _nested_runnable_source(payload: Mapping[str, Any]) -> str:
    paths = _mapping(payload.get("paths"))
    candidates = [
        str(paths.get("external_handoff_path") or "").strip(),
        str(paths.get("filmgen_handoff_path") or "").strip(),
        str(paths.get("subtitle_handoff_path") or "").strip(),
        str(paths.get("result_path") or "").strip(),
    ]
    for item in candidates:
        if item and Path(item).is_file():
            kind = detect_runnable_protocol_kind(item)
            if kind:
                return item
    return ""


def _default_external_style_package() -> str:
    root = Path(__file__).resolve().parents[2]
    candidates = list(default_external_style_package_candidates(root))
    for candidate in candidates:
        if (candidate / "style_package.json").is_file() or (candidate / "style_pack.json").is_file():
            return str(candidate)
    return ""


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


def _bool_with_default(value: bool | None, *, default: bool) -> bool:
    return default if value is None else value is True
