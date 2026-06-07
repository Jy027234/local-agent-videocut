from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from smart_video_cut.edit_brief import build_edit_brief
from smart_video_cut.models import LocalEditTask


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
LOCAL_EXPORT_HANDOFF_SCHEMAS = {
    "smart_video_cut.local.export_filmgen_handoff.v0",
    "smart_video_cut.local.export_filmgen_handoff.v1",
}
FILMGEN_EXPORT_HANDOFF_IMPORT_VALIDATION_SCHEMA = "smart_video_cut.local.export_filmgen_handoff_import_validation.v0"


def load_filmgen_edit_pack(manifest_path: str | Path) -> dict[str, Any]:
    path = Path(manifest_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema = str(payload.get("schema") or "")
    if schema == "aifilm-studio.smart-video-cut-handoff.v1":
        handoff = payload
    elif schema == "aifilm-studio.edit-pack.v1":
        handoff = _handoff_from_manifest(payload, manifest_path=path)
    elif schema in LOCAL_EXPORT_HANDOFF_SCHEMAS:
        handoff = _handoff_from_local_export(payload, manifest_path=path)
    else:
        raise ValueError(f"unsupported FilmGen edit pack schema: {schema or '<missing>'}")
    handoff["source_manifest_path"] = str(path)
    handoff["video_assets"] = _sort_video_assets_by_shot_position(
        _annotate_video_assets(handoff.get("video_assets") or []),
        handoff.get("shots") or [],
    )
    handoff["input_video_candidates"] = [
        asset["file_path"]
        for asset in handoff["video_assets"]
        if asset.get("usable_as_input") is True
    ]
    return handoff


def validate_filmgen_export_handoff_import(handoff_path: str | Path) -> dict[str, Any]:
    path = Path(handoff_path)
    if not path.is_file():
        return _export_handoff_validation_result(
            handoff_path=path,
            validation={
                "valid": False,
                "errors": [{"code": "file_not_found", "message": "filmgen_handoff.json 不存在"}],
                "warnings": [],
            },
            local_export={},
            filmgen_handoff={},
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return _export_handoff_validation_result(
            handoff_path=path,
            validation={
                "valid": False,
                "errors": [{"code": "invalid_json", "message": f"handoff JSON 解析失败：{exc.msg}"}],
                "warnings": [],
            },
            local_export={},
            filmgen_handoff={},
        )
    if not isinstance(payload, dict):
        return _export_handoff_validation_result(
            handoff_path=path,
            validation={
                "valid": False,
                "errors": [{"code": "invalid_payload", "message": "handoff 根节点必须是 JSON object"}],
                "warnings": [],
            },
            local_export={},
            filmgen_handoff={},
        )
    validation = _validate_local_export_handoff(payload)
    filmgen_handoff: dict[str, Any] = {}
    if not any(error.get("code") == "unsupported_schema" for error in validation["errors"]):
        try:
            filmgen_handoff = load_filmgen_edit_pack(path)
        except Exception as exc:  # pragma: no cover - defensive API surface guard
            validation["errors"].append({"code": "filmgen_bridge_load_failed", "message": str(exc)})
            validation["valid"] = False
    return _export_handoff_validation_result(
        handoff_path=path,
        validation=validation,
        local_export=payload,
        filmgen_handoff=filmgen_handoff,
    )


def build_edit_brief_from_filmgen_pack(
    *,
    manifest_path: str | Path,
    style_package: str | Path,
    input_video: str | Path = "",
    input_videos: list[str | Path] | None = None,
    output_dir: str | Path = "",
    user_request: str = "",
    settings_overrides: Mapping[str, Any] | None = None,
    execute_real_render: bool = False,
    use_memory: bool = True,
) -> dict[str, Any]:
    handoff = load_filmgen_edit_pack(manifest_path)
    selected_inputs = _selected_inputs(handoff, input_video=input_video, input_videos=input_videos)
    if not selected_inputs:
        raise ValueError("FilmGen edit pack has no usable video input; provide input_video or input_videos")
    request_text = str(user_request or handoff.get("recommended_user_request") or "").strip()
    selected_output_dir = str(output_dir or handoff.get("recommended_output_dir") or Path("workspace") / "output" / "filmgen-edit")
    brief = build_edit_brief(
        style_package=style_package,
        input_video=selected_inputs[0],
        input_videos=selected_inputs,
        output_dir=selected_output_dir,
        user_request=request_text,
        settings_overrides=settings_overrides,
        execute_real_render=execute_real_render,
        use_memory=use_memory,
    )
    return {
        "schema": "smart_video_cut.local.filmgen_edit_brief.v0",
        "ok": True,
        "filmgen_handoff": handoff,
        "edit_brief": brief,
    }


def build_local_edit_task_from_filmgen_pack(
    *,
    manifest_path: str | Path,
    style_package: str | Path,
    input_video: str | Path = "",
    input_videos: list[str | Path] | None = None,
    output_dir: str | Path = "",
    user_request: str = "",
    settings_overrides: Mapping[str, Any] | None = None,
    confirmed_brief: str | None = None,
    execute_real_render: bool = False,
    allow_edge_tts: bool = False,
    use_memory: bool = True,
) -> LocalEditTask:
    handoff = load_filmgen_edit_pack(manifest_path)
    selected_inputs = _selected_inputs(handoff, input_video=input_video, input_videos=input_videos)
    if not selected_inputs:
        raise ValueError("FilmGen edit pack has no usable video input; provide input_video or input_videos")
    selected_output_dir = str(output_dir or handoff.get("recommended_output_dir") or Path("workspace") / "output" / "filmgen-edit")
    return LocalEditTask(
        style_package=Path(style_package),
        input_video=Path(selected_inputs[0]),
        input_videos=[Path(path) for path in selected_inputs],
        output_dir=Path(selected_output_dir),
        user_request=str(user_request or handoff.get("recommended_user_request") or ""),
        project_id=str(handoff.get("recommended_project_id") or "filmgen_project"),
        settings_overrides=dict(settings_overrides or {}),
        confirmed_brief=confirmed_brief,
        execute_real_render=execute_real_render,
        allow_edge_tts=allow_edge_tts,
        use_memory=use_memory,
    )


def _handoff_from_manifest(manifest: dict[str, Any], *, manifest_path: Path) -> dict[str, Any]:
    project = dict(manifest.get("project") or {})
    shots = list(manifest.get("shots") or [])
    assets = list(manifest.get("assets") or [])
    video_assets = _sort_video_assets_by_shot_position([
        {
            "asset_id": asset.get("id"),
            "shot_id": asset.get("shot_id"),
            "type": asset.get("type"),
            "title": asset.get("title"),
            "file_path": asset.get("file_path"),
            "provider": asset.get("provider"),
            "model": asset.get("model"),
            "status": asset.get("status"),
        }
        for asset in assets
        if str(asset.get("type") or "") in {"video", "final"}
    ], shots)
    shot_lines = [
        " / ".join(
            part
            for part in [
                f"镜头{shot.get('position')}",
                str(shot.get("title") or "").strip(),
                str(shot.get("summary") or "").strip(),
                str(shot.get("prompt") or "").strip(),
            ]
            if part
        )
        for shot in shots
    ]
    return {
        "schema": "aifilm-studio.smart-video-cut-handoff.v1",
        "source_schema": manifest.get("schema"),
        "source_manifest_path": str(manifest_path),
        "project": project,
        "recommended_project_id": project.get("id") or "filmgen_project",
        "recommended_user_request": "\n".join(
            part
            for part in [
                f"项目：{project.get('title') or project.get('id')}",
                str(project.get("logline") or "").strip(),
                "请根据以下分镜和已生成素材，进入智能剪辑软件完成剪辑标准确认与后续装配。",
                *shot_lines,
            ]
            if part
        ),
        "recommended_output_dir": str(Path("workspace") / "output" / f"filmgen-{project.get('id') or 'project'}"),
        "shots": shots,
        "video_assets": video_assets,
        "all_assets": assets,
    }


def _handoff_from_local_export(export_handoff: dict[str, Any], *, manifest_path: Path) -> dict[str, Any]:
    output_dir = str(export_handoff.get("output_dir") or manifest_path.parent)
    final_video = export_handoff.get("final_video") if isinstance(export_handoff.get("final_video"), Mapping) else {}
    toolkit_summary = (
        export_handoff.get("toolkit_summary")
        if isinstance(export_handoff.get("toolkit_summary"), Mapping)
        else {}
    )
    final_path = str(final_video.get("path") or "").strip()
    project_id = str(toolkit_summary.get("project_id") or Path(output_dir).name or "smart_video_cut_export")
    video_assets = []
    if final_path:
        video_assets.append({
            "asset_id": "smart-video-cut-final",
            "shot_id": "smart-video-cut-final",
            "type": "final",
            "title": "Smart Video Cut final render",
            "file_path": final_path,
            "provider": "smart_video_cut",
            "model": str(toolkit_summary.get("workflow_kind") or "local_export"),
            "status": "ready" if final_video.get("ready") else "referenced",
        })
    request_parts = [
        "从智能剪辑软件导出的 FilmGen handoff 继续处理。",
        f"项目：{project_id}",
        f"输出目录：{output_dir}",
        str(toolkit_summary.get("creative_objective") or "").strip(),
        "如果 final_video 可用，请优先使用成片；否则解析 ProjectPack 或原始输出目录继续联调。",
    ]
    return {
        "schema": "aifilm-studio.smart-video-cut-handoff.v1",
        "source_schema": export_handoff.get("schema"),
        "source_schema_version": export_handoff.get("schema_version"),
        "source_manifest_path": str(manifest_path),
        "project": {
            "id": project_id,
            "title": str(toolkit_summary.get("creative_objective") or project_id),
            "source": "smart_video_cut_export_filmgen_handoff",
        },
        "recommended_project_id": project_id,
        "recommended_user_request": "\n".join(part for part in request_parts if part),
        "recommended_output_dir": output_dir,
        "shots": [],
        "video_assets": video_assets,
        "all_assets": video_assets,
        "smart_video_cut_export": export_handoff,
    }


def _validate_local_export_handoff(export_handoff: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    schema = str(export_handoff.get("schema") or "")
    if schema not in LOCAL_EXPORT_HANDOFF_SCHEMAS:
        errors.append({
            "code": "unsupported_schema",
            "message": f"不支持的 Smart Video Cut 导出 handoff schema：{schema or '<missing>'}",
        })
    if schema == "smart_video_cut.local.export_filmgen_handoff.v0":
        warnings.append({
            "code": "legacy_schema",
            "message": "这是 v0 handoff，仍可读取；建议用新版剪辑结果重新生成 v1 handoff。",
        })
    if schema == "smart_video_cut.local.export_filmgen_handoff.v1" and _safe_int(export_handoff.get("schema_version")) < 1:
        warnings.append({"code": "missing_schema_version", "message": "v1 handoff 建议包含 schema_version=1。"})

    final_video = export_handoff.get("final_video") if isinstance(export_handoff.get("final_video"), Mapping) else {}
    if not final_video:
        errors.append({"code": "missing_final_video", "message": "handoff 缺少 final_video 节点。"})
    else:
        final_path = str(final_video.get("path") or "").strip()
        final_ready = final_video.get("ready") is True
        if final_ready and not final_path:
            errors.append({"code": "final_video_path_missing", "message": "final_video 标记 ready，但 path 为空。"})
        if final_path and not Path(final_path).is_file():
            severity = errors if final_ready else warnings
            severity.append({
                "code": "final_video_not_found",
                "message": f"final_video.path 指向的文件不存在：{final_path}",
            })
        if not final_ready and not final_path:
            warnings.append({
                "code": "plan_only_handoff",
                "message": "handoff 未携带可直接导入的 final_video，可作为计划/项目上下文交接。",
            })

    contract = export_handoff.get("filmgen_contract") if isinstance(export_handoff.get("filmgen_contract"), Mapping) else {}
    if contract.get("input_kind") != "smart_video_cut_local_export":
        errors.append({
            "code": "invalid_contract_kind",
            "message": "filmgen_contract.input_kind 应为 smart_video_cut_local_export。",
        })
    if contract.get("supports_plan_only") is not True:
        warnings.append({"code": "plan_only_not_declared", "message": "filmgen_contract 未声明 supports_plan_only=true。"})
    if not isinstance(export_handoff.get("project_pack_export"), Mapping):
        warnings.append({"code": "missing_project_pack_export", "message": "未记录 ProjectPack 导出入口，外部工具只能读取成片路径。"})
    return {"valid": not errors, "errors": errors, "warnings": warnings}


def _export_handoff_validation_result(
    *,
    handoff_path: Path,
    validation: dict[str, Any],
    local_export: dict[str, Any],
    filmgen_handoff: dict[str, Any],
) -> dict[str, Any]:
    candidates = filmgen_handoff.get("input_video_candidates") if isinstance(filmgen_handoff, Mapping) else []
    return {
        "schema": FILMGEN_EXPORT_HANDOFF_IMPORT_VALIDATION_SCHEMA,
        "ok": validation.get("valid") is True,
        "reason": "filmgen_export_handoff_ready" if validation.get("valid") is True else "filmgen_export_handoff_invalid",
        "handoff_path": str(handoff_path),
        "source_schema": local_export.get("schema") if isinstance(local_export, Mapping) else "",
        "source_schema_version": local_export.get("schema_version") if isinstance(local_export, Mapping) else None,
        "validation": validation,
        "ready_for_filmgen_import": bool(candidates) or validation.get("valid") is True,
        "input_video_candidate_count": len(candidates or []),
        "filmgen_handoff": filmgen_handoff,
        "local_export": local_export,
        "import_contract": {
            "external_center": "FilmGen or compatible generation hub",
            "accepted_schemas": sorted(LOCAL_EXPORT_HANDOFF_SCHEMAS),
            "preferred_input": "filmgen_handoff.input_video_candidates[0]",
        },
    }


def _annotate_video_assets(assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    annotated = []
    for asset in assets:
        item = dict(asset)
        path = Path(str(item.get("file_path") or ""))
        item["file_exists"] = path.is_file()
        item["usable_as_input"] = path.is_file() and path.suffix.casefold() in VIDEO_EXTENSIONS
        annotated.append(item)
    return annotated


def _sort_video_assets_by_shot_position(assets: list[dict[str, Any]], shots: list[Any]) -> list[dict[str, Any]]:
    shot_positions = {
        str(shot.get("id") or ""): int(shot.get("position") or 999999)
        for shot in shots
        if isinstance(shot, Mapping)
    }
    return sorted(
        assets,
        key=lambda asset: (shot_positions.get(str(asset.get("shot_id") or ""), 999999), str(asset.get("title") or "")),
    )


def _selected_inputs(
    handoff: Mapping[str, Any],
    *,
    input_video: str | Path = "",
    input_videos: list[str | Path] | None = None,
) -> list[str]:
    selected = []
    for value in [input_video, *(input_videos or [])]:
        text = str(value or "").strip()
        if text and text not in selected:
            selected.append(text)
    if selected:
        return selected
    return [str(value) for value in handoff.get("input_video_candidates") or []]


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
